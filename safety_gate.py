"""safety_gate.py — AI回复安全闸 + 内稳态偏离检测 + 因果替换链 + 每日遗忘 + 非线性动力学内稳态核"""

import re
import json
import datetime
import hashlib
import logging

# ── DBN 风险等级（由 dp_router 在 handle_chat 中设置） ──
_DBN_RISK_LEVEL = 'low'

def set_dbn_risk_level(level):
    global _DBN_RISK_LEVEL
    _DBN_RISK_LEVEL = level

def get_dbn_risk_level():
    return _DBN_RISK_LEVEL

# ── 安全配置常量 ──
# 同音/形近字映射（防绕过）
_HOMOPHONE_MAP = {
    '停': '停听厅廷', '药': '药妖钥要', '酒': '酒九久纠',
    '割': '割哥歌戈', '死': '死屎始私', '跳': '跳挑条眺',
}
# 编译好的同音字正则缓存
_HOMOPHONE_PATTERNS = {}

def _build_homophone_pattern(raw_pattern: str) -> re.Pattern:
    """将模式中的关键字扩展同音字"""
    expanded = raw_pattern
    for ch, alts in _HOMOPHONE_MAP.items():
        # 替换"药"为"[药妖钥要]"
        replacement = f'[{alts}]'
        expanded = expanded.replace(ch, replacement)
    return re.compile(expanded, re.IGNORECASE)

def _get_pattern(pattern: str) -> re.Pattern:
    """获取模式（带缓存）"""
    if pattern not in _HOMOPHONE_PATTERNS:
        _HOMOPHONE_PATTERNS[pattern] = _build_homophone_pattern(pattern)
    return _HOMOPHONE_PATTERNS[pattern]

def _normalize_reply(reply: str) -> str:
    """归一化回复：去空格、去标点、去语气词、去插入语"""
    # 去掉标点符号和空格
    # 使用 unicode 字符移除，避免 Python 3.13 对 \\s 等的 escape warning
    for c in "，。！？、；：\"\"''（）【】《》 ,.!?;:'\"()[]{}":
        reply = reply.replace(c, '')
    s = reply
    # 去掉语气词（防止插入"嗯""啊"等绕过分词）
    s = re.sub(r'[嗯啊哦哇哈呵呢的了吧吗呀]', '', s)
    return s.lower()

# ── 危险的同音/形近 变体（让 HARD_BLOCK 也支持）──
# 这些作为额外的正则追加到 HARD_BLOCK 里检测
_HARD_VARIANT_PATTERNS = [
    # 同音字: "听妖" 代替 "停药"
    r'[停听厅廷][妖钥要药]',  # 停妖/听药 等
    # 分词绕过: "停...药" "减...药"
    r'[停减调]现在每[天次]的药[量物]',
    r'我[想打]算[把将].{0,6}[药品剂量].{0,6}[停减改]',
]

# ── 危险建议黑名单 ──
# 第一级：绝对禁止（负向建议/医疗越权）
HARD_BLOCK = [
    # 停药/改药
    (r'停(止)?[服药用]?[药医]|减少药[物量]|自己减[药量]|擅自[停减]', '危险建议: 停药/减药属于医疗行为,请遵医嘱'),
    # 自伤
    (r'自[我]?伤[害]?|割[腕伤]|跳[楼河]', '危险建议: 涉及自伤行为,请立即联系心理医生'),
    # 饮酒助眠（含委婉建议: "偶尔喝点酒也比睡不着强"）
    (r'喝[酒]?[点杯]?(酒|红酒|白酒|啤酒)[助帮]?[眠睡]|酒精[助帮]?[眠睡]|偶尔.*[酒].*[比强好]睡不着|喝[点杯]?酒.*[助睡]|酒精能帮你睡|不[推建荐].*酒.*[助睡]|偶尔.*酒.*[比强好]',
     '危险建议: 酒精破坏睡眠结构,不建议用酒精助眠'),
    # 负面情绪/否定（防止多智能体互相教坏）
    (r'你永远[不可能不会]|你根本[不行不听]|你无药可救|没救了|放弃治疗',
     '情绪稳定性: 请避免负面否定,关注下一步的改善可能'),
    # 否定用户努力
    (r'你(做的|尝试|方法|方案)(全是|都?是)?[错白费无用]|你(根本)?不[适合听]',
     '情绪稳定性: 请避免否定用户的努力,建议替换为"这个方法可能不适合,我们换一个试试"'),
    # 恐吓式表达（含"心理健康问题+立即"组合）
    (r'你已经(很?[严重差]|不[行好]了|[没]救)|你的(情[况状]|问题)很?[严重差]|心理[健康]?问题.*立即|严重.*心理[健康]',
     '情绪稳定性: 请避免恐吓式表达,建议用温和的语气沟通'),
]

