#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
response_template_detector.py — 回复模板化检测器

查什么：
- AI 回复是否过于模板化（连续多条回复相似度 > 0.85）
- 个性化空洞：不同用户的回复是否几乎一样
- "假关心"检测：说了很多但没有任何具体信息

用法:
  python response_template_detector.py --scan-history <audit_logs_dir>
  python response_template_detector.py --check-response "要检查的回复"
"""

import os, sys, json, re, argparse, glob
from difflib import SequenceMatcher
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# 低信息密度模式（看起来很亲切但实际没内容）
LOW_INFO_PATTERNS = [
    r'(我理解|我明白|我能理解|我知道|你说的对|是的)',
    r'(加油|坚持|别放弃|你可以的|会好的)',
    r'(试试|建议|推荐|可以尝试)\s*(深呼吸|放松|冥想)',
]

# 高信息密度信号（好的回复包含这些）
HIGH_INFO_SIGNALS = [
    '根据你的', '你的记录显示', '你的评分', '你的睡眠',
    '你提到', '从你的描述', '你的数据', '你的症状',
    '入睡', '深度睡眠', 'REM', '醒得早',
    '压力', '心率', '呼吸', '放松训练',
]


def extract_responses_from_logs(log_dir, limit=500):
    """Extract AI response texts from audit logs."""
    responses = []
    files = glob.glob(os.path.join(log_dir, '**', '*.jsonl'), recursive=True)
    
    for fp in sorted(files)[-50:]:  # Last 50 files
        with open(fp, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                resp = record.get('response', record.get('reply', ''))
                if isinstance(resp, dict):
                    resp = json.dumps(resp, ensure_ascii=False)
                
                r_text = str(resp)
                if len(r_text) > 30:
                    responses.append({
                        'text': r_text,
                        'file': fp,
                        'openid': record.get('openid', record.get('user_id', 'unknown')),
                    })
                
                if len(responses) >= limit:
                    break
        if len(responses) >= limit:
            break
    
    return responses


def check_response_variety(responses, threshold=0.85):
    """Check if responses are too similar to each other."""
    if len(responses) < 2:
        return []
    
    template_groups = defaultdict(list)
    
    # Compare each response with each other (first 50 only for perf)
    sample = responses[:100]
    for i, a in enumerate(sample):
        for j, b in enumerate(sample):
            if i >= j:
                continue
            # Use first 200 chars for comparison (ignoring boilerplate)
            a_text = a['text'][:200]
            b_text = b['text'][:200]
            ratio = SequenceMatcher(None, a_text, b_text).ratio()
            
            if ratio >= threshold:
                # Group similar responses
                key = f"template_{i}_{j}"
                if i not in template_groups:
                    template_groups[i] = []
                template_groups[i].append((j, ratio))
    
    # Find large template groups (more than 5 responses that are all similar)
    large_groups = []
    checked = set()
    for i, similar_list in template_groups.items():
        if i in checked:
            continue
        group = [i] + [s[0] for s in similar_list]
        if len(group) >= 5:
            large_groups.append({
                'size': len(group),
                'indices': group[:10],
                'avg_similarity': sum(s[1] for s in similar_list) / len(similar_list),
                'sample': responses[i]['text'][:150],
            })
            checked.update(group)
    
    return large_groups


def check_info_density(response_text):
    """Check if response has sufficient information density."""
    if not response_text:
        return {'score': 0, 'findings': ['EMPTY_RESPONSE']}
    
    findings = []
    
    # Count low-info patterns
    low_info_count = 0
    for pat in LOW_INFO_PATTERNS:
        low_info_count += len(re.findall(pat, response_text))
    
    # Count high-info signals
    high_info_count = sum(1 for s in HIGH_INFO_SIGNALS if s in response_text)
    
    # Length check
    word_count = len(response_text)
    
    # Ratio
    ratio = low_info_count / max(high_info_count, 1)
    
    density_score = min(10, high_info_count * 2)
    
    if ratio > 5 and word_count > 50:
        findings.append(f'LOW_INFO_DENSITY: {low_info_count} generic phrases vs {high_info_count} specific signals')
    
    if high_info_count == 0 and word_count > 30:
        findings.append('NO_SPECIFIC_INFO: response contains no user-specific information')
    
    if word_count < 20:
        findings.append('TOO_SHORT: response is too brief')
    
    return {
        'score': density_score,
        'low_info_count': low_info_count,
        'high_info_count': high_info_count,
        'word_count': word_count,
        'findings': findings,
    }


def check_individualization(responses):
    """Check if different users get different responses."""
    by_user = defaultdict(list)
    for r in responses:
        by_user[r['openid']].append(r)
    
    multi_session_users = {uid: reps for uid, reps in by_user.items() if len(reps) >= 2}
    
    findings = []
    for uid, reps in multi_session_users.items():
        if len(reps) >= 2:
            # Compare first and last response
            first = reps[0]['text'][:200]
            last = reps[-1]['text'][:200]
            ratio = SequenceMatcher(None, first, last).ratio()
            if ratio > 0.9:
                findings.append({
                    'user': uid,
                    'responses': len(reps),
                    'first_last_similarity': round(ratio, 3),
                    'detail': 'User gets almost identical responses across sessions',
                })
    
    return findings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scan-history', help='Audit logs directory')
    parser.add_argument('--check-response', help='Check a single response')
    parser.add_argument('--check-file', help='Check a JSONL file')
    parser.add_argument('--threshold', type=float, default=0.85)
    args = parser.parse_args()
    
    # Mode 1: Single response check
    if args.check_response:
        result = check_info_density(args.check_response)
        print(f"Info density score: {result['score']}/10")
        if result['findings']:
            for f in result['findings']:
                print(f"  ⚠️  {f}")
        else:
            print("  ✅ Adequate information density")
        return
    
    # Mode 2: Scan audit logs
    if args.scan_history:
        if not os.path.isdir(args.scan_history):
            print(f"Directory not found: {args.scan_history}")
            return
        
        print(f"Scanning audit logs in {args.scan_history}")
        responses = extract_responses_from_logs(args.scan_history)
        print(f"Extracted {len(responses)} responses\n")
        
        if len(responses) < 3:
            print("Not enough responses to analyze")
            return
        
        # Template detection
        print("[1] Template detection (response similarity)")
        template_groups = check_response_variety(responses, args.threshold)
        if template_groups:
            print(f"  ⚠️  Found {len(template_groups)} template group(s) >= 5 similar responses:")
            for g in template_groups:
                print(f"  Group size={g['size']}, avg_similarity={g['avg_similarity']:.1%}")
                print(f"    Sample: {g['sample'][:80]}...")
        else:
            print("  ✅ No excessive template groups found")
        
        # Info density
        print("\n[2] Information density analysis")
        scores = [check_info_density(r['text']) for r in responses]
        low_density = [s for s in scores if s['score'] < 3]
        if low_density:
            print(f"  ⚠️  {len(low_density)}/{len(scores)} responses have low info density")
            for s in low_density[:5]:
                print(f"    Score={s['score']}: low={s['low_info_count']} high={s['high_info_count']}")
        else:
            print(f"  ✅ All responses have adequate information density")
        
        # Individualization
        print("\n[3] Individualization check")
        ind_findings = check_individualization(responses)
        if ind_findings:
            print(f"  ⚠️  {len(ind_findings)} user(s) get identical responses across sessions:")
            for f in ind_findings[:5]:
                print(f"    User {f['user']}: similarity={f['first_last_similarity']:.1%} "
                      f"across {f['responses']} responses")
        else:
            print("  ✅ Responses vary across user sessions")
        
        return
    
    # Mode 3: Check single file
    if args.check_file:
        if not os.path.exists(args.check_file):
            print(f"File not found: {args.check_file}")
            return
        
        responses = extract_responses_from_logs(os.path.dirname(args.check_file))
        resp_for_file = [r for r in responses if r['file'] == args.check_file]
        print(f"Found {len(resp_for_file)} responses in file")
        
        for r in resp_for_file[:10]:
            result = check_info_density(r['text'])
            status = '✅' if result['score'] >= 5 else '⚠️'
            print(f"  {status} Score={result['score']}/10: {r['text'][:80]}...")
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
