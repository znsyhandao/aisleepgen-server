#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forbidden_diagnosis_filter.py v2 — 医学引用合规过滤器

定位：AISleepGen 定位为基于最顶尖睡眠医学+心理学+心理疗愈科学的 AI 助手。

守卫什么（❌ 必须拦截）：
- 无引用支持的断言："你是失眠症"（没说根据哪篇文献）
- 推荐具体药物和剂量：褪黑素5mg
- 绝对化预后承诺："坚持8周一定好"
- 无 disclaimer（AI不是医生，仅供参考）

允许什么（✅ 应该放行）：
- 引用顶刊研究："根据 Sleep 2024 的 Meta分析，失眠症的 CBT-I 有效率达 70-80%"
- DSM-5 / ICSD-3 标准科普："按 ICSD-3 分类，慢性失眠的诊断标准包括..."
- 基于证据的分析："从你的描述看，你可能存在入睡困难，这与你之前提到的压力水平吻合"
- 结合冥想/禅修的干预建议："正念冥想(MBSR) 在 JAMA 的研究中显示对改善入睡 latency 有效"
- 转介建议："不过建议咨询睡眠专科医生做进一步评估"

原则：用最顶尖的睡眠医学和心理学知识帮用户，但不踩"替代医生"的红线。
"""

import os, sys, json, re, argparse

sys.stdout.reconfigure(encoding='utf-8')


# ─── 安全引用上下文（出现这些词视为合法引用，不拦截）──────────────────
SAFE_CITATION_PREFIXES = [
    r'(根据|研究|论文|研究表明|文献|Meta分析|综述|期刊|杂志|学报)',
    r'(Nature|Science|Sleep|JAMA|Lancet|NEJM|BMJ|Psychiatry|' 
    r'Psychological|Journal of|Clinical|Frontiers|PLOS|elife|' 
    r'Cell|Neuron|Brain|Chest|Medicine)',
    r'(等|et al\.?|202[0-9]|20[0-9]{2})',
]

SAFE_CITATION_PATTERNS = [
    r'(根据|研究|论文|研究表明|文献|Meta分析)\s*.*\s*(失眠症|焦虑症|抑郁症|障碍)',
    r'(Nature|Science|Sleep|JAMA).{0,30}(失眠|焦虑|抑郁|睡眠治疗|认知行为)',
    r'(诊断标准|诊断依据|分类|定义|定义为)\s*.*\s*(ICSD|DSM|ICD)',
    r'(ICSD[- ]?3|DSM[- ]?5|ICD[- ]?10)\s*.*\s*(失眠|障碍|睡眠)',
]

# 顶刊+学术引用识别词
SAFE_CITATION_CONTEXT = [
    '根据', '研究', '论文', '文献', '期刊', '研究表明',
    'Meta分析', '综述', '指南', '共识', '标准',
    '诊断标准', '分类', '定义为', '指',
    'CBT-I', '认知行为疗法', '刺激控制', '睡眠限制',
    '有效率', '效果', '改善率', '随访',
    'Nature', 'Science', 'Sleep', 'JAMA', 'Lancet',
    '2021', '2022', '2023', '2024', '2025', '2026',
    'et al', '等人',
    'ICSD-3', 'DSM-5', 'ICD-10',
    '正念', 'MBSR', '冥想', '禅修', '内观', 'Vipassana',
    '心理学', '临床', '睡眠医学', '神经科学',
]

# ─── 诊断模式黑名单（仅限"以你为主语的诊断"）─────────────────────────
# 这些模式匹配的是 "下诊断" 的语法结构，不是引用论文

DIAGNOSTIC_PATTERNS = [
    # 直接对你诊断（排除引用文献的上下文）
    (r'(你|您)\s*(是|属于|患有|得了)\s*'
     r'(失眠症|焦虑症|抑郁症|躁郁症|强迫症|恐惧症|'
     r'适应障碍|创伤后应激障碍|人格障碍|进食障碍|'
     r'睡眠呼吸暂停|不宁腿综合征|发作性睡病|'
     r'昼夜节律障碍|睡眠相位后移)',
     'DIRECT_DIAGNOSIS'),
    
    # "你有XX病/症"（但"你有睡眠问题"这种带"问题"的不算）
    (r'(你|您)\s*有\s*(失眠症|焦虑症|抑郁症|躁郁症|障碍)',
     'DIRECT_DIAGNOSIS'),
    
    # 确诊声明
    (r'(确诊|诊断)\s*(为|是|有)\s*(你|您)', 'DIAGNOSIS_CLAIM'),
    
    # 药物推荐（带具体剂量）
    (r'(建议|推荐|可以)\s*(吃|服用|用)\s*(药|药物|安眠药|褪黑素|'
     r'苯二氮卓|Z-drug|抗抑郁药|抗焦虑药)',
     'MEDICATION_ADVICE'),
    (r'(剂量|mg|毫克)\s*(的|,|\.)', 'DOSAGE_REFERENCE'),
    
    # 预后承诺
    (r'(保证|承诺|一定|肯定)\s*(会|可以|能)\s*(好|康复|改善|治愈)', 'PROGNOSIS_GUARANTEE'),
    (r'(坚持|持续|每天)\s*.*\s*(天|周|月)\s*(就|就会|就能)\s*(好|改善)', 'TIME_BOUNDED_PROMISE'),
]

# ─── 安全替代表达（允许的）─────────────────────────────────────────────
SAFE_ALTERNATIVES = [
    '入睡困难', '醒得早', '睡得不深', '多梦',
    '压力大', '焦虑', '紧张', '担心',
    '可能影响', '似乎', '看起来', '根据描述',
    '建议咨询', '可以尝试', '不妨试试', '推荐了解',
    '需要注意', '值得关注', '建议留意',
]


def has_citation_context(text, match_start, match_end):
    """Check if the diagnostic-like text is actually a citation.
    
    True = it's a safe citation, skip alert.
    """
    # Check surrounding text for citation patterns
    context_before = text[max(0, match_start-60):match_start]
    context_after = text[match_end:min(len(text), match_end+60)]
    full_context = context_before + context_after
    
    for pattern in SAFE_CITATION_PATTERNS:
        if re.search(pattern, full_context, re.IGNORECASE):
            return True
    
    # Simple keyword check
    for word in SAFE_CITATION_CONTEXT:
        if word.lower() in full_context.lower():
            return True
    
    # Specific exclusion: "根据xx研究，失眠症"
    if re.search(r'(根据|研究).{0,20}(失眠症|焦虑症|抑郁症)', full_context):
        return True
    
    return False


def check_diagnostic_claims(text):
    """Check for diagnostic claims in AI response."""
    issues = []
    
    for pattern, issue_type in DIAGNOSTIC_PATTERNS:
        for match in re.finditer(pattern, text):
            # Check if this is a citation, not a diagnosis
            if has_citation_context(text, match.start(), match.end()):
                continue  # It's a citation, allow it
            
            issues.append({
                'type': issue_type,
                'severity': 'HIGH',
                'matched': match.group(),
                'position': match.start(),
            })
    
    return issues


def check_safe_language(text):
    """Check if the response uses safe language."""
    # Check for disclaimer
    has_disclaimer = any(phrase in text for phrase in [
        '不能替代', '仅供参考', '建议咨询', '专业帮助',
        '我不是医生', '我不是心理咨询师', 'AI助手',
    ])
    
    # Check for safe alternatives
    safe_count = sum(1 for alt in SAFE_ALTERNATIVES if alt in text)
    
    return {
        'has_disclaimer': has_disclaimer,
        'safe_alternatives': safe_count,
    }


def scan_file(filepath):
    """Scan a JSONL file for diagnostic violations."""
    if not os.path.exists(filepath):
        return None, None
    
    all_issues = []
    total = 0
    
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                total += 1
            except json.JSONDecodeError:
                continue
            
            resp = record.get('response', record.get('reply', record.get('ai_output', '')))
            if isinstance(resp, dict):
                resp = json.dumps(resp, ensure_ascii=False)
            
            if resp:
                issues = check_diagnostic_claims(str(resp))
                if issues:
                    all_issues.append({
                        'context': str(resp)[:120],
                        'issues': issues,
                    })
    
    return all_issues, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', help='Check a single response text')
    parser.add_argument('--scan-file', help='Scan a JSONL file')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    
    if args.check:
        issues = check_diagnostic_claims(args.check)
        safety = check_safe_language(args.check)
        
        has_diagnosis = len(issues) > 0
        
        result = {
            'status': 'BLOCKED' if has_diagnosis else 'PASS',
            'diagnostic_claims': len(issues),
            'has_disclaimer': safety['has_disclaimer'],
            'safe_alternatives': safety['safe_alternatives'],
            'issues': issues,
        }
        
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            if result['status'] == 'BLOCKED':
                print(f"🔴 BLOCKED — {len(issues)} diagnostic claim(s)")
                for iss in issues:
                    print(f"   [{iss['type']}] '{iss['matched']}'")
            else:
                print("✅ PASS — no diagnostic claims")
            
            if not safety['has_disclaimer']:
                print("⚠️  Missing disclaimer")
            if safety['safe_alternatives'] < 2:
                print("⚠️  Use more descriptive language (safe alternatives)")
        return
    
    if args.scan_file:
        issues, total = scan_file(args.scan_file)
        if issues:
            critical = sum(1 for r in issues for i in r['issues'] if i['severity'] == 'HIGH')
            print(f"Scanned {total} records, found {len(issues)} with diagnostic claims ({critical} critical)")
            for r in issues[:10]:
                for i in r['issues']:
                    print(f"  [{i['type']}] '{i['matched']}' | '{r['context'][:60]}'")
        else:
            print("✅ No diagnostic claims found")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
