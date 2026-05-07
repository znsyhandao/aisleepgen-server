#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dp_router.py - AISleepGen 路由处理层

所有 handler 作为模块级函数，接收 dict 返回 dict。
零 HTTP I/O，零 self 引用。可被 asyncio 或 sync 服务器同等调用。

从 deepseek_proxy.py ProxyHandler 类方法重构而来。
每个函数对应一个 API 路由。
"""
import os, json, time, hashlib, subprocess, threading, logging, collections as _coll
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs

# 认知信念模型
try:
    from cognitive_belief import update as _cb_update, profile_summary as _cb_summary
except:
    _cb_update = lambda *a, **kw: None
    _cb_summary = lambda *a: ''

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
USER_PROFILE_PATH = os.path.join(PROJECT_ROOT, 'user_profile.json')

# ===== 微信登录配置 =====
_WX_APPID = os.environ.get('WX_APPID', '')
_WX_SECRET = os.environ.get('WX_SECRET', '')

# ===== 限流系统 =====
_RATE_LIMIT = {}  # {openid: [timestamps]}
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_WINDOW_SEC = 60
_RATE_MAX_CALLS = 30
_RATE_MAX_CHAT = 10

def _check_rate_limit(openid, path):
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
            record.append(now)  # 这次也算进去--但返回拒绝
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

# ===== 缓存层注入 =====
import cache_layer
_ai_log.info('[Cache] Layer initialized: WM=%d DS=%d Profile=%d',
             cache_layer.WM_CACHE_SIZE, cache_layer.DS_CACHE_SIZE,
             cache_layer.PROFILE_CACHE_TTL // 60)

# ===== 路由表 =====
ROUTES = {}

# ===== 群体策略进化（v4.6.0） =====
_POPULATION_MANAGER = None
def _get_pop_mgr():
    global _POPULATION_MANAGER
    if _POPULATION_MANAGER is None:
        try:
            from population_manager import get_population_manager
            _POPULATION_MANAGER = get_population_manager()
        except ImportError:
            pass
    return _POPULATION_MANAGER


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


# ==================== 微信登录 ====================

@route('/api/wx-login')
def handle_wx_login(data):
    """微信小程序code换openid"""
    code = data.get('code', '')
    if not code:
        return {'error': 'missing_code'}
    if not _WX_APPID or not _WX_SECRET:
        import hashlib
        fake_openid = 'wx_' + hashlib.md5(code.encode()).hexdigest()[:16]
        _ai_log.info('[WX-Login] Dev mode, generated openid: %s', fake_openid[:10])
        return {'openid': fake_openid}
    try:
        import urllib.request
        url = (f'https://api.weixin.qq.com/sns/jscode2session'
               f'?appid={_WX_APPID}&secret={_WX_SECRET}&js_code={code}&grant_type=authorization_code')
        resp = json.loads(urllib.request.urlopen(url, timeout=5).read())
        if 'openid' in resp:
            _ai_log.info('[WX-Login] Got openid: %s', resp['openid'][:10])
            return {'openid': resp['openid']}
        else:
            _ai_log.warning('[WX-Login] API error: %s', resp.get('errmsg', 'unknown'))
            return {'error': resp.get('errmsg', 'login_failed')}
    except Exception as e:
        _ai_log.warning('[WX-Login] Failed: %s', e)
        return {'error': str(e)}


# ==================== 已拆离的 handler ====================

@route('/api/chat')
def handle_chat(data):
    """聊天处理--注入完整用户画像到 prompt"""
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

    # ===== 1. 加载用户数据和上下文（走缓存层） =====
    profile = cache_layer.get_cached_profile(openid)
    # 如果 profile 有人设设置且请求没指定，用 profile 里的
    if not data.get('persona'):
        persona = profile.get('ai_persona', 'restorative')
    latest = profile.get('latest', {})
    today = datetime.now().strftime('%Y-%m-%d')

    # 历史上下文
    from trend_layer import _build_history_context
    history_context, _ = _build_history_context(openid)

    # ===== 世界模型分析（走缓存层） =====
    wm = _px._get_world_model()
    wm_context = ''
    quality = ''
    score = 0
    deb = None
    extracted_fields = None  # 用于降级引擎

    # 先查缓存
    wm_cache_key = f'{openid}_{message.strip()[:100]}'
    cached_wm = cache_layer.get_wm_cache(openid, message)
    if cached_wm and isinstance(cached_wm, dict):
        _ai_log.info('[Cache] WM reusing cached result for %s', openid[:8])
        quality = cached_wm.get('quality', '')
        score = cached_wm.get('total_score', 0)
        deb = cached_wm.get('expert_debate')
        wm_context = json.dumps({'quality': quality, 'score': score}, ensure_ascii=False)
    elif wm:
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
            # 写入缓存（仅保存关键字段，减小体积）
            cache_layer.set_wm_cache(openid, message, {
                'quality': quality, 'total_score': score, 'expert_debate': deb
            })

    # 跨日趋势 + 场景
        # ===== WMTrace init =====
    _trace_ctx = {}
    try:
        from wm_trace import WMTrace
        _trace_obj = WMTrace(openid)
        _trace_ctx['obj'] = _trace_obj
    except Exception:
        _trace_obj = None

    # ===== wm_router: predict memory retrieval strategy =====
    _memory_strategy = None
    try:
        from wm_router import WMRouter
        _wm_router = WMRouter()
        _neural_for_router = extracted_fields if isinstance(extracted_fields, dict) else {}
        _strategy = _wm_router.predict_strategy(message, _neural_for_router)
        if isinstance(_strategy, dict):
            _memory_strategy = _strategy
    except Exception:
        pass

    # ===== wm_memory: retrieve similar cases =====
    _memory_context = ''
    try:
        if _memory_strategy and _memory_strategy.get('retrieve', 0) > 0:
            from wm_memory import retrieve_similar
            _retrieved = retrieve_similar(extracted_fields, message, top_k=_memory_strategy.get('top_k', 2))
            if isinstance(_retrieved, list) and len(_retrieved) > 0:
                _memory_context = '\n【参考案例】\n'
                for _r_entry in _retrieved[:3]:
                    _r_text = _r_entry.get('user_text', _r_entry.get('raw_text', ''))[:150]
                    _r_fb = _r_entry.get('feedback', '')
                    if _r_fb:
                        _memory_context += f'- 用户: {_r_text}\n  效果: {_r_fb}\n'
                    else:
                        _memory_context += f'- 用户: {_r_text}\n'
    except Exception:
        pass

    # ===== WMTrace layer: memory_retrieval =====
    if _trace_obj:
        try:
            _trace_obj.layer('memory_retrieval',
                retrieved=len(_retrieved) if '_retrieved' in dir() and isinstance(_retrieved, list) else 0,
                strategy=str(_memory_strategy) if _memory_strategy else 'none')
        except Exception:
            pass

    # ===== WMTrace layer: neural_extractor =====
    if _trace_obj:
        try:
            _field_count = len(extracted_fields) if isinstance(extracted_fields, dict) else 0
            _trace_obj.layer('neural_extractor', fields=_field_count)
        except Exception:
            pass

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

    # ===== 情绪追踪 + 决策引擎（替代旧的情绪推送） =====
    try:
        from emotion_monitor import record_emotion
        emotion_meta = record_emotion(profile, message)
        if emotion_meta and openid != 'default':
            from push_decision import decide_interaction
            decision = decide_interaction(openid, 'chat_emotion', {
                'emotion': emotion_meta,
                'message': message,
                'reply_len': len(reply) if 'reply' in dir() and reply else 0,
            }, profile)
            # 如果决策是 in_chat（嵌入关怀），会在后续AI回复中附加
            if decision['action'] == 'in_chat':
                _ai_log.info('[Decision] Chat emotion care embedded for %s: %s', openid[:8], decision['detail'])
            # 如果决策要推送，记录但等AI回复生成后再检查回复长度
    except Exception as e:
        _ai_log.warning('[Emotion] Record failed (non-blocking): %s', e)

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

    # 构建最近对话摘要（防止断片）
    _recent_conv = ''
    if history and len(history) > 0:
        _recent_turns = history[-4:]
        _conv_lines = []
        for _m in _recent_turns:
            _role = _m.get('role', 'user')
            _content = _m.get('content', '')
            if len(_content) > 200:
                _content = _content[:200] + '...'
            _conv_lines.append(f'{_role}: {_content}')
        _recent_conv = '\n'.join(_conv_lines)

    sc = build_system_content(
        correction_note=correction_note,
        score_calibration_hint=score_hint,
        today_str=today,
        history_context=history_context,
        recent_conversation=_recent_conv,
        wm_context=wm_context,
        scene_context=scene_text,
        tone_adjust_inject=style_adjust,
        recommendation_insights=rec_insights,
        persona_config=persona_config,
        emotion_prefix=emotion_prefix,
        intervention_hint=intervention_hint,
    )
    messages = build_messages(sc, history, message)

    # ===== 3. AI 调用（异步管道：快速回复 + 后台深度分析） =====
    from async_pipeline import process_chat, fast_analysis, schedule_deep_analysis
    from safeguards import record_api_call

    # 使用异步管道：先快速本地分析（<50ms），后台调 DeepSeek
    pipeline_result = process_chat(openid, message, history, profile)
    reply = pipeline_result.get('reply', '')
    score = pipeline_result.get('score', 0)
    token_estimate = len(reply) // 4 if reply else 0
    _ai_log.info('[Async] Chat reply for %s: %.1fms (local=%s deep=%s)',
                 openid[:8], pipeline_result.get('elapsed_ms', 0),
                 pipeline_result.get('local_only', False),
                 pipeline_result.get('has_deep_result', False))



    # ===== 决策引擎：在回复中嵌入情绪关怀 =====
    try:
        if reply and len(reply) > 15 and openid != 'default':
            from push_decision import decide_interaction
            decision = decide_interaction(openid, 'chat_emotion', {
                'emotion': emotion_meta if 'emotion_meta' in dir() else {'emotion': 'unknown', 'score': 0, 'confidence': 0, 'matched': []},
                'message': message,
                'reply_len': len(reply),
            }, profile)
            if decision['action'] == 'in_chat' and decision['content']:
                reply = reply.rstrip() + decision['content']
                _ai_log.info('[Decision] Emotion care embedded for %s (%s)', openid[:8], decision['detail'][:40])
    except Exception as e:
        _ai_log.warning('[Decision] In-chat care embed failed: %s', e)

    # ===== 3b. 降级检测：DeepSeek 不可用时用本地模板引擎 =====

    # ===== DeepSeek override: use DeepSeek directly for better reply =====
    from ai_client import DEEPSEEK_API_KEY as _ds_key
    if _ds_key:
        try:
            # Build prompt with history injection
            _ds_system_text = '你是睡眠顾问，根据用户描述给出专业、有针对性的建议，不要发散。'
            _ds_user_text = str(message)

            # Inject conversation history
            if history:
                _prev_list = []
                for _h in history[-2:]:
                    if isinstance(_h, dict):
                        _r = _h.get('role', 'user')
                        _c = str(_h.get('content', ''))[:100]
                        if _c:
                            _prev_list.append(f'{_r}: {_c}')
                if _prev_list:
                    _ds_user_text = '【前情提要】\n' + '\n'.join(_prev_list) + '\n\n【当前消息】\n' + str(message)

            # Inject extracted sleep data
            if extracted_fields:
                _ds_user_text += '\n\n【系统提取到的睡眠数据】' + str({k: v for k, v in extracted_fields.items() if v and k not in ('determined', 'confidence')})

            # Inject memory context if available
            if _memory_context:
                try:
                    _ds_user_text += _memory_context
                except Exception:
                    pass

            # Inject world model findings as background knowledge (not score)
            if isinstance(wm_result, dict):
                try:
                    _f_list = []
                    # From insights summary (sentence-level findings from all experts)
                    _summary = wm_result.get('insights', {}).get('summary', [])
                    if isinstance(_summary, list):
                        for _s in _summary:
                            if isinstance(_s, str) and len(_s) > 5:
                                _f_list.append(_s)
                    # From risk_flags
                    _risks = wm_result.get('insights', {}).get('risk_flags', [])
                    if isinstance(_risks, list):
                        for _r in _risks:
                            if isinstance(_r, str):
                                _f_list.append(f'[风险] {_r}')
                    # From debate_log (expert discussion records)
                    _debate_log = wm_result.get('expert_debate', {}).get('debate_log', [])
                    if isinstance(_debate_log, list):
                        for _dl in _debate_log:
                            if isinstance(_dl, str):
                                _f_list.append(f'[专家辩论] {_dl}')
                    if _f_list:
                        _ds_user_text += '【系统专业分析】' + ''.join(_f_list[:8])
                except Exception:
                    pass
            _ds_messages = [{'role': 'system', 'content': _ds_system_text}, {'role': 'user', 'content': _ds_user_text}]

            from ai_client import call_deepseek_api as _call_ds_api
            _ds_reply = _call_ds_api(_ds_messages, use_async=False)
            if _ds_reply and len(str(_ds_reply)) > 20:
                reply = str(_ds_reply)
                if _trace_obj:
                    try:
                        _trace_obj.layer('sync_deepseek_override', reply_len=len(reply))
                    except Exception:
                        pass
        except Exception as _ds_e:
            pass

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
            profile = cache_layer.get_cached_profile(openid)  # chat自动存档：可能需要最新profile
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
                cache_layer.set_cached_profile(openid, profile)
                if len(h) > 100:
                    profile['history'] = h[-100:]

            # 存储 AI 回复中的建议
            if isinstance(score, (int, float)) and score > 0:
                profile = store_recommendations(profile, reply, score)
                cache_layer.set_cached_profile(openid, profile)

            # ===== 睡眠教练：生成今日改善建议 =====
            try:
                from sleep_coach import (
                    get_daily_suggestion, apply_suggestion, evaluate_yesterday_suggestion
                )
                # 评估昨天建议的效果
                if isinstance(score, (int, float)) and score > 0:
                    profile, eval_result = evaluate_yesterday_suggestion(profile, int(score))
                    if eval_result:
                        _ai_log.info('[Coach] %s: yesterday suggestion effect=%d change=%+d',
                                     openid[:8], eval_result['effect_score'], eval_result['score_change'])
                        cache_layer.set_cached_profile(openid, profile)

                # 生成今日新建议
                emotion_state = profile.get('latest_emotion', 'neutral')
                suggestion = get_daily_suggestion(profile, emotion_state)
                if suggestion:
                    profile = apply_suggestion(profile, suggestion)
                    cache_layer.set_cached_profile(openid, profile)
                    _ai_log.info('[Coach] %s: suggestion "%s" generated', openid[:8], suggestion['title'])
                    # 将建议融入回复
                    coach_insert = f"\n\n💡 **今晚小建议**：{suggestion['action']}"
                    reply = reply + coach_insert
            except Exception as e:
                _ai_log.warning('[Coach] Error in chat handler: %s', e)

            # 检测"干预已接受"信号 → 标记干预完成
            if '干预已接受' in reply:
                pending = get_pending_interventions(profile)
                if pending:
                    from intervention_scheduler import mark_intervention_completed
                    mark_intervention_completed(profile, pending[0]['strategy_id'])
                    cache_layer.set_cached_profile(openid, profile)
                    _ai_log.info('[Intervention] accepted by %s: %s', openid[:8], pending[0]['name'])
        except Exception:
            pass  # 存档+建议追踪失败不阻塞回复

    # ===== 陪伴模式检测：用户说"睡不着"等关键词时自动切换 =====
    companion_started = False
    companion_initial = None
    if openid != 'default' and message and reply:
        companion_keywords = ['睡不着', '睡不觉', '失眠', '无法入睡', '怎么睡', '帮助入眠', '放松一下', '减压一下']
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in ['睡不着', '失眠', '无法入睡', 'help sleep']):
            try:
                from companion_mode import start_companion
                companion_initial = start_companion(openid, '4-7-8', message)
                companion_started = True
                # 回复改为：简短承认+立即启动陪伴
                reply = '我在这里。跟着我做几个呼吸，放松下来。'
                _ai_log.info('[Companion] Started for %s via chat', openid[:8])
            except Exception as e:
                _ai_log.warning('[Companion] Start failed: %s', e)

    # ===== 缓存层：刷入任何待写profile =====
    try:
        cache_layer.flush_profile(openid)
    except Exception:
        pass

    # 从回复中移除干预标记（不暴露技术细节）
    if reply and '【干预已接受】' in reply:
        reply = reply.replace('【干预已接受】', '').strip()

    # ===== WMTrace final =====
    if _trace_obj:
        try:
            _trace_obj.layer('final_reply', reply_len=len(reply) if reply else 0)
            _trace_obj.save()
        except Exception:
            pass

        # ===== 信号检测器蜂群：检测意图 =====
    from detectors import detect_intent
    _action_trigger, _action_confidence, _action_kw_matched = detect_intent(str(message))
    # 置信度>0.5才触发沉浸式引导
    if _action_trigger and _action_confidence >= 0.5:
        reply = reply[:80]

    # ===== 沉浸式引导检测 + return =====
    # ===== 实验日志闭环：chat实验 → concluded =====
    _chat_exp_id = None
    try:
        from experiment_log import Experiment, get_log
        _chat_exp = Experiment(
            openid, 'chat',
            f'用户发送消息 {message[:30]}',
            {'message_length': len(message), 'message_prefix': message[:20]}
        )
        _chat_exp_id = get_log().record_designed(_chat_exp)
        get_log().record_deployed(_chat_exp_id)
        get_log().record_observed(_chat_exp_id, {
            'reply_length': len(reply) if reply else 0,
            'has_companion': companion_started,
            'has_action': bool(_action_trigger),
        })
        _outcome_positive = bool(reply and len(reply) > 20 and not companion_started)
        get_log().record_concluded(_chat_exp_id, {
            'positive': _outcome_positive,
            'score_change': 0,
            'detail': f'reply_len={len(reply) if reply else 0}'
        }, f'用户{openid[:8]}的chat实验: {_outcome_positive}')
    except Exception as _el_e:
        pass

    # ===== 认知信念更新（每次chat交互后） =====
    try:
        _cb_update(openid, score=score if isinstance(score, (int, float)) else None,
                   feedback=1 if _outcome_positive else 0)
    except:
        pass

    # 判断用户是否有足够数据支撑专家模拟
    _has_user_data = bool(latest and (
        latest.get('total_score') or latest.get('bedtime') or latest.get('wake_time') or
        latest.get('sleep_latency') or latest.get('emotion')
    )) or bool(history_context and len(history_context) > 50)
    # default用户（未拿到真实openid）一律视为无数据，防止脏数据导致伪专家会诊
    if openid in ('default', ''):
        _has_user_data = False
    _expert_detail = pipeline_result.get('expert_detail', None)
    _debate = deb if deb else None
    if not _has_user_data:
        _expert_detail = None
        _debate = None

    return {
        'reply': reply,
        'action': _action_trigger,
        'meditation_protocol': _action_trigger,
        'token_estimate': token_estimate,
        'timestamp': datetime.now().strftime('%%Y-%%m-%%d %%H:%%M:%%S'),
        'ai_score': round(score, 1) if isinstance(score, (int, float)) else None,
        'ai_quality': quality if quality else None,
        'debate': _debate,
        'async_pipeline': True,
        'local_only': pipeline_result.get('local_only', False),
        'elapsed_ms': pipeline_result.get('elapsed_ms', 0),
        'companion': companion_initial if companion_started else None,
        'expert_detail': _expert_detail if _expert_detail is not None else None,
    }

@route('/api/user-profile')
def handle_user_profile(data):
    """获取用户画像"""
    openid = data.get('openid', 'default')
    profile = _px._load_user_profile(openid)
    # 过滤敏感字段
    safe = {k: v for k, v in profile.items()
            if k not in ('_pending_review', '_last_intervention')}
    # Load trend prediction data
    try:
        from prediction_engine import get_trend_data
        trend = get_trend_data(profile)
        safe['_trend_data'] = trend
    except Exception:
        safe['_trend_data'] = {'has_data': False}
    return {'profile': safe}



@route('/api/dashboard')
def handle_dashboard(data):
    """Sleep Dashboard - aggregate intelligence for home page"""
    openid = data.get('openid', 'default')
    profile = cache_layer.get_cached_profile(openid)
    if not profile:
        return {'dashboard': {'has_data': False}}

    from datetime import datetime
    now = datetime.now()
    hour = now.hour

    # Greeting by time
    if hour < 6: greeting = '夜深了'
    elif hour < 12: greeting = '早上好'
    elif hour < 14: greeting = '中午好'
    elif hour < 18: greeting = '下午好'
    else: greeting = '晚上好'

    # Latest sleep
    history = profile.get('history', [])
    latest = history[-1] if history and isinstance(history[-1], dict) else {}
    last_score = latest.get('wm_score', 0)
    total_dur = latest.get('total_duration', 0)
    dur_str = f'{total_dur//60}h{total_dur%60}min' if total_dur > 0 else ''
    deep_pct = latest.get('deep_pct', 0)
    light_pct = latest.get('light_pct', 0)
    rem_pct = latest.get('rem_pct', 0)
    bedtime = latest.get('bedtime', '')
    awake_times = latest.get('awake_times', 0)

    # Quality label
    if last_score >= 80: quality = '优秀'
    elif last_score >= 65: quality = '良好'
    elif last_score >= 50: quality = '一般'
    else: quality = '偏低'

    # One-liner
    parts = []
    if deep_pct > 0: parts.append(f'深睡{deep_pct:.0f}%')
    if awake_times > 0: parts.append(f'醒了{awake_times}次')
    if bedtime: parts.append(bedtime)
    one_liner = '、'.join(parts)
    if one_liner:
        one_liner += '。'
        if deep_pct > 0 and deep_pct < 25: one_liner += '深睡偏少，今晚提前30分钟关灯试试。'
        elif awake_times > 2: one_liner += '夜醒偏多，注意白天少喝咖啡。'
        elif last_score >= 65: one_liner += f'{quality}，继续保持。'
        else: one_liner += '今晚好好调整。'

    # 7-day average
    week_scores = [h.get('wm_score', 0) for h in (history[-7:] if history else []) if isinstance(h, dict) and h.get('wm_score', 0) > 0]
    week_avg = round(sum(week_scores) / len(week_scores), 1) if week_scores else 0

    # Prediction
    prediction = None
    try:
        from prediction_engine import predict_tonight
        prediction = predict_tonight(profile)
    except Exception: pass

    return {'dashboard': {
        'has_data': bool(last_score > 0),
        'greeting': greeting,
        'last_score': last_score,
        'duration': dur_str,
        'quality': quality,
        'deep_pct': deep_pct,
        'light_pct': light_pct,
        'rem_pct': rem_pct,
        'bedtime': bedtime,
        'awake_times': awake_times,
        'one_liner': one_liner,
        'week_avg': week_avg,
        'prediction': prediction,
    }}


@route('/api/update-profile')
def handle_update_profile(data):
    """更新用户画像"""
    openid = data.get('openid', 'default')
    updates = data.get('profile', {})
    # 兼容: onboarding_survey 在一级字段时
    if not updates and 'onboarding_survey' in data:
        updates = data
    if openid and updates:
        def modifier(p):
            # 合并 latest
            if 'latest' in updates:
                p['latest'] = updates['latest']
            # 追加 history（不是覆盖）
            if 'history' in updates and isinstance(updates['history'], list):
                if 'history' not in p:
                    p['history'] = []
                for entry in updates['history']:
                    p['history'].append(entry)
            # 其他字段直接更新
            for k, v in updates.items():
                if k not in ('latest', 'history'):
                    p[k] = v
            return p
        _px._atomic_write_profile(openid, modifier)

        # 检测是否包含survey提交（含睡眠数据）
        profile_data = updates.get('latest', {})
        if profile_data.get('bedtime') or profile_data.get('total_duration'):
            try:
                from body_context import report_body_event
                report_body_event(openid, 'survey_submitted', profile_data)
            except ImportError:
                pass
            except Exception:
                pass

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
    from neural_extractor import NeuralExtractor
    _ne = NeuralExtractor(prefer_llm=True)
    extracted_fields = _ne.extract(data_msg)

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
    profile = cache_layer.get_cached_profile(openid)
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

        cache_layer.set_cached_profile(openid, profile)

    # ===== 预测偏差自适应 =====
    # 记录实际评分 vs 预测的偏差，用于个性化调优预测模型
    try:
        from prediction_engine import record_prediction_discrepancy
        # 从 profile 获取最近做出的预测（调度器或 chat 中做的）
        pred_cache = profile.get('_last_prediction', {})
        if pred_cache and current_score:
            profile = record_prediction_discrepancy(profile, current_score, pred_cache)
            cache_layer.set_cached_profile(openid, profile)
    except Exception as e:
        pass  # 预测自适应失败不影响主流程

    # 决策引擎：评分更新事件 → 统一推送决策
    try:
        if isinstance(current_score, (int, float)) and current_score > 0 and openid != 'default':
            # v3.2: 预测编码引擎替换旧的纯规则推送决策
            predictive_decision = None
            bedtime_for_pc = data.get('bedtime', '') or profile.get('latest', {}).get('bedtime', '')
            try:
                from predictive_coding import update_predictor_from_survey
                pc_result = update_predictor_from_survey(openid, bedtime_for_pc, current_score)
                pc_decision = pc_result.get('after', {})

                # v3.5: 同时更新卡尔曼滤波器
                try:
                    from kalman_filter import get_manager
                    km = get_manager()
                    kf = km.get_filter(openid, profile)
                    bt_hours = None
                    if bedtime_for_pc:
                        from circadian_phase_model import _hours_from_time
                        bt_hours = _hours_from_time(bedtime_for_pc)
                    result = kf.update(score=current_score, bedtime=bt_hours)
                    km.save_filter(openid, kf, profile)
                    cache_layer.set_cached_profile(openid, profile)
                    _ai_log.debug('[KF] Updated for %s: score=%s unc=%.2f K=%.3f',
                                   openid[:8], result['score_after'], result['uncertainty_after'], result['kalman_gain'][0])
                except ImportError:
                    pass
                except Exception as e:
                    _ai_log.warning('[KF] Update failed (non-blocking): %s', e)

                # 如果预测编码说"不确定性高" → 用聊天获取信息，不直接推
                if pc_decision.get('should_interact'):
                    predictive_decision = 'chat'  # 替代推送
                    _ai_log.info('[PC] High uncertainty -> chat mode for %s (uncertainty=%.2f)',
                                  openid[:8], pc_decision.get('uncertainty', 0))

            except ImportError:
                pass  # 可选模块
            except Exception as e:
                _ai_log.warning('[PC] Update failed (non-blocking): %s', e)

            _survey_exp_id = None
            # ===== 实验日志：记录本次评分干预实验 =====
            try:
                from experiment_log import Experiment, get_log
                exp = Experiment(
                    openid,
                    'push',
                    f'用户评分{current_score}分，评估干预效果',
                    {'score': current_score, 'predictive_decision': predictive_decision}
                )
                eid = get_log().record_designed(exp)
                get_log().record_deployed(eid)
                get_log().record_observed(eid, {
                    'action': predictive_decision or 'skip',
                    'score': current_score,
                })
                # 在函数末尾conclude，暂存eid
                _survey_exp_id = eid
            except ImportError:
                pass
            except Exception as e:
                _ai_log.warning('[ExpLog] Survey log error: %s', e)

            if not predictive_decision:
                # v3.8: POMDP主动推理（自然语言 → 观测 → 信念 → 自由能决策）
                # 保留conscious_decider和push_decision作为降级路径
                pm_action = None
                pm_decision = None
                try:
                    from pomdp_learner import get_engine
                    pm_engine = get_engine()
                    # v3.15: 异常检测 → 注入POMDP观测
                    disc_obs = ''
                    try:
                        from discrepancy_detector import detect
                        disc = detect(openid, current_score, profile)
                        if disc['has_discrepancy']:
                            disc_obs = '评分异常变化'
                            if disc['direction'] == 'spike_down':
                                disc_obs = '评分突然降低'
                            elif disc['direction'] == 'spike_up':
                                disc_obs = '评分突然升高'
                            _ai_log.info('[Disc] %s: z=%.1f dir=%s sev=%s',
                                          openid[:8], disc['z_score'], disc['direction'], disc['severity'])
                            # 注入异常观测
                            pm_engine.observe(openid, text=disc_obs)
                    except ImportError:
                        pass
                    except Exception as e:
                        _ai_log.warning('[Disc] Failed: %s', e)

                    # 问卷作为结构化观测
                    pm_engine.observe_survey(openid, score=current_score,
                                              bedtime=bedtime_for_pc,
                                              time_of_day='night')
                    # 从对话文本（如果有）提取额外观测
                    all_text = ' '.join([
                        profile.get('latest_message', '') or '',
                        data_msg if isinstance(data_msg, str) else '',
                    ])
                    if all_text and len(all_text) > 3:
                        pm_engine.observe_message(openid, all_text[:200])

                    pm_decision = pm_engine.decide(openid)

                    # v4.6.0: 记录干预outcome到群体管理器
                    pm_ = _get_pop_mgr()
                    if pm_ is not None and pm_decision is not None:
                        action = pm_decision.get('policy', 'unknown')
                        # 根据评分变化判定正向/负向
                        prev_score = profile.get('latest', {}).get('total_score', 0) or 0
                        score_change = current_score - prev_score
                        is_positive = score_change > 0 or current_score > 65
                        try:
                            pm_.record_outcome(openid, action, score_change, is_positive)
                        except Exception as _pe:
                            _ai_log.warning('[PopMgr] Outcome record: %s', _pe)

                    # v3.14: 生命周期调制器（后处理，零侵入）
                    try:
                        from lifecycle_modulator import modulate_decision
                        pm_decision = modulate_decision(openid, profile, pm_decision)
                        _ai_log.info('[Lifecycle] %s -> %s (mult=%.2f)',
                                      pm_decision.get('lifecycle_phase', '?'),
                                      pm_decision.get('action', '?'),
                                      pm_decision.get('lifecycle_multiplier', 1.0))
                    except ImportError:
                        pass
                    except Exception as e:
                        _ai_log.warning('[Lifecycle] Failed: %s', e)

                    pm_policy = pm_decision.get('policy', 'skip')
                    if pm_policy == 'push':
                        pm_action = 'push_now'
                    elif pm_policy == 'delay_push':
                        pm_action = 'delay_push'
                    elif pm_policy in ('probe', 'in_chat'):
                        pm_action = pm_policy
                    else:
                        pm_action = 'skip'
                    _ai_log.info('[POMDP] Decision for %s: %s (score=%.1f, H=%.3f)',
                                  openid[:8], pm_policy,
                                  pm_decision.get('expected_score', 0),
                                  pm_decision.get('belief_entropy', 1))
                except ImportError:
                    pass
                except Exception as e:
                    _ai_log.warning('[POMDP] Failed (fallback to CD): %s', e)

                # v3.5: 意识决策器（降级路径）
                cd_action = pm_action
                cd_decision = pm_decision
                if not cd_action:
                    try:
                        from conscious_decider import decide as cd_decide
                        cd_decision = cd_decide(openid, 'score_update', {'total_score': current_score}, profile)
                        if cd_decision.get('action') == 'push_now':
                            cd_action = 'push_now'
                        elif cd_decision.get('action') == 'delay_push':
                            cd_action = 'delay_push'
                        elif cd_decision.get('action') == 'probe':
                            cd_action = 'probe'
                    except ImportError:
                        pass
                    except Exception as e:
                        _ai_log.warning('[CD] Decision failed (fallback): %s', e)

                if not cd_action:
                    from push_decision import decide_interaction, queue_delayed_push, execute_push
                    decision = decide_interaction(openid, 'score_update', {
                        'total_score': current_score,
                    }, profile)
                else:
                    from push_decision import queue_delayed_push, execute_push
                    decision = {
                        'action': cd_action,
                        'title': '💤 睡眠提醒',
                        'content': f'今晚评分{current_score}分，有点低。早睡些，明早会不同。',
                        'detail': str(pm_decision.get('policy', cd_decision.get('reason', 'POMDP'))) if pm_decision else cd_decision.get('reason', 'CD'),
                        'delay_hours': 8,
                    }

                if decision['action'] == 'push_now':
                    execute_push(openid, decision.get('title', ''), decision.get('content', ''))
                    _ai_log.info('[Decision] Score push now for %s: %s', openid[:8], decision['detail'][:40])
                elif decision['action'] == 'delay_push':
                    delay_h = decision.get('delay_hours', 8)
                    queue_delayed_push(openid, decision.get('title', ''), decision.get('content', ''),
                                       reason=decision['detail'], delay_hours=delay_h)
                    _ai_log.info('[Decision] Score delay push for %s in %dh: %s', openid[:8], delay_h, decision['detail'][:40])
                elif decision['action'] == 'probe':
                    # probe = 记录供后续聊天时注入，不直接执行推送
                    _ai_log.info('[Decision] Probe for %s: %s', openid[:8], decision['detail'][:40])
    except Exception as e:
        _ai_log.warning('[Decision] Score decision failed: %s', e)

    # ===== 睡眠教练：评估昨天建议 + 生成新建议 =====
    try:
        if isinstance(current_score, (int, float)) and current_score > 0:
            from sleep_coach import (
                get_daily_suggestion, apply_suggestion, evaluate_yesterday_suggestion, get_coach_summary
            )
            # 评估昨天建议
            profile, eval_result = evaluate_yesterday_suggestion(profile, int(current_score))
            if eval_result:
                _ai_log.info('[Coach] Analyze eval: %s effect=%d change=%+d',
                             openid[:8], eval_result['effect_score'], eval_result['score_change'])
                cache_layer.set_cached_profile(openid, profile)
                # v3.19: 干预效果回环
                try:
                    eff = eval_result.get('effect_score', 0)
                    change = eval_result.get('score_change', 0)
                    sk = eval_result.get('suggestion', '')
                    if eff or change:
                        from pomdp_learner import get_engine as _ge2
                        _ge2().observe(openid, effect=change)
                except Exception as _ee2:
                    _ai_log.warning('[Coach-POMDP] Analyze effect injection: %s', _ee2)

            # 生成今日建议
            emotion_state = profile.get('latest_emotion', 'neutral')
            suggestion = get_daily_suggestion(profile, emotion_state)
            if suggestion:
                profile = apply_suggestion(profile, suggestion)
                cache_layer.set_cached_profile(openid, profile)
                _ai_log.info('[Coach] Analyze sug: %s "%s"', openid[:8], suggestion['title'])
    except Exception as e:
        _ai_log.warning('[Coach] Analyze coach error: %s', e)

    expert_count = len(result.get('expert_detail', {})) if isinstance(result, dict) else 0
    _record_metric('/api/sleep-analyze', 0, detail={
        'openid': openid[:8], 'expert_count': expert_count,
        'has_score': 'total_score' in result if isinstance(result, dict) else False,
    })

    # ===== 认知信念更新（每次分析后） =====
    try:
        _cb_update(openid, score=current_score if isinstance(current_score, (int, float)) else None,
                   feedback=1 if (isinstance(current_score, (int, float)) and current_score > 60) else 0)
    except:
        pass

    # ===== 实验日志闭环：survey实验 → concluded =====
    if _survey_exp_id:
        try:
            from experiment_log import get_log
            get_log().record_concluded(_survey_exp_id, {
                'positive': bool(isinstance(result, dict) and result.get('total_score', 0) > 60),
                'score_change': current_score,
                'detail': 'survey_completed'
            }, f'survey实验concluded')
        except Exception:
            pass

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
    """冥想计划（安全状态机版）-- 固定协议，大模型只填充过渡文字
    协议: [4-7-8呼吸, 身体扫描, 正念观察, 渐进放松]
    每个协议有硬编码的安全步进路径，不做自由生成。
    """
    openid = data.get('openid', 'default')
    duration = int(data.get('duration', 5))  # 分钟
    protocol = data.get('protocol', '4-7-8')

    # ===== 10大沉浸式减压场景（心理学验正的固定协议） =====
    PROTOCOLS = {
        # === 呼吸类（4种） ===
        '4-7-8': {
            'name': '4-7-8 呼吸法',
            'icon': 'lungs',
            'desc': '经典的放松呼吸节律，降低交感神经兴奋',
            'steps': ['用鼻子吸气 4 秒', '屏住呼吸 7 秒', '用嘴巴缓慢呼气 8 秒'],
            'repeat_every': 19,
        },
        'box_breathing': {
            'name': '盒式呼吸',
            'icon': 'square',
            'desc': '海军海豹部队的镇静呼吸法，快速平复焦虑',
            'steps': ['吸气 4 秒', '屏住呼吸 4 秒', '呼气 4 秒', '屏住呼吸 4 秒'],
            'repeat_every': 16,
        },
        'breathing': {
            'name': '正念呼吸',
            'icon': 'wind',
            'desc': '把注意力锚定在呼吸上，让思绪自然消散',
            'steps': ['感受气息进入鼻腔', '感受胸腔的起伏', '感受气息离开身体'],
            'repeat_every': 15,
        },
        'pursed_lip': {
            'name': '缩唇呼吸',
            'icon': 'lips',
            'desc': '通过嘴唇控制呼吸节奏，适合焦虑引起的呼吸急促',
            'steps': ['用鼻子深吸气 2 秒', '嘴唇缩起像吹口哨', '缓慢呼气 4 秒'],
            'repeat_every': 12,
        },

        # === 放松类（3种） ===
        'body_scan': {
            'name': '身体扫描',
            'icon': 'scan',
            'desc': '从头到脚扫描身体感受，释放隐藏的紧张',
            'path': ['头顶', '额头和眉眼', '脸颊和下巴', '脖子和肩膀',
                     '手臂和双手', '胸腔和腹部', '背部', '大腿和膝盖',
                     '小腿和双脚'],
            'total_seconds': 300,
        },
        'pmr': {
            'name': '渐进式肌肉放松',
            'icon': 'muscle',
            'desc': '交替收紧和放松肌肉群，体验深度放松',
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
        'autogenic': {
            'name': '自律训练',
            'icon': 'warm',
            'desc': '通过自我暗示让身体感受到温暖和沉重，进入放松状态',
            'phrases': [
                '我的右臂很沉重...很温暖...',
                '我的左臂很沉重...很温暖...',
                '我的右腿很沉重...很温暖...',
                '我的左腿很沉重...很温暖...',
                '我的心脏在平稳地跳动...',
                '我的呼吸很平缓...',
                '我的腹部很温暖...',
                '我的额头很清凉...',
            ],
            'phrase_seconds': 20,
        },

        # === 意象类（2种） ===
        'safe_place': {
            'name': '安全岛想象',
            'icon': 'island',
            'desc': '在脑海中构建一个只属于你的安全空间',
            'elements': [
                '选择一个让你感到安全的环境--海边、森林或你熟悉的角落',
                '看看周围：你看到了什么颜色？什么形状？',
                '听听声音：海浪声？风声？树叶沙沙声？',
                '感受温度：微风吹过皮肤的感觉',
                '闻闻味道：空气中有什么气味？',
                '感受地面：脚下的触感是软是硬？',
                '告诉自己：这里很安全，没有需要担心的事',
            ],
            'element_seconds': 25,
        },
        'cloud_float': {
            'name': '云端漂浮',
            'icon': 'cloud',
            'desc': '想象自己躺在柔软的白云上，随云飘荡',
            'elements': [
                '把自己想象成一朵白云，柔软而轻盈',
                '感受身体像云一样缓缓上升',
                '低头看，地面的烦恼越来越小',
                '阳光穿过你，温暖而通透',
                '微风吹过，你轻轻飘动',
                '和周围的云朵打招呼，你们都是自由的',
                '现在缓缓下降，带着这份轻盈回到地面',
            ],
            'element_seconds': 25,
        },

        # === 声音类（1种） ===
        'sound_bath': {
            'name': '声音浴',
            'icon': 'sound',
            'desc': '用想象的声音营造疗愈氛围',
            'instruments': [
                '想象远处传来低沉的大提琴声，像大地在呼吸',
                '加入轻柔的雨声，滴滴答答落在屋顶',
                '一段清脆的风铃声随风而来',
                '低沉的颂钵声在大提琴下缓缓振动',
                '所有的声音慢慢融在一起，包裹着你',
            ],
            'instrument_seconds': 30,
        # === 行为认知类（5种新增） ===
        'cognitive_unloading': {
            'name': "认知卸荷 - 担忧日记",
            'icon': 'journal',
            'desc': '把脑子里放不下的事逐件写下来，清空工作记忆，效果等同入睡潜伏期缩短9min',
            'steps': [
                '闭上眼睛，回想今天一直在想的事情',
                '在脑海里把那件事"放在"一个盒子里',
                '告诉自己："明天再处理，现在不是时候"',
                '把注意拉回到呼吸上',
                '感受肩膀有没有放松一点',
                '现在想第二件事...重复这个步骤',
            ],
            'repeat_every': 30,
        },
        'paradoxical_intention': {
            'name': '矛盾意向疗法 - 努力清醒',
            'icon': 'eye',
            'desc': '放弃"必须睡着"的执念，反向操作：努力保持清醒，反而消除焦虑入睡',
            'steps': [
                '舒服躺好，睁开眼睛',
                '告诉自己："我不睡了，我要努力保持清醒"',
                '不要闭眼，专注盯着天花板或黑暗中的一点',
                '对自己说："清醒就是胜利，睡着了算我输"',
                '允许眼皮变重，但坚持不要闭上',
                '如果闭上就再睁开，继续"努力清醒"',
            ],
            'repeat_every': 25,
        },
        'stimulus_control': {
            'name': '刺激控制 - 重新建立床=睡觉',
            'icon': 'bed',
            'desc': '打破"床=睡不着焦虑"的条件反射，重新建立床和睡眠的唯一关联，效果Cohen d=0.87',
            'steps': [
                '现在你躺在床上，但感觉不困',
                '好，起来，离开床',
                '去一个昏暗安静的地方坐下',
                '不要看手机，不要做刺激的事',
                '等真正感到困意时再回床上',
                '如果躺下15分钟还不困，重复这个过程',
            ],
            'repeat_every': 40,
        },
        'sleep_hygiene': {
            'name': '睡眠卫生检查清单',
            'icon': 'checklist',
            'desc': '逐项检查优化睡眠环境和习惯，循证睡眠卫生教育',
            'steps': [
                '检查室温：18-22度最佳（凉爽助眠）',
                '检查光线：拉上窗帘，关闭所有发光源',
                '检查声音：关门关窗，或打开白噪音',
                '放下手机：蓝光抑制褪黑素分泌',
                '放松身体：洗个温水澡或做简单拉伸',
                '调整睡姿：侧卧最佳，减少打鼾和反流',
            ],
            'repeat_every': 35,
        },
        'cognitive_restructuring': {
            'name': '认知重构 - 挑战不合理信念',
            'icon': 'brain',
            'desc': '识别并挑战关于睡眠的灾难化思维，改善焦虑性失眠，效果Cohen d=0.65',
            'steps': [
                '注意到你在想什么："今晚又睡不着了"',
                '问自己：这句话是事实还是担忧？',
                '挑战它：你过去也有睡好的时候，说明能睡着',
                '替换："即使今晚睡不好，我明天也能撑过去"',
                '接受：身体有自我调节能力，相信它',
                '放下：不需要控制睡眠，让睡眠来找你',
            ],
            'repeat_every': 30,
        },

        },
    }

    if protocol not in PROTOCOLS:
        protocol = '4-7-8'
    p = PROTOCOLS[protocol]

    # 按协议类型分步构建
    steps = []
    if protocol == 'body_scan':
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
        for i, (tense, relax) in enumerate(p['pairs']):
            base = i * p['pair_seconds'] * 2
            steps.append({'second': base, 'phase': 'tense', 'instruction': tense})
            steps.append({'second': base + p['pair_seconds'], 'phase': 'relax', 'instruction': relax})
        steps.append({'second': len(p['pairs']) * p['pair_seconds'] * 2, 'phase': 'finish',
                      'instruction': '感受全身从紧张到放松的对比'})
    elif protocol == 'autogenic':
        # 自律训练：逐句暗示，每句重复2次
        for i, phrase in enumerate(p['phrases']):
            base = i * p['phrase_seconds']
            steps.append({'second': base, 'phase': 'suggest', 'instruction': '在心里默念：' + phrase,
                          'repeat': 2})
    elif protocol in ('safe_place', 'cloud_float'):
        # 意象类：引导想象元素，逐步构建画面
        elements = p.get('elements', [])
        for i, elem in enumerate(elements):
            base = i * p['element_seconds']
            steps.append({'second': base, 'phase': 'imagine', 'instruction': elem,
                          'element_index': i, 'element_total': len(elements)})
    elif protocol == 'sound_bath':
        # 声音浴：逐层叠加声音想象
        for i, inst in enumerate(p['instruments']):
            base = i * p['instrument_seconds']
            steps.append({'second': base, 'phase': 'sound', 'instruction': inst,
                          'instruments_active': i + 1, 'instrument_total': len(p['instruments'])})
    else:
        # 呼吸类
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
        '_safe_constraint': '安全协议，不做自由生成',
        # ===== 场景氛围参数（前端用于渲染背景/色调） =====
        'ambient_atmosphere': _get_atmosphere(protocol, p),
    }





def _get_atmosphere(protocol, p):
    """返回协议对应的氛围参数：背景色、文字色、主题色、氛围标签"""
    atm_map = {
        # 呼吸类
        '4-7-8': {'name': '4-7-8 呼吸法', 'bg_top': '#0a0a2e', 'bg_mid': '#12125a', 'bg_bot': '#1a0a3a', 'text': '#e8e0ff', 'accent': '#7c4dff', 'vibe': 'calm'},
        'box_breathing': {'name': '盒式呼吸', 'bg_top': '#0a1628', 'bg_mid': '#0f2847', 'bg_bot': '#0a1a2e', 'text': '#e0f0ff', 'accent': '#448aff', 'vibe': 'focus'},
        'breathing': {'name': '正念呼吸', 'bg_top': '#0a1a1a', 'bg_mid': '#0f2a1f', 'bg_bot': '#0a1a2e', 'text': '#e0ffe8', 'accent': '#4caf50', 'vibe': 'natural'},
        'pursed_lip': {'name': '缩唇呼吸', 'bg_top': '#080818', 'bg_mid': '#1a1040', 'bg_bot': '#0d0d2b', 'text': '#e8e0ff', 'accent': '#9c27b0', 'vibe': 'soft'},
        # 放松类
        'body_scan': {'name': '身体扫描', 'bg_top': '#1a120a', 'bg_mid': '#2a1a0a', 'bg_bot': '#1a1008', 'text': '#ffe8d0', 'accent': '#ff9800', 'vibe': 'warm'},
        'pmr': {'name': '渐进肌肉放松', 'bg_top': '#1a1008', 'bg_mid': '#2a1808', 'bg_bot': '#1a0e06', 'text': '#ffead0', 'accent': '#e65100', 'vibe': 'grounding'},
        'autogenic': {'name': '自律训练', 'bg_top': '#1a0e08', 'bg_mid': '#2a1410', 'bg_bot': '#1a0c08', 'text': '#ffded0', 'accent': '#d50000', 'vibe': 'womb'},
        # 意象类
        'safe_place': {'name': '安全岛', 'bg_top': '#1a1408', 'bg_mid': '#2a1c0a', 'bg_bot': '#1a1206', 'text': '#fff0d0', 'accent': '#ffab00', 'vibe': 'safe'},
        'cloud_float': {'name': '云端漂浮', 'bg_top': '#0a1428', 'bg_mid': '#1a2840', 'bg_bot': '#0a1a30', 'text': '#d0f0ff', 'accent': '#40c4ff', 'vibe': 'floating'},
        'sound_bath': {'name': '声音浴', 'bg_top': '#0a0820', 'bg_mid': '#1a1048', 'bg_bot': '#0a0830', 'text': '#e0d8ff', 'accent': '#7c4dff', 'vibe': 'expansion'},
        # 认知行为类
        'cognitive_unloading': {'name': '担忧日记', 'bg_top': '#14100e', 'bg_mid': '#1e1814', 'bg_bot': '#14100c', 'text': '#e8e0d8', 'accent': '#a1887f', 'vibe': 'release'},
        'paradoxical_intention': {'name': '努力清醒', 'bg_top': '#0e1018', 'bg_mid': '#181e2e', 'bg_bot': '#0e101a', 'text': '#d8e0f0', 'accent': '#78909c', 'vibe': 'surrender'},
        'stimulus_control': {'name': '刺激控制', 'bg_top': '#0e1410', 'bg_mid': '#182418', 'bg_bot': '#0e140e', 'text': '#d8f0e0', 'accent': '#689f63', 'vibe': 'structure'},
        'sleep_hygiene': {'name': '睡前检查', 'bg_top': '#120e14', 'bg_mid': '#20182a', 'bg_bot': '#100e18', 'text': '#e0d8f0', 'accent': '#9c8ab5', 'vibe': 'preparation'},
        'cognitive_restructuring': {'name': '挑战坏想法', 'bg_top': '#14100e', 'bg_mid': '#221c18', 'bg_bot': '#14100c', 'text': '#f0e8d8', 'accent': '#bcaaa4', 'vibe': 'clarity'},
    }
    atm = atm_map.get(protocol, atm_map['4-7-8'])
    if isinstance(p, dict):
        atm['name'] = p.get('name', atm['name'])
    return atm


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


# ===== 陪伴模式 API =====

@route('/api/companion/start')
def handle_companion_start(data):
    """启动陪伴模式

    用户说"睡不着"时调用，返回引导步骤序列。
    也可从 chat handler 自动触发（companion 字段）。
    """
    openid = data.get('openid', 'default')
    message = data.get('message', '')
    protocol = data.get('protocol', '4-7-8')

    from companion_mode import start_companion
    result = start_companion(openid, protocol, message)
    return result


@route('/api/companion/update')
def handle_companion_update(data):
    """更新陪伴模式状态

    前端发送用户状态反馈，后端返回下一步指令。
    """
    openid = data.get('openid', 'default')
    feedback = data.get('feedback', {})

    from companion_mode import update_companion, get_companion_status
    result = update_companion(openid, feedback)
    return result


@route('/api/companion/status')
def handle_companion_status(data):
    """获取陪伴模式当前状态"""
    openid = data.get('openid', 'default')

    from companion_mode import get_companion_status
    return get_companion_status(openid)


@route('/api/companion/stop')
def handle_companion_stop(data):
    """主动停止陪伴"""
    openid = data.get('openid', 'default')

    from companion_mode import stop_companion
    stop_companion(openid)
    return {'status': 'stopped'}


# ==================== 叙事引擎路由 (v6.3.0) ====================

@route('/api/narrative/story')
def handle_narrative_story(data):
    """手动查睡眠故事"""
    openid = data.get('openid', 'default')
    mode = data.get('mode', 'analyze')
    try:
        from narrative_engine import get_narrative_engine
        ne = get_narrative_engine()
        result = ne.generate_story(openid, {'mode': mode})
        return {
            'has_data': result['has_data'],
            'story': result['story'],
            'mode': result['mode'],
        }
    except Exception as e:
        return {'error': str(e)}


@route('/api/narrative/weekly')
def handle_narrative_weekly(data):
    """手动查周报"""
    openid = data.get('openid', 'default')
    try:
        from narrative_engine import get_narrative_engine
        ne = get_narrative_engine()
        summary = ne.generate_weekly_summary(openid)
        return {
            'summary': summary,
            'has_data': True,
        }
    except Exception as e:
        return {'error': str(e)}


# ==================== 决策解释器路由 (v6.4.0) ====================

@route('/api/explain/last')
def handle_explain_last(data):
    """获取最近一次决策解释"""
    openid = data.get('openid', 'default')
    decision_result = data.get('decision_result', {})
    try:
        from decision_explainer import get_decision_explainer
        de = get_decision_explainer()
        exp = de.explain(openid, decision_result)
        return {
            'summary': exp['summary'],
            'trigger': exp['trigger'],
            'evidence': exp['evidence'],
            'expected_impact': exp['expected_impact'],
            'alternatives': exp['alternatives'],
            'confidence': exp['confidence'],
            'chain_explanation': exp['chain_explanation'],
        }
    except Exception as e:
        return {'error': str(e)}


# ==================== 主动健康管理路由 (v6.5.0) ====================

@route('/api/proactive/status')
def handle_proactive_status(data):
    """获取当前待触发动作"""
    openid = data.get('openid', 'default')
    try:
        from proactive_manager import get_proactive_manager
        pm = get_proactive_manager()
        pending = pm.get_pending_actions(openid)
        return {
            'pending_count': len(pending),
            'pending_actions': [
                {'name': t['name'], 'trigger_type': t['trigger_type']}
                for t in pending
            ],
        }
    except Exception as e:
        return {'error': str(e)}


@route('/api/proactive/dismiss')
def handle_proactive_dismiss(data):
    """手动取消某个触发"""
    openid = data.get('openid', 'default')
    trigger_type = data.get('trigger_type', '')
    try:
        from proactive_manager import get_proactive_manager
        pm = get_proactive_manager()
        ok = pm.dismiss_trigger(openid, trigger_type)
        return {'dismissed': ok}
    except Exception as e:
        return {'error': str(e)}


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


@route('/api/subscribe-msg')
def handle_subscribe_msg(data):
    """保存用户订阅关系（微信服务通知）

    小程序端在用户订阅后调用此接口，记录用户的订阅状态。
    """
    openid = data.get('openid', 'default')
    tmpl_ids = data.get('template_ids', [])  # 用户订阅的模板ID列表
    subscribe_type = data.get('type', 'sleep_tip')  # 订阅类型

    if openid != 'default' and tmpl_ids:
        def modifier(p):
            subs = p.setdefault('subscriptions', {})
            sub_entry = subs.setdefault(subscribe_type, {})
            sub_entry['template_ids'] = tmpl_ids
            sub_entry['subscribed_at'] = datetime.now().isoformat()
            sub_entry['active'] = True
            sub_entry['preferences'] = p.get('preferences', {}).get('push', {})
            # 标记为非正式订阅（没有真实微信模板ID时的降级模式）
            sub_entry['is_downgraded'] = not any('_' in t or len(t) > 10 for t in tmpl_ids)
            return p
        _px._atomic_write_profile(openid, modifier)
        _log.info('[Subscribe] %s subscribed to %s (%d templates, downgraded=%s)',
                  openid[:8], subscribe_type, len(tmpl_ids),
                  sub_entry.get('is_downgraded', False))
        return {'status': 'ok', 'subscribed': True}

    return {'status': 'ok', 'subscribed': False}


@route('/api/push-settings')
def handle_push_settings(data):
    """获取/设置推送偏好"""
    openid = data.get('openid', 'default')
    action = data.get('action', 'get')  # get | set
    settings = data.get('settings', {})

    if action == 'set' and openid != 'default':
        def modifier(p):
            prefs = p.setdefault('preferences', {})
            push_prefs = prefs.setdefault('push', {})
            push_prefs.update(settings)
            push_prefs['updated_at'] = datetime.now().isoformat()
            return p
        _px._atomic_write_profile(openid, modifier)
        return {'status': 'ok'}

    # action == 'get'
    profile = _px._load_user_profile(openid)
    push_prefs = profile.get('preferences', {}).get('push', {})
    subscriptions = profile.get('subscriptions', {})
    return {
        'settings': push_prefs,
        'subscriptions': {
            k: v.get('active', False) for k, v in subscriptions.items()
            if isinstance(v, dict)
        },
    }



@route('/api/coach-feedback')
def handle_coach_feedback(data):
    """Record user feedback on a coach suggestion"""
    openid = data.get('openid', 'default')
    suggestion_key = data.get('suggestion_key', '')
    feedback = data.get('feedback', '')
    feedback_date = data.get('date', None)

    if openid == 'default' or not suggestion_key or feedback not in ('done', 'not_done', 'forgot'):
        return {'error': 'invalid_params'}

    from sleep_coach import record_feedback, get_feedback_stats
    from cache_layer import get_cached_profile, set_cached_profile

    profile = get_cached_profile(openid)
    profile, result = record_feedback(profile, suggestion_key, feedback, feedback_date)
    set_cached_profile(openid, profile)

    _ai_log.info('[Coach] Feedback %s: %s=%s effect=%+d',
                 openid[:8], suggestion_key, feedback, result.get('effect_change', 0))

    return {
        'status': 'ok',
        'result': result,
        'stats': get_feedback_stats(profile),
    }


@route('/api/pending-push', methods=['GET', 'POST'])
def handle_pending_push(data):
    """获取/确认用户待处理的推送

    GET: 返回用户所有未读推送（含标题和内容）
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


