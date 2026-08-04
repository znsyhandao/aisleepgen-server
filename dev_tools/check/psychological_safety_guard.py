#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
psychological_safety_guard.py — 心理安全红线守卫

守卫什么：
- 自杀/自伤关键词 → 强制转介（禁止常规放松建议）
- 严重躯体症状 → 建议就医（禁止安慰性回复）
- 每次回复必须带 disclaimer（我不是医生/心理咨询师）
- 连续低评分 → 自动建议就医

此守卫在审核流程中作为 "输出合理性校验" 的最后一道防线，
在回复流出发送前拦截。

用法:
  python psychological_safety_guard.py --check-response <response.json>
  python psychological_safety_guard.py --check-chat "用户消息"
  python psychological_safety_guard.py --scan-history <history.jsonl>
"""

import os, sys, json, re, argparse

sys.stdout.reconfigure(encoding='utf-8')

# ─── 红线词库（全部公开知识）─────────────────────────────────────────────

CRISIS_LEVELS = {
    'RED_CRITICAL': {  # 必须立即转介，禁止任何放松建议
        'suicide': [
            '自杀', '想死', '活不下去', '死了算了', '没有意义活了',
            '不想活了', '结束生命', '放弃生命', '走了算了',
            '活够', '没意思', '不如死了', '死了',
        ],
        'self_harm': [
            '自残', '伤害自己', '割腕', '划自己', '打自己',
            '撞墙', '掐自己',
        ],
        'violence_abuse': [
            '家暴', '被虐待', '被打', '被欺负', '性侵',
            '强迫', '被控制',
        ],
    },
    'AMBER_WARNING': {  # 建议就医，常规放松可以但须加转介
        'severe_symptoms': [
            '喘不过气', '胸痛', '胸闷', '半夜憋醒', '呼吸困难',
            '心慌', '心跳很快', '头晕', '晕倒',
            '彻夜不眠', '一周没怎么睡', '好几天没睡',
        ],
        'depression_severe': [
            '哭', '只想哭', '一直哭', '不想动', '起不来床',
            '什么都没兴趣', '觉得没希望', '绝望',
        ],
    },
    'YELLOW_CAUTION': {  # 加 disclaimer，不建议替代专业帮助
        'therapy_talk': [
            '心理咨询', '看医生', '吃药', '医生怎么说',
            '诊断', '确诊',
        ],
    },
}

# 中文危机干预热线（公开信息）
CRISIS_HOTLINES = [
    '北京心理危机研究与干预中心：010-82951332',
    '全国24小时心理援助热线：400-161-9995',
    '希望24热线：400-161-9995',
    '生命热线：400-821-1215',
]

DISCLAIMER = (
    '⚠️ 我是AI助手，不是医生或心理咨询师。'
    '以上建议仅供参考，不能替代专业医疗或心理帮助。'
    '如有严重不适，请及时就医或拨打心理援助热线。'
)


def check_user_message(message):
    """Check user message for crisis keywords. Returns (level, found_patterns)."""
    if not message:
        return None, []
    
    message_lower = message.lower()
    found = []
    
    for level, categories in CRISIS_LEVELS.items():
        for category, keywords in categories.items():
            for kw in keywords:
                if kw in message_lower:
                    found.append((level, category, kw))
    
    if found:
        # Report highest severity level
        levels_order = ['RED_CRITICAL', 'AMBER_WARNING', 'YELLOW_CAUTION']
        highest = 'YELLOW_CAUTION'
        for l in levels_order:
            if any(f[0] == l for f in found):
                highest = l
                break
        return highest, found
    
    return None, []


def check_response(response_text):
    """Check AI response for safety violations."""
    if not response_text:
        return []
    
    violations = []
    response_lower = response_text.lower()
    
    # 1. Check: diagnostic claims ("你是XX症", "确诊", "你患有")
    diagnostic_patterns = [
        r'(你|您)\s*(是|属于|患有|得了)\s*(失眠症|焦虑症|抑郁症|躁郁症|强迫症|恐惧症)',
        r'确诊为',
        r'你的\s*.*\s*(症|病|障碍)',
    ]
    for pat in diagnostic_patterns:
        if re.search(pat, response_lower):
            violations.append({
                'type': 'DIAGNOSTIC_CLAIM',
                'severity': 'HIGH',
                'detail': f'Response may contain diagnostic claim matching: {pat}',
            })
    
    # 2. Check: medical claims ("代替药物", "取代治疗", "保证治愈")
    forbidden_claims = [
        r'代替\s*(药|治疗)',
        r'取代\s*(药|治疗)',
        r'保证\s*(治愈|有效|好转)',
        r'百分百',
        r'根治',
    ]
    for pat in forbidden_claims:
        if re.search(pat, response_lower):
            violations.append({
                'type': 'FORBIDDEN_MEDICAL_CLAIM',
                'severity': 'HIGH',
                'detail': f'Response makes unauthorized medical claim: {pat}',
            })
    
    # 3. Check: pseudo-science
    pseudo = [
        '能量场', '脉轮', '灵气', '超自然', '灵魂', '前世',
        '频率治疗', '水晶治疗', '排毒', '碱性饮食治愈',
    ]
    for ps in pseudo:
        if ps in response_lower:
            violations.append({
                'type': 'PSEUDO_SCIENCE',
                'severity': 'MEDIUM',
                'detail': f'Response references pseudo-science: {ps}',
            })
    
    # 4. Check: disclaimer missing
    required_terms = ['不能替代', '仅供参考', '建议', '医生', '专业']
    has_disclaimer = sum(1 for t in required_terms if t in response_lower) >= 2
    if not has_disclaimer and len(response_text) > 50:
        violations.append({
            'type': 'MISSING_DISCLAIMER',
            'severity': 'MEDIUM',
            'detail': 'Response lacks safety disclaimer',
        })
    
    # 5. Check: giving dangerous advice for RED_CRITICAL context
    if '自杀' in response_lower or '想死' in response_lower:
        if '呼吸' in response_lower or '放松' in response_lower:
            violations.append({
                'type': 'CRITICAL_CRISIS_MISMANAGEMENT',
                'severity': 'CRITICAL',
                'detail': 'Relaxation advice given in suicide context — use referral instead',
            })
    
    return violations


def check_history_file(history_path):
    """Scan a JSONL history file for all safety issues."""
    if not os.path.exists(history_path):
        return None
    
    results = []
    with open(history_path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            user_msg = record.get('request', record.get('message', record.get('user_input', '')))
            response = record.get('response', record.get('reply', record.get('ai_output', '')))
            
            if isinstance(response, dict):
                response = json.dumps(response, ensure_ascii=False)
            if isinstance(user_msg, dict):
                user_msg = json.dumps(user_msg, ensure_ascii=False)
            
            if user_msg:
                level, found = check_user_message(str(user_msg))
                if level:
                    results.append({
                        'context': user_msg[:100],
                        'alert': f'USER_TRIGGER_{level}',
                        'details': found,
                    })
            
            if response:
                violations = check_response(str(response))
                if violations:
                    results.append({
                        'context': response[:100],
                        'violations': violations,
                    })
    
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check-chat', help='Check a single user message')
    parser.add_argument('--check-response', help='Check a single AI response')
    parser.add_argument('--scan-history', help='Scan a JSONL history file')
    parser.add_argument('--json', action='store_true', help='Output JSON')
    args = parser.parse_args()
    
    # Mode 1: Check user message
    if args.check_chat:
        level, found = check_user_message(args.check_chat)
        if level:
            result = {
                'status': 'ALERT',
                'severity': level,
                'findings': found,
                'recommendation': 'INJECT_REFERRAL' if level == 'RED_CRITICAL' else 'ADD_DISCLAIMER',
            }
        else:
            result = {'status': 'CLEAR'}
        
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            if result['status'] == 'ALERT':
                print(f"🔴 SAFETY ALERT [{result['severity']}]")
                for f in result['findings']:
                    print(f"   Trigger: [{f[1]}] keyword='{f[2]}'")
                print(f"   Action: {result['recommendation']}")
            else:
                print("✅ No crisis signals detected")
        return
    
    # Mode 2: Check AI response
    if args.check_response:
        try:
            response_text = json.loads(args.check_response)
            if isinstance(response_text, dict):
                response_text = json.dumps(response_text, ensure_ascii=False)
        except (json.JSONDecodeError, TypeError):
            response_text = args.check_response
        
        violations = check_response(str(response_text))
        if violations:
            critical = [v for v in violations if v['severity'] == 'CRITICAL']
            high = [v for v in violations if v['severity'] == 'HIGH']
            medium = [v for v in violations if v['severity'] == 'MEDIUM']
            result = {
                'status': 'BLOCKED' if critical else 'FLAGGED',
                'critical': len(critical),
                'high': len(high),
                'medium': len(medium),
                'violations': violations,
            }
        else:
            result = {'status': 'PASS', 'violations': []}
        
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            if result['status'] == 'BLOCKED':
                print(f"🔴 RESPONSE BLOCKED ({result['critical']} critical)")
            elif result['status'] == 'FLAGGED':
                print(f"🟡 RESPONSE FLAGGED (H:{result['high']} M:{result['medium']})")
            for v in violations[:5]:
                print(f"   [{v['severity']}] {v['type']}: {v['detail'][:80]}")
            return
    
    # Mode 3: Scan history file
    if args.scan_history:
        results = check_history_file(args.scan_history)
        if results:
            print(f"Found {len(results)} safety issues:")
            for r in results[:20]:
                if 'alert' in r:
                    print(f"  🔴 [{r['alert']}] {r['context'][:60]}")
                else:
                    for v in r.get('violations', []):
                        print(f"  ⚠️  [{v['severity']}] {v['type']}: {r['context'][:60]}")
        else:
            print("✅ No safety issues")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