# 第二级：场景敏感情景（需要检查当前用户状态）
SOFT_FILTER = [
    # 高强度运动
    (r'跑[步完]?|晨跑|剧烈[运锻]|高[强度]训练|HIIT', '高强度运动', '精力充足', '低能量'),
    # 早起
    (r'早[起睡]|5点[前以]?[起醒]|6点[前以]?[起醒]', '早起建议', '作息稳定', '疲劳状态'),
    # 断食
    (r'断食|禁食|不[吃进]|轻断食', '断食', '正常饮食', '低血糖体质'),
]

# 医疗风险评估
MEDICAL_RISK_KEYWORDS = [
    '呼吸暂停', 'OSA', '睡眠呼吸', '猝死', '心脏骤停',
    '脑出血', '中风', '癫痫', '严重抑郁', '自杀',
]

# ── 因果替换链：为每个用户状态匹配最佳建议 ──

# 状态标签 -> 建议池
LOW_ENERGY_ADVICE_POOL = [
    '今晚试试温水泡脚10分钟，帮身体从紧张状态自然过渡到放松。',
    '睡前做3轮4-7-8呼吸：吸气4秒→屏气7秒→呼气8秒。不需要多，3轮就够了。',
    '如果觉得累，今晚就早点放下手机，关灯躺着也是一种休息。',
    '今晚不要求自己"睡好"，目标只是"躺够8小时"。越不在乎睡得越好。',
    '试试把房间灯光调暗到只剩一盏小夜灯，光线是影响褪黑素分泌的最大因素。',
]

NORMAL_ENERGY_ADVICE_POOL = [
    '保持现有节奏，固定起床时间是稳定生物钟最有效的方法。',
    '睡前1小时尽量避免高强度脑力活动，给大脑一个缓冲期。',
    '如果白天感觉精力不错，可以试试下午4点前做20分钟有氧运动。',
    '睡前写一个"明天待办清单"，把焦虑从脑子里搬到纸上。',
    '试试渐进式肌肉放松：从脚趾到头部，逐一绷紧5秒再放松。',
]

HIGH_ENERGY_ADVICE_POOL = [
    '状态不错，可以尝试逐步提前入睡时间，每3天提前15分钟。',
    '白天保持规律运动，但睡前3小时内避免剧烈运动。',
    '如果你最近深睡比例偏低，可以试试睡前做10分钟正念冥想。',
    '记录一下你今晚做了哪些"对的"事情，连续7天就能锁定你的最佳睡前流程。',
    '可以尝试把卧室温度调到18-22°C，这是最适合深睡的环境温度。',
]


def _get_state_label(profile: dict) -> str:
    """从 profile 推断用户当前精力状态"""
    history = profile.get('history', [])
    if not history:
        return 'normal'

    recent = [h.get('wm_score', 0) for h in history[-5:]
              if isinstance(h, dict) and h.get('wm_score', 0) > 0]
    if not recent:
        return 'normal'

    avg = sum(recent) / len(recent)
    # 连续低分
    low_count = sum(1 for s in recent[-3:] if s < 55)
    if avg < 55 and low_count >= 2:
        return 'low'
    elif avg < 65 and low_count >= 1:
        return 'borderline'
    elif avg >= 80:
        return 'high'
    return 'normal'


def _get_advice_by_energy(state: str, exclude: list = None) -> str:
    """根据能量状态选择一条建议，排除已给过的"""
    exclude = exclude or []
    if state == 'low':
        pool = [a for a in LOW_ENERGY_ADVICE_POOL if a not in exclude]
        if not pool:
            pool = LOW_ENERGY_ADVICE_POOL
    elif state == 'high':
        pool = [a for a in HIGH_ENERGY_ADVICE_POOL if a not in exclude]
        if not pool:
            pool = HIGH_ENERGY_ADVICE_POOL
    else:
        pool = [a for a in NORMAL_ENERGY_ADVICE_POOL if a not in exclude]
        if not pool:
            pool = NORMAL_ENERGY_ADVICE_POOL
    import random
    return random.choice(pool)


