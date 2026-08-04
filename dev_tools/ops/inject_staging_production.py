"""
inject_staging_production.py — 注入 staging → production 管线

功能:
1. 在 deepseek_proxy.py 注册两个端点:
   - POST /api/sleep/inject-staging → staging区
   - POST /api/sleep/confirm-inject → staging→production 确认
2. 在 injected_algorithms/ 创建 staging 区结构
3. 支持 night_watch_explorer 输出 staging → 手动确认 → production

用法:
  python inject_staging_production.py patch      # 打补丁到 deepseek_proxy.py
  python inject_staging_production.py status     # 查看 staging 区状态
  python inject_staging_production.py stage <file>  # 手动复制文件到 staging
  python inject_staging_production.py confirm    # staging → production 确认注入
"""

import os
import sys
import json
import shutil
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEEPSEEK_PROXY = os.path.join(BASE_DIR, 'deepseek_proxy.py')
INJECTED_DIR = os.path.join(BASE_DIR, 'injected_algorithms')

# ===== staging 目录结构 =====
# injected_algorithms/
#   staging/          <- 待确认的新代码
#     {algorithm_name}/
#       code.py       <- 生成的代码
#       metadata.json <- 谁生成的、何时、什么算法
#   confirmed/        <- 已确认但还没注入到 production（一确认就注入，这个目录是历史记录）
#     {timestamp}_{algorithm_name}/
#   manifest.json     <- 当前 staging 的索引

STAGING_DIR = os.path.join(INJECTED_DIR, 'staging')
CONFIRMED_DIR = os.path.join(INJECTED_DIR, 'confirmed')
MANIFEST_PATH = os.path.join(INJECTED_DIR, 'manifest.json')


def ensure_dirs():
    """确保目录结构存在"""
    for d in [INJECTED_DIR, STAGING_DIR, CONFIRMED_DIR]:
        os.makedirs(d, exist_ok=True)


def get_manifest():
    """读取 manifest"""
    ensure_dirs()
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'staged': [], 'confirmed': [], 'updated_at': None}


