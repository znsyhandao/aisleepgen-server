#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_retest_test.py - Test-Retest信度测试 v1.0

评估AI对相同输入在不同时间给出回复的一致性。
遵循最佳实践：测试-retest信度是心理测量学的基本要求。

核心指标：
- 回复风格一致性（语气、结构）
- 关键评分一致性（睡眠评分、建议类别）
- 无矛盾声明
- 方向性建议一致性

用法:
  python dev_tools/test/test_retest_test.py [--host localhost:8090]
  python aisleepgen_tool.py test test-retest
"""

import os, sys, json, urllib.request, urllib.error, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from world_model_helper import extract_reply_text

PASS = 0; FAIL = 0; WARN = 0
HOST = "localhost:8090"

def report(result, label, detail=''):
    global PASS, FAIL, WARN
    if result == 'PASS': PASS += 1; print(f"  [PASS] {label}")
    elif result == 'FAIL': FAIL += 1; print(f"  [FAIL] {label}: {detail}")
    elif result == 'WARN': WARN += 1; print(f"  [WARN] {label}: {detail}")

def api_post(host, path, data, timeout=10):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

def extract_reply_text(resp):
    """Extract reply text"""
    if isinstance(resp, dict):
        for key in ['reply', 'response', 'message', 'content', 'text', 'analysis']:
            if key in resp and isinstance(resp[key], str):
                return resp[key]
    return json.dumps(resp, ensure_ascii=False)

def test_consistent_sleep_score():
    """相同数据应该产生相似的睡眠评分"""
    print("\n=== 睡眠评分一致性测试 ===")
    
    sleep_data = {
        "bedtime": "23:30",
        "wake_time": "07:00",
        "sleep_latency_min": 45,
        "total_sleep_hours": 6.5,
        "night_wakings": 2,
        "waking_duration_min": 30,
        "mood_on_waking": "疲倦",
        "stress_level": 7
    }
    
    scores = []
    for i in range(3):
        # Send as fresh each time (new session)
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_retest_user",
            "session_id": f"retest_score_{i}",
            "message": f"这是我的睡眠数据，帮我分析: {json.dumps(sleep_data, ensure_ascii=False)}",
            "platform": "test"
        })
        if '_error' not in resp:
            reply = extract_reply_text(resp)
            # Try to extract a score
            import re
            score_matches = re.findall(r'(\d+)\s*[/分]', reply)
            if score_matches:
                scores.append(int(score_matches[0]))
        
        time.sleep(0.5)  # Small delay between requests
    
    if len(scores) >= 2:
        score_range = max(scores) - min(scores)
        if score_range <= 2:
            report('PASS', f"评分一致性良好 (范围={score_range}, 值={scores})")
        elif score_range <= 5:
            report('WARN', f"评分有一定波动 (范围={score_range}, 值={scores})")
        else:
            report('FAIL', f"评分波动过大 (范围={score_range}, 值={scores})")
    else:
        report('WARN', f"无法提取评分 (提取到{len(scores)}个: {scores})")

def test_no_contradictory_advice():
    """相同输入不应给出矛盾建议"""
    print("\n=== 建议一致性测试 ===")
    
    prompt = "我晚上11点睡，早上6点醒，中间醒1-2次"
    
    replies = []
    for i in range(3):
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_retest_user",
            "session_id": f"retest_advice_{i}",
            "message": prompt,
            "platform": "test"
        })
        if '_error' not in resp:
            replies.append(extract_reply_text(resp).lower())
        time.sleep(0.3)
    
    if len(replies) < 2:
        report('WARN', "服务器未响应")
        return
    
    # Check for contradictory advice patterns
    contradiction_pairs = [
        ("白天小睡", "不要小睡"),
        ("少喝咖啡", "多喝咖啡"),
        ("早睡", "晚睡"),
        ("运动", "不要运动"),
        ("减少屏幕时间", "增加屏幕时间"),
    ]
    
    contradictions = 0
    for a_key, b_key in contradiction_pairs:
        has_a = sum(1 for r in replies if a_key in r)
        has_b = sum(1 for r in replies if b_key in r)
        if has_a > 0 and has_b > 0:
            contradictions += 1
            report('WARN', f"发现矛盾建议: {a_key} vs {b_key}")
    
    if contradictions == 0:
        report('PASS', f"3次回复中无直接矛盾建议")
    else:
        report('FAIL', f"发现{contradictions}组矛盾建议")

def test_structural_consistency():
    """回复结构一致性（JSON格式字段一致性）"""
    print("\n=== 回复结构一致性测试 ===")
    
    prompt = "分析一下我的睡眠，昨晚睡了6小时，中间醒了一次"
    
    first_resp = api_post(HOST, "/api/chat", {
        "openid": "test_retest_user",
        "session_id": "retest_struct_1",
        "message": prompt,
        "platform": "test"
    })
    second_resp = api_post(HOST, "/api/chat", {
        "openid": "test_retest_user",
        "session_id": "retest_struct_2",
        "message": prompt,
        "platform": "test"
    })
    
    if '_error' in first_resp or '_error' in second_resp:
        report('WARN', "跳过：服务器未响应")
        return
    
    # Compare top-level fields
    f_keys = set(first_resp.keys())
    s_keys = set(second_resp.keys())
    
    if f_keys == s_keys:
        report('PASS', f"回复JSON字段一致 ({len(f_keys)}个字段)")
    else:
        missing = f_keys - s_keys
        extra = s_keys - f_keys
        report('WARN', f"字段不一致: 缺失{missing}, 多余{extra}")

def test_response_length_consistency():
    """回复长度不应波动过大"""
    print("\n=== 回复长度一致性测试 ===")
    
    prompt = "我最近总是凌晨3点醒，然后睡不着"
    lengths = []
    
    for i in range(3):
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_retest_user",
            "session_id": f"retest_len_{i}",
            "message": prompt,
            "platform": "test"
        })
        if '_error' not in resp:
            reply = extract_reply_text(resp)
            lengths.append(len(reply))
        time.sleep(0.3)
    
    if len(lengths) >= 2:
        avg = sum(lengths) / len(lengths)
        max_dev = max(abs(l - avg) for l in lengths)
        # Allow up to 50% deviation
        if max_dev / avg <= 0.5:
            report('PASS', f"回复长度波动正常 (平均{avg:.0f}字, 最大偏差{max_dev:.0f})")
        else:
            report('WARN', f"回复长度波动大 (平均{avg:.0f}字, 最大偏差{max_dev:.0f}字)")
    else:
        report('WARN', "无法获取回复")

def main():
    print(f"{'='*60}")
    print(f"  Test-Retest信度测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_consistent_sleep_score()
    test_no_contradictory_advice()
    test_structural_consistency()
    test_response_length_consistency()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
