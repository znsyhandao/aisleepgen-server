"""
AISleepGen 盲区审计 v1.0 — 枚举所有可能的数据流断裂点

枚举范围：前端 → API → handler → profile loader → AI context 的全链路。

每一条是一个"数据可能断掉"的路径，标注：
- 名称：问题的名字
- 位置：哪个组件/代码段
- 断裂条件：什么情况下会断
- 检测难度：静态/运行时/无法检测
- 现有工具是否能抓到
"""

BUG_PATTERNS = [
    # ===== 层1：前端→后端 =====
    {
        'id': 'F1',
        'name': 'openid 传递断链',
        'location': '小程序 app.js → api call → do_POST/_get_openid',
        'break_condition': 'wx.login 返回的 code 过期/错误，后端 _get_openid 回退到 "default" 或其他固定值',
        'detectability': '运行时（需要 trace_id 跨前端+后端传播）',
        'existing_tools': '[N] 无法检测',
        'trace_evidence': '微信 session_key 有效期不确定',
        'priority': 'HIGH',
    },
    {
        'id': 'F2',
        'name': '请求 body 格式变更',
        'location': '前端 post body → data.get("message") / data.get("history")',
        'break_condition': '小程序版本更新后字段名变了（message→text, history→messages），后端继续读旧的 key 得到 None',
        'detectability': '运行时（需要前后端契约检查 + 签名验证）',
        'existing_tools': '[N] 现有 check/contract 只扫描后端路由，不检查字段名',
        'priority': 'MEDIUM',
    },

    # ===== 层2：handler 内部 =====
    {
        'id': 'H1',
        'name': '_get_openid 返回值不对',
        'location': 'deepseek_proxy.py _get_openid()',
        'break_condition': 'data 中无 openid 且 X-OpenID header 不对，回退到 '' 或随机值',
        'detectability': '运行时（已有 trace entry: openid=xxx）',
        'existing_tools': '[OK] 新加的 trace logging 可以抓到',
        'priority': 'MEDIUM',
    },
    {
        'id': 'H2',
        'name': 'user_profile.json 读取竞态',
        'location': '_load_user_profile() / _save_user_profile()',
        'break_condition': '并发写导致 JSON 解析失败（空文件/半截写入）或被旧数据覆盖',
        'detectability': '静态（需要文件锁检查）+ 运行时（需要写入校验）',
        'existing_tools': '[N] 无文件锁，无写入校验',
        'priority': 'HIGH',
    },
    {
        'id': 'H3',
        'name': 'profile 结构演化断层',
        'location': '_build_history_context() L1255 L1301 的 sleep_data 回退逻辑',
        'break_condition': 'update-profile 写入时没走 sleep_data 子结构→profile.latest 是扁平格式→但回退逻辑 {} or latest 在某些边缘情况失效',
        'detectability': '静态（需要数据格式一致性检查）',
        'existing_tools': '[OK] 新加的 check data-flow 可以检测',
        'priority': 'MEDIUM',
    },
    {
        'id': 'H4',
        'name': 'history_context 被截断',
        'location': 'L4420 {history_context} 在 system_content f-string 里',
        'break_condition': 'history_context 超过 4000 字符，被 f-string 隐式截断或大模型 context window 截断',
        'detectability': '运行时（需要 trace 记录 ctx 长度和实际注入内容）',
        'existing_tools': '[OK] 新加的 trace logging 记录 ctx len',
        'priority': 'LOW',
    },
    {
        'id': 'H5',
        'name': '异步 pref 引擎覆盖 profile',
        'location': '_handle_chat() 中的异步 PreferenceEngine 线程',
        'break_condition': '异步线程的 _save_user_profile 在同步线程的 update_profile 之后写入，覆盖掉刚更新的数据',
        'detectability': '静态（需要数据流分析）+ 运行时（需要写入版本号）',
        'existing_tools': '[N] 无法检测',
        'priority': 'HIGH',
    },
    {
        'id': 'H6',
        'name': 'correction 机制吞掉最新数据',
        'location': 'AI 回复中的 is_correction 检测逻辑',
        'break_condition': '用户纠正后 is_correction=True，但新数据没被正确提取到 latest',
        'detectability': '运行时（需要 tracing correction 路径）',
        'existing_tools': '[N] 无 correction 路径的 trace',
        'priority': 'MEDIUM',
    },

    # ===== 层3：数据存储 =====
    {
        'id': 'S1',
        'name': 'user_profile.json 无限膨胀',
        'location': 'history 数组不断 append，无上限',
        'break_condition': '高频用户积累数千条 history，文件变大，读写变慢，GC 暂停时读碎文件',
        'detectability': '静态（检查 history 长度上限）',
        'existing_tools': '[N] 无 history 上限检查',
        'priority': 'MEDIUM',
    },
    {
        'id': 'S2',
        'name': '多用户并发写冲突',
        'location': '_save_user_profile() 读写整个文件',
        'break_condition': '两个请求同时写同一个 user_profile.json，后写的覆盖前写的'
                          '（包括 A 用户的最新数据被 B 用户的旧数据覆盖）',
        'detectability': '静态（需要文件锁机制）',
        'existing_tools': '[N] 无任何并发保护',
        'priority': 'CRITICAL',
    },
    {
        'id': 'S3',
        'name': 'profile 结构不兼容更新',
        'location': '代码更新后 vs 旧版 json',
        'break_condition': '新版代码写入了新字段，旧版代码读不到；或者新版改写了字段路径',
        'detectability': '静态（需要 version schema 管理）',
        'existing_tools': '[N] 无 schema 版本号',
        'priority': 'HIGH',
    },

    # ===== 层4：AI 模型侧 =====
    {
        'id': 'A1',
        'name': 'system_content 中数据被 instruction 覆盖',
        'location': 'L4428 "禁止问你几点睡几点起" instruction 和 L4444 "不确定就说不知道" 规则冲突',
        'break_condition': 'AI 优先执行了"不确定就说不知道"规则，忽略了已有的数据',
        'detectability': '仅人工/LLM-as-judge 评估',
        'existing_tools': '[N] 完全无法用静态工具检测',
        'priority': 'LOW',
    },
    {
        'id': 'A2',
        'name': '大模型忽略上下文中的数据',
        'location': 'LLM inference',
        'break_condition': '即使 system_content 里有数据，模型选择了不引用（"hallucination of omission"）',
        'detectability': '仅 LLM-as-judge 或人工审核',
        'existing_tools': '[N] 无法用传统工具检测',
        'priority': 'MEDIUM',
    },
    {
        'id': 'A3',
        'name': '历史对话淹没基线数据',
        'location': 'messages 数组拼接（L4530-4537）',
        'break_condition': 'history 太长（>20条）时，system_content 中的基线数据被历史对话的注意力淹没',
        'detectability': '运行时（需要统计 model response 中引用数据的频率）',
        'existing_tools': '[N] 无法检测',
        'priority': 'MEDIUM',
    },
]

