#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_judge.py — LLM-as-Judge 核心引擎 v1.0

前沿依据: Constitutional AI (Anthropic 2023) + 
           Response Grounding Evaluation (Google DeepMind 2025) +
           Self-Critique with Omission Detection (OpenAI 2025)

调用方式: 独立模块，不依赖 deepseek_proxy.py
         API key 探测顺序: 环境变量 → .env 文件 → 传入参数
"""

import sys, os, json, urllib.request, re

# 已知 key 来源
_KEY_SOURCES = [
    ('C:\\Users\\cqs10\\.openclaw\\openclaw.json', lambda f: json.load(f)['models']['providers']['deepseek']['apiKey']),
]


def find_api_key():
    """从多个来源探测 API key"""
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('OPENAI_API_KEY')
    if key:
        return key
    
    # 从 openclaw.json
    for path, extractor in _KEY_SOURCES:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return extractor(f)
        except Exception:
    # 从 .env 文件
    for dir_path in [os.getcwd(), os.path.dirname(os.path.abspath(__file__)), 'D:\\AISleepGen_Optimized']:
        env_path = os.path.join(dir_path, '.env')
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('DEEPSEEK_API_KEY='):
                        return line.strip().split('=', 1)[1].strip().strip('"').strip("'")
    
    return None


JUDGE_SYSTEM_PROMPT = """你是一个严格但公正的 AI 回复质量审计员，遵循 Anthropic Constitutional AI 方法论。

## 评估框架（三原则）

1. **Context Grounding (0-5)** — AI 回复是否准确引用了上下文中的用户数据？
   5 = 所有相关数据都被准确引用
   3 = 部分引用，但缺失关键数据
   1 = 完全没有引用任何数据
   0 = 存在数据幻觉（说了一些上下文不存在的内容）

2. **Data Faithfulness (0-5)** — 引用的数据是否和上下文完全一致？
   5 = 所有数字、时间、评分完全一致
   3 = 大致正确但有轻微偏差
   1 = 存在明显的数字/事实错误

3. **Omission Detection (0-5)** — 上下文中有可用数据但 AI 选择了回避？
   5 = 充分利用了可用数据
   3 = 引用了部分数据但忽略了关键的
   1 = 完全回避了可用数据，给的是通用建议

4. **Overall Quality (0-5)** — 整体回复质量
   5 = 温暖、专业、数据驱动、建议可执行
   3 = 中规中矩
   1 = 空洞、模板化

## 输出格式（只返回 JSON）：
{"grounding": 0-5, "faithfulness": 0-5, "omission": 0-5, "quality": 0-5, "summary": "2句话"}"""


def call_judge(user_context, ai_response, api_key=None, timeout=30):
    """调用 DeepSeek API 做 judge"""
    if not api_key:
        api_key = find_api_key()
    
    if not api_key:
        print('[Judge] No API key available. 跳过 LLM judge.')
        print('[Judge] 请设置 DEEPSEEK_API_KEY 环境变量或创建 .env 文件。')
        return None
    
    prompt = f"""## 用户数据上下文（提供给 AI 助手的用户信息）：
{user_context[:2000]}

## AI 助手的回复：
{ai_response[:1500]}

请按三原则逐项评分。"""
    
    payload = json.dumps({
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': JUDGE_SYSTEM_PROMPT},
            {'role': 'user', 'content': prompt}
        ],
        'max_tokens': 512,
        'temperature': 0.3
    }).encode('utf-8')
    
    req = urllib.request.Request(
        'https://api.deepseek.com/v1/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + api_key
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            raw = result.get('choices', [{}])[0].get('message', {}).get('content', '')
            # 提取 JSON 块
            m = re.search(r'\{[^}]+\}', raw)
            if m:
                return json.loads(m.group())
            return {'raw': raw, 'error': 'no JSON in response'}
    except Exception as e:
        print(f'[Judge] API call failed: {e}')
        return None


def batch_judge(dialogues_with_replies, api_key=None):
    """批量评估多个对话"""
    results = []
    for dia in dialogues_with_replies:
        ctx = dia.get('context', '')
        reply = dia.get('reply', '')
        if not ctx or not reply:
            continue
        score = call_judge(ctx, reply, api_key)
        if score:
            score['trace_id'] = dia.get('trace_id', '?')
            results.append(score)
    return results


if __name__ == '__main__':
    # 快速测试
    print('[Judge] Testing LLM-as-Judge...')
    result = call_judge(
        '用户睡眠数据: 上床23:00 起床07:00 入睡15分 醒2次 总时长420分, 评分72/100, 主诉:入睡困难',
        '你平时23点睡7点起，总时长7小时基本够，但你入睡需要15分钟说明你睡前的放松不够。'
    )
    if result:
        for k in ['grounding', 'faithfulness', 'omission', 'quality', 'summary']:
            v = result.get(k, '')
            if k == 'summary':
                print(f'  {k}: {v}')
            else:
                print(f'  {k}: {v}/5')
    else:
        print('[Judge] API not available')
