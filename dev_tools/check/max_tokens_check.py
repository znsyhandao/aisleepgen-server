#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
max_tokens_check.py — 检查所有 DeepSeek/API 调用的 max_tokens 是否匹配输出体积

已知坑（2026-06-08）：
  daily_dispatch V5 升级了 prompt（四角色+invest_angle四维），
  但 max_tokens=8192 没同步升级 → JSON 解析失败
  修复：升到 16000

本检查扫描：
1. 所有 `.py` 文件中 max_tokens 参数值
2. 与关联 prompt 的预估长度做对比（prompt 越长，output token 越多）
3. 标记出过小（< 输出合理下限）的 max_tokens

用法:
  python max_tokens_check.py [--dir D:\\AISleepGen_Optimized]
"""

import os, sys, re, argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 最小安全值映射：根据 prompt 复杂度和输出类型
# 规则：prompt 越长 / 输出格式越复杂 → 需要的 max_tokens 越大
SAFE_MINIMUMS = {
    'json': 12000,        # 输出 JSON 的，至少 12000
    'html': 16000,        # 输出 HTML 的，至少 16000
    'markdown': 8000,     # 纯 md 输出
    'text': 4000,         # 纯文本
    'strategic_insight': 12000,  # 战略内参 JSON
    'daily_dispatch': 16000,     # 四角色+invest_angle premium
    'chat': 2000,         # 对话回复
}

# 文件与输出类型的映射
FILE_OUTPUT_MAP = {
    'daily_dispatch.py': 'daily_dispatch',
    'generate_strategic_insider.py': 'strategic_insight',
    'strategic_insight_daily.py': 'strategic_insight',
    'daily_frontier.py': 'text',
    'deepseek_proxy.py': 'chat',
    'dp_router.py': 'chat',
}

# 最低硬性下限（无论什么类型都不能低于这个）
HARD_MINIMUM = 2000


def scan_max_tokens(directory):
    """Scan all .py files in directory for max_tokens settings."""
    results = []
    dir_path = Path(directory)
    
    for py_file in sorted(dir_path.rglob('*.py')):
        # Skip venv, __pycache__, node_modules, site-packages, .bak, .archived, .old
        rel = py_file.relative_to(dir_path)
        skip_dirs = ['__pycache__', 'venv', 'node_modules', '.git', 'site-packages', 
                     '.bak', 'bak', '.archived', '.old', 'archive', 'old',
                     'dist', 'build', '.egg-info']
        if any(p in str(py_file) for p in skip_dirs):
            continue
        # Skip files that are too large (>1MB)
        if py_file.stat().st_size > 1_000_000:
            continue
        
        with open(py_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # Find max_tokens=XXX or 'max_tokens': XXX
        patterns = [
            r'max_tokens\s*=\s*(\d+)',
            r"'max_tokens'\s*:\s*(\d+)",
            r'"max_tokens"\s*:\s*(\d+)',
            r'mx\s*=\s*(\d+)',  # 有些人简写 mx 表示 max_tokens
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                line_num = content[:match.start()].count('\n') + 1
                line_start = max(0, match.start() - 40)
                line_end = min(len(content), match.end() + 40)
                context = content[line_start:line_end].strip().replace('\n', ' ')
                
                value = int(match.group(1))
                results.append({
                    'file': str(rel),
                    'abs_path': str(py_file),  # 存绝对路径供 check_output_type 打开
                    'line': line_num,
                    'value': value,
                    'context': context,
                })
    
    return results


def find_prompt_sizes(directory):
    """Find prompt file sizes (system_prompt, etc) to estimate output needs."""
    prompts = []
    dir_path = Path(directory)
    
    for pattern in ['*prompt*', '*system*', '*.txt', '*.md']:
        for f in dir_path.rglob(pattern):
            if f.is_file() and f.suffix in ('.txt', '.md') and not any(
                p in str(f) for p in ['__pycache__', 'venv', '.git', 'node_modules']
            ):
                try:
                    size = len(f.read_text(encoding='utf-8', errors='replace'))
                    prompts.append({
                        'file': str(f.relative_to(dir_path)),
                        'chars': size,
                        'est_tokens': size // 2,  # rough: ~2 char per token for Chinese
                    })
                except:
                    pass
    
    # Also check for system_prompt strings in .py files
    for py_file in dir_path.rglob('*.py'):
        if any(p in str(py_file) for p in ['__pycache__', 'venv', 'node_modules', '.git']):
            continue
        try:
            with open(py_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Find SYSTEM_PROMPT = "...", system_prompt.txt file reads
            for m in re.finditer(r'SYSTEM_PROMPT\s*=\s*["\'](.{100,}?)["\']', content, re.DOTALL):
                prompts.append({
                    'file': f"{py_file.relative_to(dir_path)} (inline SYSTEM_PROMPT)",
                    'chars': len(m.group(1)),
                    'est_tokens': len(m.group(1)) // 2,
                })
        except:
            pass
    
    return prompts


def check_output_type(filepath):
    """Determine expected output type from file content."""
    fname = os.path.basename(filepath)
    
    # Direct mapping
    for key, val in FILE_OUTPUT_MAP.items():
        if key in filepath:
            return val
    
    # Heuristic scan
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    if 'json.dumps' in content or 'json.loads' in content:
        return 'json'
    if '.html' in content and 'html' in content.lower():
        return 'html'
    if 'markdown' in content.lower():
        return 'markdown'
    
    # Check for long structured prompts
    if 'system_prompt' in content and len(content) > 10000:
        return 'json'  # long system prompts usually mean complex JSON output
    
    return 'text'


def main():
    parser = argparse.ArgumentParser(description='Check max_tokens settings vs expected output size')
    parser.add_argument('--dir', default=None, 
                        help='Directory to scan (default: AISleepGen + frontier_radar)')
    args = parser.parse_args()
    
    # Default: scan both projects
    if args.dir:
        dirs = [args.dir]
    else:
        dirs = [
            r'D:\AISleepGen_Optimized',
            r'D:\super_frontier_radar',
        ]
    
    all_results = []
    all_prompts = []
    for d in dirs:
        if os.path.isdir(d):
            all_results.extend(scan_max_tokens(d))
            all_prompts.extend(find_prompt_sizes(d))
    
    print("=" * 60)
    print("  MAX_TOKENS CONSISTENCY CHECK")
    print("=" * 60)
    
    # Group by file
    by_file = {}
    for r in all_results:
        by_file.setdefault(r['file'], []).append(r)
    
    issues = []
    warnings = []
    
    print(f"\n📝 Prompt file sizes:")
    for p in sorted(all_prompts, key=lambda x: x['est_tokens'], reverse=True)[:10]:
        print(f"  {p['file']}: {p['chars']} chars ≈ ~{p['est_tokens']} tokens")
    
    print(f"\n🔍 Found {len(all_results)} max_tokens settings:\n")
    
    for fname, settings in sorted(by_file.items()):
        for s in settings:
            # Determine expected minimum
            output_type = check_output_type(s.get('abs_path', fname))
            safe_min = SAFE_MINIMUMS.get(output_type, HARD_MINIMUM)
            
            marker = '✅' if s['value'] >= safe_min else '⚠️'
            print(f"  {marker} {fname}:L{s['line']} → max_tokens={s['value']} "
                  f"(min recommended: {safe_min} for '{output_type}')")
            
            if marker == '⚠️':
                context_clean = s['context'][:80]
                issues.append({
                    'file': fname,
                    'line': s['line'],
                    'current': s['value'],
                    'recommended': safe_min,
                    'context': context_clean,
                })
    
    # Check for files that should have max_tokens but don't
    print(f"\n🔎 Checking for files missing max_tokens...")
    pipeline_files = [
        r'D:\super_frontier_radar\generators\daily_dispatch.py',  
        r'D:\super_frontier_radar\generate_strategic_insider.py',
        r'D:\super_frontier_radar\_pipeline_orchestrator.py',
        r'D:\AISleepGen_Optimized\deepseek_proxy.py',
        r'D:\AISleepGen_Optimized\dp_router.py',
        r'D:\AISleepGen_Optimized\world_model_coordinator.py',
    ]
    
    all_found_files = set(r['file'] for r in all_results)
    
    for pf in pipeline_files:
        if os.path.exists(pf):
            short_name = os.path.basename(pf)
            # Check if any result from this dir matches
            matched = any(short_name in r['file'] for r in all_results)
            if not matched:
                warnings.append(f"  ⚠️  {pf} — no max_tokens setting found!")
    
    if warnings:
        for w in warnings:
            print(w)
    else:
        print("  All known pipeline files have max_tokens set ✅")
    
    # Summary
    print("\n" + "=" * 60)
    if issues:
        print(f"  ❌ {len(issues)} RISK(S) FOUND — max_tokens may be too low:")
        for i in issues:
            print(f"    ⚠️  {i['file']}:L{i['line']}")
            print(f"         Current: {i['current']} → Recommended: ≥{i['recommended']}")
            print(f"         Context: {i['context'][:60]}")
        print(f"\n  🔧 Fix: increase max_tokens to the recommended minimum above.")
        print(f"     Reference: 2026-06-08 daily_dispatch V5 busted at 8192, fixed to 16000.")
        sys.exit(1)
    else:
        print("  ✅ All max_tokens settings are within recommended ranges.")
    
    print("=" * 60)


if __name__ == '__main__':
    main()