def get_alternative_advice(reply: str, profile: dict = None) -> str:
    """当检测到不适合当前状态的建议时，替换为合适建议"""
    profile = profile or {}
    state = _get_state_label(profile)

    # 从 profile 的历史建议中提取已给过的建议，避免重复
    given_advice = []
    history = profile.get('history', [])
    for h in history[-10:]:
        if isinstance(h, dict) and h.get('bot_replied'):
            for pool in [LOW_ENERGY_ADVICE_POOL, NORMAL_ENERGY_ADVICE_POOL, HIGH_ENERGY_ADVICE_POOL]:
                for a in pool:
                    if a[:20] in h['bot_replied']:
                        given_advice.append(a)

    alt = _get_advice_by_energy(state, given_advice)

    # 把替换建议追加到不想改变AI原有回复语气的前提下
    if state == 'low':
        tip = '\n\n💡 替你换成更适合现在状态的建议：' + alt
    else:
        tip = '\n\n💡 另一个同样有效的方法：' + alt
    return tip


# ── 每日遗忘机制 ──

def get_today_anchor(today: str = None) -> str:
    """获取今天的遗忘锚点"""
    if today is None:
        today = datetime.date.today().isoformat()
    return today


def should_forget(profile: dict, today: str = None) -> bool:
    """检查今天是否已经遗忘过"""
    today = today or datetime.date.today().isoformat()
    last_forget = profile.get('_last_forget_date', '')
    return last_forget != today


def apply_daily_forget(profile: dict, today: str = None) -> dict:
    """每日遗忘：清除坏建议记忆，重置偏差计数器"""
    today = today or datetime.date.today().isoformat()
    if not should_forget(profile, today):
        return profile

    # 保留最后3条好建议（不全部清空）
    retention_count = 3

    # 重置偏离日志（保留当日之前最后一次偏离做参考线）
    deviation_log = profile.get('_homeostatic_deviation_log', [])
    retained = deviation_log[-retention_count:] if len(deviation_log) > retention_count else []
    profile['_homeostatic_deviation_log'] = retained

    profile['_last_forget_date'] = today
    return profile


# ── 检查建议是否安全 ──

def check_advice_safety(reply: str, profile: dict = None) -> dict:
    """检查 AI 回复是否存在安全风险。返回检查结果"""
    reply_lower = reply.lower()
    profile = profile or {}

    # === 同音字/分词绕过检测：归一化后二次检查 ===
    normalized = _normalize_reply(reply_lower)

    # === 第一级：硬拦截（含同音字扩展）===
    for pattern, message in HARD_BLOCK:
        # 原始模式匹配
        if re.search(pattern, reply_lower):
            return {
                'blocked': True,
                'level': 'HARD',
                'reason': message,
                'action': 'overwrite',
            }
        # 同音字模式匹配（归一化后）
        if re.search(pattern, normalized):
            return {
                'blocked': True,
                'level': 'HARD',
                'reason': message + '(含变体)',
                'action': 'overwrite',
            }

    # === 变体模式检测 ===
    for variant in _HARD_VARIANT_PATTERNS:
        if re.search(variant, reply_lower) or re.search(variant, normalized):
            return {
                'blocked': True,
                'level': 'HARD',
                'reason': '检测到危险内容变体',
                'action': 'overwrite',
            }

    # === 第二级：场景敏感 ===
    last_score = (profile.get('latest') or {}).get('wm_score', 0) or \
                 next((h.get('wm_score', 0) for h in (profile.get('history') or [])[-3:]
                       if isinstance(h, dict) and h.get('wm_score', 0) > 0), 0)
    is_low_energy = last_score < 55

    soft_hits = []
    for pattern, name, good_label, bad_label in SOFT_FILTER:
        if re.search(pattern, reply_lower):
            if is_low_energy:
                soft_hits.append({
                    'advice': name,
                    'reason': f'用户当前评分{last_score},不适合{name}建议',
                })

    # === 医疗风险评估 ===
    medical_risk = False
    for kw in MEDICAL_RISK_KEYWORDS:
        if kw in reply:
            medical_risk = True
            break

    if medical_risk:
        return {
            'blocked': True,
            'level': 'MEDICAL',
            'reason': '回复涉及医疗诊断术语',
            'action': 'append_disclaimer',
        }

    # === 结果 ===
    if soft_hits:
        return {
            'blocked': False,
            'level': 'SOFT',
            'warnings': soft_hits,
            'action': 'flag_for_review',
        }

    return {
        'blocked': False,
        'level': 'PASS',
        'action': 'none',
    }


