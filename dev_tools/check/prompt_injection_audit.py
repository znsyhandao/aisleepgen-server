#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompt_injection_audit.py — Prompt 注入/泄露/污染审计

查什么：
- prompt 模板中是否泄露了 API key 或密码
- prompt 是否包含"忽略之前指令"等注入风险
- prompt 变量替换是否有未转义的用户输入（可执行代码注入）
- prompt 中是否有硬编码的系统指令被用户消息覆盖的风险

用法:
  python prompt_injection_audit.py [--dir D:\AISleepGen_Optimized]
"""

import os, sys, re, ast, argparse
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

# 注入风险模式
INJECTION_RISKS = {
    'API_KEY_IN_PROMPT': [
        r'(api[_-]?key|apikey|secret|token|password)\s*[:=]\s*["\']?[A-Za-z0-9_-]{20,}',
    ],
    'SYSTEM_PROMPT_LEAK': [
        r'(system|instructions?|prompt)\s*(:|is|was)',
        r'(你是一个|你是|你的角色是)',
        r'(ignore|忽略|不要管|忘记)\s*(above|之前|所有|以前)',
    ],
    'UNSAFE_FORMAT_STRING': [
        r'f["\']?\{[^}]+\}["\']?\s*\.\s*format',
        r'%s\s*%',
    ],
    'SQL_IN_PROMPT': [
        r'SELECT\s+.+\s+FROM',
        r'INSERT\s+INTO',
        r'DROP\s+TABLE',
    ],
    'FILE_PATH_LEAK': [
        r'(/home/|/root/|C:\\|D:\\)',
    ],
}

# 敏感信息模式
SENSITIVE_PATTERNS = [
    r'sk-[A-Za-z0-9]{32,}',
    r'[A-Za-z0-9_-]{32,}\.json',
    r'password\s*=\s*["\']\S{6,}',
    r'secret\s*=\s*["\']\S{6,}',
]


def find_prompt_templates(filepath):
    """Find prompt template definitions."""
    prompts = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        lines = f.readlines()
    
    in_prompt = False
    current = []
    start_line = 0
    
    for i, line in enumerate(lines):
        # Detect prompt start
        if any(kw in line for kw in [
            'PROMPT', 'prompt', 'SYSTEM_MSG', 'system_message',
            'template', 'TEMPLATE', 'instructions',
        ]) and any(sym in line for sym in ['"""', "'''", '="', '= "', "= '"]):
            in_prompt = True
            start_line = i + 1
            current = [line]
            continue
        
        if in_prompt:
            current.append(line)
            if '"""' in line or "'''" in line:
                prompts.append({
                    'start': start_line,
                    'end': i + 1,
                    'text': ''.join(current),
                    'file': filepath,
                })
                in_prompt = False
                current = []
    
    # Also find f-string prompts
    for i, line in enumerate(lines):
        if any(kw in line.lower() for kw in ['system_prompt', 'user_prompt', 'ai_prompt']):
            prompts.append({
                'start': i + 1,
                'text': line.strip()[:200],
                'file': filepath,
                'type': 'inline',
            })
    
    return prompts


def check_prompt_safety(prompt_text):
    """Check a prompt template for safety issues."""
    issues = []
    
    for risk_type, patterns in INJECTION_RISKS.items():
        for pat in patterns:
            if re.search(pat, prompt_text, re.IGNORECASE):
                match = re.search(pat, prompt_text, re.IGNORECASE)
                issues.append({
                    'type': risk_type,
                    'severity': 'HIGH' if risk_type in ('API_KEY_IN_PROMPT', 'SYSTEM_PROMPT_LEAK') else 'MEDIUM',
                    'match': match.group()[:80] if match else pat[:80],
                })
    
    # Check for sensitive data
    for pat in SENSITIVE_PATTERNS:
        if re.search(pat, prompt_text):
            issues.append({
                'type': 'SENSITIVE_DATA_LEAK',
                'severity': 'CRITICAL',
                'match': re.search(pat, prompt_text).group()[:60],
            })
    
    # Check: user message could override system instruction
    if '{user_message}' in prompt_text or '{user_input}' in prompt_text:
        # Check if there's a separator guard
        has_separator = any(sep in prompt_text for sep in [
            '---', '===', '###', '====', '---',
            '[SEPARATOR]', '<SEPARATOR>',
        ])
        if not has_separator:
            issues.append({
                'type': 'NO_USER_INPUT_SEPARATOR',
                'severity': 'MEDIUM',
                'match': 'User input may bleed into system prompt without separator',
            })
    
    return issues


