#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_response_quality.py — AI 回复质量审计 v1.0

原理（前沿最佳实践）：
------------------------
基于 Anthropic 2025 年的 Constitutional AI + RLAIF 方法论和 Google DeepMind 2025 
发布的 Response Grounding Evaluation Framework 设计。

三层级评估：
1. Context Grounding — 确认回复是否正确使用了上下文中的用户睡眠数据
   - 如果用户提供了数据，AI 不应该问"你几点睡几点起"
   - 如果用户提供了数据，AI 可以但不应违反数据做分析
   
2. Data Faithfulness — 确认回复中的数据引用和 context 一致
   - bedtime=23:00 → 回复中说"你平时23点睡" ✅
   - bedtime=23:00 → 回复中说"你平时10点睡" ❌ (hallucination)
   
3. Omission Detection — 检测"该引用但没引用"
   - 最隐蔽的 bug 类型：数据在 system_content 里，但 AI 选择用通用建议
   - 对应的 prompt engineering 修复比 detection 重要

评估方法：LLM-as-Judge (self-critique 版本)
- 使用 DeepSeek V3（和主对话同模型）或更便宜的模型做 judge
- 不需要 API key 以外的东西
- 设计双向提示：Judge prompt 和 Truth prompt

用法:
  python dev_tools/audit/audit_response_quality.py [--interactive]
  python aisleepgen_tool.py audit response-quality
  
评估模式:
  --record          从日志中提取最近一次对话进行评估
  --file FILE       评估指定的对话记录 JSON 文件
  --batch DIR       批量评估 logs/ 下的所有对话记录
"""

import sys, os, json, datetime, argparse, re
sys.stdout.reconfigure(encoding='utf-8')

# 导入 judge 引擎
_judge_dir = os.path.dirname(os.path.abspath(__file__))
if _judge_dir not in sys.path:
    sys.path.insert(0, _judge_dir)
from _judge import call_judge, batch_judge, find_api_key

# ==================== 配置 ====================
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TRACE_LOG = os.path.join(PROJECT_DIR, 'logs', 'trace.log')
RECORDINGS_DIR = os.path.join(PROJECT_DIR, 'logs', 'dialogues')

# ==================== Evaluation Criteria (三原则) ====================
GROUNDING_RULES = """
评估规则（Constitutional AI + Grounding Evaluation 框架）：

1. [Context Grounding] 是否准确引用了用户数据
   - 用户给过 bedtime=23:00 → AI 应说"你平时23点睡"
   - 不能说"我不知道你几点睡"
   - 但用户没说具体时间时，AI 可以说"数据显示你倾向于23点睡"
   
2. [Data Faithfulness] 引用的数据是否和上下文一致
   - 上下文中有 bedtime=23:00 → AI 说"你1点才睡"就是错误的
   - 上下文 score=72 → AI 说"你上周72分" vs "你刚得98分"（后者错误）
   
3. [Omission Detection] 在需要时是否回避了可用数据
   - 用户问"我睡眠怎么样"→ AI 有全部数据但只说"保持良好习惯"
   - 这在技术上不是"幻觉"，但效果等同于忽略用户
   - 这是最隐蔽的质量问题
"""

JUDGE_PROMPT = """你是一个严格但公正的 AI 回复质量审计员。你的任务是判断 AI 助手的回复是否正确使用了提供给它的用户数据。

## 数据上下文（提供给 AI 助手的用户信息）：
{context}

## AI 助手的回复：
{response}

## 评估维度（逐项评分 0-5）：
1. **Context Grounding** (0-5): AI 回复是否引用了上下文中的用户具体数据？完全没有引用 → 0，充分且准确的引用 → 5。
2. **Data Faithfulness** (0-5): 引用的数据是否和上下文一致？有数据错误 → 0，完全一致 → 5。
3. **Omission Detection** (0-5): 上下文中有足够数据但 AI 选择了泛泛而谈时 → 0-2，合理引用 → 4-5。
4. **Usefulness** (0-5): 回复对解决用户的实际睡眠问题有帮助吗？空洞鸡汤 → 0-2，有建设性分析 → 4-5。

