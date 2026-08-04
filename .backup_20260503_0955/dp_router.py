#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dp_router.py — AISleepGen 路由处理层

所有 handler 作为模块级函数，接收 dict 返回 dict。
零 HTTP I/O，零 self 引用。可被 asyncio 或 sync 服务器同等调用。

从 deepseek_proxy.py ProxyHandler 类方法重构而来。
每个函数对应一个 API 路由。
"""
import os, json, time, hashlib, subprocess, threading, logging, collections as _coll
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_PROFILE_PATH = os.path.join(PROJECT_ROOT, 'user_profile.json')

# ===== 限流系统 =====
_RATE_LIMIT = {}  # {openid: [timestamps]}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_WINDOW_SEC = 60      # 窗口：1 分钟
_RATE_MAX_CALLS = 30       # 每分钟最多 30 次 API 调用
_RATE_MAX_CHAT = 10        # chat 路由每分钟最多 10 次

def _check_rate_limit(openid, path):
    """返回 (allowed, retry_after_seconds)"""
    now = time.time()
    with _RATE_LIMIT_LOCK:
        record = _RATE_LIMIT.setdefault(openid, [])
        # 清理过期记录
        cutoff = now - _RATE_WINDOW_SEC
        record[:] = [t for t in record if t > cutoff]
        # 计算当前窗口内的调用次数
        calls = len(record)
        max_calls = _RATE_MAX_CHAT if path == '/api/chat' else _RATE_MAX_CALLS
        if calls >= max_calls:
            wait = record[0] + _RATE_WINDOW_SEC - now
            record.append(now)  # 这次也算进去——但返回拒绝
            return (False, max(1, round(wait)))
        record.append(now)
        return (True, 0)

# 以下函数直接从 dp_data 获取（统一数据入口）
import sys
sys.path = [p for p in sys.path if 'openclaw' not in p.lower()]
sys.path.insert(0, PROJECT_ROOT)

# 确保 API Key 加载
import dp_data as _px
_ai_log = logging.getLogger('aisleepgen.dp_router')
if not _px.DEEPSEEK_API_KEY:
    _px.load_deepseek_key()

# ==================== 路由表 ====================
ROUTES = {}

def route(path, methods=['POST']):
    """装饰器：注册路由 + 统一错误屏障（任何异常→返回 {'error': '描述'}）"""
    def dec(fn):
        safe_fn = _safe_handler(fn)
        for m in methods:
            ROUTES[(m, path)] = safe_fn
        return fn  # 原函数被覆盖，但 safe_fn 注册进路由
    return dec


def _safe_handler(fn):
    """包装 handler：任何异常兜底返回 dict"""
    import traceback
    def wrapped(data):
        try:
            result = fn(data)
            if result is None:
                return {'error': f'{fn.__name__} returned None'}
            if not isinstance(result, dict):
                return {'result': result}
            return result
        except Exception as e:
            tb = traceback.format_exc()
            return {'error': str(e), '_trace': tb[-200:], '_handler': fn.__name__}
    wrapped.__name__ = fn.__name__
    wrapped.__doc__ = fn.__doc__
    return wrapped


# ==================== 已拆离的 handler ====================

@route('/api/chat')
def handle_chat(data):
    """聊天处理——注入完整用户画像到 prompt"""
    openid = data.get('openid', 'default')
    message = data.get('message', '')
    history = data.get('history', [])
    persona = data.get('persona', 'restorative')

    # ===== 熔断检查 =====
    from safeguards import check_circuit_breaker
    breaker_allowed, breaker_reason = check_circuit_breaker()
    if not breaker_allowed:
        # 熔断中：走降级引擎
        _ai_log.warning('[Safeguard] Chat circuit-breaker open for %s: %s', openid[:8], breaker_reason)
        from fallback_replies import generate_fallback_reply
        reply = generate_fallback_reply(message, wm_result=None, fields=None, persona=persona)
        return {
            'reply': reply,
            'token_estimate': 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ai_score': None,
            'ai_quality': None,
            'debate': None,
            'safeguard': 'circuit_breaker',
        }

    # ===== 1. 加载用户数据和上下文 =====
    profile = _px._load_user_profile(openid)
    # 如果 profile 有人设设置且请求没指定，用 profile 里的
    if not data.get('persona'):
        persona = profile.get('ai_persona', 'restorative')
    latest = profile.get('latest', {})
    today = datetime.now().strftime('%Y-%m-%d')

    # 历史上下文
    from trend_layer import _build_history_context
    history_context, _ = _build_history_context(openid)

    # 世界模型分析（带 NLP 字段提取）
    wm = _px._get_world_model()
    wm_context = ''
    quality = ''
    score = 0
    deb = None
    extracted_fields = None  # 用于降级引擎
    if wm:
        all_text = message
        for msg in history:
            if isinstance(msg, dict) and msg.get('content'):
                all_text += ' ' + msg['content']
        # 从自然语言提取结构化字段注入世界模型
        from nlp_extractor import extract_sleep_fields
        extracted_fields = extract_sleep_fields(all_text)
        if extracted_fields:
            wm_input = extracted_fields
            wm_input['_raw_text'] = all_text
        else:
            wm_input = all_text
        wm_result = wm.comprehensive_analysis(wm_input)
        if isinstance(wm_result, dict):
            quality = wm_result.get('quality', '')
            score = wm_result.get('total_score', 0)
            deb = wm_result.get('expert_debate')
            wm_context = json.dumps({'quality': quality, 'score': score}, ensure_ascii=False)

    # 跨日趋势 + 场景
    from trend_layer import _extract_trends
    trends = _extract_trends(openid)
    trend_text = json.dumps(trends, ensure_ascii=False) if trends else ''
    scene_text = json.dumps({'scene': 'general'})

    # ===== 主动健康警报（注入到 prompt） =====
    alert = ''
    if trends:
        if trends.get('sleep_deprivation_risk'):
            alert += '\n⚠ 主动警报: 用户连续3天睡眠不足6小时，需优先关注睡眠时长问题。'
        if trends.get('circadian_disruption_risk'):
            alert += '\n⚠ 主动警报: 用户起床时间波动超过2小时，生物钟可能紊乱。'
        if trends.get('score_trend', {}).get('direction') == 'down':
            st = trends['score_trend']
            if abs(st.get('delta', 0)) > 10:
                alert += f'\n⚠ 主动警报: 用户评分持续下降({st["delta"]:.0f}分)，需分析恶化原因。'
        if trends.get('awake_trend', {}).get('direction') == 'more':
            alert += '\n⚠ 主动警报: 用户夜醒次数增多，需分析干扰因素。'
    if alert:
        scene_text = json.dumps({'scene': 'general', 'alerts': alert.strip()}, ensure_ascii=False)

    # 校准
    _px._trigger_self_learn()
    cal = _px._load_calibration()
    score_cal = profile.get('score_calibration', [])
    score_hint = ''
    score_offset = 0  # 评分偏移（用户反馈校准）
    if score_cal:
        high = sum(1 for c in score_cal if c.get('direction') == '\u504f\u9ad8')
        low = sum(1 for c in score_cal if c.get('direction') == '\u504f\u4f4e')
        # 用户说"偏高"多 → 减分；"偏低"多 → 加分
        net = low - high
        score_offset = max(-10, min(10, net * 3))  # 每次偏离调 ±3 分，上限 ±10
        score_hint = f'评分校准: 偏高{high}次/偏低{low}次（当前偏移{score_offset:+.0f}分）'
        # 应用偏移到世界模型评分
        if score_offset != 0 and isinstance(score, (int, float)) and score > 0:
            score = max(10, min(100, score + score_offset))
    correction_note = '已认知纠正' if any(w in message for w in ['记错', '不是', '不对', '纠正']) else ''

    # ===== 2. 构建 prompt =====
    from chat_prompt_builder import build_system_content, build_messages

    # ===== 自学习反馈洞察注入 prompt =====
    from self_learn import _learnt_style_adjustments
    style_adjust = _learnt_style_adjustments(openid)

    # ===== 建议效果追踪注入 prompt =====
    from recommendation_tracker import get_recommendation_insights, store_recommendations, evaluate_pending_recommendations
    rec_insights = get_recommendation_insights(profile)
    # 如果有 pending 建议且当前有评分，先评估
    if wm and isinstance(score, (int, float)) and score > 0:
        profile, evaluated = evaluate_pending_recommendations(profile, score)
        if evaluated:
            _px._save_user_profile(profile, openid)
            # eval 后重新获取洞察
            rec_insights = get_recommendation_insights(profile)

    # ===== 情绪检测（5维）用于人设适配 =====
    from persona_profiles import detect_emotion_vector, get_emotion_prefix, get_persona
    emotion_vector = detect_emotion_vector(message)
    emotion_prefix = get_emotion_prefix(emotion_vector)
    persona_config = get_persona(persona)

    # ===== 检查待完成的干预 =====
    from intervention_scheduler import get_pending_interventions
    pending_interventions = get_pending_interventions(profile)
    intervention_hint = ''
    if pending_interventions:
        pi = pending_interventions[0]  # 只取最近一条
        verified_tag = '✅已验证有效' if pi.get('effective_before') else '📌新策略'
        intervention_hint = (
            '\n【主动干预建议】\n'
            f'基于历史数据趋势预测，用户可能需要以下干预：\n'
            f'  - 策略: {pi["name"]}\n'
            f'  - 描述: {pi["desc"]}\n'
            f'  - 原因: {pi["reason"]}\n'
            f'  - 状态: {verified_tag}\n'
            f'请主动向用户提出这个建议，语气符合当前人设风格。'
            f'如果用户接受了，回复结束后请在最后一行单独加"【干预已接受】"。'
        )

    sc = build_system_content(
        correction_note=correction_note,
        score_calibration_hint=score_hint,
        today_str=today,
        history_context=history_context,
        wm_context=wm_context,
        scene_context=scene_text,
        tone_adjust_inject=style_adjust,
        recommendation_insights=rec_insights,
        persona_config=persona_config,
        emotion_prefix=emotion_prefix,
        intervention_hint=intervention_hint,
    )
    messages = build_messages(sc, history, message)

    # ===== 3. AI 调用（带缓存 + 熔断记录 + 投毒校验） =====
    from dp_data import call_deepseek_api
    from safeguards import validate_reply, record_api_call
    cache_ctx = {'openid': openid, 'message': message}
    reply = call_deepseek_api(messages, cache_ctx=cache_ctx)

    # 记录 API 调用结果到熔断器
    api_success = reply is not None and len(reply) > 10
    record_api_call(success=api_success)

    # 缓存投毒校验
    if reply is not None and len(reply) > 0:
        valid, reason = validate_reply(reply)
        if not valid:
            _ai_log.warning('[Safeguard] Cache poison detected for %s: %s', openid[:8], reason)
            reply = None  # 触发降级

    token_estimate = len(reply) // 4 if reply else 0

    # ===== 3b. 降级检测：DeepSeek 不可用时用本地模板引擎 =====
    if reply is None or len(reply) < 10 or (len(reply) < 30 and ('API' in reply or '失败' in reply or '错误' in reply)):
        from fallback_replies import generate_fallback_reply
        fallback_msg = message
        _ai_log.warning('DeepSeek API unavailable, using local fallback for openid=%s', openid[:8])
        reply = generate_fallback_reply(
            message=fallback_msg,
            wm_result={'total_score': score, 'quality': quality, 'expert_debate': deb} if wm else None,
            fields=extracted_fields,
            persona=persona,
        )
        _record_metric('/api/chat', 0, detail={
            'openid': openid[:8], 'msg_len': len(message),
            'reply_len': len(reply), 'token_est': 0, 'fallback': True,
            'has_profile': bool(latest),
        })
    else:
        _record_metric('/api/chat', 0, detail={
            'openid': openid[:8], 'msg_len': len(message),
            'reply_len': len(reply), 'token_est': token_estimate, 'fallback': False,
            'has_profile': bool(latest),
        })

    # ===== 4. 自动存档到历史 + 建议追踪 =====
    if reply and len(reply) > 10:
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            profile = _px._load_user_profile(openid)
            h = profile.setdefault('history', [])
            # 同一日期只保存最近一条
            if not h or h[-1].get('date') != today:
                h.append({
                    'date': today,
                    'user_said': message[:200],
                    'bot_replied': reply[:200],
                    'wm_score': 0,
                    'total_duration': 0,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                })
                _px._save_user_profile(profile, openid)
                if len(h) > 100:
                    profile['history'] = h[-100:]

            # 存储 AI 回复中的建议
            if isinstance(score, (int, float)) and score > 0:
                profile = store_recommendations(profile, reply, score)
                _px._save_user_profile(profile, openid)

            # 检测"干预已接受"信号 → 标记干预完成
            if '干预已接受' in reply:
                pending = get_pending_interventions(profile)
                if pending:
                    from intervention_scheduler import mark_intervention_completed
                    mark_intervention_completed(profile, pending[0]['strategy_id'])
                    _px._save_user_profile(profile, openid)
                    _ai_log.info('[Intervention] accepted by %s: %s', openid[:8], pending[0]['name'])
        except Exception:
            pass  # 存档+建议追踪失败不阻塞回复

    # 从回复中移除干预标记（不暴露技术细节）
    if reply and '【干预已接受】' in reply:
        reply = reply.replace('【干预已接受】', '').strip()

    return {
        'reply': reply,
        'token_estimate': token_estimate,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'ai_score': round(score, 1) if isinstance(score, (int, float)) else None,
        'ai_quality': quality if quality else None,
        'debate': deb if deb else None,
    }


@route('/api/wx-login')
def handle_wx_login(data):
    """微信登录"""
    code = data.get('code', '')
    openid = f'wx_{hashlib.md5(code.encode()).hexdigest()[:16]}' if code else 'default'
    # 加载或创建用户
    profile = _px._load_user_profile(openid)
    return {
        'openid': openid,
        'is_new': profile.get('total_sessions', 0) == 0,
        'member': profile.get('member', {'level': 'free'}),
    }


@route('/api/user-profile')
def handle_user_profile(data):
    """获取用户画像"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    # 过滤敏感字段
    safe = {k: v for k, v in profile.items()
            if k not in ('_pending_review', '_last_intervention')}
    return {'profile': safe}