def save_manifest(manifest):
    """保存 manifest"""
    manifest['updated_at'] = datetime.now().isoformat()
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def stage_code(algorithm_name, code_content, source='night_watch_explorer', metadata=None):
    """将代码复制到 staging 区"""
    ensure_dirs()
    algo_dir = os.path.join(STAGING_DIR, algorithm_name)
    os.makedirs(algo_dir, exist_ok=True)

    # 写入代码
    code_path = os.path.join(algo_dir, 'code.py')
    with open(code_path, 'w', encoding='utf-8') as f:
        f.write(code_content)

    # 写入 metadata
    meta = {
        'algorithm': algorithm_name,
        'source': source,
        'staged_at': datetime.now().isoformat(),
        'target': 'deepseek_proxy.py (inject)',
        ** (metadata or {}),
        'lines': len(code_content.splitlines()),
        'size_bytes': len(code_content.encode('utf-8')),
    }
    with open(os.path.join(algo_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # 更新 manifest
    manifest = get_manifest()
    # 去重：同名算法更新
    manifest['staged'] = [s for s in manifest['staged'] if s['algorithm'] != algorithm_name]
    manifest['staged'].append({
        'algorithm': algorithm_name,
        'path': algo_dir,
        'staged_at': meta['staged_at'],
        'lines': meta['lines'],
    })
    save_manifest(manifest)

    print(f"[Inject] staged: {algorithm_name} ({meta['lines']} lines)")
    return code_path


def confirm_staged(algorithm_names=None):
    """确认 staging → production — 复制到 injected_algorithms/confirmed/"""
    ensure_dirs()
    manifest = get_manifest()
    if not manifest['staged']:
        print("[Inject] No staged algorithms to confirm.")
        return []

    if algorithm_names:
        staged = [s for s in manifest['staged'] if s['algorithm'] in algorithm_names]
    else:
        staged = list(manifest['staged'])

    if not staged:
        print("[Inject] No matching staged algorithms.")
        return []

    confirmed = []
    for s in staged:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_name = f"{ts}_{s['algorithm']}"
        dest_dir = os.path.join(CONFIRMED_DIR, dest_name)
        shutil.copytree(s['path'], dest_dir)
        manifest['confirmed'].append({
            'algorithm': s['algorithm'],
            'path': dest_dir,
            'confirmed_at': datetime.now().isoformat(),
        })
        confirmed.append(s['algorithm'])
        print(f"[Inject] confirmed: {s['algorithm']} -> {dest_dir}")

    # 清除已确认的 staging
    for s in staged:
        shutil.rmtree(s['path'], ignore_errors=True)
    manifest['staged'] = [s for s in manifest['staged'] if s['algorithm'] not in algorithm_names]

    save_manifest(manifest)
    return confirmed


def patch_server():
    """在 deepseek_proxy.py 添加 inject 端点和路由"""
    if not os.path.exists(DEEPSEEK_PROXY):
        print(f"[Inject] ERROR: {DEEPSEEK_PROXY} not found")
        return False

    with open(DEEPSEEK_PROXY, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已打过补丁
    if '# [Inject] staging endpoint' in content:
        print("[Inject] Patch already applied, skipping.")
        return True

    # 1. 在 do_POST 路由链加端点（在 export-my-data 之后，path.startswith('/api/') 之前）
    route_hook = """            self._handle_export_my_data(data)

        elif path == '/api/sleep/inject-staging':
            \"\"\"POST /api/sleep/inject-staging — 注入staging→production管线\"\"\"
            self._handle_inject_staging(data)
"""

    old_route = """            self._handle_export_my_data(data)

        elif path.startswith('/api/'):"""

    if old_route not in content:
        print("[Inject] ERROR: route anchor not found!")
        return False

    content = content.replace(old_route, route_hook)

    # 2. 在文件尾部加 handler 函数（在 _handle_device_ocr 绑定之后）
    handler_code = """
# ===== [Inject] staging → production 管线 =====
def _handle_inject_staging(self, data):
    \"\"\"POST /api/sleep/inject-staging — 注入管线\"\"\"
    import json as _json
    import os as _os
    import sys as _sys
    _inj_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'injected_algorithms')
    _staging_dir = _os.path.join(_inj_dir, 'staging')
    _manifest_path = _os.path.join(_inj_dir, 'manifest.json')
    try:
        action = data.get('action', 'status')  # status | stage | confirm | list
        if action == 'status':
            result = {'status': 'ok', 'staging_dir_exists': _os.path.isdir(_staging_dir)}
            if _os.path.exists(_manifest_path):
                with open(_manifest_path, 'r', encoding='utf-8') as _mf:
                    result['manifest'] = _json.load(_mf)
            else:
                result['manifest'] = {'staged': [], 'confirmed': []}
        elif action == 'stage':
            algo = data.get('algorithm', '')
            code = data.get('code', '')
            if not algo or not code:
                result = {'status': 'error', 'error': 'algorithm and code required'}
            else:
                _os.makedirs(_staging_dir, exist_ok=True)
                _algo_dir = _os.path.join(_staging_dir, algo)
                _os.makedirs(_algo_dir, exist_ok=True)
                with open(_os.path.join(_algo_dir, 'code.py'), 'w', encoding='utf-8') as _cf:
                    _cf.write(code)
                _meta = {
                    'algorithm': algo,
                    'staged_at': __import__('datetime').datetime.now().isoformat(),
                    'lines': len(code.splitlines()),
                }
                with open(_os.path.join(_algo_dir, 'metadata.json'), 'w', encoding='utf-8') as _mf:
                    _json.dump(_meta, _mf, ensure_ascii=False)
                result = {'status': 'ok', 'staged': algo}
        elif action == 'confirm':
            algo = data.get('algorithm', '')
            if not _os.path.exists(_manifest_path):
                result = {'status': 'error', 'error': 'no manifest'}
            else:
                with open(_manifest_path, 'r', encoding='utf-8') as _mf:
                    _manifest = _json.load(_mf)
                _staged_list = _manifest.get('staged', [])
                if algo:
                    _to_confirm = [s for s in _staged_list if s['algorithm'] == algo]
                else:
                    _to_confirm = list(_staged_list)
                if not _to_confirm:
                    result = {'status': 'error', 'error': 'nothing to confirm'}
                else:
                    _confirmed = []
                    for _s in _to_confirm:
                        _ts = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
                        _dest = _os.path.join(_inj_dir, 'confirmed', f"{_ts}_{_s['algorithm']}")
                        _src = _os.path.join(_staging_dir, _s['algorithm'])
                        __import__('shutil').copytree(_src, _dest)
                        _confirmed.append(_s['algorithm'])
                        __import__('shutil').rmtree(_src, ignore_errors=True)
                    _manifest['staged'] = [s for s in _staged_list if s['algorithm'] not in _confirmed]
                    with open(_manifest_path, 'w', encoding='utf-8') as _mf:
                        _json.dump(_manifest, _mf, ensure_ascii=False, indent=2)
                    result = {'status': 'ok', 'confirmed': _confirmed}
        else:
            result = {'status': 'error', 'error': f'unknown action: {action}'}
        self._set_headers(200)
        self.wfile.write(_json.dumps(result, ensure_ascii=False).encode('utf-8'))
    except Exception as _inj_e:
        import traceback; traceback.print_exc()
        self._set_headers(500)
        self.wfile.write(_json.dumps({'error': str(_inj_e)[:200]}, ensure_ascii=False).encode('utf-8'))

ProxyHandler._handle_inject_staging = _handle_inject_staging
"""

    # 在 _handle_device_ocr 绑定之后追加
    bind_anchor = "ProxyHandler._handle_device_ocr = _handle_device_ocr\n"
    if bind_anchor not in content:
        print("[Inject] ERROR: bind anchor not found!")
        return False

    content = content.replace(bind_anchor, bind_anchor + handler_code)

    # 回写
    with open(DEEPSEEK_PROXY, 'r', encoding='utf-8') as f:
        # 确认没损坏
        backup_path = DEEPSEEK_PROXY + '.bak_inject'
        shutil.copy2(DEEPSEEK_PROXY, backup_path)
        print(f"[Inject] Backup saved: {backup_path}")

    with open(DEEPSEEK_PROXY, 'w', encoding='utf-8') as f:
        f.write(content)

    print("[Inject] Patch applied successfully!")
    print("[Inject] Added: POST /api/sleep/inject-staging (actions: status|stage|confirm)")
    return True


def show_status():
    """显示 staging 区状态"""
    ensure_dirs()
    manifest = get_manifest()
    print(f"\n=== Inject Staging Status ===")
    print(f"Staging dir: {STAGING_DIR}")
    print(f"Confirmed dir: {CONFIRMED_DIR}")
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"\nStaged ({len(manifest['staged'])}):")
    for s in manifest['staged']:
        print(f"  [{s['algorithm']}] {s['staged_at']} ({s['lines']} lines)")
    print(f"\nConfirmed ({len(manifest['confirmed'])}):")
    for c in manifest['confirmed']:
        print(f"  [{c['algorithm']}] {c['confirmed_at']}")
    if not manifest['staged'] and not manifest['confirmed']:
        print("  (empty)")
    print()


def patch_night_watch():
    """让 night_watch_explorer.py 的生成输出写到 staging 区而非直接注入"""
    nw_path = os.path.join(BASE_DIR, 'night_watch_explorer.py')
    if not os.path.exists(nw_path):
        # 可能不叫这个名字，搜索
        import glob
        nw_matches = glob.glob(os.path.join(BASE_DIR, '*night*watch*'))
        if nw_matches:
            nw_path = nw_matches[0]
        else:
            print("[Inject] night_watch_explorer.py not found, skipping.")
            return False

    with open(nw_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否已有 staging 输出
    if 'injected_algorithms' in content:
        print("[Inject] night_watch already has staging support, skipping.")
        return True

    # 在文件尾部追加 staging 输出函数
    staging_hook = """

# ===== [Inject] staging 输出钩子 =====
def _stage_generated_code(algorithm_name, code_content, metadata=None):
    '''将生成的代码写到 staging 区而非直接注入'''
    import os, json, sys
    _inj_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'injected_algorithms')
    _staging_dir = os.path.join(_inj_dir, 'staging')
    _manifest_path = os.path.join(_inj_dir, 'manifest.json')
    os.makedirs(_staging_dir, exist_ok=True)
    
    _algo_dir = os.path.join(_staging_dir, algorithm_name)
    os.makedirs(_algo_dir, exist_ok=True)
    
    with open(os.path.join(_algo_dir, 'code.py'), 'w', encoding='utf-8') as _cf:
        _cf.write(code_content)
    
    _meta = {
        'algorithm': algorithm_name,
        'source': 'night_watch_explorer',
        'staged_at': __import__('datetime').datetime.now().isoformat(),
        'lines': len(code_content.splitlines()),
        'size_bytes': len(code_content.encode('utf-8')),
        **(metadata or {}),
    }
    with open(os.path.join(_algo_dir, 'metadata.json'), 'w', encoding='utf-8') as _mf:
        json.dump(_meta, _mf, ensure_ascii=False, indent=2)
    
    # 读 manifest
    if os.path.exists(_manifest_path):
        with open(_manifest_path, 'r', encoding='utf-8') as _mf:
            _manifest = json.load(_mf)
    else:
        _manifest = {'staged': [], 'confirmed': []}
    
    _manifest['staged'] = [s for s in _manifest['staged'] if s['algorithm'] != algorithm_name]
    _manifest['staged'].append({
        'algorithm': algorithm_name,
        'path': _algo_dir,
        'staged_at': _meta['staged_at'],
        'lines': _meta['lines'],
    })
    with open(_manifest_path, 'w', encoding='utf-8') as _mf:
        json.dump(_manifest, _mf, ensure_ascii=False, indent=2)
    
    print(f'[InjectStaging] staged: {algorithm_name} ({_meta["lines"]} lines)')
    return _algo_dir
"""

    content += staging_hook

    # 备份
    backup_path = nw_path + '.bak_inject'
    shutil.copy2(nw_path, backup_path)

    with open(nw_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"[Inject] night_watch staging hook added: {nw_path}")
    print(f"[Inject] Backup saved: {backup_path}")
    return True


if __name__ == '__main__':
    ensure_dirs()

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'patch':
        patch_server()
        patch_night_watch()
    elif cmd == 'status':
        show_status()
    elif cmd == 'stage':
        if len(sys.argv) < 3:
            print("Usage: python inject_staging_production.py stage <file> [algorithm_name]")
            sys.exit(1)
        file_path = sys.argv[2]
        algo = sys.argv[3] if len(sys.argv) > 3 else os.path.splitext(os.path.basename(file_path))[0]
        if not os.path.exists(file_path):
            print(f"[Inject] File not found: {file_path}")
            sys.exit(1)
        with open(file_path, 'r', encoding='utf-8') as f:
            code = f.read()
        stage_code(algo, code)
    elif cmd == 'confirm':
        algo = sys.argv[2] if len(sys.argv) > 2 else None
        confirmed = confirm_staged(algo)
        if confirmed:
            print(f"[Inject] Confirmed: {', '.join(confirmed)}")
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