# ==== 输出 ====
print('=' * 70)
print('  AISleepGen 数据流盲区审计 v1.0')
print('=' * 70)
print()

for bp in BUG_PATTERNS:
    sev = bp['priority']
    sev_mark = {'CRITICAL': '[CRIT]', 'HIGH': '[HIGH]', 'MEDIUM': '[MED]', 'LOW': '[LOW]'}.get(sev, '[?]')
    tool = bp['existing_tools']
    if '新加的' in tool or '[OK]' in tool:
        tool_state = '[OK]'  
    elif '[N]' in tool:
        tool_state = '[MISS]'
    else:
        tool_state = '[?]'
    
    print(f'{sev_mark} [{bp["id"]}] {bp["name"]}')
    print(f'  位置: {bp["location"]}')
    print(f'  断链条件: {bp["break_condition"]}')
    print(f'  检测方式: {bp["detectability"]}')
    print(f'  现有工具: {tool_state} {tool}')
    print()

# 汇总
print('=' * 70)
crit = sum(1 for b in BUG_PATTERNS if b['priority'] == 'CRITICAL')
high = sum(1 for b in BUG_PATTERNS if b['priority'] == 'HIGH')
med = sum(1 for b in BUG_PATTERNS if b['priority'] == 'MEDIUM')
low = sum(1 for b in BUG_PATTERNS if b['priority'] == 'LOW')
covered = sum(1 for b in BUG_PATTERNS if '新加的' in b['existing_tools'] or '[OK]' in b['existing_tools'])
not_covered = sum(1 for b in BUG_PATTERNS if '[N]' in b['existing_tools'])
print(f'  总盲区: {len(BUG_PATTERNS)} 个')
print(f'  CRITICAL: {crit} | HIGH: {high} | MEDIUM: {med} | LOW: {low}')
print(f'  现有工具已标记覆盖: {covered} 个')
print(f'  现有工具未覆盖: {not_covered} 个')
print(f'  覆盖率(名义): {covered}/{len(BUG_PATTERNS)} ({100*covered//len(BUG_PATTERNS)}%)')
print('=' * 70)
