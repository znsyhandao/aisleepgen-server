"""单进程串行测试 - 无并发连接"""
import json, urllib.request, sys, os, time, py_compile
sys.stdout.reconfigure(encoding='utf-8')

API = 'http://localhost:8090'
PASS = 0
FAIL = 0

def req(method, path, data=None, timeout=30):
    url = API + path
    body = json.dumps(data).encode() if data else None
    r = urllib.request.Request(url, data=body, headers={'Content-Type':'application/json'}, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except Exception as e:
        return 0, {'error': str(e)}

def check(name, ok, detail=''):
    global PASS, FAIL
    icon = '✅' if ok else '❌'
    print(f'{icon} {name}')
    if not ok and detail:
        print(f'   {detail[:200]}')
    if ok: PASS += 1
    else: FAIL += 1

print('='*60)
print('AISleepGen 串行诊断')
print('='*60)

# 1. 健康
code, r = req('GET', '/health')
check('健康检查', code==200)

# 2. 语法
try:
    py_compile.compile('D:\\AISleepGen_Optimized\\deepseek_proxy.py', doraise=True)
    check('代码语法', True)
except Exception as e:
    check('代码语法', False, str(e))

# 3. GET user-profile
code, r = req('GET', '/api/user-profile?openid=dev_e209266b333b1329')
check('GET user-profile', code==200 and 'latest' in r)

# 4. update-profile (写入扁平数据)
code, r = req('POST', '/api/update-profile', {
    'openid': 'default',
    'profile': {'latest': {'bedtime':'23:00','wake_time':'07:00','sleep_latency':15,'awake_times':2,'total_duration':420}}
})
check('POST update-profile', code==200 and r.get('success'))

# 5. 验证 latest 持久化
code, r = req('GET', '/api/user-profile?openid=default')
check('GET latest 有 bedtime', r.get('latest',{}).get('bedtime')=='23:00')

# 6. chat - 你知道我几点睡几点起吗
code, r = req('POST', '/api/chat', {'message':'你知道我几点睡几点起吗？','history':[],'openid':'default'}, timeout=120)
reply = r.get('reply','')
check('chat 响应', code==200 and bool(reply))
check('chat 含基线数据', '23:00' in reply or '23点' in reply or '07:00' in reply)

# 7. chat - 呼吸练习
code, r = req('POST', '/api/chat', {'message':'帮我做个呼吸练习吧，我现在压力很大','history':[],'openid':'default'}, timeout=120)
has_action = r.get('action') == 'start_breathing' and 'action_params' in r
check('chat 呼吸练习 action', has_action)
if has_action:
    ap = r['action_params']
    check('呼吸参数完整', all(k in ap for k in ['inhale','hold','exhale','rounds','name']))

# 8. chat - 数据提取评分
code, r = req('POST', '/api/chat', {'message':'我昨晚11点睡7点起，睡了8小时醒了一次','history':[],'openid':'default'}, timeout=120)
check('chat 数据提取', code==200 and bool(r.get('reply','')))

# 9. chat - 纠正
code, r = req('POST', '/api/chat', {'messages':[{'role':'user','content':'你记错了，我11点睡的不是12点'}],'openid':'default'}, timeout=120)
check('chat 纠正检测不崩溃', code==200)

# 10. chat - 空消息
code, r = req('POST', '/api/chat', {'message':'','history':[],'openid':'default'}, timeout=120)
check('chat 空消息', code==200)

# 11. stop-breathing
code, r = req('POST', '/api/stop-breathing', {'openid':'default'})
check('stop-breathing', code==200)

# 12. relax-feedback
code, r = req('POST', '/api/relax-feedback', {'openid':'default','score':8,'pattern':'4-7-8'})
check('relax-feedback', code==200)

# 13. 所有GET接口
for ep in ['sleep-stats','onboarding-status','history','timeline','data-export','self-heal']:
    code, r = req('GET', f'/api/{ep}?openid=default')
    check(f'GET /api/{ep}', code==200)

# 14. memory-recall
code, r = req('POST', '/api/memory-recall', {'openid':'default'})
check('memory-recall', code==200)

# 15. chat - 冥想
code, r = req('POST', '/api/chat', {'message':'我想做冥想放松','history':[],'openid':'default'}, timeout=120)
check('chat 冥想引导', code==200)

# 16. 小程序格式的 chat（message 字段）
code, r = req('POST', '/api/chat', {'message':'睡前放松方法','history':[],'openid':'default'}, timeout=120)
check('chat message格式', code==200)

print('\n' + '='*60)
print(f'总计: {PASS}✅ / {FAIL}❌  ({PASS+FAIL}项)')
print('='*60)