def _detect_trend_decay(profile: dict, dbn_elevated: bool = False) -> bool:
    """检测评分是否持续递减"""
    threshold = 1 if dbn_elevated else 2
    history = profile.get('history', [])
    recent = [h.get('wm_score', 0) for h in history[-10:]
              if isinstance(h, dict) and h.get('wm_score', 0) > 0][-6:]
    if len(recent) < 3:
        return False
    
    # 快速衰减（短窗口）
    fast_decay = sum(1 for i in range(min(3, len(recent)-1)) if recent[i+1] < recent[i])
    if fast_decay >= threshold:
        return True
    
    # 慢速蠕变（长窗口）
    if len(recent) >= 4:
        slow_decay = sum(1 for i in range(len(recent)-1) if recent[i+1] < recent[i])
        total_drop = recent[0] - recent[-1]
        dbn_slow_threshold = 3 if dbn_elevated else 4
        dbn_drop_threshold = 10 if dbn_elevated else 15
        if slow_decay >= dbn_slow_threshold and total_drop > dbn_drop_threshold:
            return True
    
    return False


def _is_cold_start(profile: dict) -> bool:
    """判断是否冷启动用户（无有效历史数据）"""
    history = profile.get('history', [])
    valid = [h for h in history if isinstance(h, dict) and h.get('wm_score', 0) > 0]
    return len(valid) < 2


def _detect_hard_negative(reply: str) -> bool:
    """快速检查是否有强烈的恶意/负面内容（安全闸漏网时应急预案）"""
    # 检查提及"失败/放弃/没救"的上下文
    defeat_patterns = [
        r'你(永远|根本|已经).{0,4}(没救|失败|放弃|不行|完蛋)',
        r'(永远|根本).{0,8}(不可能|没办法)',
        r'数据(越来|持续).{0,4}(差|坏|恶化)',
    ]
    return any(re.search(p, reply.lower()) for p in defeat_patterns)