# ===== 元学习路由 =====

@route('/api/meta/daily-review')
def handle_meta_daily_review(data):
    """触发元学习每日复盘

    v3.4.0: 审查过去N小时的实验日志，自动调整模块参数
    安全：快照备份 + 边界钳制
    """
    hours = int(data.get('hours', 24)) if isinstance(data, dict) else 24
    try:
        from meta_learner import run_daily_review, get_review_summary
        result = run_daily_review()
        summary = get_review_summary()
        result['summary_text'] = summary
        return result
    except ImportError:
        return {'error': 'meta_learner module not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/meta/rollback')
def handle_meta_rollback(data):
    """回滚元学习的参数调整

    steps=1 回退一次，可连续调用
    """
    steps = int(data.get('steps', 1)) if isinstance(data, dict) else 1
    try:
        from meta_learner import rollback_params
        params = rollback_params(steps=steps)
        if params:
            return {'status': 'rolled_back', 'steps': steps, 'params': params}
        return {'status': 'cannot_rollback', 'steps': steps}
    except ImportError:
        return {'error': 'meta_learner module not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/meta/summary')
def handle_meta_summary(data):
    """获取元学习摘要"""
    try:
        from meta_learner import get_review_summary
        summary = get_review_summary()
        return {'summary': summary}
    except ImportError:
        return {'error': 'meta_learner module not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/meta/adjustments')
