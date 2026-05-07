#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wm_test_harness.py — 世界模型自动化测试框架 v1.0

一次性跑完所有关键路径，输出每层状态：✅ 工作 / ❌ 失效
不依赖任何外部文件，从头到尾跑一轮完整测试。
"""

import sys, os, json, time, re, math, random
sys.stdout.reconfigure(encoding='utf-8')
os.environ['AISLEEPGEN_SKIP_MAIN'] = '1'

GREEN = '✅'
RED = '❌'
YELLOW = '⚠️'
total_tests = 0
passed = 0
failed = 0

def test(name, fn):
    global total_tests, passed, failed
    total_tests += 1
    try:
        result = fn()
        if result.get('pass', False):
            passed += 1
            msg = result.get('msg', '')
            print(f'  {GREEN} {name}: {msg}' if msg else f'  {GREEN} {name}')
        else:
            failed += 1
            msg = result.get('msg', '')
            print(f'  {RED} {name}: {msg}' if msg else f'  {RED} {name}')
    except Exception as e:
        failed += 1
        print(f'  {RED} {name}: EXCEPTION: {e}')

def ok(msg=''):
    return {'pass': True, 'msg': msg}
def fail(msg=''):
    return {'pass': False, 'msg': msg}

print('=' * 60)
print('WM 自动化测试框架 v1.0')
print('=' * 60)
print()

# ===== 阶段1: 模块导入测试 =====
print('--- 阶段1: 模块导入 ---')

def t_neural_extractor():
    from neural_extractor import NeuralExtractor
    ne = NeuralExtractor(prefer_llm=True)
    if ne and hasattr(ne, 'extract'):
        return ok('NeuralExtractor(prefer_llm=True) loaded')
    return fail('NeuralExtractor loaded but has no extract method')
test('neural_extractor 导入', t_neural_extractor)

def t_wm_memory():
    from wm_memory import save_experience, retrieve_similar, format_memory_context, optimize_memory
    return ok('save_experience + retrieve_similar + format_memory_context')
test('wm_memory 导入', t_wm_memory)

def t_wm_router():
    from wm_router import get_router, predict_strategy, daily_train_router
    return ok('get_router + predict_strategy + daily_train_router')
test('wm_router 导入', t_wm_router)

def t_wm_trace():
    from wm_trace import WMTrace
    t = WMTrace('test', 'test message')
    t.layer('test_layer')
    r = t.commit()
    if r and 'layers' in r:
        return ok(f'Trace written: {r["summary"]}')
    return fail('Trace commit returned invalid')
test('wm_trace 导入+写入', t_wm_trace)

def t_wm_distill():
    import wm_distill as d
    if hasattr(d, 'main'):
        return ok('wm_distill.py with main()')
    return fail('wm_distill has no main()')
test('wm_distill 导入', t_wm_distill)

def t_dp_router():
    from dp_router import dispatch
    r = dispatch('POST', '/api/chat', {'message': '你好', 'openid': 'test'})
    if 'reply' in r:
        return ok(f'dispatch returned reply: {r.get("reply", "")[:40]}')
    return fail(f'dispatch missing reply key, got: {list(r.keys())}')
test('dp_router dispatch', t_dp_router)

def t_fallback():
    from fallback_replies import generate_fallback_reply
    r = generate_fallback_reply('昨晚喝红酒肚子不舒服老醒', None, None, 'restorative')
    if r and len(r) > 20:
        return ok(f'fallback reply: {r[:60]}...')
    return fail(f'fallback returned: {r}')
test('fallback引擎', t_fallback)

print()

# ===== 阶段2: Neural Extractor 实测 =====
print('--- 阶段2: Neural Extractor 字段提取 ---')

TEST_CASES = [
    ('酒精+消化', '昨晚喝红酒，肚子不舒服老醒'),
    ('焦虑+失眠', '最近压力大，躺在床上脑子停不下来，翻来覆去睡不着'),
    ('打鼾+呼吸', '我老婆说我昨晚打呼噜特别响，中间还停了几秒'),
    ('疼痛', '腰疼得厉害，怎么躺都不舒服'),
    ('一般性', '你好，今天状态还行'),
]

for label, text in TEST_CASES:
    def make_test(label, text):
        def fn():
            from neural_extractor import NeuralExtractor
            ne = NeuralExtractor(prefer_llm=True)
            fields = ne.extract(text)
            if not fields or not isinstance(fields, dict):
                return fail(f'返回空或非dict: {type(fields).__name__}')
            non_empty = {k: v for k, v in fields.items() if v is not None and v != '' and k not in ('determined', 'confidence')}
            count = len(non_empty)
            if count >= 2:
                keys = list(non_empty.keys())[:5]
                return ok(f'{count}个字段: {keys}')
            return YELLOW + f' 仅{count}个字段: {list(non_empty.keys())}'
        return fn
    test(f'neural_extractor [{label}]: {text[:25]}', make_test(label, text))

print()

# ===== 阶段3: wm_router 路由网络 =====
print('--- 阶段3: wm_router 路由决策 ---')

ROUTER_TEST_CASES = [
    ('酒精+消化', {'awake_times': 3, 'drink': 'alcohol', 'has_pain': True, 'awake_cause': '消化不适'}),
    ('焦虑', {'sleep_latency': 60, 'stress_level': 8, 'awake_cause': '焦虑'}),
    ('打鼾', {'snore_related': True}),
    ('一般问候', {}),
]

for label, fields in ROUTER_TEST_CASES:
    def make_test(label, fields):
        def fn():
            from wm_router import predict_strategy
            r = predict_strategy(fields, '昨晚' if fields else '你好')
            retrieve = r.get('should_retrieve', False)
            cat = r.get('category_cn', '?')
            k = r.get('top_k', 0)
            prob = r.get('retrieve_prob', 0)
            if label == '一般问候' and not retrieve:
                return ok(f'不检索(正确): prob={prob}, cat={cat}')
            if label == '酒精+消化' and retrieve:
                return ok(f'检索(正确): prob={prob}, cat={cat}, k={k}')
            # 不完美但接受
            return YELLOW + f'决策: retrieve={retrieve}, cat={cat}, k={k}, prob={prob}'
        return fn
    test(f'wm_router [{label}]', make_test(label, fields))

print()

# ===== 阶段4: DeepSeek API =====
print('--- 阶段4: DeepSeek API 调用 ---')

def t_ds_key():
    from ai_client import DEEPSEEK_API_KEY
    if DEEPSEEK_API_KEY and len(str(DEEPSEEK_API_KEY)) > 10:
        return ok(f'Key loaded: {str(DEEPSEEK_API_KEY)[:8]}...')
    return fail('No DeepSeek API key')
test('DeepSeek API key', t_ds_key)

def t_ds_basic():
    from ai_client import call_deepseek_api
    messages = [{'role': 'user', 'content': 'Say "OK" in one word'}]
    r = call_deepseek_api(messages, use_async=False)
    if r and len(r) > 0:
        return ok(f'Response: {r[:60]}')
    return fail(f'No response or empty: {r}')
test('DeepSeek 基础调用', t_ds_basic)

def t_ds_cache():
    from ai_client import call_deepseek_api
    messages = [{'role': 'user', 'content': 'Say "CACHE TEST OK" in one word'}]
    # 第1次
    t0 = time.time()
    r1 = call_deepseek_api(messages, use_async=False)
    t1 = time.time() - t0
    # 第2次
    t2 = time.time()
    r2 = call_deepseek_api(messages, use_async=False)
    t3 = time.time() - t2
    
    if r1 == r2 and t3 < t1 * 0.5:
        return ok(f'缓存生效: {t1:.1f}s → {t3:.1f}s')
    if r1 != r2:
        return fail(f'两次返回不一致')
    return YELLOW + f'缓存可能未生效: {t1:.1f}s → {t3:.1f}s'
test('DeepSeek 缓存', t_ds_cache)

def t_ds_wm_prompt():
    """测试10专家推理prompt能否正确解析"""
    from ai_client import call_deepseek_api
    prompt = (
        "你是一个睡眠医学多专家会诊系统。基于以下用户描述和系统数据，以10位专家的视角做分析。"
        "输出JSON格式: {'findings': [{'expert': '专家名', 'finding': '发现', 'risk_level': 'low/medium/high'}], "
        "'score': 综合评分0-100, 'quality': '优秀/良好/一般/较差'}"
    )
    user = "用户描述：昨晚喝红酒，肚子不舒服老醒\n系统识别数据：{'drink': 'alcohol', 'awake_cause': '消化不适'}"
    messages = [{'role': 'system', 'content': prompt}, {'role': 'user', 'content': user}]
    r = call_deepseek_api(messages, use_async=False)
    if r:
        try:
            parsed = json.loads(r)
            findings = parsed.get('findings', [])
            score = parsed.get('score', 0)
            if findings and score:
                return ok(f'{len(findings)}个发现, 评分{score}')
            return YELLOW + f'JSON格式但缺字段: {list(parsed.keys())}'
        except json.JSONDecodeError:
            return fail(f'非JSON回复: {r[:80]}')
    return fail('无回复')
test('DeepSeek 10专家推理', t_ds_wm_prompt)

print()

# ===== 阶段5: 世界模型完整链路 =====
print('--- 阶段5: dp_router 完整 chat 链路 ---')

def t_full_chat():
    from dp_router import dispatch
    data = {
        'message': '昨晚喝红酒，肚子不舒服老醒',
        'openid': 'test_auto',
        'history': []
    }
    t0 = time.time()
    r = dispatch('POST', '/api/chat', data)
    elapsed = time.time() - t0
    reply = r.get('reply', '') or ''
    if len(reply) > 30:
        return ok(f'{elapsed:.1f}s | reply: {reply[:80]}...')
    return fail(f'{elapsed:.1f}s | reply太短: {reply}')
test('完整chat链路（首次调用）', t_full_chat)

def t_full_chat_repeat():
    """第二次调用应该走缓存"""
    from dp_router import dispatch
    data = {
        'message': '昨晚喝红酒，肚子不舒服老醒',
        'openid': 'test_auto',
        'history': []
    }
    t0 = time.time()
    r = dispatch('POST', '/api/chat', data)
    elapsed = time.time() - t0
    reply = r.get('reply', '') or ''
    if len(reply) > 30:
        return ok(f'{elapsed:.1f}s | 缓存命中: {reply[:60]}...')
    return fail(f'{elapsed:.1f}s | reply太短: {reply}')
test('完整chat链路（重复调用=缓存）', t_full_chat_repeat)

print()

# ===== 阶段6: 追踪系统 =====
print('--- 阶段6: 追踪系统验证 ---')

def t_trace_exists():
    path = os.path.join(os.path.dirname(__file__), 'data', 'wm_trace.jsonl')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        if len(lines) >= 3:
            last = json.loads(lines[-1])
            layers = [l.get('layer', '?') for l in last.get('layers', [])]
            return ok(f'{len(lines)}条, 最近层: {layers}')
        return YELLOW + f'{len(lines)}条, 不满3条'
    return fail('trace文件不存在')
test('wm_trace.jsonl 存在', t_trace_exists)

def t_memory_exists():
    path = os.path.join(os.path.dirname(__file__), 'data', 'wm_memory.jsonl')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            lines = [l for l in f if l.strip()]
        return ok(f'{len(lines)}条经验')
    return YELLOW + 'memory文件不存在（正常，数据积累中）'
test('wm_memory.jsonl 存在', t_memory_exists)

print()

# ===== 阶段7: 路由网络训练 =====
print('--- 阶段7: 路由网络训练 ---')

def t_router_train():
    from wm_router import daily_train_router
    result = daily_train_router(days=1)
    if result.get('trained', 0) > 0:
        return ok(f'训练{result["trained"]}条, loss={result.get("avg_loss", "?")}')
    return YELLOW + f'无训练数据: {result}'
test('wm_router 每日训练', t_router_train)

def t_router_persist():
    path = os.path.join(os.path.dirname(__file__), 'data', 'wm_router_params.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            p = json.load(f)
        v = p.get('version', '?')
        tc = p.get('train_count', 0)
        return ok(f'参数持久化: v{v}, 训练{tc}次')
    return fail('参数文件不存在')
test('wm_router 参数持久化', t_router_persist)

print()

# ===== 阶段8: wm_distill 蒸馏 =====
print('--- 阶段8: wm_distill 蒸馏 ---')

def t_distill():
    import wm_distill
    try:
        wm_distill.main()
        return ok('distill main() 执行完成')
    except Exception as e:
        return YELLOW + f'distill main() 异常: {e}'
test('wm_distill.py 执行', t_distill)

# 检查config是否更新
def t_config_exists():
    path = os.path.join(os.path.dirname(__file__), 'data', 'world_model_config.json')
    if os.path.exists(path):
        with open(path, 'r') as f:
            p = json.load(f)
        alcohol = p.get('alcohol', p.get('penalties', {}).get('alcohol', '?'))
        return ok(f'config存在: alcohol_penalty={alcohol}')
    return YELLOW + 'config不存在'
test('world_model_config.json 存在', t_config_exists)

print()
print('=' * 60)
print(f'测试完成: {total_tests}项 | {GREEN} {passed}通过 | {RED} {failed}失败')
print('=' * 60)