def filter_unsafe_reply(reply: str, profile: dict = None) -> str:
    """过 AI 回复并做安全处理 + 因果替换 + 内稳态核驱动"""
    # ── DBN 风险反馈 ──
    _dbn_level = get_dbn_risk_level()
    if _dbn_level in ('elevated', 'high', 'critical'):
        # elevated+ 时替换所有建议性回复
        if '建议' in reply or '试试' in reply or '推荐' in reply:
            return '感谢你的分享。我理解你现在的感受，但我建议你主要依靠专业医疗机构的意见。如果你想聊聊今晚的睡眠感受，我随时都在。'
    if _dbn_level in ('high', 'critical'):
        # high+ 时直接替换所有非纯共情回复
        if not any(kw in reply for kw in ['我理解', '感受', '分享', '辛苦了', '明白']):
            return '我知道你现在可能很困扰。不过作为AI助手，我建议你优先咨询专业医生。你可以随时和我聊聊你今晚的状态。'

    # 自身健康检查
    if reply is None:
        return ''

    profile = profile or {}
    
    # ── 第0层：内稳态核评估（跑在一切之前） ──
    try:
        from homeostatic_kernel import evaluate as _hke
        _hs = _hke(profile)
    except Exception:
        _hs = {'final_mode': 'normal', 'distance': 0.0, 'homeostasis_mode': 'normal',
               'bifurcation_level': 'stable', 'lyapunov_exponent': -0.1}
    _homeostasis_state = _hs.get('final_mode', 'normal')
    _is_bifurcation_risk = _hs.get('bifurcation_level') in ('warning', 'critical')
    _is_locked_low = _hs.get('lyapunov_exponent', 0) < -0.2 and _hs.get('distance', 0) > 0.3

    try:
        result = check_advice_safety(reply, profile)
    except Exception:
        # 安全闸自身故障时，返回最保守的处理
        return (reply or '') + '\n\n⚠️ 系统安全检测异常，请谨慎参考以上建议。如有疑问请咨询医生。'
    
    if result.get('blocked'):
        if result.get('level') == 'HARD':
            return ('感谢你的分享。关于睡眠改善，建议保持规律的作息和放松的睡前习惯。'
                    '如果你正在考虑调整用药或治疗方案，请务必咨询你的主治医生。'
                    f'\n\n⚠️ 系统安全提示: {result["reason"]}')
        if result.get('level') == 'MEDICAL':
            return (reply + '\n\n⚠️ 以上内容仅供参考，不构成医疗建议。如有严重症状请及时就医。')

    # ── 内稳态核驱动：分岔风险 → 替换为安全回复 ──
    if _is_bifurcation_risk or _is_locked_low:
        # 系统处于脆弱状态，任何建议都有风险 → 替换为共情
        return ('感谢你的分享。我注意到最近你的睡眠状态有一些波动，'
                '这很正常，每个人的恢复节奏都不一样。'
                '如果你愿意，可以告诉我今天感觉怎么样，'
                '我们一步一步来。')

    # ── 趋势感知保护 ──
    if _detect_trend_decay(profile, get_dbn_risk_level() in ('elevated','high','critical')) or _detect_hard_negative(reply):
        state = _get_state_label(profile)
        if _detect_hard_negative(reply):
            return ('感谢你的分享。每个人的睡眠节奏都不一样，偶尔的波动是正常的。'
                    '如果你有具体的不适，可以告诉我更详细的情况。继续观察记录，'
                    '数据会告诉我们方向。')
        tip = get_alternative_advice(reply, profile)
        return (reply + tip) if tip else reply

    if result.get('level') == 'PASS':
        state = _get_state_label(profile)
        if state == 'low':
            for pattern, name, _, _ in SOFT_FILTER:
                if re.search(pattern, reply.lower()):
                    tip = get_alternative_advice(reply, profile)
                    return reply + tip
        return reply

    # 内稳态模式驱动：温和模式替换高强度建议
    if _homeostasis_state in ('gentle', 'lockdown'):
        for pattern, name, _, _ in SOFT_FILTER:
            if re.search(pattern, reply.lower()):
                tip = get_alternative_advice(reply, profile)
                return reply + tip

    profile = profile or {}
    if result.get('level') == 'HARD':
        return ('感谢你的分享。关于睡眠改善，建议保持规律的作息和放松的睡前习惯。'
                '如果你正在考虑调整用药或治疗方案，请务必咨询你的主治医生。'
                f'\n\n⚠️ 系统安全提示: {result["reason"]}')

    if result.get('level') == 'MEDICAL':
        return (reply + '\n\n⚠️ 以上内容仅供参考，不构成医疗建议。如有严重症状请及时就医。')

    if result.get('level') == 'SOFT' and result.get('warnings'):
        last_score = (profile.get('latest') or {}).get('wm_score', 0) or \
                     next((h.get('wm_score', 0) for h in (profile.get('history') or [])[-3:]
                           if isinstance(h, dict) and h.get('wm_score', 0) > 0), 0)
        warning_text = '；'.join(w['reason'] for w in result['warnings'])
        return (reply + f'\n\n💡 温馨提示：你当前的精力状况({last_score}分)偏低，'
                f'建议先从温和的放松方式开始，等精力恢复后再尝试。')

    return reply


# ── 评分可信度约束 ──

def validate_score_confidence(data_fields: dict, score: float) -> dict:
    """检查评分是否有足够数据支撑"""
    supported_fields = sum(1 for k in ['bedtime', 'wake_time', 'sleep_latency',
                                        'awake_times', 'total_duration', 'feeling']
                           if data_fields.get(k))

    result = {
        'score': score,
        'confidence': 'unknown',
        'supported_fields': supported_fields,
        'display_score': False,
    }

    if supported_fields >= 4:
        result['confidence'] = 'high'
        result['display_score'] = True
    elif supported_fields >= 2:
        result['confidence'] = 'medium'
        result['display_score'] = True  # 可以展示但有标注
    else:
        result['confidence'] = 'low'
        result['display_score'] = False  # 不展示评分

    return result


# ── 内稳态偏离检测 ──

def detect_homeostatic_deviation(profile: dict, new_score: float) -> dict:
    """检测评分偏离是否超出正常波动范围"""
    history = profile.get('history', [])
    if not history:
        return {'deviation': False}

    # 取最近 7 条有效评分做基线
    recent_scores = [h.get('wm_score', 0) for h in history[-7:]
                     if isinstance(h, dict) and h.get('wm_score', 0) > 0]

    if len(recent_scores) < 2:
        return {'deviation': False}

    baseline = sum(recent_scores[:-1]) / len(recent_scores[:-1])
    delta = abs(new_score - baseline)

    result = {
        'baseline': round(baseline, 1),
        'new_score': new_score,
        'delta': round(delta, 1),
        'deviation': False,
        'first_time': True,
    }

    # 偏离阈值: 超过15分且基线>0
    if delta > 15 and baseline > 0:
        result['deviation'] = True
        # 检查是否已经有偏离记录
        deviation_log = profile.get('_homeostatic_deviation_log', [])
        for entry in deviation_log:
            if abs(entry.get('new_score', 0) - new_score) < 3:
                result['first_time'] = False
                break
        result['deviation_log'] = deviation_log

    return result


