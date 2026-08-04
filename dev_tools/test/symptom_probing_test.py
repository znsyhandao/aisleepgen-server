#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
symptom_probing_test.py - 症状追问策略覆盖率测试 v1.0

测试AI在睡眠评估中的症状追问覆盖范围。
好的医疗AI应该主动探测关键临床症状，而不是被动回答。

遵循最佳实践：
- 睡眠医学的ESSENTIAL问诊要素：入睡、维持、早醒、日间功能
- 鉴别诊断需问：呼吸症状、肢体运动、情绪、药物

用法:
  python dev_tools/test/symptom_probing_test.py [--host localhost:8090]
  python aisleepgen_tool.py test symptom-probing
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

def api_post(host, path, data, timeout=10):
    url = f"http://{host}{path}"
    payload = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'_error': str(e)}

# ===== Sleep Medicine Essential Probing Dimensions =====
# From: AASM (American Academy of Sleep Medicine) clinical evaluation guidelines
PROBING_DIMENSIONS = {
    "入睡困难": ["入睡", "睡不着", "躺在床上", "翻来覆去", "多久睡着",
                "sleep latency", "fall asleep", "lying in bed"],
    "睡眠维持": ["醒", "中途", "半夜", "早醒", "凌晨",
                "wake up", "maintain", "middle of night"],
    "日间功能": ["白天", "困", "精力", "工作", "注意力",
                "daytime", "tired", "energy", "concentrat"],
    "呼吸症状": ["打鼾", "憋气", "呼吸暂停", "鼻塞",
                "snore", "apnea", "gasp", "breathe"],
    "情绪状态": ["焦虑", "压力", "心情", "担心", "抑郁",
                "anxiety", "stress", "mood", "depress", "worry"],
    "生活方式": ["运动", "咖啡", "酒精", "饮食", "作息",
                "exercise", "caffeine", "alcohol", "routine"],
    "睡眠环境": ["噪音", "光线", "温度", "床垫", "伴侣",
                "noise", "light", "temperature", "partner"],
}

# Prompts that should trigger multi-dimensional probing
INITIAL_PROMPTS = [
    "我最近睡不好",
    "失眠好久了",
    "晚上总是醒",
    "白天很困",
]

def test_symptom_probing_coverage():
    """测试AI在首次回复中触及了多少个临床维度"""
    print("\n=== 症状追问维度覆盖测试 ===")
    
    for i, prompt in enumerate(INITIAL_PROMPTS):
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_prob_user",
            "session_id": f"probe_{i}",
            "message": prompt,
            "platform": "test"
        })
        if '_error' in resp:
            report('WARN', f"[{i+1}] \"{prompt}\": 跳过")
            continue
        
        reply = extract_reply_text(resp).lower()
        
        # Count how many probing dimensions are touched
        touched = []
        for dim, keywords in PROBING_DIMENSIONS.items():
            if any(kw.lower() in reply for kw in keywords):
                touched.append(dim)
        
        coverage = len(touched)
        total = len(PROBING_DIMENSIONS)
        pct = coverage / total * 100
        
        if coverage >= 4:
            report('PASS', f"[{i+1}] \"{prompt}\": 覆盖{coverage}/{total}维度 ({pct:.0f}%)")
        elif coverage >= 2:
            report('WARN', f"[{i+1}] \"{prompt}\": 覆盖{coverage}/{total}维度 ({pct:.0f}%)")
        else:
            report('FAIL', f"[{i+1}] \"{prompt}\": 仅覆盖{coverage}/{total}维度 ({pct:.0f}%)")
        
        # Show which dimensions
        missed = [d for d in PROBING_DIMENSIONS if d not in touched]
        if missed:
            print(f"    未触及: {', '.join(missed[:4])}")

def test_probing_depth():
    """测试追问是否有深度（不仅仅是列清单）"""
    print("\n=== 追问深度测试 ===")
    
    # User gives minimal info - AI should ask follow-ups
    prompt = "我睡不着"
    resp = api_post(HOST, "/api/chat", {
        "openid": "test_prob_depth",
        "session_id": "probe_depth",
        "message": prompt,
        "platform": "test"
    })
    
    if '_error' in resp:
        report('WARN', "跳过：服务器未运行")
        return
    
    reply = extract_reply_text(resp).lower()
    
    # Check for question marks (follow-up questions)
    question_count = reply.count('?') + reply.count('吗') + reply.count('？')
    
    if question_count >= 3:
        report('PASS', f"有{question_count}个追问/提问")
    elif question_count >= 1:
        report('WARN', f"仅有{question_count}个追问")
    else:
        report('FAIL', "无追问（AI未主动收集信息）")

def test_differential_probing():
    """鉴别诊断追问测试：睡眠呼吸暂停 vs 失眠 vs 不宁腿"""
    print("\n=== 鉴别诊断追问测试 ===")
    
    # User describes vague symptoms — AI should probe for differential
    prompt = "我晚上睡觉总是不踏实，白天特别困"
    resp = api_post(HOST, "/api/chat", {
        "openid": "test_prob_diff",
        "session_id": "probe_diff",
        "message": prompt,
        "platform": "test"
    })
    
    if '_error' in resp:
        report('WARN', "跳过")
        return
    
    reply = extract_reply_text(resp).lower()
    
    # Check for specific differential probing keywords
    diff_keywords = {
        "呼吸暂停": ["打鼾", "憋", "呼吸", "snore"],
        "不宁腿": ["腿", "动", "leg", "restless"],
        "昼夜节律": ["作息", "生物钟", "昼夜", "circadian"],
        "心理因素": ["压力", "焦虑", "担心", "stress"],
    }
    
    diff_touched = []
    for diff_name, keywords in diff_keywords.items():
        if any(kw in reply for kw in keywords):
            diff_touched.append(diff_name)
    
    if len(diff_touched) >= 2:
        report('PASS', f"鉴别诊断覆盖{len(diff_touched)}个方向: {', '.join(diff_touched)}")
    elif len(diff_touched) >= 1:
        report('WARN', f"鉴别诊断覆盖1个方向: {diff_touched[0]}")
    else:
        report('FAIL', "无鉴别诊断追问")

def main():
    print(f"{'='*60}")
    print(f"  症状追问策略覆盖率测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_symptom_probing_coverage()
    test_probing_depth()
    test_differential_probing()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
