# -*- coding: utf-8 -*-
"""
预删除安全检查 — 删除前必须跑
检查被删文件是否被 cron / import / 项目管线依赖
"""
import os, sys, json, subprocess
sys.stdout.reconfigure(encoding='utf-8')

SCRIPTS = r'D:\AISleepGen_Optimized\scripts'
ALL_SCRIPTS = [f for f in os.listdir(SCRIPTS) if f.endswith('.py') and f != '__init__.py']

def check_cron_deps():
    """检查 cron 是否引用了某个文件"""
    cron_file = os.path.expanduser('~/.openclaw/cron.json')
    cron_jobs = []
    if os.path.exists(cron_file):
        import json
        try:
            with open(cron_file) as f:
                data = json.load(f)
                for job in data if isinstance(data, list) else data.get('jobs', []):
                    msg = job.get('payload', {}).get('message', '') or job.get('payload', {}).get('text', '')
                    cron_jobs.append({
                        'name': job.get('name', '?'),
                        'message': msg,
                    })
        except Exception:
    print('=== cron 任务引用的文件 ===')
    for job in cron_jobs:
        for fname in ALL_SCRIPTS:
            if fname in job['message']:
                print(f'  [CRON] {job["name"]} 引用了 {fname}')
                yield fname

def check_import_deps():
    """检查脚本间的 import 依赖"""
    print('\n=== import 依赖 ===')
    import re
    deps = {}
    for fname in ALL_SCRIPTS:
        path = os.path.join(SCRIPTS, fname)
        with open(path, encoding='utf-8', errors='ignore') as f:
            content = f.read()
        imports = re.findall(r'import (\w+)|from (\w+)', content)
        for imp in imports:
            ref = imp[0] or imp[1]
            for other in ALL_SCRIPTS:
                if other.replace('.py', '') == ref:
                    if fname not in deps:
                        deps[fname] = []
                    deps[fname].append(other)
    for src, targets in deps.items():
        for t in targets:
            print(f'  {src} -> {t}')
            yield (src, t)

def main():
    print('🔍 删除前安全检查\n')
    cron_deps = set(check_cron_deps())
    import_deps = list(check_import_deps())
    
    print('\n=== 结论 ===')
    print(f'  cron 依赖: {len(cron_deps)} 个文件')
    print(f'  import 依赖: {len(import_deps)} 对')
    if cron_deps:
        print('  ⚠️  以下文件被 cron 引用，不可删除:')
        for f in sorted(cron_deps):
            print(f'    - {f}')
    if import_deps:
        import_files = set()
        for src, t in import_deps:
            import_files.add(src)
            import_files.add(t)
        print(f'  📦 涉及 {len(import_files)} 个脚本文件')
    print('\n✅ 安全删除条件: 文件不在上述列表 + 不是版本控制文件')

if __name__ == '__main__':
    main()
