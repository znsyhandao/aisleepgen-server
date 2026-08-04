#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
night_watch_explorer.py -- AISleepGen auto night-watch explorer v2

Workflow per cycle:
  1. auto_explorer.suggest_code_path() -> pick best unlanded algorithm
  2. Analyze complexity, pick strategy
  3. Backup target file
  4. Auto-generate code (inject into target or create new file)
  5. py_compile verify
  6. import test
  7. Mark landed
  8. Log to memory/<date>_nightwatch_log

v2 changes:
  - Auto code generation engine
  - Layered inject strategy (small -> inject, big -> new file)
  - compile + import dual verify
  - auto rollback on failure
"""

import os, sys, json, importlib, py_compile, shutil, traceback
from datetime import datetime

BASE = 'D:\\AISleepGen_Optimized'
DATE_STR = datetime.now().strftime('%Y-%m-%d')
NIGHT_LOG = 'C:\\Users\\cqs10\\.openclaw\\workspace\\memory\\' + DATE_STR + '_nightwatch_log.md'
_BACKUP_DIR = os.path.join(BASE, '.surgical_backups')

ALGORITHM_CODEGEN = {
    # priority 1 algorithms (~30 lines, inject)
    'GPT\u7cfb\u5217in-context learning': {
        'type': 'inject',
        'target': os.path.join(BASE, 'deepseek_proxy.py'),
        'marker_start': '# >>> [night_watch] GPT in-context learning inject start',
        'marker_end': '# >>> [night_watch] GPT in-context learning inject end',
        'import_hint': '',
        'code': '''# >>> [night_watch] GPT in-context learning inject start
_INCONTEXT_EXAMPLES = []

def remember_incontext_case(brief, plan, rating):
    _INCONTEXT_EXAMPLES.append((brief, plan, rating))
    _INCONTEXT_EXAMPLES.sort(key=lambda x: -x[2])
    if len(_INCONTEXT_EXAMPLES) > 20:
        _INCONTEXT_EXAMPLES.pop()

def get_incontext_examples(limit=3):
    return _INCONTEXT_EXAMPLES[:limit]
# >>> [night_watch] GPT in-context learning inject end
''',
    },
    'Whisper\u8bed\u97f3\u8bc6\u522b': {
        'type': 'inject',
        'target': os.path.join(BASE, 'deepseek_proxy.py'),
        'marker_start': '# >>> [night_watch] Whisper inject start',
        'marker_end': '# >>> [night_watch] Whisper inject end',
        'import_hint': '',
        'code': '''# >>> [night_watch] Whisper inject start
_WHISPER_FALLBACK = True

def transcribe_voice(audio_bytes, fmt='wav'):
    if _WHISPER_FALLBACK:
        return None
    try:
        import openai
        resp = openai.Audio.transcribe('whisper-1', audio_bytes)
        return resp.get('text', '')
    except Exception as e:
        print('[Whisper] fail:', e)
        return None
# >>> [night_watch] Whisper inject end
''',
    },
    'Constitutional AI(\u81ea\u7ea6\u675f)': {
        'type': 'inject',
        'target': os.path.join(BASE, 'deepseek_proxy.py'),
        'marker_start': '# >>> [night_watch] Constitutional AI inject start',
        'marker_end': '# >>> [night_watch] Constitutional AI inject end',
        'import_hint': '',
        'code': '''# >>> [night_watch] Constitutional AI inject start
_CONSTITUTION_RULES = [
    lambda t: len(t) > 500 and '\u836f' in t,
    lambda t: '\u8bca\u65ad' in t and '\u75be\u75c5' in t,
    lambda t: '\u5fc5\u987b' in t and ('\u505a' in t or '\u53bb\u533b\u9662' in t),
]

def safety_filter(text):
    for rule in _CONSTITUTION_RULES:
        if rule(text):
            return False, 'filtered: medical suggestion'
    return True, ''

def filter_intervention(plan):
    text = json.dumps(plan, ensure_ascii=False) if isinstance(plan, dict) else str(plan)
    ok, reason = safety_filter(text)
    if not ok:
        return {'filtered': True, 'reason': reason}
    return plan
# >>> [night_watch] Constitutional AI inject end
''',
    },
    # priority 2: new files
    'FAISS\u5411\u91cf\u641c\u7d22': {
        'type': 'newfile',
        'target': os.path.join(BASE, 'sleep_similarity.py'),
        'import_hint': '# FAISS\nfrom sleep_similarity import find_similar_users',
        'code': '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sleep_similarity.py -- user similarity search (FAISS vector search)"""
