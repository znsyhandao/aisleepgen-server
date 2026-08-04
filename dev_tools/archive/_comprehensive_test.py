"""全面 API 测试 — 覆盖昨晚测试报错 + 所有主要路由"""
import urllib.request, json, sys, time, urllib.error, os

sys.stdout.reconfigure(encoding='utf-8')

API = os.environ.get('API', 'http://127.0.0.1:8090')

PASS = 0
FAIL = 0
STOP_ON_ERROR = False  # 设为True则第一个失败停止

def check(name, method='GET', path='/health', data=None):
    global PASS, FAIL
    try:
        if method == 'GET':
            r = urllib.request.Request(f'{API}{path}')
        else:
            body = json.dumps(data).encode() if data else b'{}'
            r = urllib.request.Request(f'{API}{path}', data=body,
                headers={'Content-Type': 'application/json'}, method=method)
        resp = json.loads(urllib.request.urlopen(r, timeout=10).read())
        print(f'  ✅ {name}')
        PASS += 1
        return resp
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'  ❌ {name} — HTTP {e.code}: {body[:200]}')
        FAIL += 1
        if STOP_ON_ERROR:
            raise
        return None
    except Exception as e:
        print(f'  ❌ {name} — {str(e)[:200]}')
        FAIL += 1
        if STOP_ON_ERROR:
            raise
        return None

print('=' * 55)
print('🍬 小甜甜全面API测试')
print(f'Server: {API}')
print(f'Started: {time.strftime("%H:%M:%S")}')
print('=' * 55)

# ===== 0. Health =====
print('\n--- 0. 基础健康检查 ---')
check('GET /health', 'GET', '/health')

# ===== 1. 昨晚失败路由 =====
print('\n--- 1. 昨晚失败了的路由 ---')
check('POST /api/stop-breathing', 'POST', '/api/stop-breathing', {'openid': 'test123'})
check('POST /api/relax-feedback', 'POST', '/api/relax-feedback', {'openid': 'test123', 'action': 'breathing'})

# ===== 2. Chat =====
print('\n--- 2. AI对话 ---')
check('POST /api/chat (normal)', 'POST', '/api/chat', {'openid': 'test123', 'text': '我今天睡眠怎么样'})
check('POST /api/chat (empty)', 'POST', '/api/chat', {'openid': 'test123', 'text': ''})
check('POST /api/chat (wrong data)', 'POST', '/api/chat', {})  # 无openid

# ===== 3. 用户系统 =====
print('\n--- 3. 用户系统 ---')
check('POST /api/wx-login', 'POST', '/api/wx-login', {'code': 'test_code'})
check('POST /api/update-profile', 'POST', '/api/update-profile', {'openid': 'test123', 'nickname': '测试用户'})
check('POST /api/user-profile', 'POST', '/api/user-profile', {'openid': 'test123'})
check('POST /api/onboarding-status', 'POST', '/api/onboarding-status', {'openid': 'test123'})

# ===== 4. 数据查询 =====
print('\n--- 4. 数据查询 ---')
check('GET /api/sleep-stats', 'GET', '/api/sleep-stats?openid=test123')
check('GET /api/history', 'GET', '/api/history?openid=test123')
check('GET /api/timeline', 'GET', '/api/timeline?openid=test123')
check('GET /api/data-export', 'GET', '/api/data-export?openid=test123')

# ===== 5. 记忆系统 =====
print('\n--- 5. 记忆系统 ---')
check('POST /api/memory/recall', 'POST', '/api/memory/recall', {'openid': 'test123'})

# ===== 6. 自愈系统 =====
print('\n--- 6. 自愈系统 ---')
check('GET /api/self-heal', 'GET', '/api/self-heal')

# ===== 7. 情绪追踪 =====
print('\n--- 7. 情绪/时间线 ---')
check('POST /api/emotion-timeline', 'POST', '/api/emotion-timeline', {'openid': 'test123'})
check('POST /api/conversation-summaries', 'POST', '/api/conversation-summaries', {'openid': 'test123'})

# ===== 8. 晚安/临床报告 =====
print('\n--- 8. 晚安/临床报告 ---')
check('POST /api/goodnight', 'POST', '/api/goodnight', {'openid': 'test123'})
check('POST /api/clinical-report', 'POST', '/api/clinical-report', {'openid': 'test123'})

# ===== 9. 支付= ====
print('\n--- 9. 支付/推荐 ---')
check('GET /api/pricing', 'GET', '/api/pricing')
check('POST /api/recommend-tier', 'POST', '/api/recommend-tier', {'openid': 'test123'})

# ===== 10. 反馈 =====
print('\n--- 10. 反馈 ---')
check('POST /api/feedback', 'POST', '/api/feedback', {'openid': 'test123', 'rating': 5, 'comment': '测试'})

# ===== 11. 公开前沿 =====
print('\n--- 11. 前沿文献 ---')
check('GET /api/pubmed-recent', 'GET', '/api/pubmed-recent')
check('POST /api/mark-brief-read', 'POST', '/api/mark-brief-read', {'openid': 'test123', 'pmid': '12345'})

# ===== 汇总 =====
print()
print('=' * 55)
print(f'📊 汇总: ✅ {PASS} 通过 | ❌ {FAIL} 失败')
if FAIL == 0:
    print('🎉 全部通过！昨晚的崩溃问题已修复')
else:
    print(f'🔥 {FAIL} 个失败需要关注')
print(f'Done at: {time.strftime("%H:%M:%S")}')
print('=' * 55)
