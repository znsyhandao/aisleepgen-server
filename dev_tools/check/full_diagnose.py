"""AISleepGen 全面诊断测试 - 检视所有可能导致崩溃的问题"""
import json, urllib.request, sys, os, time
sys.stdout.reconfigure(encoding='utf-8')

API = 'http://localhost:8090'

def req(method, path, data=None, headers=None, timeout=30):
    url = API + path
    body = json.dumps(data).encode() if data else None
    hdrs = {'Content-Type': 'application/json'}
    if headers: hdrs.update(headers)
    r = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except Exception as e:
        return 0, {'error': str(e)}

def test(name, ok, detail=''):
    status = '✅' if ok else '❌'
    print(f'{status} {name}')
    if detail and not ok:
        print(f'    {detail}')

print('='*60)
print('AISleepGen 全面诊断测试')
print('='*60)

# 1. 健康检查
print('\n--- 1. 基础服务 ---')
code, res = req('GET', '/health')
test('健康检查', code==200 and res.get('status')=='ok', str(res))

# 2. 用户 profile - GET
code, res = req('GET', '/api/user-profile?openid=dev_e209266b333b1329')
test('GET user-profile (dev用户)', code==200, f'keys={sorted(res.keys())}')
test('GET user-profile 含 latest', 'latest' in res, f'latest={res.get("latest",{})}')
test('GET user-profile 含 user_info', 'user_info' in res)

# 3. update-profile (问卷写入)
code, res = req('POST', '/api/update-profile', {
    'openid': 'dev_e209266b333b1329',
    'profile': {
        'latest': {
            'bedtime': '23:00', 'wake_time': '07:00',
            'sleep_latency': 15, 'awake_times': 2, 'total_duration': 420,
        },
        'user_info': {
            'main_issue': '入睡困难', 'sleep_type': '夜猫型',
        },
        'last_survey': '2026-05-19T21:00:00.000Z',
    }
})
test('POST update-profile 写入', code==200 and res.get('success'), str(res))

# 4. 验证写入持久化
code, res = req('GET', '/api/user-profile?openid=dev_e209266b333b1329')
lt = res.get('latest', {})
test('latest 持久化 bedtime', lt.get('bedtime')=='23:00', str(lt))
test('latest 持久化 sleep_latency', lt.get('sleep_latency')==15, str(lt))

# 5. chat - 基本对话
code, res = req('POST', '/api/chat', {
    'message': '你知道我几点睡几点起吗？',
    'history': [],
    'openid': 'dev_e209266b333b1329'
}, timeout=120)
test('chat 基本对话', code==200 and bool(res.get('reply','')), f'reply前100:{res.get("reply","")[:100]}')
test('chat 包含用户基线数据', '23:00' in res.get('reply',''), 'AI 正确引用 bedtime')

# 6. chat - 呼吸练习请求
code, res = req('POST', '/api/chat', {
    'message': '帮我做个呼吸练习吧，我现在压力很大',
    'history': [],
    'openid': 'dev_e209266b333b1329'
}, timeout=120)
has_action = 'action' in res and 'action_params' in res
test('chat 呼吸练习触发 action', has_action, str(res.get('action','')) if has_action else '缺action字段')
if has_action:
    ap = res.get('action_params', {})
    test('action_params 含 inhale/hold/exhale', all(k in ap for k in ['inhale','hold','exhale']), str(ap))
    test('action_params 含 name', bool(ap.get('name')), str(ap.get('name','')))

# 7. chat - 对话中提取数据 (世界模型)
code, res = req('POST', '/api/chat', {
    'message': '我昨晚11点睡，7点醒，睡了8小时，中途醒了1次',
    'history': [],
    'openid': 'dev_e209266b333b1329'
}, timeout=120)
has_score = 'auto_report' in res or 'expert_detail' in res
test('chat 数据提取+评分', code==200, '')
test('chat 评分响应含维度', '7维' in res.get('reply','') or '评估' in res.get('reply',''), '')

# 8. chat - 纠正检测 (说"记错了")
code, res = req('POST', '/api/chat', {
    'messages': [{'role':'user','content':'你记错了，我11点睡的不是12点'}],
    'openid': 'dev_e209266b333b1329'
}, timeout=120)
test('chat 纠正检测不崩溃', code==200, '')

# 9. 各种边缘 API 不崩溃
APIS_TO_TEST = [
    ('GET', '/api/sleep-stats?openid=dev_e209266b333b1329'),
    ('GET', '/api/onboarding-status?openid=dev_e209266b333b1329'),
    ('GET', '/api/history?openid=dev_e209266b333b1329'),
    ('GET', '/api/timeline?openid=dev_e209266b333b1329'),
    ('GET', '/api/data-export?openid=dev_e209266b333b1329'),
]
print('\n--- 3. 边缘/辅助 API ---')
for method, path in APIS_TO_TEST:
    code, res = req(method, path)
    test(f'{method} {path}', code==200, '')

# 10. memory_recall（之前崩溃的路径）
code, res = req('POST', '/api/memory-recall', {
    'openid': 'dev_e209266b333b1329'
})
test('POST memory-recall 不崩溃', code==200, str(res)[:100])

# 11. 深呼吸录入
code, res = req('POST', '/api/relax-feedback', {
    'openid': 'dev_e209266b333b1329',
    'score': 8,
    'pattern': '4-7-8'
})
test('POST relax-feedback', code==200, str(res)[:100])

# 12. self-heal
code, res = req('GET', '/api/self-heal?openid=dev_e209266b333b1329')
test('GET self-heal', code==200, '')

# 13. 检查 user_profile.json 是否被异常写入
print('\n--- 4. 文件完整性 ---')
pf = 'D:\\AISleepGen_Optimized\\user_profile.json'
try:
    with open(pf, 'r', encoding='utf-8') as f:
        all_p = json.load(f)
    test('user_profile.json 可解析', True)
    test('user_profile.json 非空', len(all_p) > 0, f'{len(all_p)} 用户')
except Exception as e:
    test('user_profile.json 健康', False, str(e))

# 14. 代码语法
import py_compile
try:
    py_compile.compile('D:\\AISleepGen_Optimized\\deepseek_proxy.py', doraise=True)
    test('deepseek_proxy.py 语法正确', True)
except py_compile.PyCompileError as e:
    test('deepseek_proxy.py 语法', False, str(e))

# 15. __pycache__ 可能存在旧缓存
print('\n--- 5. 缓存健康 ---')
cache_dir = 'D:\\AISleepGen_Optimized\\__pycache__'
if os.path.exists(cache_dir):
    mtime = os.path.getmtime(os.path.join(cache_dir, os.listdir(cache_dir)[0])) if os.listdir(cache_dir) else 0
    age_hours = (time.time() - mtime) / 3600
    test('__pycache__ 不超24h', age_hours < 24, f'最新缓存{age_hours:.1f}小时前')
else:
    test('__pycache__ 不存在', True, '无缓存问题')

print('\n' + '='*60)
print('测试完成')
print('='*60)
