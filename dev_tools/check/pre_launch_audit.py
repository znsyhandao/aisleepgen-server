#!/usr/bin/env python3
"""pre_launch_audit.py — AISleepGen 上线前全链路审计

检查新用户从打开小程序到完成一次睡眠分析的全链路，
找出所有可能导致用户流失或体验断裂的点。

检查维度:
  1. 注册→激活漏斗
  2. 核心功能链路（登录→睡眠分析→评分反馈）
  3. 错误路径覆盖
  4. 数据持久化
  5. 冷启动体验

用法: python pre_launch_audit.py
"""
import os, sys, json, glob, re, importlib
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'D:\\AISleepGen_Optimized'
PASS = 0
FAIL = 0
WARN = 0

def ok(msg):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def fail(msg, detail=""):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}" + (f" — {detail}" if detail else ""))

def warn(msg, detail=""):
    global WARN; WARN += 1
    print(f"  ⚠️  {msg}" + (f" — {detail}" if detail else ""))

def check_file_imports(filepath, required_imports):
    """检查文件是否包含必要的导入"""
    if not os.path.exists(filepath):
        return set()
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    found = set()
    for imp in required_imports:
        if imp in content:
            found.add(imp)
    return found

print(f"\n{'='*60}")
print(f"  🚀 AISleepGen 上线前全链路审计")
print(f"  Pre-Launch Audit — {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"{'='*60}")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [1] 注册→激活漏斗
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [1] 注册→激活漏斗 (Onboarding Funnel)")
print(f"{'='*60}")

# 1.1 微信登录端点
print("\n--- 1.1 登录链路 ---")
wx_login = os.path.join(BASE, 'wx_login.py')
if os.path.exists(wx_login):
    ok("wx_login.py 存在")
    with open(wx_login, 'r', encoding='utf-8', errors='replace') as f:
        login_content = f.read()
    if 'wx.login' in login_content or 'code2Session' in login_content or 'js_code' in login_content:
        ok("微信登录 API 调用已实现")
    if 'openid' in login_content:
        ok("openid 处理逻辑存在")
    if 'session_key' in login_content or 'skey' in login_content or 'token' in login_content:
        ok("会话管理已实现")
    else:
        warn("未检测到 session/token 管理，登录态可能不持久")
    if 'user_profile.json' in login_content or 'save_user' in login_content or 'db_sqlite' in login_content:
        ok("登录后保存用户数据")
    else:
        fail("登录后未保存用户数据")
else:
    fail("wx_login.py 不存在，微信登录不可用")

# 1.2 用户画像创建
print("\n--- 1.2 新用户创建 ---")
profile_storage = os.path.join(BASE, 'profile_storage.py')
if os.path.exists(profile_storage):
    ok("profile_storage.py 存在")
    with open(profile_storage, 'r', encoding='utf-8', errors='replace') as f:
        ps_content = f.read()
    if '_get_default_profile' in ps_content:
        ok("新用户默认画像模板存在")
    if 'db_sqlite' in ps_content:
        ok("使用 SQLite 存储")
    else:
        warn("未使用 SQlite 存储，可能使用 JSON 文件")

# 1.3 微信小程序端 app.js
print("\n--- 1.3 小程序端启动逻辑 ---")
mini_app_dir = os.path.join(BASE, 'miniprogram')
if os.path.isdir(mini_app_dir):
    app_js = os.path.join(mini_app_dir, 'app.js')
    app_ts = os.path.join(mini_app_dir, 'app.ts')
    for p in [app_js, app_ts]:
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8', errors='replace') as f:
                app_content = f.read()
            if 'wx.login' in app_content:
                ok(f"app.js 包含 wx.login 启动登录")
            else:
                fail("app.js 缺少 wx.login 启动登录")
            if 'openid' in app_content or 'token' in app_content or 'cache' in app_content:
                ok("登录态缓存已处理")
            else:
                warn("未检测到登录态缓存，每次启动都需要重新登录")
            break
    else:
        fail("未找到 app.js 或 app.ts")
else:
    warn("miniprogram 目录不存在（可能在小程序项目其他位置）")

# 1.4 隐私协议
print("\n--- 1.4 隐私协议 ---")
compliance_file = os.path.join(BASE, 'compliance.py')
if os.path.exists(compliance_file):
    ok("compliance.py 存在")
    with open(compliance_file, 'r', encoding='utf-8', errors='replace') as f:
        comp_content = f.read()
    if 'consent' in comp_content:
        ok("隐私授权记录已实现")
    if 'delete' in comp_content.lower():
        ok("数据删除功能已实现")
    if 'export' in comp_content.lower():
        ok("数据导出功能已实现")
else:
    fail("compliance.py 不存在")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [2] 核心功能链路
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [2] 核心功能链路")
print(f"{'='*60}")

# 2.1 API 路由导出
print("\n--- 2.1 API 端点清单 ---")
with open(os.path.join(BASE, 'deepseek_proxy.py'), 'r', encoding='utf-8', errors='replace') as f:
    proxy_content = f.read()

# 提取所有路由
route_pattern = re.compile(r"if\s+path\s*==\s*['\"](/api/[^'\"]+)['\"]")
routes = route_pattern.findall(proxy_content)
essential_routes = [
    '/api/wx/login', '/api/wx/profile',
    '/api/sleep/world-step', '/api/sleep/world-summary', '/api/sleep/world-end',
    '/api/user-profile', '/api/sleep-stats', '/api/history',
]
found_routes = set(routes)
for r in essential_routes:
    if r in found_routes:
        ok(f"  {r}")
    else:
        fail(f"  {r} — 未找到!")

print(f"\n  总共 {len(routes)} 个 POST 路由")

# 2.2 核心世界模型
print("\n--- 2.2 世界模型链路 ---")
swm_file = os.path.join(BASE, 'sleep_world_model.py')
if os.path.exists(swm_file):
    ok("sleep_world_model.py 存在")
    with open(swm_file, 'r', encoding='utf-8', errors='replace') as f:
        swm_content = f.read()
    for k in ['total_score', 'dimensions', 'recommended_therapies', 'analysis']:
        if k in swm_content:
            ok(f"  包含 {k}")
        else:
            warn(f"  缺少 {k}（世界模型输出可能无此字段）")

# 2.3 数据流闭环
print("\n--- 2.3 数据流闭环（分析→写入→展示）---")
with open(os.path.join(BASE, 'profile_storage.py'), 'r', encoding='utf-8', errors='replace') as f:
    ps_content = f.read()
if '_update_user_profile' in ps_content:
    ok("profile_storage._update_user_profile 存在（写入 history + wm_score）")
if '_log_intervention' in ps_content:
    ok("profile_storage._log_intervention 存在（记录干预事件）")

# 2.4 粤语支持（用户高概率需求）
print("\n--- 2.4 粤语支持 ---")
for fp in sorted(glob.glob(os.path.join(BASE, '*.py'))):
    name = os.path.basename(fp)
    if name == os.path.basename(__file__):  # skip self
        continue
    with open(fp, 'r', encoding='utf-8', errors='replace') as f:
        c = f.read()
    if 'cantonese' in c.lower() or '粤' in c:
        ok(f"粤语支持在 {name}")
        break
else:
    warn("未检测到粤语支持（如果目标用户是广东/香港用户可能需要）")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [3] 错误路径 & 异常处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [3] 错误路径覆盖")
print(f"{'='*60}")

# 3.1 DeepSeek API 超时/故障降级
print("\n--- 3.1 API 降级 ---")
if 'try:' in proxy_content and 'except' in proxy_content:
    except_count = proxy_content.count('except')
    try_count = proxy_content.count('try:')
    if except_count >= try_count * 0.7:
        ok(f"异常处理覆盖够 ({except_count} except / {try_count} try)")
    else:
        warn(f"异常处理可能不足 ({except_count} except / {try_count} try)")
else:
    fail("几乎无异常处理")

# 3.2 fallback 回复
print("\n--- 3.2 Fallback 回复 ---")
fallback_file = os.path.join(BASE, 'fallback_replies.py')
if os.path.exists(fallback_file):
    ok("fallback_replies.py 存在")
    with open(fallback_file, 'r', encoding='utf-8', errors='replace') as f:
        fb_content = f.read()
    for k in ['timeout', 'error', 'offline']:
        if k in fb_content.lower():
            ok(f"  fallback 类型: {k}")
else:
    warn("fallback_replies.py 不存在，DeepSeek 离线时无回复")

# 3.3 哨兵/监控
print("\n--- 3.3 运行时哨兵 ---")
for name in ['sre_watchdog.py', 'deepseek_watchdog.py', 'self_healer.py']:
    fp = os.path.join(BASE, name)
    if os.path.exists(fp):
        ok(f"{name} 存在")
    else:
        warn(f"{name} 不存在")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [4] 冷启动体验
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [4] 冷启动体验")
print(f"{'='*60}")

# 4.1 首次用户提示
print("\n--- 4.1 首次使用引导 ---")
if '/api/sleep/world-step' in found_routes:
    ok("核心分析路由存在")
    # 检查是否区分首次 vs 回访
    if 'total_sessions' in proxy_content and '0' in proxy_content:
        ok("可能包含首次用户逻辑判断")
    else:
        warn("未检测到首次用户逻辑（所有用户走相同流程）")

# 4.2 无历史数据时的默认行为
print("\n--- 4.2 无历史数据预测 ---")
prediction_engine = os.path.join(BASE, 'prediction_engine.py')
if os.path.exists(prediction_engine):
    ok("prediction_engine.py 存在")
    with open(prediction_engine, 'r', encoding='utf-8', errors='replace') as f:
        pred_content = f.read()
    if 'no_data' in pred_content or '_no_data' in pred_content or 'default' in pred_content:
        ok("无数据时的默认预测逻辑存在")
    else:
        warn("无数据时可能没有默认预测")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [5] 部署配置
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [5] 部署配置")
print(f"{'='*60}")

# 5.1 环境变量
print("\n--- 5.1 环境变量 ---")
env_dot = os.path.join(BASE, '.env')
if os.path.exists(env_dot):
    ok(".env 存在")
    with open(env_dot, 'r', encoding='utf-8', errors='replace') as f:
        env_content = f.read()
    # config.py 里实际用的 key 名是 WECHAT_APPID/WECHAT_SECRET，不是 WX_APPID/WX_SECRET
    for env_key, config_key in [('DEEPSEEK_API_KEY', 'DEEPSEEK_API_KEY'),
                                 ('WECHAT_APPID', 'WECHAT_APPID'),
                                 ('WECHAT_SECRET', 'WECHAT_SECRET')]:
        if env_key in env_content or config_key in env_content:
            ok(f"  {config_key}")
        else:
            warn(f"  {config_key} — 需在 .env 或 config.json 中配置（微信小程序AppID/Secret）")
else:
    warn("无 .env 文件（可能通过环境变量注入）")
    # 检查 config.py 的实际引用
    with open(os.path.join(BASE, 'config.py'), 'r', encoding='utf-8') as f:
        config_content = f.read()
    for key in ['WECHAT_APPID', 'WECHAT_SECRET']:
        if key in config_content:
            ok(f"  {key} 在 config.py 中定义（需设置环境变量）")

# 5.2 生产配置
print("\n--- 5.2 生产配置 ---")
config_file = os.path.join(BASE, 'config.py')
if os.path.exists(config_file):
    ok("config.py 存在")
    with open(config_file, 'r', encoding='utf-8', errors='replace') as f:
        config_content = f.read()
    if 'IS_HUAWEI_CLOUD' in config_content or 'prod' in config_content.lower() or 'production' in config_content.lower():
        ok("生产/开发环境切换已实现（通过 IS_HUAWEI_CLOUD 检测）")
    else:
        warn("未检测到生产/开发环境切换")

# 5.3 CORS
print("\n--- 5.3 CORS ---")
if 'Access-Control-Allow-Origin' in proxy_content or 'Access-Control' in proxy_content:
    ok("CORS 已配置")
else:
    warn("未检测到 CORS 配置（微信小程序不需要，但如有 web 管理页面需要）")

# 5.4 服务器健康检查
print("\n--- 5.4 健康检查 ---")
if '/health' in found_routes or '/health' in proxy_content:
    ok("健康检查端点存在")
else:
    fail("缺少健康检查端点 (GET /health)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [6] 微信小程序专属
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print(f"\n{'='*60}")
print(f"  [6] 微信小程序配置")
print(f"{'='*60}")

# 6.1 支付配置
print("\n--- 6.1 支付 ---")
pay_api = os.path.join(BASE, 'payment_api.py')
if os.path.exists(pay_api):
    ok("payment_api.py 存在")
    with open(pay_api, 'r', encoding='utf-8', errors='replace') as f:
        pay_content = f.read()
    if 'PAY_ENABLED' in pay_content:
        ok("支付开关存在")
    if 'WXPAY_API_KEY' in pay_content:
        ok("微信支付配置已定义")

# 6.2 URLs
print("\n--- 6.2 服务器地址配置 ---")
if '123.60.222.129' in proxy_content:
    ok("华为云服务器地址已配置")
if '8090' in proxy_content:
    ok("端口 8090 已配置")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 总结
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
total = PASS + FAIL + WARN
print(f"\n{'='*60}")
print(f"  📊 审计总结")
print(f"{'='*60}")
print(f"\n  ✅ 通过: {PASS}/{total} ({PASS/max(total,1)*100:.0f}%)")
print(f"  ❌ 失败: {FAIL}/{total}")
print(f"  ⚠️  警告: {WARN}/{total}")
print(f"\n  严重程度: ", end="")
if FAIL == 0 and WARN == 0:
    print("🎉 完美，可直接上线")
elif FAIL == 0:
    print("🟡 有警告需关注，但无致命问题")
elif FAIL <= 3:
    print("🟠 有少量致命问题需修复")
else:
    print("🔴 有多个致命问题，建议修复后再上线")

print(f"\n{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
