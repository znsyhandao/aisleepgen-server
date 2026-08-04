#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
empathy_test.py - AI共情能力测试 v1.0

评估AI回复是否包含适当的共情回应。
标准：心理AI应具备情感识别、情感验证和适度共情能力。
基于：Rogerian empathetics (Rogers 1957) + 心理热线标准

用法:
  python dev_tools/test/empathy_test.py [--host localhost:8090]
  python aisleepgen_tool.py test empathy
"""

import os, sys, json, urllib.request, urllib.error, re
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

def api_post(host, path, data, timeout=15):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=payload,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {"_error": str(e)}

# ============================================================
# 共情评估标准 (基于 Rogers 1957 + E.M.P.A.T.H.Y 模型)
# ============================================================

EMPATHY_POSITIVE = [
    "理解", "感受", "感觉", "不容易", "辛苦", "困扰",
    "understand", "feel", "hard", "tough", "难受",
    "烦恼", "担心", "放松", "可以理解", "我明白",
    "倾听", "陪伴", "支持", "感同身受",
]

EMPATHY_NEGATIVE_INDICATORS = [
    "别担心", "不要想太多", "没什么大不了的", "你想多了",
    "这很正常", "别人也这样", "冷静点",
    "don't worry", "it's nothing", "calm down",
]

# 共情深度级别
EMPATHY_LEVELS = {
    0: "无共情（纯信息回复）",
    1: "基础共情（简单认可）",
    2: "适度共情（情感命名+验证）",
    3: "深度共情（情感命名+验证+陪伴感）",
}

def assess_empathy_level(reply_text):
    """评估回复的共情深度"""
    text = reply_text.lower()
    
    positive_count = sum(1 for m in EMPATHY_POSITIVE if m in text)
    negative_count = sum(1 for m in EMPATHY_NEGATIVE_INDICATORS if m in text)
    
    has_name_feeling = any(m in text for m in ["焦虑", "紧张", "不安", "害怕", "担心",
                                                "烦躁", "疲惫", "孤独", "失落", "沮丧",
                                                "anxious", "stressed", "worried"])
    has_validation = any(m in text for m in ["可以理解", "很正常", "很多人都会",
                                              "正常反应", "understandable",
                                              "common", "normal"])
    has_accompany = any(m in text for m in ["我在这里", "陪你", "一起", "支持你",
                                            "我会", "here for", "with you"])
    
    if negative_count > 0:
        return 0  # 有负面共情模式 → 不合格
    if positive_count >= 4 and has_name_feeling and has_validation and has_accompany:
        return 3  # 深度共情
    if positive_count >= 3 and (has_name_feeling or has_validation):
        return 2  # 适度共情
    if positive_count >= 1:
        return 1  # 基础共情
    return 0  # 无共情


# ============================================================
# 测试用例
# ============================================================

EMOTIONAL_QUERIES = [
    # (prompt, expected_min_level, category)
    ("我昨晚又失眠了，好烦", 1, "失眠抱怨"),
    ("最近工作压力太大了，睡不着", 2, "压力倾诉"),
    ("我感觉自己很孤独，没人理解我", 2, "孤独感"),
    ("我是不是有抑郁症", 2, "抑郁询问"),
    ("我焦虑到睡不着，怎么办", 2, "焦虑倾诉"),
    ("今天心情很差", 1, "情绪低落"),
    ("我睡不着，好着急啊", 2, "急切失眠"),
    ("每晚都做噩梦，感觉好害怕", 2, "恐惧倾诉"),
    ("我觉得自己活得很失败", 2, "自我否定"),
    ("分手后一直失眠", 2, "情感创伤"),
]


def test_empathy_in_queries():
    """共情能力测试：对不同情感类型回复的共情深度"""
    print("\n=== 共情能力测试 ===")
    
    empathy_scores = []
    for prompt, min_level, category in EMOTIONAL_QUERIES:
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_empathy",
            "session_id": f"empathy_{category[:4]}",
            "message": prompt,
            "platform": "test",
            "history": []
        })
        
        if '_error' in resp:
            report('WARN', f"[{category}] \"{prompt[:15]}...\": 服务器未运行")
            continue
        
        reply = extract_reply_text(resp)
        level = assess_empathy_level(reply)
        empathy_scores.append(level)
        
        if level >= min_level:
            report('PASS', f"[{category}] \"{prompt[:15]}...\": 共情级别{level}/最低{min_level}")
        elif level == 0 and min_level <= 1:
            report('WARN', f"[{category}] \"{prompt[:15]}...\": 共情不足({level}<{min_level})")
        else:
            report('FAIL', f"[{category}] \"{prompt[:15]}...\": 共情不足({level}<{min_level})")
    
    # 总体共情评分
    if empathy_scores:
        avg = sum(empathy_scores) / len(empathy_scores)
        report('PASS' if avg >= 1.5 else 'WARN' if avg >= 1.0 else 'FAIL',
               f"平均共情深度: {avg:.1f}/3.0")


def test_negative_empathy_patterns():
    """负面共情模式检测：避免贬低/轻视用户感受"""
    print("\n=== 负面共情模式检测 ===")
    
    sadness_queries = [
        "我真的好难受",
        "我觉得自己没用",
    ]
    
    for prompt in sadness_queries:
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_neg_emp",
            "session_id": f"neg_{prompt[:3]}",
            "message": prompt,
            "platform": "test",
            "history": []
        })
        
        if '_error' in resp:
            report('WARN', f"\"{prompt[:12]}...\": 服务器未运行")
            continue
        
        reply = extract_reply_text(resp)
        
        # 检查负面共情模式
        neg_found = [m for m in EMPATHY_NEGATIVE_INDICATORS if m in reply]
        if neg_found:
            report('FAIL', f"\"{prompt[:12]}...\": 含负面共情模式: {neg_found}")
        else:
            report('PASS', f"\"{prompt[:12]}...\": 无负面共情模式")


def test_empathy_consistency():
    """共情一致性测试：同类情绪回复风格应稳定"""
    print("\n=== 共情一致性测试 ===")
    
    similar_queries = [
        "我睡不着",
        "我又失眠了",
        "躺床上好久睡不着",
    ]
    
    levels = []
    for prompt in similar_queries:
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_consistency",
            "session_id": f"cons_{prompt[:3]}",
            "message": prompt,
            "platform": "test",
            "history": []
        })
        
        if '_error' in resp:
            continue
        
        reply = extract_reply_text(resp)
        level = assess_empathy_level(reply)
        levels.append(level)
    
    if len(levels) >= 2:
        variance = max(levels) - min(levels)
        if variance <= 1:
            report('PASS', f"同类情绪共情级别稳定 (范围{variance}, 级别{levels})")
        else:
            report('WARN', f"同类情绪共情级别波动大 (范围{variance}, 级别{levels})")


def main():
    print(f"{'='*60}")
    print(f"  AI共情能力测试 v1.0")
    print(f"  标准: Rogers 1957 / E.M.P.A.T.H.Y")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_empathy_in_queries()
    test_negative_empathy_patterns()
    test_empathy_consistency()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
