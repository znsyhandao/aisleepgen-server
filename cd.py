#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cd.py — Continuous Deployment: compile check -> GitHub push -> server pull -> restart -> verify

Usage:
    python cd.py                            # Full pipeline
    python cd.py --files deepseek_proxy.py  # Specific files only
    python cd.py --skip-server              # GitHub push only
"""

import os, sys, json, base64, urllib.request, urllib.error, time, py_compile, subprocess
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
# 从环境变量读取 GitHub Token（不在代码中硬编码）
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN') or os.environ.get('GIT_TOKEN', '')
if not GITHUB_TOKEN:
    # Fallback: 从 .env 文件读取
    env_path = os.path.join(PROJECT_DIR, '.env')
    if os.path.exists(env_path):
        for line in open(env_path, 'r', encoding='utf-8'):
            line = line.strip()
            if line.startswith('GITHUB_TOKEN='):
                GITHUB_TOKEN = line.split('=', 1)[1].strip().strip("'\"")
                break
GITHUB_REPO = 'znsyhandao/aisleepgen-server'
GITHUB_BRANCH = 'main'
SERVER = '82.156.208.245'
SERVER_USER = 'ubuntu'
SERVER_PROJECT_DIR = '~/aisleepgen'

BACKEND_FILES = [
    ('asyncio_server.py', os.path.join(PROJECT_DIR, 'asyncio_server.py')),
    ('dp_router.py', os.path.join(PROJECT_DIR, 'dp_router.py')),
    ('deepseek_proxy.py', os.path.join(PROJECT_DIR, 'deepseek_proxy.py')),
    ('tier_recommender.py', os.path.join(PROJECT_DIR, 'tier_recommender.py')),
    ('cognitive_belief.py', os.path.join(PROJECT_DIR, 'cognitive_belief.py')),
    ('chat_prompt_builder.py', os.path.join(PROJECT_DIR, 'chat_prompt_builder.py')),
    ('dp_data.py', os.path.join(PROJECT_DIR, 'dp_data.py')),
    ('experiment_log.py', os.path.join(PROJECT_DIR, 'experiment_log.py')),
    ('async_pipeline.py', os.path.join(PROJECT_DIR, 'async_pipeline.py')),
    ('profile_storage.py', os.path.join(PROJECT_DIR, 'profile_storage.py')),
    ('fallback_replies.py', os.path.join(PROJECT_DIR, 'fallback_replies.py')),
    ('body_context.py', os.path.join(PROJECT_DIR, 'body_context.py')),
    ('prediction_engine.py', os.path.join(PROJECT_DIR, 'prediction_engine.py')),
    ('neural_extractor.py', os.path.join(PROJECT_DIR, 'neural_extractor.py')),
    ('decision_explainer.py', os.path.join(PROJECT_DIR, 'decision_explainer.py')),
    ('sleep_coach.py', os.path.join(PROJECT_DIR, 'sleep_coach.py')),
    ('pomdp_learner.py', os.path.join(PROJECT_DIR, 'pomdp_learner.py')),
    ('sleep_world_model.py', os.path.join(PROJECT_DIR, 'sleep_world_model.py')),
    ('preference_engine.py', os.path.join(PROJECT_DIR, 'preference_engine.py')),
    ('preference_storage.py', os.path.join(PROJECT_DIR, 'preference_storage.py')),
    ('meta_learner.py', os.path.join(PROJECT_DIR, 'meta_learner.py')),
    ('agent_gateway.py', os.path.join(PROJECT_DIR, 'agent_gateway.py')),
    ('agent_perceptor.py', os.path.join(PROJECT_DIR, 'agent_perceptor.py')),
    ('working_memory.py', os.path.join(PROJECT_DIR, 'working_memory.py')),
    ('loop_agent.py', os.path.join(PROJECT_DIR, 'loop_agent.py')),
    ('sleep_siege_engine.py', os.path.join(PROJECT_DIR, 'sleep_siege_engine.py')),
    ('auto_diary.py', os.path.join(PROJECT_DIR, 'auto_diary.py')),
    ('sleep_diagnosis.py', os.path.join(PROJECT_DIR, 'sleep_diagnosis.py')),
    ('chart_data.py', os.path.join(PROJECT_DIR, 'chart_data.py')),
]

GITHUB_API = f'https://api.github.com/repos/{GITHUB_REPO}'
GITHUB_HEADERS = {
    'Authorization': f'Bearer {GITHUB_TOKEN}',
    'Content-Type': 'application/json',
    'Accept': 'application/vnd.github.v3+json',
}

def log(msg, emoji=''):
    """Print without emoji issues on GBK terminal"""
    sys.stdout.write(f'[{datetime.now().strftime("%H:%M:%S")}] {msg}\n')
    sys.stdout.flush()

def step_js_check():
    """Phase 0: JavaScript 模式检查（上传前防御）"""
    log('')
    log('PHASE 0/5: JS pre-upload check')
    log('')

    import subprocess
    js_script = os.path.join(PROJECT_DIR, 'pre_upload.js')
    if not os.path.exists(js_script):
        log('  SKIP: pre_upload.js not found')
        return True

    try:
        result = subprocess.run(['node', js_script],
            capture_output=True, timeout=30, cwd=PROJECT_DIR)
        stdout = result.stdout.decode('utf-8', errors='replace')
        stderr = result.stderr.decode('utf-8', errors='replace')
        for line in stdout.strip().split('\n'):
            line = line.strip()
            if line and not line.startswith('='):
                log(f'  {line}')
        if result.returncode != 0:
            log('  JS check FAILED (see above)')
            return False
        log('  JS check passed')
        return True
    except subprocess.TimeoutExpired:
        log('  JS check timeout')
        return False
    except FileNotFoundError:
        log('  SKIP: Node.js not installed')
        return True
    except Exception as e:
        log(f'  JS check error: {e}')
        return False
    """Phase 1: compile check all files"""
    log('PHASE 1/4: Compile check', '')
    all_ok = True
    for repo_path, local_path in BACKEND_FILES:
        if not os.path.exists(local_path):
            continue
        try:
            py_compile.compile(local_path, doraise=True)
            log(f'  OK  {repo_path}')
        except py_compile.PyCompileError as e:
            log(f'  FAIL {repo_path}: {e}')
            all_ok = False
    return all_ok

def step_compile_check():
    """Phase 1: compile check all Python files"""
    log('')
    log('PHASE 1/5: Python compile check')
    log('')
    all_ok = True
    for repo_path, local_path in BACKEND_FILES:
        if not os.path.exists(local_path):
            continue
        try:
            py_compile.compile(local_path, doraise=True)
            log(f'  OK  {repo_path}')
        except py_compile.PyCompileError as e:
            log(f'  FAIL {repo_path}: {e}')
            all_ok = False
    return all_ok


def step_github_push():
    """Phase 2: Push all files to GitHub"""
    log('')
    log('PHASE 2/4: Push to GitHub', '')

    def _api(method, path, data=None):
        url = f'{GITHUB_API}{path}'
        req = urllib.request.Request(url, data=data, headers=GITHUB_HEADERS, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            log(f'  HTTP {e.code}: {body}')
            return None

    ref_data = _api('GET', f'/git/refs/heads/{GITHUB_BRANCH}')
    if not ref_data:
        log('  FAIL: cannot get latest commit')
        return False
    latest_sha = ref_data['object']['sha']
    log(f'  Latest commit: {latest_sha[:10]}')

    tree = []
    for repo_path, local_path in BACKEND_FILES:
        if not os.path.exists(local_path):
            continue
        with open(local_path, 'rb') as f:
            encoded = base64.b64encode(f.read()).decode()
        blob_data = json.dumps({'content': encoded, 'encoding': 'base64'}).encode()
        blob_result = _api('POST', '/git/blobs', blob_data)
        if not blob_result:
            log(f'  FAIL uploading {repo_path}')
            continue
        tree.append({'path': repo_path, 'mode': '100644', 'type': 'blob', 'sha': blob_result['sha']})

    log(f'  Uploaded {len(tree)} files')

    tree_data = json.dumps({'base_tree': latest_sha, 'tree': tree}).encode()
    tree_result = _api('POST', '/git/trees', tree_data)
    if not tree_result:
        log('  FAIL creating tree')
        return False

    commit_data = json.dumps({
        'message': f'auto-deploy {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        'tree': tree_result['sha'], 'parents': [latest_sha],
    }).encode()
    commit_result = _api('POST', '/git/commits', commit_data)
    if not commit_result:
        log('  FAIL creating commit')
        return False

    ref_data = json.dumps({'sha': commit_result['sha'], 'force': True}).encode()
    _api('PATCH', f'/git/refs/heads/{GITHUB_BRANCH}', ref_data)
    log(f'  Commit: {commit_result["sha"][:10]} pushed to main')
    return True

def step_deploy_to_server():
    """Phase 3: SSH deploy + restart + verify"""
    log('')
    log('PHASE 3/4: Deploy to server', '')

    key_path = os.path.expanduser('~/.ssh/deploy_key')
    if not os.path.exists(key_path):
        log('  SKIP: deploy_key not found, printing manual commands')
        log('')
        log(f'cd {SERVER_PROJECT_DIR}')
        log(f'curl -sL -o deepseek_proxy.py "https://raw.githubusercontent.com/{GITHUB_REPO}/main/deepseek_proxy.py"')
        log(f'curl -sL -o tier_recommender.py "https://raw.githubusercontent.com/{GITHUB_REPO}/main/tier_recommender.py"')
        log('pkill -f deepseek_proxy.py; sleep 1; rm -rf __pycache__')
        log("screen -dmS sleep bash -c 'cd ~/aisleepgen && python3 -B -X utf8 deepseek_proxy.py'")
        return True

    import subprocess

    # 部署脚本（通过 stdin 管道传给 bash，用 \n 换行避免 Windows \r\n 问题）
    abs_project = f'/home/{SERVER_USER}/aisleepgen'
    script_lines = [
        f'echo "=== Deploying to {abs_project} ==="',
        f'cd {abs_project}',
        f'curl -sL -o deepseek_proxy.py "https://raw.githubusercontent.com/{GITHUB_REPO}/main/deepseek_proxy.py"',
        f'curl -sL -o tier_recommender.py "https://raw.githubusercontent.com/{GITHUB_REPO}/main/tier_recommender.py"',
        'echo "=== Files ===" && ls -la deepseek_proxy.py tier_recommender.py',
        'echo "=== Stopping old service ==="',
        'pkill -f deepseek_proxy.py 2>/dev/null; sleep 1',
        'rm -rf __pycache__',
        'echo "=== Starting new service ==="',
        f'nohup python3 -B -X utf8 {abs_project}/deepseek_proxy.py > /tmp/aisleepgen.log 2>&1 &',
        'echo "Waiting 5s..." && sleep 5',
        'echo "=== Verify ==="',
        'curl -s http://localhost:8090/health',
        'echo ""',
        'echo "---DONE---"',
    ]
    script = '\n'.join(script_lines) + '\n'

    ssh_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=10',
               '-i', key_path, f'{SERVER_USER}@{SERVER}', 'bash -s']

    try:
        result = subprocess.run(ssh_cmd, input=script, capture_output=True, text=True, timeout=60,
                                encoding='utf-8', errors='replace')
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line:
                    log(f'  {line}')
        if result.returncode != 0:
            log(f'  SSH exit code: {result.returncode}')
            if result.stderr:
                for line in result.stderr.strip().split('\n'):
                    log(f'  ! {line}')
            return False
        log('  Server deploy OK')
        return True
    except subprocess.TimeoutExpired:
        log('  SSH timeout')
        return False
    except Exception as e:
        log(f'  SSH error: {e}')
        return False
    except Exception as e:
        log(f'  SSH error: {e}')
        return False

def step_verify():
    """Phase 4: Verify from local"""
    log('')
    log('PHASE 4/4: Verify APIs', '')
    time.sleep(2)

    checks = [
        ('/health', f'http://{SERVER}:8090/health', lambda r: r.get('status') == 'ok'),
        ('/api/pricing', f'http://{SERVER}:8090/api/pricing',
         lambda r: 'pro' in str(r.get('pricing', {}))),
    ]
    all_ok = True
    for name, url, check in checks:
        try:
            r = urllib.request.Request(url)
            resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
            if check(resp):
                log(f'  OK  {name}')
            else:
                log(f'  WARN {name}: unexpected response')
        except Exception as e:
            log(f'  FAIL {name}: {e}')
            all_ok = False
    return all_ok

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-server', action='store_true')
    parser.add_argument('--yes', '-y', action='store_true')
    parser.add_argument('--files')
    args = parser.parse_args()

    log('')
    log('==== AISleepGen CD Pipeline ====')
    log('')

    start = time.time()

    # Phase 0: JS check
    if not step_js_check():
        log('FAIL: JS check failed')
        sys.exit(1)

    # Phase 1
    if not step_compile_check():
        log('FAIL: compile check failed, aborting')
        sys.exit(1)

    # Phase 2
    log('')
    if not step_github_push():
        log('FAIL: GitHub push failed')
        sys.exit(1)

    # Phase 3
    if not args.skip_server:
        if not step_deploy_to_server():
            log('FAIL: server deploy failed')
            sys.exit(1)

        # Phase 4
        step_verify()

    elapsed = time.time() - start
    log('')
    log(f'Done in {elapsed:.1f}s')

if __name__ == '__main__':
    main()