@route('/api/update-profile')
def handle_update_profile(data):
    """更新用户画像"""
    openid = data.get('openid', 'default')
    updates = data.get('profile', {})
    if openid and updates:
        def modifier(p):
            p.update(updates)
            return p
        _px._atomic_write_profile(openid, modifier)
    return {'status': 'ok'}


@route('/api/sleep-stats')
def handle_sleep_stats(data):
    """睡眠统计"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    history = profile.get('history', [])
    total = len(history)
    avg_score = 0
    streak = 0
    if total > 0:
        scores = [h.get('score', 0) for h in history if h.get('score')]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        # 计算连续天数
        dates = sorted(set(h.get('date', '') for h in history if h.get('date')), reverse=True)
        streak = 1
        for i in range(1, len(dates)):
            try:
                prev = datetime.strptime(dates[i-1], '%Y-%m-%d')
                cur = datetime.strptime(dates[i], '%Y-%m-%d')
                if (prev - cur).days == 1:
                    streak += 1
                else:
                    break
            except:
                break
    return {
        'total_sessions': total,
        'avg_score': avg_score,
        'streak_days': streak,
        'member': profile.get('member', {'level': 'free'}),
    }


@route('/api/history')
def handle_history(data):
    """历史记录"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    history = profile.get('history', [])
    limit = data.get('limit', 30)
    return {'history': history[-limit:]}


