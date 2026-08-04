"""全面健康检查 — 扫描崩溃隐患、文件完整性、路由覆盖、编码问题"""
import os, sys, json, py_compile, traceback

sys.stdout.reconfigure(encoding='utf-8')

BASE = r'D:\AISleepGen_Optimized'
results = {'pass': 0, 'fail': 0, 'warnings': []}

def ok(msg):
    results['pass'] += 1
    print(f'  ✅ {msg}')

def fail(msg):
    results['fail'] += 1
    print(f'  ❌ {msg}')

def warn(msg):
    results['warnings'].append(msg)
    print(f'  ⚠️  {msg}')

print('=' * 50)
print('🍬 小甜甜全面健康检查')
print('=' * 50)

# 1. 编译检查
print('\n--- 1. 编译检查 ---')
main_file = os.path.join(BASE, 'deepseek_proxy.py')
try:
    py_compile.compile(main_file, doraise=True)
    ok('deepseek_proxy.py 编译通过')
except py_compile.PyCompileError as e:
    fail(f'编译错误: {e}')

# 2. _send_json 定义检查
print('\n--- 2. 关键方法定义检查 ---')
with open(main_file, 'r', encoding='utf-8') as f:
    content = f.read()

calls = content.count('self._send_json(')
defs = content.count('def _send_json(')
if calls > 0 and defs == 0:
    fail(f'_send_json() 被调用 {calls} 次但未定义！崩溃源头')
elif defs > 0:
    ok(f'_send_json() 已定义，被调用 {calls} 次')
else:
    ok('_send_json() 未使用')

# 检查其他常用方法
for method in ['_set_headers', '_get_openid', '_handle_memory_recall', 
               '_handle_chat', '_handle_goodnight', '_handle_clinical_report',
               '_do_self_heal', '_handle_emotion_timeline', '_handle_conversation_summaries',
               'do_POST', 'do_GET']:
    if f'def {method}(' in content:
        ok(f'{method}() 已定义')
    else:
        warn(f'{method}() 未找到定义')

# 3. stop-breathing 路由检查
print('\n--- 3. 路由完整性检查 ---')
routes_found = []
for line in content.split('\n'):
    if "path == '/api/" in line:
        route = line.strip().split("path == '")[1].split("'")[0] if "'" in line else '?'
        routes_found.append(route)

required_routes = [
    '/api/stop-breathing', '/api/relax-feedback', '/api/memory/recall',
    '/api/chat', '/api/sleep-stats', '/api/onboarding-status',
    '/api/history', '/api/timeline', '/api/data-export',
    '/api/self-heal', '/api/wx-login', '/api/update-profile',
    '/api/feedback', '/api/goodnight', '/api/clinical-report',
    '/api/emotion-timeline', '/api/conversation-summaries',
    '/api/mark-brief-read', '/api/prediction-stats',
    '/api/pubmed-update', '/api/pubmed-recent',
    '/api/create-order', '/api/pay-callback', '/api/pricing',
    '/api/recommend-tier', '/api/user-profile',
    '/api/sleep-chart', '/api/sleep-details',
    '/api/relax-presets', '/api/start-breathing',
]

for route in required_routes:
    if route in routes_found:
        ok(f'路由 {route}')
    else:
        if 'relax-feedback' in route or 'stop-breathing' in route:
            fail(f'路由 {route} 缺失 — 昨晚测试报错')
        else:
            warn(f'路由 {route} 未找到')

# 4. 文件完整性
print('\n--- 4. 文件完整性 ---')
for fname in ['user_profile.json', 'deepseek_proxy.py', 'dp_router.py', 'feedback_routes.py',
              'audio_library_engine.py', 'sleep_world_model.py', 'recommendation_tracker.py']:
    fpath = os.path.join(BASE, fname)
    if os.path.exists(fpath):
        try:
            if fname.endswith('.json'):
                with open(fpath, 'r', encoding='utf-8') as f:
                    json.load(f)
                ok(f'{fname} 可解析')
            else:
                py_compile.compile(fpath, doraise=True)
                ok(f'{fname} 编译通过')
        except Exception as e:
            fail(f'{fname} 异常: {e}')
    else:
        warn(f'{fname} 不存在')

# 5. 编码问题检查 (GBK/UTF-8)
print('\n--- 5. 编码安全性检查 ---')
with open(main_file, 'rb') as f:
    raw = f.read()
try:
    raw.decode('utf-8')
    ok('deepseek_proxy.py 纯 UTF-8')
except UnicodeDecodeError:
    fail('deepseek_proxy.py 包含非 UTF-8 字节（GBK污染风险）')

# 检查所有 Python 文件的编码
bad_enc = []
for f in os.listdir(BASE):
    if f.endswith('.py') and f != os.path.basename(__file__):
        fpath = os.path.join(BASE, f)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                fh.read()
        except UnicodeDecodeError:
            bad_enc.append(f)
        except Exception:
            pass