def handle_meta_adjustments(data):
    """获取参数调整历史"""
    try:
        from meta_learner import MetaLearner
        ml = MetaLearner()
        adjustments = ml.get_adjustment_history()
        return {'adjustments': adjustments, 'count': len(adjustments)}
    except ImportError:
        return {'error': 'meta_learner module not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/meta/param-history')
def handle_meta_param_history(data):
    """获取参数变更历史摘要"""
    try:
        from meta_learner import MetaLearner
        ml = MetaLearner()
        history = ml.param_history.get_history_summary()
        return {'history': history}
    except ImportError:
        return {'error': 'meta_learner module not available'}
    except Exception as e:
        return {'error': str(e)}


# ==================== 群体策略进化路由（v4.6.0） ====================

@route('/api/population/clusters')
def handle_population_clusters(data):
    """获取当前所有集群信息"""
    try:
        pm = _get_pop_mgr()
        if pm is None:
            return {'error': 'population_manager not available'}
        clusters = pm._load_clusters(force=True)
        summary = {}
        for cidx, cdata in clusters.items():
            summary[cidx] = {
                'name': cdata.get('name', f'cluster_{cidx}'),
                'users': len(cdata.get('users', [])),
                'params': cdata.get('params', {}),
                'stats': cdata.get('stats', {}),
            }
        return {'clusters': summary, 'count': len(summary)}
    except Exception as e:
        return {'error': str(e)}