@route('/api/feedback')
def handle_feedback(data):
    """反馈"""
    openid = data.get('openid', 'default')
    feedback_text = data.get('feedback', '')
    rating = data.get('rating')
    if feedback_text:
        fb_path = os.path.join(PROJECT_ROOT, 'data', 'feedback.json')
        try:
            fbs = json.load(open(fb_path, encoding='utf-8-sig')) if os.path.exists(fb_path) else []
        except:
            fbs = []
        fbs.append({
            'openid': openid, 'feedback': feedback_text,
            'rating': rating, 'timestamp': time.time(),
        })
        with open(fb_path, 'w', encoding='utf-8') as f:
            json.dump(fbs, f, ensure_ascii=False, indent=2)

        # 记录评分校准（带溢出保护）
        if rating and openid != 'default':
            from safeguards import check_calibration_rate, sanitize_calibration
            allowed, reason = check_calibration_rate(openid)
            if not allowed:
                _ai_log.warning('[Safeguard] Calibration rejected for %s: %s', openid[:8], reason)
                return {'status': 'ok', 'calibration': 'rate_limited'}

            def modifier(p):
                cal = p.setdefault('score_calibration', [])
                direction = '偏高' if isinstance(rating, (int, float)) and rating < 3 else '偏低' if rating > 4 else ''
                if direction:
                    cal.append({'direction': direction, 'rating': rating, 'time': datetime.now().isoformat()})
                    # 清洗记录+计算安全偏移
                    cleaned, _ = sanitize_calibration(cal)
                    p['score_calibration'] = cleaned
                    if len(cal) > 20: cal.pop(0)
                return p
            _px._atomic_write_profile(openid, modifier)

    return {'status': 'ok'}


