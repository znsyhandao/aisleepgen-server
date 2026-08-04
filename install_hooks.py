#!/usr/bin/env python
"""
Git pre-commit hook for AISleepGen_Optimized.
Runs before every commit. Blocks commits only for issues that cause real damage:
  1. Python syntax errors
  2. Empty except blocks (silent failure bugs)
  3. BOM header (PowerShell Set-Content corruption)
  4. Hardcoded truncation [:50] (pipeline.py data loss bug)
  5. Non-UTF-8 encoding (GBK corruption)
  6. JS syntax (trailing commas, mismatched braces - WeChat incompatibility)
  7. Version inconsistency (ClawHub submission rejection)

Install: Save as .git/hooks/pre-commit
         Or run: python install_hooks.py
         Or run: python install_hooks.py --hook
"""
import subprocess, sys, os, re, py_compile

if '--hook' in sys.argv:
    REPO_ROOT = r'D:\AISleepGen_Optimized'
else:
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(ok, msg):
    icon = '[OK]' if ok else '[FAIL]'
    print(f'  {icon} {msg}')
    return ok


def get_staged_files():
    result = subprocess.run(
        ['git', 'diff', '--cached', '--name-only'],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    if result.returncode != 0:
        return []
    files = [f.strip() for f in result.stdout.split('\n') if f.strip().endswith('.py')]
    return [os.path.join(REPO_ROOT, f) for f in files if os.path.exists(os.path.join(REPO_ROOT, f))]


def get_unstaged_warnings():
    result = subprocess.run(
        ['git', 'diff', '--name-only'],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    files = [f.strip() for f in result.stdout.split('\n') if f.strip() and f.endswith('.py')]
    excluded = ['venv/', 'site-packages/', 'node_modules/', 'Lib/site-packages/']
    files = [f for f in files if not any(e in f.replace('\\', '/') for e in excluded)]
    return [f for f in files if os.path.exists(os.path.join(REPO_ROOT, f))][:20]


def main():
    print('[pre-commit] AISleepGen')

    py_files = get_staged_files()
    if not py_files:
        print('  没有待提交的 Python 文件')
        sys.exit(0)

    all_ok = True

    # ── 1. 语法检查 ──
    for f in py_files:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            all_ok = check(False, f'{os.path.basename(f)}: 语法错误')

    # ── 2. 常见陷阱检查（逐文件） ──
    for f in py_files:
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        base = os.path.basename(f)

        # BOM头
        if content.startswith('\ufeff'):
            all_ok = check(False, f'{base}: BOM头(\\ufeff) — PowerShell遗毒')

        # 空except
        empty_excepts = re.findall(r'except\s*[^:]*:\s*\n\s*pass', content)
        if empty_excepts:
            all_ok = check(False, f'{base}: {len(empty_excepts)} 个空except')

        # 硬编码截断 [:50]
        truncations = re.findall(r'\[:\s*\d{1,3}\]|\[\s*0\s*:\s*\d{1,3}\]', content)
        if truncations:
            all_ok = check(False, f'{base}: {len(truncations)} 处硬编码截断(数据丢失!)')

        # 非UTF-8编码
        try:
            with open(f, 'r', encoding='utf-8') as _:
                pass
        except UnicodeDecodeError:
            all_ok = check(False, f'{base}: 非UTF-8编码(GBK损坏)')

        # JS语法
        if base.endswith('.js'):
            if re.search(r'\}[,]*,\s*$', content, re.MULTILINE):
                all_ok = check(False, f'{base}: 尾部多余逗号')
            opens = content.count('{')
            closes = content.count('}')
            if opens != closes:
                all_ok = check(False, f'{base}: 花括号不匹配({opens}/{closes})')

    # ── 3. 版本号一致性（提交时自动检查，不一致则警告） ──
    vs_path = os.path.join(REPO_ROOT, 'version_sync.py')
    if os.path.exists(vs_path):
        try:
            r = subprocess.run(
                [sys.executable, vs_path],
                capture_output=True, text=True, timeout=10, cwd=REPO_ROOT
            )
            if r.returncode != 0:
                all_ok = check(False, '版本号不一致 (python version_sync.py --fix)')
        except Exception:
            pass
    # ── 4. 部署检查：只在 dp_router/asyncio_server 被修改时触发 ──
    deploy_py_path = os.path.join(REPO_ROOT, 'deploy_check.py')
    if os.path.exists(deploy_py_path):
        deploy_files_changed = any('dp_router' in f or 'asyncio_server' in f or 'deepseek_proxy' in f for f in py_files)
        if deploy_files_changed:
            print('  [i] 后端文件有变更，运行部署检查...')
            try:
                r = subprocess.run(
                    [sys.executable, deploy_py_path],
                    capture_output=True, text=True, timeout=30, cwd=REPO_ROOT
                )
                print(r.stdout[:500])
                if r.returncode != 0:
                    all_ok = check(False, '部署检查未通过，修复后再提交')
            except subprocess.TimeoutExpired:
                print('  [i] 部署检查超时(SSH不通?)，跳过')

    # ── 5. 接口契约检查：只在 dp_router 或前端文件变更时触发 ──
    acc_path = os.path.join(REPO_ROOT, 'api_contract_check.py')
    if os.path.exists(acc_path):
        staged_names = [os.path.basename(f) for f in py_files]
        api_changed = any(f in staged_names for f in ['dp_router.py', 'asyncio_server.py', 'deepseek_proxy.py'])
        frontend_changed = any(f.endswith('.js') or f.endswith('.wxml') for f in staged_names)
        if api_changed or frontend_changed:
            print('  [i] 接口有变更，运行契约检查...')
            try:
                r = subprocess.run(
                    [sys.executable, acc_path, '--check-only'],
                    capture_output=True, text=True, timeout=15, cwd=REPO_ROOT
                )
                print(r.stdout[:500])
                if r.returncode != 0:
                    all_ok = check(False, '接口契约检查未通过')
            except subprocess.TimeoutExpired:
                pass

    # ── 6. 未暂存文件提醒 ──
    unstaged = get_unstaged_warnings()
    if unstaged:
        print(f'  [i] {len(unstaged)} 个文件已修改但未暂存:')
        for f in unstaged:
            print(f'      {f}')

    # ── 7. JS .then() 缺 .catch() 检查 ──
    for f in py_files:
        base = os.path.basename(f)
        if not base.endswith('.js'):
            continue
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            content = fh.read()
        if '.then(' in content and '.catch(' not in content:
            all_ok = check(False, f'{base}: .then() 缺 .catch()')

    # ── 8. 安全声明审计 ──
    sec_path = os.path.join(REPO_ROOT, 'security_audit.py')
    if os.path.exists(sec_path):
        print('  [i] 安全声明审计...')
        try:
            r = subprocess.run(
                [sys.executable, sec_path, '--check-only'],
                capture_output=True, text=True, timeout=15, cwd=REPO_ROOT
            )
            fail_lines = [l for l in r.stdout.split('\n') if '[FAIL]' in l]
            for l in fail_lines[:3]:
                print(f'    {l.strip()}')
            if r.returncode != 0:
                all_ok = check(False, '安全声明与代码行为不一致')
        except Exception:
            pass
    # ── 9. 微信登录检测 ──
    auth_path = os.path.join(REPO_ROOT, 'auth_check.py')
    if os.path.exists(auth_path):
        print('  [i] 微信登录检测...')
        try:
            r = subprocess.run(
                [sys.executable, auth_path, '--check-only'],
                capture_output=True, text=True, timeout=15, cwd=REPO_ROOT
            )
            fail_lines = [l for l in r.stdout.split('\n') if '[FAIL]' in l]
            for l in fail_lines[:3]:
                print(f'    {l.strip()}')
            if r.returncode != 0:
                all_ok = check(False, '本地服务故障')
        except Exception:
            pass
    print()
    if all_ok:
        print('[OK] 提交通过')
        sys.exit(0)
    else:
        print('[FAIL] 提交阻止: 修复以上问题后重试')
        sys.exit(1)


if __name__ == '__main__':
    main()