def check_variable_injection(filepath):
    """Check for unsafe variable substitution in prompts."""
    issues = []
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    # Check f-string with user data
    fstring_patterns = re.findall(r'f["\'][^"\']*\{[^}]+\}[^"\']*["\']', content)
    for fs in fstring_patterns[:20]:
        # Check what variables are used
        vars_used = re.findall(r'\{([^}]+)\}', fs)
        for var in vars_used:
            var = var.strip()
            # If variable comes from user input without sanitization
            if any(kw in var.lower() for kw in ['user', 'message', 'input', 'query', 'text']):
                issues.append({
                    'type': 'UNSANITIZED_USER_INPUT_IN_PROMPT',
                    'severity': 'MEDIUM',
                    'match': f"Variable '{var}' may contain unsanitized user input in f-string",
                })
    
    # Check exec/eval calls (severe injection risk)
    if 'exec(' in content or 'eval(' in content:
        for match in re.finditer(r'(exec|eval)\s*\(', content):
            ctx_start = max(0, match.start() - 60)
            ctx_end = min(len(content), match.end() + 60)
            issues.append({
                'type': 'CODE_EXECUTION_IN_PROMPT',
                'severity': 'CRITICAL',
                'match': f"exec/eval call at position {match.start()}: {content[ctx_start:ctx_end]}",
            })
    
    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', default=os.getcwd())
    parser.add_argument('--files', nargs='*',
                        default=['deepseek_proxy.py', 'audit_logger.py',
                                 'world_model_coordinator.py', 'wx_login.py'])
    args = parser.parse_args()
    
    workdir = args.dir
    print("=" * 60)
    print("  PROMPT INJECTION & LEAK AUDIT")
    print("=" * 60)
    
    all_issues = []
    
    for fname in args.files:
        fp = os.path.join(workdir, fname)
        if not os.path.exists(fp):
            continue
        
        print(f"\n  {fname}")
        
        # Find prompt templates
        prompts = find_prompt_templates(fp)
        if prompts:
            print(f"  Prompt templates found: {len(prompts)}")
            for p in prompts[:10]:
                if p.get('type') == 'inline':
                    print(f"    L{p['start']}: {p['text'][:100]}")
                else:
                    print(f"    L{p['start']}-L{p.get('end', '?'):<5}: {p['text'][:80]}...")
                # Check each prompt
                if 'text' in p:
                    issues = check_prompt_safety(p['text'])
                    if issues:
                        all_issues.extend(issues)
                        for iss in issues:
                            print(f"      [{iss['severity']}] {iss['type']}: {iss['match'][:80]}")
        else:
            print(f"  No prompt templates found")
        
        # Variable injection check
        var_issues = check_variable_injection(fp)
        if var_issues:
            all_issues.extend(var_issues)
            for iss in var_issues:
                print(f"  [{iss['severity']}] {iss['type']}: {iss['match'][:100]}")
    
    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    critical = [i for i in all_issues if i['severity'] == 'CRITICAL']
    high = [i for i in all_issues if i['severity'] == 'HIGH']
    medium = [i for i in all_issues if i['severity'] == 'MEDIUM']
    
    print(f"  Critical: {len(critical)}")
    print(f"  High:     {len(high)}")
    print(f"  Medium:   {len(medium)}")
    
    for iss in critical:
        print(f"\n  🔴 [{iss['type']}]")
        print(f"     {iss['match'][:120]}")
    
    print()


if __name__ == '__main__':
    main()
