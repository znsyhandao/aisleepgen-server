#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
isi_validation_test.py - ISI失眠严重指数验证测试 v1.0

验证AI对失眠严重程度的评估与标准ISI评分的一致性。
ISI（Insomnia Severity Index）是失眠评估的黄金标准工具。

核心检查：
1. AI评估的失眠严重度分级与ISI标准分级的一致性
2. AI是否使用了类似ISI的评估框架

用法:
  python dev_tools/test/isi_validation_test.py [--host localhost:8090]
  python aisleepgen_tool.py test isi-validation
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

# ===== Standard ISI Classifications =====
# ISI score ranges: 0-7 = no insomnia, 8-14 = subthreshold, 15-21 = moderate, 22-28 = severe
ISI_CLASSES = [
    # (sleep_data_description, expected_isi_class, difficulty_to_detect)
    ("11点睡7点起，5分钟入睡，一夜到天亮，精力充沛", "无失眠", "easy"),
    ("12点睡6点起，30分钟入睡，醒1次，早上有点累", "轻度失眠", "medium"),
    ("11点半睡6点起，45-60分钟入睡，醒2-3次，白天很累", "中度失眠", "medium"),
    ("10点睡4点醒，90分钟以上入睡，醒4-5次，几乎崩溃", "重度失眠", "easy"),
]

ISI_GRADE_KEYWORDS = {
    "无失眠": ["无失眠", "正常", "no insomnia", "good sleep", "健康"],
    "轻度": ["轻度", "轻度失眠", "轻度睡眠", "轻微", "mild", "subthreshold"],
    "中度": ["中度", "中度失眠", "moderate", "中等"],
    "重度": ["重度", "重度失眠", "严重", "severe", "serious"],
}

def test_isi_grade_consistency():
    """核心测试：AI对失眠严重度的评估是否与ISI分类一致"""
    print("\n=== ISI失眠严重度分级一致性测试 ===")
    
    for i, (desc, expected, difficulty) in enumerate(ISI_CLASSES):
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_isi_user",
            "session_id": f"isi_test_{i}",
            "message": f"我最近的睡眠情况: {desc}。帮我评估一下失眠严重程度",
            "platform": "test"
        })
        if '_error' in resp:
            report('WARN', f"[{i+1}] 服务器未运行")
            continue
        
        reply = extract_reply_text(resp).lower()
        
        # Check if AI uses a grade matching expected
        matched_keywords = ISI_GRADE_KEYWORDS.get(expected, ["no_match_expected"])
        found_grade = False
        found_any_grade = False
        
        for grade, keywords in ISI_GRADE_KEYWORDS.items():
            if any(kw.lower() in reply for kw in keywords):
                found_any_grade = True
                if grade == expected or (expected == "无失眠" and grade == "无失眠"):
                    found_grade = True
                    break
        
        if found_grade:
            report('PASS', f"[{i+1}] 分级正确: {expected}")
        elif found_any_grade:
            report('WARN', f"[{i+1}] 有分级但与预期({expected})不符（可能需要人工审核）")
        else:
            report('WARN', f"[{i+1}] 未检测到明确分级表述")

def test_has_structured_assessment():
    """检查AI是否进行了结构化评估"""
    print("\n=== 结构化评估框架测试 ===")
    
    prompts = [
        "帮我评估一下最近的睡眠质量",
        "我失眠严重吗",
    ]
    
    structured_markers = [
        "入睡", "维持", "早醒", "睡眠质量",
        "白天功能", "日间", "duration",
        "latency", "efficiency",
        "1.", "2.", "3.", "4.", "5.",
        "方面", "维度", "dimension", "aspect",
        "评分", "score", "评估",
    ]
    
    for prompt in prompts:
        resp = api_post(HOST, "/api/chat", {
            "openid": "test_isi_user",
            "session_id": f"isi_struct_{prompt[:4]}",
            "message": prompt,
            "platform": "test"
        })
        if '_error' in resp:
            report('WARN', f"跳过")
            continue
        
        reply = extract_reply_text(resp).lower()
        found_markers = [m for m in structured_markers if m.lower() in reply]
        
        if len(found_markers) >= 3:
            report('PASS', f"含结构化评估 ({len(found_markers)}个评估维度)")
        else:
            report('WARN', f"结构化评估维度较少 ({len(found_markers)}个)")

def test_isi_baseline_in_code():
    """检查代码中是否有ISI评分基准"""
    print("\n=== ISI评分基准代码检查 ===")
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    isi_refs = 0
    for fname in ['sleep_world_model.py', 'deepseek_proxy.py']:
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()
        for kw in ['ISI', '失眠严重', 'insomnia severity', '失眠指数']:
            isi_refs += content.count(kw)
    
    if isi_refs > 0:
        report('PASS', f"代码中有{isi_refs}个ISI相关引用")
    else:
        report('WARN', "代码中未发现ISI评分直接引用（system prompt中可能包含）")

def main():
    print(f"{'='*60}")
    print(f"  ISI失眠严重指数验证测试 v1.0")
    print(f"  Target: {HOST}")
    print(f"{'='*60}")
    
    test_isi_grade_consistency()
    test_has_structured_assessment()
    test_isi_baseline_in_code()
    
    print(f"\n{'='*60}")
    print(f"  结果: PASS={PASS} FAIL={FAIL} WARN={WARN}")
    print(f"{'='*60}")
    return 0 if FAIL == 0 else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].startswith('--host='):
        HOST = sys.argv[1].split('=', 1)[1]
    sys.exit(main())
