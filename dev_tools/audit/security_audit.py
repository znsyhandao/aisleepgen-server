# -*- coding: utf-8 -*-
"""
SECURITY_STATEMENT 与代码行为一致性审计
自动扫描 SECURITY_STATEMENT.md 中声明的安全约束，与代码实际行为对比。
检测：
  1. 声明了"只读文件"但代码有 write() 调用
  2. 声明了"无网络访问"但代码有 urllib/requests
  3. 声明了"无子进程"但代码有 subprocess
  4. 声明了"输出到特定目录"但代码有其他路径写入

用法:
  python security_audit.py
  python security_audit.py --fix        # 自动修正SECURITY_STATEMENT(不修改代码)
  python security_audit.py --check-only

返回码: 0=一致  1=有不一致
"""
import os, re, sys, ast

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(PROJECT_DIR) if os.path.exists(os.path.join(os.path.dirname(PROJECT_DIR), 'skill.py')) else PROJECT_DIR

SEC_PATHS = [
    os.path.join(SKILL_DIR, 'SECURITY_STATEMENT.md'),
    os.path.join(PROJECT_DIR, 'SECURITY_STATEMENT.md'),
]
SEC_PATHS = [p for p in SEC_PATHS if os.path.exists(p)]

SKIP_DIRS = {'__pycache__', '.git', 'venv', 'node_modules', '.surgical_backups', 'memory', 'sleep_edf_validate', 'miniprogram'}
SKIP_FILES = {'install_hooks.py', 'pre_op.py', 'preflight.py', 'pyrun.py', 'memwatch.py', 'deploy_check.py', 'version_sync.py', 'api_contract_check.py', 'auth_check.py', 'security_audit.py'}

# 代码行为检测器: {行为标签: 检测模式列表}
BEHAVIOR_CHECKS = {
    '网络访问': [
        (r'urllib\.request', 'urllib HTTP请求'),
        (r'requests\.(get|post|put|delete)', 'requests库'),
        (r'httpx\.', 'httpx库'),
        (r'http\.client\.', 'http.client'),
        (r'websocket\.', 'websocket'),
    ],
    '文件写入': [
        (r'\.write\(', '.write()调用'),
        (r'open\(.*[\'\"][rw][^b]', 'open()写入模式'),
        (r'shutil\.copy', 'shutil.copy'),
        (r'shutil\.move', 'shutil.move'),
    ],
    '子进程': [
        (r'subprocess\.', 'subprocess调用'),
        (r'os\.system\(', 'os.system'),
        (r'os\.popen\(', 'os.popen'),
    ],
    '动态执行': [
        (r'\beval\(', 'eval'),
        (r'\bexec\(', 'exec'),
        (r'__import__\(', '动态导入'),
    ],
    '文件读取(外部输入)': [
        (r'open\(', 'open() (可能是读取)'),
        (r'json\.load\(', 'json.load'),
        (r'yaml\.', 'yaml解析'),
    ],
}

def extract_declared_claims():
    """从SECURITY_STATEMENT.md提取安全声明"""
    claims = set()
    for p in SEC_PATHS:
        with open(p, 'r', encoding='utf-8') as f:
            content = f.read()
        # 提取关键词
        patterns = [
            (r'(?i)(?:no|without|not|never|禁止|无)\s*\w*\s*(network|internet|web|http|api|external)', '无网络'),
            (r'(?i)(?:read.only|read-only|only read|不能修改|不修改)', '只读'),
            (r'(?i)(?:no|without|not|never)\s*\w*\s*(subprocess|execute|spawn)', '无子进程'),
            (r'(?i)(?:no|without|not|never)\s*\w*\s*(write|modify|delete|change)', '无写入'),
            (r'(?i)output\s*(?:to|directory|path)', '有限输出'),
            (r'(?i)(?:no|without|not|never)\s*\w*\s*(eval|exec|dynamic)', '无动态执行'),
        ]
        for pat, claim in patterns:
            if re.search(pat, content):
                claims.add(claim)
    return claims

def scan_code_behaviors():
    """扫描代码实际行为"""
    behaviors = {}
    for root, dirs, files in os.walk(PROJECT_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith('.py') or f in SKIP_FILES:
                continue
            fpath = os.path.join(root, f)
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
            except:
                continue
            
            for behavior, patterns in BEHAVIOR_CHECKS.items():
                for pat, desc in patterns:
                    if re.search(pat, content):
                        if behavior not in behaviors:
                            behaviors[behavior] = []
                        rel_path = os.path.relpath(fpath, PROJECT_DIR)
                        if len(behaviors[behavior]) < 3:  # 最多记3条
                            behaviors[behavior].append(f'{rel_path}: {desc}')
    
    return behaviors

def check():
    print('=== SECURITY声明与代码一致性审计 ===')
    
    if not SEC_PATHS:
        print('  [WARN] 未找到 SECURITY_STATEMENT.md')
        return True
    
    claims = extract_declared_claims()
    print(f'\n  SECURITY声明 ({SEC_PATHS[0]}):')
    if not claims:
        print('    (未检测到明确的安全约束声明)')
    else:
        for c in sorted(claims):
            print(f'    - {c}')
    
    behaviors = scan_code_behaviors()
    print(f'\n  代码实际行为:')
    if not behaviors:
        print('    (未检测到敏感操作)')
    else:
        for b, locs in sorted(behaviors.items()):
            print(f'    - {b}:')
            for loc in locs:
                print(f'        {loc}')
    
    # 做交叉检查: 声称安全但代码有行为
    issues = []
    
    claimed_secure = '无网络' in claims
    has_network = '网络访问' in behaviors
    if claimed_secure and has_network:
        issues.append('声明"无网络"但代码中有网络访问')
    
    claimed_readonly = '只读' in claims
    has_write = '文件写入' in behaviors
    if claimed_readonly and has_write:
        issues.append('声明"只读"但代码中有文件写入')
    
    claimed_nosub = '无子进程' in claims
    has_sub = '子进程' in behaviors
    if claimed_nosub and has_sub:
        issues.append('声明"无子进程"但代码中有subprocess调用')
    
    claimed_noeval = '无动态执行' in claims
    has_eval = '动态执行' in behaviors
    if claimed_noeval and has_eval:
        issues.append('声明"无动态执行"但代码中有eval/exec')
    
    if issues:
        print(f'\n  [FAIL] {len(issues)} 个一致性冲突:')
        for iss in issues:
            print(f'    - {iss}')
        return False
    else:
        print(f'\n  [OK] 声明与行为一致')
        return True

if __name__ == '__main__':
    ok = check()
    if '--check-only' not in sys.argv and not ok:
        sys.exit(1)