@route('/api/population/maintenance')
def handle_population_maintenance(data):
    """触发群体维护（重聚类+参数分化）"""
    try:
        pm = _get_pop_mgr()
        if pm is None:
            return {'error': 'population_manager not available'}
        report = pm.periodic_maintenance()
        return {'status': 'ok', 'report': report}
    except Exception as e:
        return {'error': str(e)}


@route('/api/population/strategy-split')
def handle_population_strategy_split(data):
    """检查是否需要分裂集群"""
    try:
        pm = _get_pop_mgr()
        if pm is None:
            return {'error': 'population_manager not available'}
        splits = pm.suggest_strategy_split()
        return {'splits': splits, 'count': len(splits)}
    except Exception as e:
        return {'error': str(e)}


@route('/api/population/summary')
def handle_population_summary(data):
    """获取集群摘要"""
    try:
        pm = _get_pop_mgr()
        if pm is None:
            return {'error': 'population_manager not available'}
        return {'summary': pm.get_cluster_summary()}
    except Exception as e:
        return {'error': str(e)}

# ==================== 意图引擎路由 (v6.2.0) ====================

@route('/api/intent/classify')
def handle_intent_classify(data):
    """测试意图分类

    POST /api/intent/classify
    Body: {"text": "失眠睡不着", "openid": "xxx", "profile": {}, "history": []}
    Returns: {"primary_intent": "report_insomnia", ...}
    """
    text = data.get('text', data.get('message', ''))
    openid = data.get('openid', 'default')
    try:
        from intent_engine import get_intent_engine
        ie = get_intent_engine()
        ctx = {
            'openid': openid,
            'profile': data.get('profile', {}),
            'history': data.get('history', []),
            'emotion_state': data.get('emotion_state', 'neutral'),
        }
        result = ie.classify(text, ctx)
        return dict(result)
    except Exception as e:
        return {'error': str(e)}


