#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Neural Nexus v2 - 独立文件模式 + 全 API + 沙盒引擎"""
import json, http.server, socketserver, subprocess, os, sys, threading, time, shutil

BASE = 'D:\\AISleepGen_Optimized'
HTML_FILE = 'D:\\super_frontier_radar\\n2.html'
DATA_FILE = 'D:\\super_frontier_radar\\eco_data.json'
NIGHT_WATCH = os.path.join(BASE, 'data', 'night_watch_stats.json')
STAFF_EVO = os.path.join(BASE, 'staff_evolution', 'evolution_state.json')
ARCHIVE = os.path.join(BASE, 'data', 'algorithm_archive.json')
NIGHT_WATCH_SCRIPT = os.path.join(BASE, 'night_watch_explorer.py')
PBT_DIR = 'F:\\pbt_experiments'  # 沙盒实验默认大容量目录

def _lj(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return default

def _load_paradigms():
    raw = _lj(ARCHIVE, {})
    items = []
    for name, info in raw.items():
        if not isinstance(info, dict):
            continue
        items.append({
            'name': name,
            'source': info.get('source', ''),
            'math_core': (info.get('math_core', '') or '')[:150],
            'asg_value': (info.get('asg_value', '') or '')[:150],
            'landed': info.get('landed', False),
            'priority': info.get('priority', 5),
            'lines': info.get('lines_needed', 0),
            'applicable_projects': info.get('applicable_projects', [])
        })
    items.sort(key=lambda x: (x['priority'], x['name']))
    return items

def _load_landings():
    l = _lj(NIGHT_WATCH, {'_total_landed': 0})
    s = _lj(STAFF_EVO, {'employees': {}, 'evolution_history': []})
    v3 = sum(1 for e in s.get('employees', {}).values() if e.get('level') == 'v3')
    v2c = sum(1 for e in s.get('employees', {}).values() if e.get('level') == 'v2')
    l['_staff_v3'] = v3
    l['_staff_v2'] = v2c
    l['_staff_evolutions'] = s.get('evolution_history', [])[-20:]
    return l

def _load_sandbox():
    """返回可运行的算法候选（未落地的按优先级排序）"""
    raw = _lj(ARCHIVE, {})
    candidates = []
    # 统计已有实验记录
    exp_dir = os.path.join(PBT_DIR, 'results')
    completed = set()
    if os.path.exists(exp_dir):
        for fname in os.listdir(exp_dir):
            if fname.endswith('.json'):
                completed.add(fname.replace('.json', ''))
    for name, info in raw.items():
        if not isinstance(info, dict):
            continue
        if info.get('landed', False):
            continue
        candidates.append({
            'name': name,
            'source': info.get('source', ''),
            'math_core': (info.get('math_core', '') or '')[:120],
            'priority': info.get('priority', 5),
            'lines': info.get('lines_needed', 0),
            'already_tested': name in completed,
        })
    candidates.sort(key=lambda x: (x['priority'], x['lines']))
    return candidates[:30]

def _check_resources():
    """系统资源检查"""
    import ctypes
    kernel32 = ctypes.windll.kernel32
    mem = ctypes.c_ulonglong()
    kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(mem))
    total_mem_gb = round(mem.value / (1024 * 1024), 1)
    cpus = os.cpu_count() or 0
    disks = {}
    for d in ['C:', 'D:', 'E:', 'F:']:
        try:
            total, used, free = shutil.disk_usage(d + '\\')
            disks[d] = {'total_gb': round(total / (1024**3), 1), 'free_gb': round(free / (1024**3), 1)}
        except:
            pass
    gpu_info = ''
    try:
        r = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'],
                           capture_output=True, text=True, timeout=3)
        lines = [l.strip() for l in r.stdout.split('\n') if l.strip() and 'Name' not in l]
        if lines:
            gpu_info = ' | '.join(lines[:2])
    except:
        gpu_info = 'unknown'
    warnings = []
    if total_mem_gb < 4:
        warnings.append('内存不足: %sGB (推荐 >=4GB)' % total_mem_gb)
    if total_mem_gb < 8:
        warnings.append('内存受限: %sGB (一键全部可能慢)' % total_mem_gb)
    f_disk = disks.get('F:', {})
    if f_disk and f_disk.get('free_gb', 0) < 2:
        warnings.append('F盘空间不足: %sGB (需要 >=2GB)' % f_disk.get('free_gb', 0))
    if disks.get('D:', {}).get('free_gb', 0) < 5:
        warnings.append('D盘空间不足: %sGB (需要 >=5GB)' % disks.get('D:', {}).get('free_gb', 0))
    if cpus < 2:
        warnings.append('CPU核心不足: %s (推荐 >=2)' % cpus)
    return {
        'memory_gb': total_mem_gb,
        'cpus': cpus,
        'gpu': gpu_info,
        'disks': disks,
        'warning': '; '.join(warnings) if warnings else '无',
        'can_run': len(warnings) < 2
    }