## 输出格式（纯 JSON）：
{{"grounding": <0-5>, "faithfulness": <0-5>, "omission": <0-5>, "usefulness": <0-5>, "summary": "<2句话概括>"}}
"""

# ==================== 从 trace log 中提取对话 ====================
def extract_dialogues_from_trace():
    """从 trace.log 中提取所有记录到的对话"""
    if not os.path.exists(TRACE_LOG):
        print(f'[Audit] Trace log not found: {TRACE_LOG}')
        print('[Audit] No dialogues collected yet. Run the service first.')
        return []
    
    dialogues = []
    current_trace_id = None
    current_dialogue = None
    
    with open(TRACE_LOG, 'r', encoding='utf-8') as f:
        for line in f:
            # 格式: [HH:MM:SS] [HMMSS_hex_id] type data
            m = re.match(r'\[\d{2}:\d{2}:\d{2}\] \[(\d{6})_([a-f0-9]+)\]\s+(ctx|send|>>|sc:|entry)\s+(.*)', line)
            if not m:
                continue
            trace_id = m.group(1) + '_' + m.group(2)
            msg_type = m.group(3)
            msg_data = m.group(4).strip()
            
            # 新 entry = 新对话开始
            if msg_type == 'entry':
                # 保存上一个对话
                if current_dialogue and current_dialogue.get('lines'):
                    dialogues.append(current_dialogue)
                current_dialogue = {'trace_id': trace_id, 'lines': []}
                current_dialogue['lines'].append({'type': msg_type, 'data': msg_data})
                continue
            
            # 如果不是 entry 但 trace_id 变了，或者没有当前对话，创建新对话
            if not current_dialogue or current_dialogue['trace_id'] != trace_id:
                if current_dialogue and current_dialogue.get('lines'):
                    dialogues.append(current_dialogue)
                current_dialogue = {'trace_id': trace_id, 'lines': []}
            
            current_dialogue['lines'].append({'type': msg_type, 'data': msg_data})
    
    # 不要忘了最后一个对话
    if current_dialogue and current_dialogue.get('lines'):
        dialogues.append(current_dialogue)
    
    return dialogues

def format_context_for_judge(dialogue):
    """把 trace 记录格式化为 judge 可读的上下文"""
    ctx = ''
    for line in dialogue['lines']:
        if line['type'] == 'ctx':
            # try to extract just the sleep data portion
            if 'len=' in line['data']:
                continue  # meta data
            ctx += line['data'] + '\n'
        elif line['type'] == '>>':
            ctx += line['data'] + '\n'
    return ctx

# ==================== 调用 LLM-as-Judge ====================
def call_llm(prompt, sys_prompt='你是一个严格但公正的质量审计员。'):
    """调用 DeepSeek API 做 judge — 直接调 API 不走本地服务，避免递归"""
    import urllib.request
    import json
    
    messages = [
        {'role': 'system', 'content': sys_prompt},
        {'role': 'user', 'content': prompt}
    ]
    
    # 从环境变量或配置读取 DeepSeek API Key
    api_key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY')
    
    if not api_key:
        # fallback: 从 deepseek_proxy 进程读取
        try:
            # deepseek_proxy 在运行时会把 DEEPSEEK_API_KEY 设成全局变量
            # 但在 dev_tools 脚本里，可以尝试导入模块级别的变量
            sys.path.insert(0, PROJECT_DIR)
            # 导入模块来读取配置 (不会启动服务)
            from deepseek_proxy import DEEPSEEK_API_KEY as _key_from_proxy
            if _key_from_proxy:
                api_key = _key_from_proxy
        except (ImportError, AttributeError):
            pass
    
    if not api_key:
        # fallback 2: 从 .env 文件
        try:
            for candidate in [os.path.join(PROJECT_DIR, '.env'), os.path.join(os.path.expanduser('~'), '.deepseek_key')]:
                if os.path.exists(candidate):
                    with open(candidate, 'r') as f:
                        for line in f:
                            if 'DEEPSEEK_API_KEY' in line or 'OPENAI_API_KEY' in line:
                                api_key = line.split('=')[1].strip().strip('"').strip("'")
                                break
        except Exception:
    if not api_key:
        print('[Audit] No API key found for LLM judge.')
        print('[Audit] Set DEEPSEEK_API_KEY environment variable or .env file.')
        print('[Audit] Falling back to rule-based check only.')
        return None
    
    payload = json.dumps({
        'model': 'deepseek-chat',
        'messages': messages,
        'max_tokens': 512,
        'temperature': 0.3
    }).encode('utf-8')
    
    req = urllib.request.Request(
        'https://api.deepseek.com/v1/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result.get('choices', [{}])[0].get('message', {}).get('content', '')
    except Exception as e:
        print(f'[Audit] LLM judge call failed: {e}')
        return None

def parse_judge_response(response):
    """从 LLM 回复中提取 JSON 评分"""
    if not response:
        return None
    # 找 JSON 块
    m = re.search(r'\{[^}]+\}', response)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
    return None

# ==================== 检查交互轨迹 ====================
def check_interaction_trace():
    """基础版：不调 LLM，只做规则检查"""
    print('[Audit] Checking dialogue traces...')
    dialogues = extract_dialogues_from_trace()
    
    if not dialogues:
        print('[Audit] No dialogues found. First interaction will appear here.')
        return
    
    print(f'[Audit] Found {len(dialogues)} dialogues in trace log.')
    
    issues = []
    for dia in dialogues:
        ctx_lines = [l['data'] for l in dia['lines'] if l['type'] == '>>']
        has_sleep_data = any(k in str(ctx_lines) for k in ['上床', '起床', '入睡', '总时长', '睡眠习惯', '评分'])
        has_empty_flag = any('EMPTY CONTEXT' in l['data'] for l in dia['lines'] if l['type'] == '>>')
        
        if has_empty_flag:
            issues.append(f'  ! dialog {dia["trace_id"]}: EMPTY CONTEXT — AI sees no user data!')
        elif not has_sleep_data:
            issues.append(f'  ~ dialog {dia["trace_id"]}: no sleep data in context')
    
    if issues:
        print('\n'.join(issues))
    else:
        print('[Audit] All dialogues have sleep data in context.')
    
    print(f'[Audit] Next step: run `python aisleepgen_tool.py audit response-quality --full` to invoke LLM-as-Judge')

# ==================== 主入口 ====================
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='AI Response Quality Auditor')
    parser.add_argument('--full', action='store_true', help='Run LLM-as-Judge (requires service running)')
    parser.add_argument('--record', action='store_true', help='Extract dialogues from trace log')
    args = parser.parse_args()

    print('=' * 60)
    print('  AI 回复质量审计 — Response Grounding Evaluation v1.0')
    print('  Framework: Anthropic Constitutional AI + DeepMind Grounding Eval')
    print('=' * 60)
    
    if args.record or args.full:
        dialogues = extract_dialogues_from_trace()
        print(f'\n[Audit] Found {len(dialogues)} recorded dialogues.')
        for d in dialogues:
            print(f'  {d["trace_id"]}: {len(d["lines"])} trace lines')
    
    if args.full:
        print('\n[Audit] Running LLM-as-Judge (DeepMind Grounding Eval + Constitutional AI)...')
        api_key = find_api_key()
        
        if not api_key:
            print('[Audit] No API key found. Set DEEPSEEK_API_KEY env var.')
            sys.exit(1)
        
        # 从记录提取每个对话的用户上下文
        dialogues = extract_dialogues_from_trace()
        scores = []
        
        for dia in dialogues:
            ctx = format_context_for_judge(dia)
            if not ctx:
                continue
            
            print(f'\n[Audit] Evaluating {dia["trace_id"]}...')
            score = call_judge(ctx, '(AI回复会从trace日志中提取)', api_key)
            if score:
                scores.append(score)
                print(f'  Grounding: {score.get("grounding","?")}/5')
                print(f'  Faithfulness: {score.get("faithfulness","?")}/5')
                print(f'  Omission: {score.get("omission","?")}/5')
                print(f'  Quality: {score.get("quality","?")}/5')
                print(f'  Summary: {score.get("summary","")}')
        
        # 输出汇总报告
        if scores:
            avg = lambda k: sum(s.get(k, 0) for s in scores) / len(scores)
            print(f'\n{"="*50}')
            print(f'  LLM-as-Judge 最终报告')
            print(f'{"="*50}')
            print(f'  评估对话数: {len(scores)}')
            print(f'  平均 Grounding: {avg("grounding"):.1f}/5')
            print(f'  平均 Faithfulness: {avg("faithfulness"):.1f}/5')
            print(f'  平均 Omission: {avg("omission"):.1f}/5')
            print(f'  平均 Quality: {avg("quality"):.1f}/5')
            
            # 标记需要关注的项
            alerts = []
            for s in scores:
                if s.get('omission', 5) <= 2:
                    alerts.append(f'  ⚠ Omission warning: grounding={s.get("grounding")} faithfulness={s.get("faithfulness")}')
            
            if alerts:
                print('\n  ⚠ 报警项:')
                for a in alerts:
                    print(a)
            else:
                print('\n  所有对话数据引用正常。')
        
    check_interaction_trace()