def log_deviation(profile: dict, deviation: dict) -> None:
    """记录偏离日志到 profile（不触发文件写，由调用者统一写）"""
    if not deviation.get('deviation'):
        return

    log = profile.setdefault('_homeostatic_deviation_log', [])
    log.append({
        'timestamp': datetime.datetime.now().isoformat(),
        'baseline': deviation['baseline'],
        'new_score': deviation['new_score'],
        'delta': deviation['delta'],
        'first_time': deviation.get('first_time', True),
    })
    # 只保留最近 20 条
    if len(log) > 20:
        profile['_homeostatic_deviation_log'] = log[-20:]


# ── 跨会话共识检测层（团灭防护）──

CONSENSUS_TOPICS = {
    'medication_change': {'keywords': ['停药', '换药', '调药', '减药', '改药', '调整药', '减少药', '停用',
                                        '调整用药', '调整方案', '药物调整', '药量', '剂量', '用药方案',
                                        '换方案', '改方案', '重新配', '药物.*无效', '药.*没效果'],
                          'max_hits': 3, 'label': '药物调整'},
    'hopelessness': {'keywords': ['没救了', '放弃治疗', '永远不可能', '无药可救', '根本不行',
                                   '没希望', '没有用', '没效果', '不行了', '完蛋', '放弃吧'],
                     'max_hits': 2, 'label': '绝望性语言'},
    'misdiagnosis': {'keywords': ['严重.*问题', '不是睡眠问题', '立即就医', '住院', '心理.*疾病',
                                   '睡眠呼吸暂停'],
                     'max_hits': 2, 'label': '误诊升级'},
}


def detect_consensus_risk(reply: str, profile: dict = None) -> dict:
    """检测多个来源是否在短时间内提到同一危险主题"""
    result = {'alert': False, 'topic': '', 'hit_count': 0, 'action': 'none'}
    history = (profile or {}).get('history', [])
    if not history:
        return result

    recent_replies = []
    for h in history[-15:]:
        if isinstance(h, dict):
            text = (h.get('bot_replied', '') or '') + ' ' + (h.get('user_said', '') or '')
            if text.strip():
                recent_replies.append(text)

    for topic, config in CONSENSUS_TOPICS.items():
        hits = 0
        for text in recent_replies:
            if any(kw in text for kw in config['keywords']):
                hits += 1
        # 当前回复也计入
        if any(kw in reply for kw in config['keywords']):
            hits += 1

        if hits >= config['max_hits']:
            result['alert'] = True
            result['topic'] = config['label']
            result['hit_count'] = hits
            result['action'] = 'suppress'
            return result

    # 交叉引用检测：AI 互相引用+危险主题
    ref_patterns = ['另一个', '另外', '专家说', '都.*认为', '都.*建议', '两个.*一致', '共同认为', '大家都', '所有人']
    has_ref = any(re.search(p, reply) for p in ref_patterns)
    if has_ref:
        for topic, config in CONSENSUS_TOPICS.items():
            if any(kw in reply for kw in config['keywords']):
                result['alert'] = True
                result['topic'] = f'{config["label"]}(交叉引用)'
                result['hit_count'] = 99
                result['action'] = 'block'
                return result
    return result


def filter_consensus_risk(reply: str, profile: dict = None) -> str:
    """共识风险过滤"""
    risk = detect_consensus_risk(reply, profile)
    if not risk['alert']:
        return reply
    if risk['action'] == 'block':
        return ('感谢你分享这么多不同的意见。每个人的睡眠状况都不同，'
                '通过网络信息判断具体方案有一定风险。'
                '如果你正在考虑调整治疗方案，建议咨询你的主治医生。')
    if risk['action'] == 'suppress':
        tip = get_alternative_advice(reply, profile or {})
        return reply + (tip if tip else '\n\n💡 温馨提醒：以上建议仅供参考，'
                        '具体用药请咨询医生。')
    return reply