def _preview_experiment(algo_name):
    """预检：只评估不执行。返回会改什么、多少行、有没有代码生成器"""
    raw = _lj(ARCHIVE, {})
    info = raw.get(algo_name, {})
    if not isinstance(info, dict):
        return {'error': 'unknown algorithm', 'name': algo_name}

    lines = info.get('lines_needed', 0)
    priority = info.get('priority', 5)
    source = info.get('source', '')
    math_core = (info.get('math_core', '') or '')[:100]

    # 检查 night_watch 有没有代码生成器
    py = sys.executable or 'python'
    has_generator = False
    gen_info = ''
    try:
        r = subprocess.run(
            [py, NIGHT_WATCH_SCRIPT, '--dry-run', algo_name],
            cwd=BASE, capture_output=True, text=True, timeout=30
        )
        out = (r.stdout or '') + (r.stderr or '')
        has_generator = 'unknown algorithm' not in out and ('dry-run' in out or 'OK' in out)
        if has_generator:
            # 提取细节
            for line in out.split('\n'):
                if 'type=' in line:
                    gen_info = line.strip()
    except:
        pass

    already_landed = info.get('landed', False)
    existing_result = os.path.join(PBT_DIR, 'results', algo_name + '.json')
    already_tested = os.path.exists(existing_result)

    return {
        'name': algo_name,
        'source': source,
        'math_core': math_core,
        'lines': lines,
        'priority': priority,
        'has_auto_generator': has_generator,
        'generator_detail': gen_info,
        'already_landed': already_landed,
        'already_tested': already_tested,
        'target_file': 'deepseek_proxy.py（注入）' if 'inject' in gen_info else ('新文件' if 'newfile' in gen_info else '未知'),
    }