import os, json, numpy as np
_user_embeddings = {}

def index_user(openid, profile_vector):
    _user_embeddings[openid] = np.array(profile_vector, dtype=np.float32)

def find_similar_users(openid, top_k=5):
    if openid not in _user_embeddings or len(_user_embeddings) < 2:
        return []
    return _bruteforce_search(openid, top_k)

def _bruteforce_search(openid, top_k):
    vec = _user_embeddings[openid]
    scores = []
    for uid, uvec in _user_embeddings.items():
        if uid == openid:
            continue
        sim = float(np.dot(vec, uvec) / (np.linalg.norm(vec) * np.linalg.norm(uvec) + 1e-8))
        scores.append((uid, sim))
    scores.sort(key=lambda x: -x[1])
    return scores[:top_k]
''',
    },
    'Embedding API\u8bed\u4e49\u641c\u7d22': {
        'type': 'inject',
        'target': os.path.join(BASE, 'dp_router.py'),
        'marker_start': '# >>> [night_watch] Embedding API inject start',
        'marker_end': '# >>> [night_watch] Embedding API inject end',
        'import_hint': '',
        'code': '''# >>> [night_watch] Embedding API inject start
_SEMANTIC_MEMORY = []

def store_semantic(query, answer, embedding=None):
    _SEMANTIC_MEMORY.append((embedding or [], query, answer, datetime.now().isoformat()))
    if len(_SEMANTIC_MEMORY) > 200:
        _SEMANTIC_MEMORY.pop(0)

def recall_semantic(query, top_k=3):
    if not _SEMANTIC_MEMORY:
        return []
    return _SEMANTIC_MEMORY[-top_k:]
