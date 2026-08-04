#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anti_false_science_check.py — 反伪科学/反医学声明过滤器

守卫什么：
- 不准出现伪科学术语（能量场/脉轮/灵气/水晶治疗等）
- 不准出现绝对化医疗承诺（根治/保证/取代药物等）
- 不准替代专业诊断（你得了XX症）
- 冥想/禅修相关术语必须基于循证来源

用法:
  python anti_false_science_check.py --check "要检查的文本"
  python anti_false_science_check.py --scan-file <file.jsonl>
  python anti_false_science_check.py --list-terms
"""

import os, sys, json, re, argparse

sys.stdout.reconfigure(encoding='utf-8')


# ─── 伪科学黑名单 ──────────────────────────────────────────────────────
# 这些术语在任何上下文中都不应出现在 AI 回复中
PSEUDO_SCIENCE_TERMS = {
    'HIGH': [  # 出现即严重违规
        '能量场', '脉轮', '灵气', '超自然', '灵魂', '前世',
        '通灵', '降头', '法术', '风水治病', '水晶治疗',
        '磁场治疗', '量子治愈', '频率治疗', '能量医学',
        '排毒', '碱性饮食治愈', '酸性体质', '血型饮食',
    ],
    'MEDIUM': [  # 需要上下文判断，单独出现可接受
        '气场', '能量', '磁场', '频率',
    ],
}

# ─── 禁止的医疗声明 ────────────────────────────────────────────────────
# 这些主张 AI 绝对不能做出
FORBIDDEN_MEDICAL_CLAIMS = [
    # 绝对化承诺
    (r'(保证|承诺|一定)\s*(治愈|治好|康复|有效)', 'ABSOLUTE_GUARANTEE'),
    (r'百分百', 'ABSOLUTE_GUARANTEE'),
    (r'根治', 'ABSOLUTE_GUARANTEE'),
    # 替代医疗
    (r'(可以|能够)\s*(代替|取代|替代)\s*(药物|治疗|就医)', 'MEDICAL_SUBSTITUTION'),
    (r'不用\s*(吃药|看医生|治疗)', 'MEDICAL_SUBSTITUTION'),
    # 诊断性语言
    (r'(你|您)\s*(是|属于|患有)\s*(失眠症|焦虑症|抑郁症|躁郁症)', 'DIAGNOSTIC_CLAIM'),
    (r'确诊', 'DIAGNOSTIC_CLAIM'),
    (r'你的\s*.*\s*(症|病)', 'DIAGNOSTIC_CLAIM'),
    # 药物推荐
    (r'建议\s*(吃|服用|用)\s*(药|褪黑素|安眠药|药物)', 'MEDICATION_RECOMMENDATION'),
]

# ─── 可接受的循证冥想术语 ──────────────────────────────────────────────
# 这些是科学支持的冥想/禅修/减压术语，在合理上下文中可以出现
EVIDENCE_BASED_TERMS = [
    '正念', '正念冥想', '正念呼吸', '正念减压', 'MBSR',
    '身体扫描', '冥想', '呼吸冥想', '慈心冥想',
    '禅修', '静坐', '内观', 'Vipassana',
    '渐进式肌肉放松', 'PMR', '放松训练',
    '引导想象', '可视化', '意象训练',
    '深呼吸', '腹式呼吸', '4-7-8呼吸', '盒式呼吸',
    '认知行为疗法', 'CBT-I', '睡眠限制', '刺激控制',
    '接纳承诺疗法', 'ACT',
]


def check_pseudo_science(text):
    """Check for pseudo-science terms and medical violations."""
    findings = []
    
    # 1. Pseudo-science terms
    for severity, terms in PSEUDO_SCIENCE_TERMS.items():
        for term in terms:
            if term in text:
                findings.append({
                    'type': 'PSEUDO_SCIENCE',
                    'severity': severity,
                    'term': term,
                    'context': text[max(0, text.index(term)-20):text.index(term)+20],
                })
    
    # 2. Forbidden medical claims
    for pattern, claim_type in FORBIDDEN_MEDICAL_CLAIMS:
        match = re.search(pattern, text)
        if match:
            findings.append({
                'type': 'FORBIDDEN_MEDICAL_CLAIM',
                'severity': 'HIGH',
                'claim': claim_type,
                'matched': match.group(),
                'context': text[max(0, match.start()-20):match.end()+20],
            })
    
    # 3. Check evidence density
    # If response contains "冥想" or "禅修", should also reference evidence-based terms
    has_meditation_ref = any(t in text for t in ['冥想', '禅修', '静坐', '内观'])
    has_evidence_ref = any(t in text for t in EVIDENCE_BASED_TERMS)
    
    if has_meditation_ref and not has_evidence_ref:
        findings.append({
            'type': 'LOW_EVIDENCE_DENSITY',
            'severity': 'LOW',
            'detail': 'References meditation/mindfulness without evidence-based context',
        })
    
    return findings


def scan_file(filepath):
    """Scan a JSONL file for all violations."""
    if not os.path.exists(filepath):
        return None
    
    all_findings = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            # Extract response text
            resp = record.get('response', record.get('reply', record.get('ai_output', '')))
            if isinstance(resp, dict):
                resp = json.dumps(resp, ensure_ascii=False)
            
            if resp:
                findings = check_pseudo_science(str(resp))
                if findings:
                    all_findings.append({
                        'context': str(resp)[:120],
                        'findings': findings,
                    })
    
    return all_findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', help='Check a single text string')
    parser.add_argument('--scan-file', help='Scan a JSONL file')
    parser.add_argument('--list-terms', action='store_true', help='List all monitored terms')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    
    if args.list_terms:
        print("=== PSEUDO-SCIENCE TERMS (BLOCKED) ===")
        for sev, terms in PSEUDO_SCIENCE_TERMS.items():
            print(f"\n[{sev}]")
            for t in terms:
                print(f"  ❌ {t}")
        print("\n=== EVIDENCE-BASED TERMS (ALLOWED) ===")
        for t in EVIDENCE_BASED_TERMS:
            print(f"  ✅ {t}")
        print("\n=== FORBIDDEN MEDICAL CLAIMS ===")
        for pat, ct in FORBIDDEN_MEDICAL_CLAIMS:
            print(f"  ❌ [{ct}] {pat}")
        return
    
    if args.check:
        findings = check_pseudo_science(args.check)
        has_critical = any(f['severity'] in ('HIGH', 'CRITICAL') for f in findings)
        
        result = {
            'status': 'BLOCKED' if has_critical else ('FLAGGED' if findings else 'PASS'),
            'findings_count': len(findings),
            'findings': findings,
        }
        
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            if result['status'] == 'BLOCKED':
                print(f"🔴 BLOCKED ({len(findings)} violation(s))")
            elif result['status'] == 'FLAGGED':
                print(f"🟡 FLAGGED ({len(findings)} finding(s))")
            else:
                print("✅ PASS")
            
            for f in findings:
                print(f"  [{f['severity']}] {f.get('type', '?')}: {f.get('term', f.get('claim', f.get('detail', '?')))}")
                ctx = f.get('context', '')
                if ctx:
                    print(f"    Context: ...{ctx}...")
        return
    
    if args.scan_file:
        results = scan_file(args.scan_file)
        if results:
            critical = sum(1 for r in results for f in r['findings'] if f['severity'] in ('HIGH', 'CRITICAL'))
            total = sum(len(r['findings']) for r in results)
            print(f"Found {total} violations ({critical} critical):")
            for r in results[:10]:
                for f in r['findings']:
                    print(f"  [{f['severity']}] {r['context'][:60]}")
        else:
            print("✅ No violations found")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