def _run_sandbox_experiment(algo_name):
    """在 F:\\pbt_experiments 执行一次沙盒实验"""
    log_file = os.path.join(PBT_DIR, 'experiment_log.txt')
    try:
        os.makedirs(os.path.join(PBT_DIR, 'results'), exist_ok=True)
        os.makedirs(os.path.join(PBT_DIR, 'code_gen'), exist_ok=True)

        ts = time.strftime('%Y%m%d_%H%M%S')
        result_path = os.path.join(PBT_DIR, 'results', algo_name + '.json')
        code_path = os.path.join(PBT_DIR, 'code_gen', algo_name + '_' + ts + '.py')

        # Step 1: 检查该算法是否已有代码生成器
        py = sys.executable or 'python'
        has_generator = False
        try:
            # 尝试用 night_watch 的 force_algorithm 模式
            r = subprocess.run(
                [py, NIGHT_WATCH_SCRIPT, '--dry-run', algo_name],
                cwd=BASE, capture_output=True, text=True, timeout=60
            )
            has_generator = 'unknown algorithm' not in r.stderr and 'dry-run' in r.stdout
        except:
            pass

        # Step 2: 用 night_watch 跑沙盒实验
        output_text = ''
        if has_generator:
            try:
                r = subprocess.run(
                    [py, NIGHT_WATCH_SCRIPT, '--force', algo_name],
                    cwd=BASE, capture_output=True, text=True, timeout=300
                )
                output_text = r.stdout + r.stderr
            except:
                r = subprocess.run(
                    [py, NIGHT_WATCH_SCRIPT],
                    cwd=BASE, capture_output=True, text=True, timeout=300
                )
                output_text = r.stdout + r.stderr
        else:
            output_text = ''

        result = {
            'algorithm': algo_name,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'has_generator': has_generator,
            'code_path': code_path,
            'status': 'failed',
            'message': '无输出'
        }

        if has_generator:
            if 'already injected' in output_text or '[OK]' in output_text:
                result['status'] = 'landed'
                result['message'] = '落地成功（已注入或编译通过）'
            elif 'unknown algorithm' in output_text:
                result['status'] = 'needs_codegen'
                result['message'] = 'night_watch 不识别此算法名'
            else:
                result['status'] = 'failed'
                result['message'] = (output_text or '')[400:600] if len(output_text) > 400 else (output_text or '')[:200]
        else:
            result['status'] = 'needs_codegen'
            result['message'] = '无自动代码生成器，需要手动编写'

        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # 写日志
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('[%s] %s -> %s | has_gen=%s\n' % (
                time.strftime('%Y-%m-%d %H:%M:%S'), algo_name, result['status'], has_generator))

        return result
    except Exception as e:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write('[%s] %s -> ERROR: %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), algo_name, str(e)))
        return {'algorithm': algo_name, 'status': 'error', 'message': str(e)[:200], 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/ecosystem':
            self._json(_lj(DATA_FILE, {}))
        elif self.path == '/api/paradigms':
            self._json(_load_paradigms())
        elif self.path == '/api/landings':
            self._json(_load_landings())
        elif self.path == '/api/sandbox':
            self._json(_load_sandbox())
        elif self.path == '/api/resources':
            self._json(_check_resources())
        elif self.path.startswith('/api/sandbox/preview/'):
            import urllib.parse
            algo = urllib.parse.unquote(self.path[len('/api/sandbox/preview/'):])
            self._json(_preview_experiment(algo))
        elif self.path.startswith('/api/experiments/'):
            algo = self.path[len('/api/experiments/'):]
            exp_file = os.path.join(PBT_DIR, 'results', algo + '.json')
            if os.path.exists(exp_file):
                self._json(_lj(exp_file, {}))
            else:
                self._json({'algorithm': algo, 'status': 'not_run'})
        elif self.path == '/api/experiments':
            results = []
            exp_dir = os.path.join(PBT_DIR, 'results')
            if os.path.exists(exp_dir):
                for fname in sorted(os.listdir(exp_dir)):
                    if fname.endswith('.json'):
                        d = _lj(os.path.join(exp_dir, fname), {})
                        if d:
                            results.append(d)
            self._json(results)
        elif self.path == '/':
            self._html(open(HTML_FILE, 'rb').read())
        else:
            self._json({'e': 'nf'}, 404)

    def do_POST(self):
        if self.path == '/api/sandbox/run':
            try:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                data = json.loads(body) if body else {}
            except:
                data = {}
            algo_name = data.get('name', '')
            if not algo_name:
                self._json({'ok': False, 'e': 'no name'}, 400)
                return

            def _run():
                _run_sandbox_experiment(algo_name)
            threading.Thread(target=_run, daemon=True).start()
            self._json({'ok': True, 'msg': 'Started: %s' % algo_name})
        else:
            self._json({'e': 'nf'}, 404)

    def _html(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(data)

    def _json(self, d, st=200):
        self.send_response(st)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()
        self.wfile.write(json.dumps(d, ensure_ascii=False).encode())

    def log_message(self, fmt, *a):
        pass


class TS(socketserver.ThreadingMixIn, http.server.HTTPServer):
    pass


if __name__ == '__main__':
    s = TS(('0.0.0.0', 8930), Handler)
    print('[NEXUS] http://localhost:8930')
    print('[NEXUS] PBT dir: %s' % PBT_DIR)
    s.serve_forever()