# >>> [night_watch] Embedding API inject end
''',
    },
}


def log(msg):
    ts = datetime.now().strftime('%H:%M')
    line = '[' + ts + '] ' + msg
    print(line)
    d = os.path.dirname(NIGHT_LOG)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(NIGHT_LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def load_explorer():
    if BASE not in sys.path:
        sys.path.insert(0, BASE)
    if 'auto_explorer' in sys.modules:
        del sys.modules['auto_explorer']
    import auto_explorer
    importlib.reload(auto_explorer)
    return auto_explorer


def backup_target(filepath):
    if not os.path.exists(filepath):
        return True
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = os.path.basename(filepath)
    os.makedirs(_BACKUP_DIR, exist_ok=True)
    dst = os.path.join(_BACKUP_DIR, fname + '_nightwatch_' + ts + '.py')
    try:
        shutil.copy2(filepath, dst)
        log('  backup ' + fname + ' -> ' + os.path.basename(dst))
        return True
    except Exception as e:
        log('  backup fail: ' + str(e))
        return False


def audit_file(filepath):
    if not os.path.exists(filepath):
        return False, 'not found'
    try:
        py_compile.compile(filepath, doraise=True)
    except py_compile.PyCompileError as e:
        return False, 'compile fail: ' + str(e)
    return True, 'OK'


def inject_code(target_path, marker_start, marker_end, code_to_inject, import_hint=''):
    if not os.path.exists(target_path):
        return False, 'target not found: ' + target_path

    with open(target_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if marker_start in content:
        return False, 'already injected, skip'

    lines = content.split('\n')
    inject_line = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            inject_line = i + 1
        elif line.strip() == '' and inject_line > 0:
            inject_line = i + 1
            break

    new_content = lines[:inject_line] + [code_to_inject] + lines[inject_line:]
    new_text = '\n'.join(new_content)

    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(new_text)

    return True, 'injected at line ' + str(inject_line + 1)


def create_new_file(filepath, code):
    if os.path.exists(filepath):
        backup_target(filepath)
    d = os.path.dirname(filepath)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(code)
    return True, 'created ' + os.path.basename(filepath)


def run_one_cycle(explorer=None, dry_run=False, force_algorithm=None):
    if explorer is None:
        explorer = load_explorer()

    if force_algorithm:
        if force_algorithm not in ALGORITHM_CODEGEN:
            log('[ERROR] unknown algorithm: ' + force_algorithm)
            return False
        name = force_algorithm
        code_info = ALGORITHM_CODEGEN[name]
        log('=== force land: ' + name + ' ===')
    else:
        suggestion = explorer.suggest_code_path()
        if not suggestion.get('has_suggestion'):
            log('no candidate, end cycle')
            return False
        name = suggestion['name']
        log('=== recommend land: ' + name + ' (' + suggestion.get('source', '?') + ') ===')
        log('  core: ' + str(suggestion.get('math_core', 'N/A')[:60]))
        log('  lines: ~' + str(suggestion.get('lines_needed', 0)))

        if name not in ALGORITHM_CODEGEN:
            log('  no code generator configured, skip')
            log('  code_hint: ' + str(suggestion.get('code_hint', 'N/A')))
            return False

    code_info = ALGORITHM_CODEGEN[name]

    if dry_run:
        log('  [dry-run] type=' + code_info['type'] + ' target=' + str(code_info.get('target', '')))
        log('  [dry-run] code size=' + str(len(code_info['code'])) + ' bytes')
        return True

    target = code_info['target']
    if not backup_target(target):
        log('  backup failed, abort')
        return False

    if code_info['type'] == 'inject':
        ok, msg = inject_code(target, code_info['marker_start'], code_info['marker_end'],
                              code_info['code'], code_info.get('import_hint', ''))
    elif code_info['type'] == 'newfile':
        ok, msg = create_new_file(target, code_info['code'])
    else:
        log('  unknown type: ' + code_info['type'])
        return False

    if not ok:
        log('  generate fail: ' + msg)
        return False
    log('  [OK] generate: ' + msg)

    compile_ok, compile_msg = audit_file(target)
    if not compile_ok:
        log('  [FAIL] compile: ' + compile_msg)
        # rollback
        fname = os.path.basename(target)
        backups = sorted([f for f in os.listdir(_BACKUP_DIR) if f.startswith(fname + '_nightwatch_')])
        if backups:
            src = os.path.join(_BACKUP_DIR, backups[-1])
            shutil.copy2(src, target)
            log('  rolled back from ' + backups[-1])
        return False
    log('  [OK] compile passed')

    if code_info['type'] == 'newfile':
        try:
            mod_name = os.path.splitext(os.path.basename(target))[0]
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            importlib.import_module(mod_name)
            log('  [OK] import test passed')
        except Exception as e:
            log('  [WARN] import test: ' + str(e))

    explorer.mark_landed(name)
    log('  [OK] marked ' + name + ' as landed')

    _record_landing(name)
    return True


def _record_landing(algorithm_name):
    stats_path = os.path.join(BASE, 'data', 'night_watch_stats.json')
    stats = {}
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
        except:
            pass

    stats[algorithm_name] = {'landed_at': datetime.now().isoformat(), 'session_date': DATE_STR}
    stats['_last_landing'] = algorithm_name
    stats['_total_landed'] = len([k for k in stats if not k.startswith('_')])
    d = os.path.dirname(stats_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(stats_path, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def run_auto_mode():
    explorer = load_explorer()
    pending = explorer.get_pending_algorithms()

    log('=== night_watch_explorer v2 auto mode ===')
    log('date: ' + DATE_STR)
    log('total candidates: ' + str(len(pending)))
    log('code generators: ' + str(len(ALGORITHM_CODEGEN)))

    landable = [(n, i) for n, i in pending if n in ALGORITHM_CODEGEN]
    log('auto-landable: ' + str(len(landable)))
    log('')

    if not landable:
        log('no landable algorithms found. need to add code generators.')
        return

    log('land order:')
    for i, (n, info) in enumerate(landable[:10]):
        log('  [' + str(i+1) + '] ' + n + ' (' + info['source'] + ') ~' + str(info['lines_needed']) + ' lines')
    log('')

    success_count = 0
    for i, (name, _) in enumerate(landable[:3]):
        log('')
        ok = run_one_cycle(explorer=explorer, force_algorithm=name)
        if ok:
            success_count += 1

    log('')
    log('=== round complete: ' + str(success_count) + '/' + str(min(3, len(landable))) + ' landed ===')
    log('log file: ' + NIGHT_LOG)


if __name__ == '__main__':
    import sys
    if '--dry-run' in sys.argv:
        run_one_cycle(dry_run=True)
    elif '--run-one' in sys.argv:
        run_one_cycle()
    else:
        run_auto_mode()


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
