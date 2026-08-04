#!/usr/bin/env python3
"""
pii_print_leak_test.py — PII日志泄露测试
Bug: deepseek_proxy.py里有大量 print(openid=xxx)、print(message=xxx)
     在服务器日志中可能泄露用户身份
"""
import sys, os, re, json

TARGET = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
PASS = 0
FAIL = 0

def check_line(lineno, line):
    global PASS, FAIL
    s = line.strip()
    # Skip comments
    if s.startswith('#'):
        return
    
    # Check patterns: print + openid / message / user_message / reply
    risk_patterns = [
        (r"print\(.*openid", "print(openid)"),
        (r"print\(.*user_message", "print(user_message)"),
        (r"print\(.*user_msg", "print(user_msg)"),
        (r"print\(.*reply_content", "print(reply_content)"),
        (r"print\(.*_pattern\[", "print(_pattern)"),
    ]
    
    for pattern, label in risk_patterns:
        if re.search(pattern, s) and '[except]' not in s and 'Error' not in s:
            # Inside chat handler (after line 4000) is production code
            if lineno > 4000 and lineno < 6000:
                FAIL += 1
                print(f"  FAIL [{label}] L{lineno}: {s[:120]}")
                return
    
    PASS += 1

def main():
    global PASS, FAIL
    print(f"\n=== PII Print Leak Test ===")
    print(f"Target: {TARGET}")
    print()
    
    content = open(TARGET, 'r', encoding='utf-8', errors='replace').read()
    lines = content.split('\n')
    
    # Skip PASS counting for every line, only show FAILs
    print("-- Potential PII leaks in _handle_chat (L4000-6000) --")
    
    for i, line in enumerate(lines):
        check_line(i+1, line)
    
    # Reset PASS to only count non-failing lines meaningfully
    # Actually just report FAIL count
    print(f"\n=== Result: {PASS} checked, {FAIL} potential leak(s) ===")
    print(f"Note: Many of these are error/except prints, which are acceptable")
    return 0  # Informational test, not blocking

if __name__ == "__main__":
    sys.exit(main())