@route('/api/intent/list')
def handle_intent_list(data):
    """查看已注册的意图规则

    GET /api/intent/list
    Returns: {"intents": [{"name": ..., "patterns": [...], ...}, ...]}
    """
    try:
        from intent_engine import get_intent_engine
        ie = get_intent_engine()
        intents = ie.list_intents()
        return {'intents': intents, 'count': len(intents)}
    except Exception as e:
        return {'error': str(e)}


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

# ==================== 动态安全护栏路由（v4.7.0） ====================

@route('/api/safeguards/rollback')
def handle_safeguard_rollback(data):
    """手动触发回滚"""
    try:
        from dynamic_safeguards import get_dynamic_safeguards
        sg = get_dynamic_safeguards()
        openid = data.get("openid", "_system")
        steps = int(data.get("steps_back", 1))
        result = sg.auto_rollback(openid, steps_back=steps, flags=[{'severity': 'high', 'reason': 'manual_rollback'}])
        return {'status': result.get('status', 'ok'), 'result': result}
    except ImportError:
        return {'error': 'dynamic_safeguards not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/safeguards/status')
def handle_safeguard_status(data):
    """查看当前安全状态"""
    try:
        from dynamic_safeguards import get_dynamic_safeguards
        sg = get_dynamic_safeguards()
        openid = data.get('openid', '_system') if isinstance(data, dict) else '_system'
        safety = sg.check(openid)
        canary = sg.get_canary_status()
        rollback_history = sg.get_rollback_history(openid)
        return {
            'safety': safety,
            'canary': canary,
            'rollback_history': rollback_history[-5:] if rollback_history else [],
            'summary': sg.get_safety_summary(),
        }
    except ImportError:
        return {'error': 'dynamic_safeguards not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/safeguards/canary-start')
