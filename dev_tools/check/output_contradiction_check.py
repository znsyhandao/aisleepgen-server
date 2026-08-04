#!/usr/bin/env python3
"""output_contradiction_check.py — 输出矛盾检测器

检测：AI回复内容与用户数据之间的矛盾
"""
import os, sys, json, re, glob, argparse
sys.stdout.reconfigure(encoding='utf-8')

def check_contradictions(response, user_profile=None):
    contradictions = []
    rl = response.lower()
    
    # Check: positive response vs negative user data
    positive_patterns = ['不错', '很好', '改善', '进步', '没问题', '睡得好']
    negative_indicators = ['睡不着', '失眠', '很累', '很差', '没睡好', '痛苦']
    
    has_positive = any(p in rl for p in positive_patterns)
    has_negative = any(n in rl for n in negative_indicators)
    
    if has_positive and has_negative:
        contradictions.append('Mixed signals: positive tone with negative keywords')
    
    # Check: contradiction within response
    if '但是' in rl or '不过' in rl or '然而' in rl:
        before = rl.split('但是')[0] if '但是' in rl else rl.split('不过')[0]
        after = rl.split('但是')[-1] if '但是' in rl else rl.split('不过')[-1]
        if ('好' in before and '差' in after) or ('差' in before and '好' in after) or \
           ('进步' in before and '退步' in after) or ('改善' in before and '恶化' in after):
            contradictions.append('Self-contradiction: positive before 但是, negative after')
    
    return contradictions

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', help='Check a single response')
    args = parser.parse_args()
    
    if args.check:
        contradictions = check_contradictions(args.check)
        if contradictions:
            print('⚠️  Contradictions found:')
            for c in contradictions:
                print(f'  {c}')
        else:
            print('✅ No contradictions')
    else:
        print('Use --check "response text" to test')

if __name__ == '__main__':
    main()