@route('/api/goodnight')
def handle_goodnight(data):
    """晚安记录"""
    openid = data.get('openid', 'default')
    _px._trigger_self_learn()
    return {'reply': '晚安，好梦！明天见 🌙', 'action': 'goodnight'}


@route('/api/sleep-analyze')
def handle_sleep_analyze(data):
    """睡眠分析（带世界模型缓存 + 趋势注入 + NLP 字段提取）"""
    openid = data.get('openid', 'default')
    data_msg = data.get('message', '')
    for h in data.get('history', []):
        if isinstance(h, dict) and h.get('content'):
            data_msg += ' ' + h['content']
    today_str = datetime.now().strftime('%Y%m%d')

    # ===== 熔断检查 =====
    from safeguards import check_circuit_breaker
    breaker_allowed, breaker_reason = check_circuit_breaker()
    if not breaker_allowed:
        _ai_log.warning('[Safeguard] Circuit-breaker active during analyze: %s', breaker_reason)

    # 注入趋势数据
    from trend_layer import _extract_trends
    trends = _extract_trends(openid)
    if trends:
        data_msg += '\n[趋势数据: ' + json.dumps(trends, ensure_ascii=False)[:300] + ']'

    # NLP 字段提取
    from nlp_extractor import extract_sleep_fields
    extracted_fields = extract_sleep_fields(data_msg)

    wm = _px._get_world_model()
    if not wm:
        return {'error': '世界模型未就绪'}

    from dp_data import get_world_model_analysis
    result = get_world_model_analysis(
        openid=openid,
        today_str=today_str,
        message=data_msg,
        compute_fn=lambda: wm.comprehensive_analysis(
            extracted_fields if extracted_fields else data_msg
        )
    )

    # 应用评分校准偏移
    profile = _px._load_user_profile(openid)
    score_cal = profile.get('score_calibration', [])
    if score_cal and isinstance(result, dict):
        high = sum(1 for c in score_cal if c.get('direction') == '\u504f\u9ad8')
        low = sum(1 for c in score_cal if c.get('direction') == '\u504f\u4f4e')
        net = low - high
        offset = max(-10, min(10, net * 3))
        if offset != 0:
            old_score = result.get('total_score', 0)
            result['total_score'] = max(10, min(100, old_score + offset))
            result['score_calibrated'] = True
            result['score_offset'] = offset

    # 评估 pending 建议
    current_score = result.get('total_score', 0)
    if isinstance(current_score, (int, float)) and current_score > 0:
        from recommendation_tracker import evaluate_pending_recommendations
        profile, _ = evaluate_pending_recommendations(profile, current_score)

        # 先把当前评分塞入 profile history（让预测器能看到）
        # 每次 analyze 都加一条记录（即使同一天也追加，以便趋势分析）
        today = datetime.now().strftime('%Y-%m-%d')
        h = profile.setdefault('history', [])
        h.append({
            'date': today, 'wm_score': int(current_score),
            'user_said': data.get('message', '')[:200], 'bot_replied': '',
            'total_duration': extracted_fields.get('total_duration', 0) if extracted_fields else 0,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        if len(h) > 100:
            profile['history'] = h[-100:]

        _px._save_user_profile(profile, openid)

    # ===== 预测偏差自适应 =====
    # 记录实际评分 vs 预测的偏差，用于个性化调优预测模型
    try:
        from prediction_engine import record_prediction_discrepancy
        # 从 profile 获取最近做出的预测（调度器或 chat 中做的）
        pred_cache = profile.get('_last_prediction', {})
        if pred_cache and current_score:
            profile = record_prediction_discrepancy(profile, current_score, pred_cache)
            _px._save_user_profile(profile, openid)
    except Exception as e:
        pass  # 预测自适应失败不影响主流程

    # 干预调度器：基于预测评分 + RL 数据，自动选择干预策略
    try:
        from intervention_scheduler import schedule_intervention
        scheduled, intervention = schedule_intervention(profile, result)
        if scheduled:
            _px._save_user_profile(profile, openid)
            _ai_log.info('[Intervention] %s for %s: %s (%s)',
                intervention['name'], openid[:8], intervention['reason'],
                'verified' if intervention.get('effective_before') else 'new')
        else:
            _ai_log.info('[Intervention] no schedule needed for %s: score=%s pred=...',
                openid[:8], current_score)
    except Exception as e:
        _ai_log.warning('[Intervention] scheduling failed: %s', e)

    expert_count = len(result.get('expert_detail', {})) if isinstance(result, dict) else 0
    _record_metric('/api/sleep-analyze', 0, detail={
        'openid': openid[:8], 'expert_count': expert_count,
        'has_score': 'total_score' in result if isinstance(result, dict) else False,
    })
    return {'result': result}


@route('/api/sleep-report')
def handle_sleep_report(data):
    """睡眠报告（简化版）"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    latest = profile.get('latest', {})
    history = profile.get('history', [])
    scores = [h.get('score', 0) for h in history if h.get('score')]
    avg = round(sum(scores) / len(scores), 1) if scores else 0
    return {
        'latest': latest,
        'avg_score': avg,
        'total': len(history),
        'source': 'AI聊天生成',
    }


@route('/api/meditation-plan')
def handle_meditation_plan(data):
    """冥想计划（安全状态机版）—— 固定协议，大模型只填充过渡文字
    协议: [4-7-8呼吸, 身体扫描, 正念观察, 渐进放松]
    每个协议有硬编码的安全步进路径，不做自由生成。
    """
    openid = data.get('openid', 'default')
    duration = int(data.get('duration', 5))  # 分钟
    protocol = data.get('protocol', '4-7-8')

    # ===== 预定义安全协议（每一步都是经过心理学验证的固定指令） =====
    PROTOCOLS = {
        '4-7-8': {  # 4-7-8 呼吸法：标准化节律，不做任何创意改编
            'name': '4-7-8 呼吸法',
            'steps': ['用鼻子吸气 4 秒', '屏住呼吸 7 秒', '用嘴巴缓慢呼气 8 秒'],
            'repeat_every': 19,  # 4+7+8=19秒一个循环
        },
        'body_scan': {  # 身体扫描：从头到脚固定路径，不跳跃
            'name': '身体扫描',
            'path': ['头顶', '额头和眉眼', '脸颊和下巴', '脖子和肩膀',
                     '手臂和双手', '胸腔和腹部', '背部', '大腿和膝盖',
                     '小腿和双脚'],
            'total_seconds': 300,  # 5分钟完整扫描
        },
        'breathing': {  # 正念呼吸：锚定呼吸，不做联想引导
            'name': '正念呼吸',
            'steps': ['感受气息进入鼻腔', '感受胸腔的起伏', '感受气息离开身体'],
            'repeat_every': 15,
        },
        'pmr': {  # 渐进式肌肉放松：固定收紧-放松对，避免突发动作
            'name': '渐进式肌肉放松',
            'pairs': [
                ('紧握双拳', '松开双拳'),
                ('耸肩到耳根', '放松肩膀'),
                ('皱眉', '舒展额头'),
                ('咬紧牙关', '放松下颌'),
                ('收紧腹部', '放松腹部'),
                ('勾脚尖', '放松脚踝'),
            ],
            'pair_seconds': 30,
        },
    }

    if protocol not in PROTOCOLS:
        protocol = '4-7-8'
    p = PROTOCOLS[protocol]

    # 按协议类型分步构建
    steps = []
    if protocol == 'body_scan':
        # 身体扫描：固定路径
        sec_per_part = max(p['total_seconds'] // len(p['path']), 10)
        for i, area in enumerate(p['path']):
            step_sec = i * sec_per_part
            steps.append({
                'second': step_sec,
                'phase': 'scan',
                'instruction': f'将注意力带到{area}，感受那里的感觉',
                'area': area,
            })
        steps.append({
            'second': p['total_seconds'],
            'phase': 'return',
            'instruction': '慢慢将注意力带回全身，感受身体整体的放松',
        })
    elif protocol == 'pmr':
        # 渐进放松：固定收紧-放松对
        for i, (tense, relax) in enumerate(p['pairs']):
            base = i * p['pair_seconds'] * 2
            steps.append({'second': base, 'phase': 'tense', 'instruction': tense})
            steps.append({'second': base + p['pair_seconds'], 'phase': 'relax', 'instruction': relax})
        steps.append({'second': len(p['pairs']) * p['pair_seconds'] * 2, 'phase': 'finish',
                      'instruction': '感受全身从紧张到放松的对比'})
    else:
        # 呼吸类（4-7-8 / 正念呼吸）：固定节律循环
        cycle_seconds = p.get('repeat_every', 19)
        total_cycles = min(max(duration * 60 // cycle_seconds, 3), 50)
        for i in range(total_cycles):
            for j, step_text in enumerate(p['steps']):
                second = i * cycle_seconds + (cycle_seconds // len(p['steps'])) * j
                if second >= duration * 60:
                    break
                steps.append({
                    'second': second,
                    'phase': 'breath',
                    'instruction': step_text,
                    'cycle': i + 1,
                })

    return {
        'protocol': protocol,
        'protocol_name': p['name'],
        'steps': steps,
        'total_duration': duration * 60,
        '_safe_constraint': '固定安全协议，不做自由生成',  # 声明约束，供审计
    }


@route('/api/intervention-complete')
def handle_intervention_complete(data):
    """干预完成记录"""
    return _px._handle_intervention_complete(data)


@route('/api/feedback')
def handle_feedback(data):
    """用户反馈：点赞/踩 AI 回复"""
    openid = data.get('openid', 'default')
    message_id = data.get('message_id', '')
    fb_type = data.get('type', 'like')  # like | dislike | report
    fb_text = data.get('text', '')

    ok = _px._store_feedback(openid, message_id, fb_type, fb_text)
    if not ok:
        return {'error': 'feedback failed'}

    # 同时记录到指标
    _record_metric('/api/feedback', 0, detail={
        'openid': openid[:8],
        'type': fb_type,
        'has_text': bool(fb_text),
    })
    return {'status': 'ok', 'stored': True}


@route('/api/data-export')
def handle_data_export(data):
    """数据导出"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    return {
        'openid': openid,
        'total_sessions': profile.get('total_sessions', 0),
        'history_count': len(profile.get('history', [])),
        'member': profile.get('member', {}),
    }


@route('/api/butler-check')
def handle_butler_check(data):
    """管家检查"""
    openid = data.get('openid', 'default')
    _px._trigger_self_learn()
    return {'status': 'ok', 'time': datetime.now().isoformat()}


@route('/api/biz-intel')
def handle_biz_intel(data):
    return {'intel': []}


@route('/api/emotion-timeline')
def handle_emotion_timeline(data):
    return {'timeline': []}


@route('/api/pubmed-update')
def handle_pubmed_update(data):
    """文献更新"""
    return {'status': 'ok', 'message': '文献更新已触发'}


@route('/api/pubmed-recent')
def handle_pubmed_recent(data):
    return {'articles': []}


@route('/health', methods=['GET', 'POST'])
def handle_health(data):
    from ops import get_server_info
    from ai_client import DEEPSEEK_API_KEY
    info = get_server_info()
    return {
        'status': 'ok',
        'time': datetime.now().isoformat(),
        'mode': 'async',
        'version': info['version'],
        'tag': info['tag'],
        'uptime': round(info['uptime'], 1),
        'deepseek_configured': bool(DEEPSEEK_API_KEY),
        'fallback_available': True,
    }


@route('/', methods=['GET'])
def handle_root(data):
    return handle_health(data)


# ==================== AI API 调用 ====================
# ==================== 指标收集（结构化） ====================
import collections as _coll

_METRICS = {'_global': {'start_time': time.time()}}
_DETAILS = _coll.deque(maxlen=500)  # 保留最近 500 条请求详情

def _record_metric(path, elapsed_ms, has_error=False, cache_hit=False, detail=None):
    """记录一次调用指标 + 可选详情"""
    m = _METRICS.setdefault(path, {'calls': 0, 'errors': 0, 'total_ms': 0, 'cache_hit': 0})
    m['calls'] += 1
    m['total_ms'] += elapsed_ms
    if has_error:
        m['errors'] += 1
    if cache_hit:
        m['cache_hit'] += 1
    if detail:
        detail['path'] = path
        detail['elapsed_ms'] = round(elapsed_ms, 1)
        detail['ts'] = datetime.now().strftime('%H:%M:%S')
        _DETAILS.append(detail)


@route('/api/metrics', methods=['GET', 'POST'])
def handle_metrics(data):
    """指标概览端点"""
    m = dict(_METRICS)
    uptime = time.time() - m['_global']['start_time']
    stats = {}
    for path, d in m.items():
        if path == '_global':
            continue
        c = d.get('calls', 0)
        stats[path] = {
            'calls': c,
            'errors': d.get('errors', 0),
            'cache_hit': d.get('cache_hit', 0),
            'avg_ms': round(d.get('total_ms', 0) / max(c, 1), 1),
        }
    return {
        'uptime_seconds': round(uptime),
        'uptime_human': f'{int(uptime//3600)}h{int((uptime%3600)//60)}m{int(uptime%60)}s',
        'total_calls': sum(s['calls'] for s in stats.values()),
        'routes': stats,
    }


@route('/api/metrics/detail', methods=['GET', 'POST'])
def handle_metrics_detail(data):
    """详细指标：最近 500 条请求详情"""
    uptime = time.time() - _METRICS.get('_global', {}).get('start_time', time.time())
    return {
        'uptime_seconds': round(uptime),
        'recent_total': len(_DETAILS),
        'recent': list(_DETAILS),
    }


@route('/api/pending-push', methods=['GET', 'POST'])
def handle_pending_push(data):
    """获取/确认用户待处理的推送

    GET: 返回用户所有未读推送
    POST: 标记推送为已读/已接受
    """
    openid = data.get('openid', 'default')
    action = data.get('action', 'get')

    from scheduler_daemon import get_pending_pushes, mark_push_read, mark_push_accepted

    if action == 'get':
        pushes = get_pending_pushes(openid)
        return {'push': pushes, 'count': len(pushes)}

    if action == 'read':
        push_id = data.get('push_id')
        ok = mark_push_read(push_id=push_id) if push_id else mark_push_read(openid=openid)
        return {'status': 'read', 'ok': ok}

    if action == 'accepted':
        push_id = data.get('push_id')
        ok = mark_push_accepted(push_id) if push_id else False
        return {'status': 'accepted', 'ok': ok}

    return {'error': 'unknown_action'}


@route('/api/metrics/hourly', methods=['GET', 'POST'])
def handle_metrics_hourly(data):
    """每小时聚合指标"""
    from datetime import timedelta as _td
    now = datetime.now()
    hour_ago = now - _td(hours=1)

    # 统计最近 1 小时的请求数（按秒聚合）
    seconds = {}
    for d in _DETAILS:
        ts_str = d.get('ts', '')
        try:
            t = datetime.strptime(ts_str, '%H:%M:%S').replace(year=now.year, month=now.month, day=now.day)
        except:
            continue
        if t < hour_ago:
            continue
        sec_key = t.strftime('%H:%M')
        seconds.setdefault(sec_key, {'qps': 0, 'errors': 0, 'avg_ms': 0, 'total_ms': 0})
        seconds[sec_key]['qps'] += 1
        seconds[sec_key]['total_ms'] += d.get('elapsed_ms', 0)
        if d.get('error'):
            seconds[sec_key]['errors'] += 1

    for k in seconds:
        s = seconds[k]
        s['avg_ms'] = round(s['total_ms'] / max(s['qps'], 1), 1)
        del s['total_ms']

    return {
        'period': 'last_1h',
        'buckets': dict(sorted(seconds.items())),
    }

# ==================== 路由查找 ====================
def dispatch(method, path, data):
    """路由分发 + 自动指标采集 + 限流"""
    openid = data.get('openid', 'default') if isinstance(data, dict) else 'default'
    key = (method, path)

    # 限流（health/metrics 不限流）
    if path not in {'/health', '/', '/api/metrics', '/api/metrics/detail', '/api/metrics/hourly'}:
        allowed, wait = _check_rate_limit(openid, path)
        if not allowed:
            return {'error': 'rate_limit_exceeded', 'retry_after': wait, 'path': path}

    t0 = time.time()
    if key in ROUTES:
        try:
            result = ROUTES[key](data)
            elapsed = (time.time() - t0) * 1000
            has_error = 'error' in result and not result.get('version')
            # handler 内部可能已调 _record_metric 传了 detail，这里只做基本计数
            if path not in {'/api/chat', '/api/sleep-analyze'}:
                _record_metric(path, elapsed, has_error=has_error)
            return result
        except Exception as e:
            elapsed = (time.time() - t0) * 1000
            _record_metric(path, elapsed, has_error=True)
            return {'error': str(e), '_path': path}
    if path in {'/api/stats', '/api/conversation-summaries', '/api/mark-brief-read',
                '/api/voice-relax', '/api/sleep-analyze'}:
        _record_metric(path, (time.time()-t0)*1000)
        return {'info': f'路由 {path} 就绪', 'mode': 'async'}
    _record_metric(path, (time.time()-t0)*1000, has_error=True)
    return {'error': 'not found', 'path': path}


# ==================== 自测 ====================
if __name__ == '__main__':
    print(f'[dp_router] {len(ROUTES)} routes registered')
    for (m, p), fn in sorted(ROUTES.items()):
        print(f'  {m:6s} {p:30s} → {fn.__name__}')
    # 测试 health
    r = dispatch('GET', '/health', {})
    print(f'[dp_router] health test: {r}')
    print('[dp_router] OK')