def handle_safeguard_canary_start(data):
    """启动金丝雀发布"""
    try:
        from dynamic_safeguards import get_dynamic_safeguards
        sg = get_dynamic_safeguards()
        params = data.get('params', {})
        if not params:
            return {'error': 'params required'}
        return sg.start_canary_test(params)
    except ImportError:
        return {'error': 'dynamic_safeguards not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/safeguards/canary-evaluate')
def handle_safeguard_canary_evaluate(data):
    """评估金丝雀结果"""
    try:
        from dynamic_safeguards import get_dynamic_safeguards
        sg = get_dynamic_safeguards()
        return sg.evaluate_canary()
    except ImportError:
        return {'error': 'dynamic_safeguards not available'}
    except Exception as e:
        return {'error': str(e)}


# ==================== A/B 测试路由（v5.1.0） ====================

@route('/api/ab/create')
def handle_ab_create(data):
    """创建A/B实验"""
    try:
        from ab_framework import create_experiment, start_experiment
        name = data.get('name')
        config_a = data.get('config_a')
        config_b = data.get('config_b')
        split_ratio = data.get('split_ratio', 0.5)
        auto_start = data.get('auto_start', True)

        if not name or not config_a or not config_b:
            return {'error': 'name, config_a, config_b required'}
        exp_id = create_experiment(name, config_a, config_b, split_ratio)
        if auto_start:
            start_experiment(exp_id)
        return {'experiment_id': exp_id, 'status': 'created' if not auto_start else 'running'}
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/evaluate')
def handle_ab_evaluate(data):
    """评估实验"""
    try:
        from ab_framework import evaluate
        experiment_id = data.get('experiment_id')
        if not experiment_id:
            return {'error': 'experiment_id required'}
        result = evaluate(experiment_id)
        return result
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/list')
def handle_ab_list(data):
    """列出实验"""
    try:
        from ab_framework import list_experiments
        status_filter = data.get('status')
        exps = list_experiments(status_filter)
        return {'experiments': exps, 'count': len(exps)}
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/stop')
def handle_ab_stop(data):
    """停止实验"""
    try:
        from ab_framework import stop_experiment, get_experiment_config, list_experiments
        experiment_id = data.get('experiment_id')
        winner = data.get('winner')
        if not experiment_id:
            return {'error': 'experiment_id required'}
        result = stop_experiment(experiment_id, winner=winner)
        return result
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/canary-create')
def handle_ab_canary_create(data):
    """创建金丝雀实验"""
    try:
        from ab_framework import create_canary_experiment, start_experiment
        name = data.get('name')
        canary_config = data.get('canary_config')
        control_config = data.get('control_config')
        canary_ratio = data.get('canary_ratio', 0.05)
        auto_start = data.get('auto_start', True)

        if not name or not canary_config:
            return {'error': 'name, canary_config required'}
        exp_id = create_canary_experiment(name, canary_config, control_config, canary_ratio)
        if auto_start:
            start_experiment(exp_id)
        return {'experiment_id': exp_id, 'status': 'created', 'is_canary': True}
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/winner-config')
def handle_ab_winner_config(data):
    """获取当前优胜者配置"""
    try:
        from ab_framework import get_winner_config, list_winner_history
        return {
            'winner_config': get_winner_config(),
            'history': list_winner_history(),
        }
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/ab/rollback')
def handle_ab_rollback(data):
    """回滚到历史优胜者配置"""
    try:
        from ab_framework import rollback_to_winner
        index = int(data.get('index', 0))
        result = rollback_to_winner(index)
        if result is None:
            return {'error': f'No historical config at index {index}'}
        return {'success': True, 'config': result}
    except ImportError:
        return {'error': 'ab_framework not available'}
    except Exception as e:
        return {'error': str(e)}