if bad_enc:
    fail(f'以下文件不是 UTF-8 编码: {bad_enc}')
else:
    ok('所有 .py 文件 UTF-8 编码正常')

# 6. 目录存在性
print('\n--- 6. 目录结构 ---')
required_dirs = ['user_profiles', 'data', 'logs', 'cached_responses', '__pycache__']
for d in required_dirs:
    if os.path.isdir(os.path.join(BASE, d)):
        ok(f'{d}/ 存在')
    else:
        warn(f'{d}/ 不存在（可能不影响运行）')

# 7. 检查异常处理（too broad except 和 pass）
print('\n--- 7. 异常处理审计 ---')
broad_except_count = 0
try:
    import ast
except ImportError:
    warn('无法导入 ast 模块，跳过异常审计')
else:
    # 简单检查 except: pass 模式
    lines = content.split('\n')
    in_try = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith('try:'):
            in_try = True
        elif in_try and stripped == 'pass':
            prev_line = lines[i-2].strip() if i >= 2 else ''
            if prev_line.startswith('except'):
                warn(f'第 {i} 行: except: pass — 隐藏异常')
                broad_except_count += 1
            in_try = False
        elif stripped.startswith(('def ', 'class ', 'if ', 'elif ', 'else:')):
            in_try = False

    if broad_except_count == 0:
        ok('没有发现 except: pass')
    else:
        fail(f'发现 {broad_except_count} 处 except: pass')

# 8. 废弃文件检测（防误删！含4种引用方式）
print('\n--- 8. 废弃文件检测---')
orphan_candidates = []
all_py_files = sorted([f for f in os.listdir(BASE) if f.endswith('.py') and f != '__init__.py'])

# 读取所有文件内容
all_content = {}
for f in all_py_files:
    fp = os.path.join(BASE, f)
    try:
        all_content[f] = open(fp, encoding='utf-8', errors='replace').read()
    except:
        all_content[f] = ''

for f in all_py_files:
    name = f[:-3]
    size = os.path.getsize(os.path.join(BASE, f))
    
    # 未引用阈值：小型文件（<12KB）且未被引用
    if size > 12000:
        continue
    
    referenced = False
    for pf, pc in all_content.items():
        if pf == f:
            continue  # 不自检
        
        # ── 4种引用方式全检查 ──
        # ① 显式 import
        if f'import {name}' in pc:
            referenced = True; break
        if f'from {name}' in pc:
            referenced = True; break
        # ② subprocess/exec/os.system 跨进程调用
        if f"'{name}'" in pc or f'"{name}"' in pc:
            referenced = True; break
        if f'{name}.py' in pc:
            referenced = True; break
        # ③ __import__ 动态加载
        if f'__import__("{name}")' in pc or f"__import__('{name}')" in pc:
            referenced = True; break
        # ④ .pth/ 模块路径引用
        if f'/{name}.py' in pc:
            referenced = True; break
    
    if not referenced:
        orphan_candidates.append(f)

if orphan_candidates:
    warn(f'{len(orphan_candidates)} 个文件未被任何代码引用（可能是废弃文件）：')
    for f in orphan_candidates:
        sz = os.path.getsize(os.path.join(BASE, f))
        warn(f'   {f} ({sz} bytes)')
else:
    ok('未发现废弃文件')

# 8. 端口占用检查
print('\n--- 9. 端口状态（运行时检查）---')
try:
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 8090))
    if result == 0:
        ok('端口 8090 已被占用（deepseek_proxy 可能正在运行）')
    else:
        ok('端口 8090 空闲')
    sock.close()
except Exception as e:
    warn(f'端口检查异常: {e}')

# 9. 轨迹预测模型状态
print('\n--- 10. 轨迹预测模型状态 ---')
try:
    sys.path.insert(0, BASE)
    from trajectory_model_db import get_model_info
    info = get_model_info()
    if info['model_ready']:
        ok(f'LightGBM 轨迹模型就绪（{info["training_samples"]} 条样本训练）')
    elif info['total_samples'] >= 30:
        warn(f'有 {info["total_samples"]} 条样本但模型未加载（需检查日志）')
    else:
        ok(f'轨迹预测降级模式（仅 {info["total_samples"]} 条样本，需≥30 激活 LightGBM）')
except Exception as e:
    warn(f'轨迹模型检查异常: {e}')
    info = {'total_samples': 0, 'model_ready': False}

# 汇总
print()
print('=' * 50)
print(f'📊 结果汇总: ✅ {results["pass"]}  ❌ {results["fail"]}  ⚠️  {len(results["warnings"])}')
if results['fail'] > 0:
    print(f'🔥 {results["fail"]} 个失败项需要修复！')
if results['warnings']:
    print(f'⚠️  {len(results["warnings"])} 个警告项')
print('=' * 50)