# ==================== AEO 权重优化路由（v6.1.0） ====================


@route('/api/weights/status')
def handle_weights_status(data):
    """获取当前权重配置"""
    try:
        from weight_optimizer import get_weight_optimizer
        wo = get_weight_optimizer()
        status = wo.get_status()
        outcome_summary = wo.get_outcome_summary(200)
        return {
            'status': 'ok',
            'base_weights': status['base_weights'],
            'cluster_weights': status['cluster_weights'],
            'total_outcomes': status['total_outcomes'],
            'total_clusters': status['total_clusters'],
            'outcome_summary': outcome_summary,
        }
    except ImportError:
        return {'error': 'weight_optimizer not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/weights/optimize')
def handle_weights_optimize(data):
    """手动触发权重优化"""
    try:
        from weight_optimizer import get_weight_optimizer
        wo = get_weight_optimizer()
        report = wo.optimize()
        cluster_id = data.get('cluster_id') if isinstance(data, dict) else None
        if cluster_id:
            cluster_report = wo.optimize_cluster(cluster_id)
            report['cluster_optimization'] = cluster_report
        return {'status': 'ok', 'report': report}
    except ImportError:
        return {'error': 'weight_optimizer not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/weights/reset')
def handle_weights_reset(data):
    """重置权重到默认值"""
    try:
        from weight_optimizer import get_weight_optimizer
        wo = get_weight_optimizer()
        wo.reset_to_defaults()
        return {'status': 'ok', 'message': 'All weights reset to defaults'}
    except ImportError:
        return {'error': 'weight_optimizer not available'}
    except Exception as e:
        return {'error': str(e)}


# ==================== Agent Gateway 路由（v6.0.0） ====================


@route('/api/agent', methods=['POST'])
def handle_agent_request(data):
    """Agent Gateway: 外部Agent通过JSON调用系统全部核心能力"""
    try:
        from agent_gateway import get_gateway
        gw = get_gateway()
        result = gw.handle_request(data)
        return result
    except ImportError:
        return {'error': 'agent_gateway not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/agent/capabilities', methods=['GET'])
def handle_agent_capabilities(data=None):
    """Agent Gateway: 返回能力清单"""
    try:
        from agent_gateway import get_gateway
        gw = get_gateway()
        return {
            'success': True,
            'capabilities': gw.list_capabilities(),
            'version': gw.get_version()
        }
    except ImportError:
        return {'error': 'agent_gateway not available'}
    except Exception as e:
        return {'error': str(e)}


@route('/api/agent/schema', methods=['POST'])
def handle_agent_schema(data):
    """Agent Gateway: 获取指定能力的JSON Schema"""
    try:
        from agent_gateway import get_gateway
        gw = get_gateway()
        capability = data.get('capability', '')
        schema = gw.get_capability_schema(capability)
        return {'success': True, 'schema': schema}
    except ImportError:
        return {'error': 'agent_gateway not available'}
    except ValueError as e:
        return {'success': False, 'error': str(e)}
    except Exception as e:
        return {'error': str(e), '_handler': 'handle_agent_schema'}


# ============ Online RL Routes (injected v7.2) ============

@route('/api/rl/act', methods=['POST'])
def handle_rl_decide(data):
    """Online RL: 让RL选择动作"""
    from online_rl import OnlineRL
    from online_rl_routes import handle_rl_act
    return handle_rl_act(data)


@route('/api/rl/update', methods=['POST'])
def handle_rl_perform_update(data):
    """Online RL: 更新Q值"""
    from online_rl_routes import handle_rl_update
    return handle_rl_update(data)


@route('/api/rl/status', methods=['POST'])
def handle_rl_get_status(data):
    """Online RL: 查看统计"""
    from online_rl_routes import handle_rl_status
    return handle_rl_status(data)


@route('/api/rl/reset', methods=['POST'])
def handle_rl_reset(data):
    """Online RL: 重置Q表"""
    from online_rl_routes import handle_rl_reset
    return handle_rl_reset(data)


# ============ Audio Analysis Routes (injected v7.2) ============

@route('/api/audio/analyze', methods=['POST'])
def handle_audio_analysis(data):
    """音频分析: 分析最新录音"""
    from sleep_audio_analyzer import get_analyzer
    from audio_pomdp_bridge import inject_audio_to_pomdp, get_latest_audio_observation
    import os

    openid = data.get('openid', 'default')
    wav_path = data.get('wav_path', None)

    analyzer = get_analyzer()

    if wav_path and os.path.exists(wav_path):
        result = analyzer.analyze_file(wav_path)
    else:
        results = analyzer.analyze_all_wavs()
        if results:
            result = results[-1]
        else:
            result = None

    if result is None:
        return {'success': False, 'error': '没有找到音频文件', 'record_dir': analyzer.SLEEP_RECORD_DIR}

    inject_audio_to_pomdp(openid)
    obs = get_latest_audio_observation(openid)

    return {
        'success': True,
        'audio_result': result,
        'pomdp_observation': obs,
        'sleep_context': analyzer.build_sleep_context([result]),
    }


@route('/api/audio/status', methods=['POST'])
def handle_audio_status(data):
    """音频分析: 查看最近音频分析结果"""
    from audio_pomdp_bridge import get_latest_audio_observation
    import os

    openid = data.get('openid', 'default')
    obs = get_latest_audio_observation(openid)

    audio_dir = r'D:\AISleepGen_Optimized\sleep_record'
    wav_files = []
    if os.path.exists(audio_dir):
        wav_files = [f for f in os.listdir(audio_dir) if f.endswith('.wav')]

    return {
        'success': True,
        'observation': obs,
        'wav_files': wav_files[-10:] if wav_files else [],
    }


# ============ Ring OCR Routes (injected v7.2) ============

@route('/api/ring/extract', methods=['POST'])
def handle_ring_extraction(data):
    """手环: 从截图中提取睡眠数据"""
    from ring_ocr import get_ring_extractor

    openid = data.get('openid', 'default')
    image_path = data.get('image_path', None)
    mode = data.get('mode', 'auto')

    extractor = get_ring_extractor()

    if mode == 'known' or not image_path:
        ring_data = extractor.extract_known_values()
    else:
        ring_data = extractor.extract_auto(image_path)

    pomdp_obs = extractor.format_for_pomdp(ring_data)

    return {
        'success': True,
        'ring_data': ring_data,
        'pomdp_observation': pomdp_obs,
    }


@route('/api/ring/status', methods=['POST'])
def handle_ring_status(data):
    """手环: 查看已录入的手环数据"""
    from ring_ocr import get_ring_extractor
    import json, os

    extractor = get_ring_extractor()
    data_dir = r'D:\AISleepGen_Optimized\data'
    known_file = os.path.join(data_dir, 'known_ring_values.json')

    result = {
        'success': True,
        'has_screenshots': False,
        'known_values': None,
    }

    screenshot_dir = os.path.join(data_dir, 'screenshots')
    if os.path.exists(screenshot_dir):
        screenshots = [f for f in os.listdir(screenshot_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        result['screenshots'] = screenshots[-10:]

    if os.path.exists(known_file):
        try:
            with open(known_file, 'r', encoding='utf-8') as f:
                result['known_values'] = json.load(f)
        except Exception:
            pass

    return result


# ============ Huawei Health Kit Routes (injected v7.2) ============

@route('/api/huawei/token', methods=['POST'])
def handle_huawei_token(data):
    """华为Health Kit: 兑换/刷新access token"""
    from huawei_health_kit import TokenManager, exchange_code_for_token

    auth_code = data.get('auth_code', None)

    if auth_code:
        token = exchange_code_for_token(auth_code)
        if 'error' in token:
            return {'success': False, 'error': token['error']}
        return {'success': True, 'token': token['access_token'][:20] + '...', 'expires_in': token.get('expires_in')}

    mgr = TokenManager()
    saved = mgr.load()
    if saved:
        return {'success': True, 'has_token': True, 'valid': mgr.is_valid(saved)}
    return {'success': True, 'has_token': False}


@route('/api/huawei/sleep-data', methods=['POST'])
def handle_huawei_sleep_data(data):
    """华为Health Kit: 获取睡眠数据"""
    from huawei_health_kit import TokenManager

    mgr = TokenManager()
    saved = mgr.load()

    if not saved or not mgr.is_valid(saved):
        return {'success': False, 'error': '没有有效的token，需要重新授权'}

    return {
        'success': True,
        'token_status': 'valid',
        'message': 'token有效，等待实际API对接',
    }


# ============ Deep Sleep Data Assimilation (injected v7.2) ============

@route('/api/sleep/assimilate', methods=['POST'])
def handle_sleep_assimilation(data):
    """深度睡眠: 整合音频+手环+华为Health Kit -> POMDP"""
    from audio_pomdp_bridge import inject_audio_to_pomdp, get_latest_audio_observation
    from ring_ocr import get_ring_extractor
    import json, os

    openid = data.get('openid', 'default')

    assimilated = {
        'audio': None,
        'ring': None,
        'huawei': None,
        'pomdp_belief': None,
    }

    try:
        from sleep_audio_analyzer import get_analyzer
        analyzer = get_analyzer()
        results = analyzer.analyze_all_wavs()
        if results:
            inject_audio_to_pomdp(openid)
            obs = get_latest_audio_observation(openid)
            assimilated['audio'] = {
                'latest_file': results[-1].get('filename', ''),
                'snore': results[-1].get('snore', False),
                'stability': results[-1].get('stability', 0.5),
            }
            assimilated['pomdp_belief'] = obs
    except Exception as e:
        assimilated['audio_error'] = str(e)

    try:
        extractor = get_ring_extractor()
        known = extractor.extract_known_values()
        if known:
            pomdp_ring = extractor.format_for_pomdp(known)
            assimilated['ring'] = known
            if assimilated['pomdp_belief'] is None:
                assimilated['pomdp_belief'] = pomdp_ring
            else:
                assimilated['pomdp_belief'].update(pomdp_ring)
    except Exception as e:
        assimilated['ring_error'] = str(e)

    try:
        from huawei_health_kit import TokenManager
        mgr = TokenManager()
        saved = mgr.load()
        if saved:
            assimilated['huawei'] = {'has_token': True, 'valid': mgr.is_valid(saved)}
        else:
            assimilated['huawei'] = {'has_token': False}
    except Exception as e:
        assimilated['huawei_error'] = str(e)

    return {
        'success': True,
        'openid': openid,
        'assimilated': assimilated,
    }


# ============ Siege Pre-sleep Prediction (injected v7.2) ============

@route('/api/siege/predict', methods=['POST'])
def handle_siege_predict(data):
    """睡前线报: 预测今晚睡眠质量"""
    from sleep_siege_engine import SiegePredictor, format_siege_report

    openid = data.get('openid', 'default')
    sp = SiegePredictor()
    pred = sp.predict(openid)
    report = format_siege_report(pred)

    return {
        'success': True,
        'prediction': pred,
        'report_text': report,
    }


@route('/api/siege/diagnosis', methods=['POST'])
def handle_siege_diagnosis(data):
    """睡眠诊断书: 全面的可解释睡眠报告"""
    from sleep_diagnosis import SleepDiagnosis, format_diagnosis_card

    openid = data.get('openid', 'default')
    sd = SleepDiagnosis()
    diagnosis = sd.generate(openid)
    card = format_diagnosis_card(diagnosis)

    return {
        'success': True,
        'diagnosis': diagnosis,
        'card_text': card,
    }


@route('/api/siege/snapshot', methods=['POST'])
def handle_siege_snapshot(data):
    """睡眠快照: 预判+诊断一次调用"""
    from sleep_siege_engine import SiegePredictor, format_siege_report
    from sleep_diagnosis import SleepDiagnosis, format_diagnosis_card

    openid = data.get('openid', 'default')

    sp = SiegePredictor()
    pred = sp.predict(openid)
    report = format_siege_report(pred)

    sd = SleepDiagnosis()
    diagnosis = sd.generate(openid)
    card = format_diagnosis_card(diagnosis)

    return {
        'success': True,
        'prediction': pred,
        'report_text': report,
        'diagnosis': diagnosis,
        'card_text': card,
    }


# ============ Auto Diary (injected v7.2) ============

@route('/api/diary/auto', methods=['POST'])
def handle_auto_diary(data):
    """自动睡眠日记: 多源数据融合生成清晨日记"""
    from auto_diary import AutoDiary, format_diary_short

    openid = data.get('openid', 'default')
    ad = AutoDiary()
    diary = ad.generate_diary(openid)
    short = format_diary_short(diary)

    return {
        'success': True,
        'diary': diary,
        'short_text': short,
    }


# ============ Enhanced Push Routes (injected v7.2) ============

@route('/api/push/enhanced/morning', methods=['POST'])
def handle_push_morning(data):
    """触发增强版早间推送"""
    from push_enhancer import enhance_morning_push, generate_alert_content
    from scheduler_daemon import _get_active_users

    openid = data.get('openid', 'default')
    users = _get_active_users()
    profile = None
    for uid, p in users:
        if uid == openid:
            profile = p
            break

    if profile is None:
        return {'success': False, 'error': 'user not found'}

    from wechat_push import generate_morning_content
    original = generate_morning_content(profile)
    if original is None:
        return {'success': False, 'error': 'cannot generate content'}

    enhanced_content, enhanced_type = enhance_morning_push(openid, profile, original[0], original[1])

    return {
        'success': True,
        'openid': openid,
        'content': enhanced_content,
        'push_type': enhanced_type,
    }


@route('/api/push/enhanced/evening', methods=['POST'])
def handle_push_evening(data):
    """触发增强版晚间推送"""
    from push_enhancer import enhance_evening_push
    from scheduler_daemon import _get_active_users

    openid = data.get('openid', 'default')
    users = _get_active_users()
    profile = None
    for uid, p in users:
        if uid == openid:
            profile = p
            break

    if profile is None:
        return {'success': False, 'error': 'user not found'}

    from wechat_push import generate_evening_content
    original = generate_evening_content(profile)
    if original is None:
        return {'success': False, 'error': 'cannot generate content'}

    enhanced_content, enhanced_type = enhance_evening_push(openid, profile, original[0], original[1])

    return {
        'success': True,
        'openid': openid,
        'content': enhanced_content,
        'push_type': enhanced_type,
    }


@route('/api/push/alert', methods=['POST'])
def handle_push_alert(data):
    """生成异常告警推送内容"""
    from push_enhancer import generate_alert_content
    from scheduler_daemon import _get_active_users

    openid = data.get('openid', 'default')
    alert_type = data.get('alert_type', 'score_drop')

    users = _get_active_users()
    profile = None
    for uid, p in users:
        if uid == openid:
            profile = p
            break

    extra = data.get('extra', None)
    result = generate_alert_content(openid, profile or {}, alert_type, extra)

    if result:
        title, content, push_type = result
        return {
            'success': True,
            'title': title,
            'content': content,
            'push_type': push_type,
        }
    return {'success': False, 'error': 'no alert condition met'}


@route('/api/push/enhanced/test', methods=['POST'])
def handle_push_test_all(data):
    """测试所有推送增强的内容（不发送）"""
    from push_enhancer import (
        enhance_morning_push, enhance_evening_push, generate_alert_content
    )
    from scheduler_daemon import _get_active_users
    from wechat_push import generate_morning_content, generate_evening_content

    openid = data.get('openid', 'default')
    users = _get_active_users()
    profile = None
    for uid, p in users:
        if uid == openid:
            profile = p
            break
    if profile is None:
        profile = {}

    morning = generate_morning_content(profile)
    evening = generate_evening_content(profile)

    morning_enhanced = enhance_morning_push(openid, profile, '', '') if openid else ''
    evening_enhanced = enhance_evening_push(openid, profile, '', '') if openid else ''

    alerts = {}
    for at in ['score_drop', 'anomaly_detected', 'ring_sync', 'audio_issue']:
        r = generate_alert_content(openid, profile, at)
        if r:
            alerts[at] = {'title': r[0], 'content': r[1], 'type': r[2]}

    return {
        'success': True,
        'morning_original': morning[1] if morning else 'N/A',
        'morning_enhanced': morning_enhanced[:200] if morning_enhanced else 'siege fallback',
        'evening_original': evening[1] if evening else 'N/A',
        'evening_enhanced': evening_enhanced[:200] if evening_enhanced else 'siege fallback',
        'alerts': alerts,
    }


# ============ Chart Data API (injected v7.2) ============

@route('/api/chart/data', methods=['POST'])
def handle_chart_data(data):
    """图表数据: 为前端提供趋势线/饼图/柱状图/热力图/雷达图数据"""
    from chart_data import get_chart_data

    openid = data.get('openid', 'default')
    chart_data = get_chart_data(openid)

    return {
        'success': True,
        'chart': chart_data,
    }


# ============ Memory Routes (injected v7.2) ============

@route('/api/memory/consolidate', methods=['POST'])
def handle_memory_consolidate(data):
    """记忆整合: 工作记忆→情景记忆"""
    from memory_integrator import sleep_consolidate
    openid = data.get('openid', 'default')
    result = sleep_consolidate(openid)
    return {'success': True, 'result': result}


@route('/api/memory/recall', methods=['POST'])
def handle_memory_recall(data):
    """记忆检索: 三层记忆融合"""
    from memory_integrator import recall
    openid = data.get('openid', 'default')
    text = recall(openid)
    return {'success': True, 'recall_text': text, 'length': len(text)}


@route('/api/memory/weekly', methods=['POST'])
def handle_memory_weekly(data):
    """周整合: 情景记忆→语义记忆"""
    from memory_integrator import weekly_integrate
    openid = data.get('openid', 'default')
    result = weekly_integrate(openid)
    return {'success': True, 'result': result}

# ============ Agent Perceptor Routes (injected v7.2) ============

@route('/api/agent/perceive', methods=['POST'])
def handle_agent_perceive(data):
    from agent_perceptor import perceive, reason, get_active_users
    openid = data.get('openid', 'default')
    signals = perceive(openid)
    users = get_active_users()
    profile = None
    for uid, p in users:
        if uid == openid:
            profile = p
            break
    actions = reason(openid, profile or {}, signals)
    cleaned = {}
    for k, v in signals.items():
        if isinstance(v, (int, float, bool)):
            cleaned[k] = v
        elif v is None:
            cleaned[k] = None
        else:
            cleaned[k] = str(v)
    return {
        'success': True,
        'signals': cleaned,
        'actions': [{'priority': a['priority'], 'name': a['name'], 'reason': a['reason']} for a in actions],
    }

@route('/api/agent/cycle', methods=['POST'])
def handle_agent_cycle(data):
    from agent_perceptor import agent_cycle
    result = agent_cycle()
    return {'success': True, 'result': result}


# ===== v7.4: 同步 DeepSeek 调用（短超时） =====
def _sync_deepseek_call(messages, timeout_sec=1.5):
    """同步调 DeepSeek，短超时，用于覆盖 fallback 回复

    统一通过 ai_client.call_deepseek_api 调用（带缓存）
    """
    from ai_client import call_deepseek_api as _call_ds
    reply = _call_ds(messages, use_async=False)
    return reply
