#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_client.py — AISleepGen AI 调用层
唯一职责：API Key 热加载 + AI回复缓存 + 世界模型分析缓存 + 同步 DeepSeek API 调用。
"""
import os, json, time, hashlib, threading, logging, copy

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ai_log = logging.getLogger('aisleepgen.ai_client')

DEEPSEEK_API_KEY = None
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 同步 HTTP 池
import urllib3
_HTTP_POOL = urllib3.PoolManager(maxsize=50, timeout=urllib3.Timeout(connect=5, read=60))


# 备注：异步 HTTP 不再使用全局 session（每次调用在独立事件循环内新建）


# ===== 统一缓存（AI回复 + 世界模型分析共享同一存储） =====
AI_CACHE_PATH = os.path.join(PROJECT_ROOT, 'data', 'ai_cache.json')
AI_CACHE_TTL = 300  # AI 回复：5 分钟
WM_CACHE_TTL = 21600  # 世界模型分析：6 小时
_ai_cache = {}
_ai_cache_dirty = False
_ai_cache_lock = threading.Lock()  # 缓存并发写保护


def _load_ai_cache():
    global _ai_cache
    try:
        if os.path.exists(AI_CACHE_PATH):
            with open(AI_CACHE_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            now = time.time()
            with _ai_cache_lock:
                _ai_cache = {k: v for k, v in raw.items() if v[0] > now}
    except:
        with _ai_cache_lock:
            _ai_cache = {}


def _save_ai_cache():
    global _ai_cache_dirty
    if not _ai_cache_dirty:
        return
    try:
        os.makedirs(os.path.dirname(AI_CACHE_PATH), exist_ok=True)
        with _ai_cache_lock:
            snapshot = copy.deepcopy(_ai_cache)
        with open(AI_CACHE_PATH, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, ensure_ascii=False)
        _ai_cache_dirty = False
    except Exception as e:
        _ai_log.warning('Save cache failed: %s', e)


def _set_cache(key, value, ttl=None):
    global _ai_cache_dirty
    with _ai_cache_lock:
        _ai_cache[key] = (time.time() + (ttl or AI_CACHE_TTL), value)
        _ai_cache_dirty = True
    _save_ai_cache()


def _get_cache(key):
    with _ai_cache_lock:
        hit = _ai_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    return None


def _make_cache_key(prefix, *parts):
    """通用缓存 key 生成器"""
    raw = '|'.join([prefix] + [str(p)[:50].strip() for p in parts])
    return hashlib.md5(raw.encode()).hexdigest()


# ===== AI 回复缓存（5 分钟 TTL） =====

def call_deepseek_api(messages, cache_ctx=None, use_async=True):
    """唯一 AI 调用入口（带 5 分钟缓存 + 可选异步 aiohttp）
    use_async: True → 使用 aiohttp 异步（需在事件循环中），False → 使用 urllib3 同步兼容
    """
    if cache_ctx:
        oid, msg = cache_ctx.get('openid'), cache_ctx.get('message')
        if oid and msg:
            key = _make_cache_key('ai', oid, msg)
            hit = _get_cache(key)
            if hit is not None:
                return hit

    if not DEEPSEEK_API_KEY:
        return None  # API 不可用，触发降级

    # 默认用同步 urllib3（稳定，无事件循环问题）
    use_async = False

    payload = {
        'model': 'deepseek-chat',
        'messages': messages,
        'max_tokens': 2000,
        'temperature': 0.7,
    }
    headers = {
        'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        if use_async:
            reply = _call_async(payload, headers)
        else:
            reply = _call_sync(payload, headers)
    except Exception as e:
        _ai_log.error('DeepSeek API call failed: %s', e)
        # 降级尝试：同步重试
        if use_async:
            try:
                _ai_log.info('Retrying with sync fallback...')
                reply = _call_sync(payload, headers)
            except Exception as e2:
                _ai_log.error('Sync retry also failed: %s', e2)
                reply = None
        else:
            reply = None

    # 不缓存 None 回复（避免绕过降级引擎）
    if cache_ctx and reply is not None:
        oid, msg = cache_ctx.get('openid'), cache_ctx.get('message')
        if oid and msg:
            key = _make_cache_key('ai', oid, msg)
            _set_cache(key, reply)
    return reply


def _call_sync(payload, headers):
    """同步 urllib3 调用（fallback）"""
    data = json.dumps(payload, ensure_ascii=False).encode()
    resp = _HTTP_POOL.request(
        'POST', f'{DEEPSEEK_BASE_URL}/v1/chat/completions',
        body=data, headers=headers)
    r = json.loads(resp.data.decode())
    return r['choices'][0]['message']['content'] if 'choices' in r \
        else f'AI错误: {r.get("error", {}).get("message", "未知")}'


def _call_async(payload, headers):
    """调用 aiohttp 异步请求（在独立事件循环中安全运行）"""
    import asyncio as _ai
    new_loop = _ai.new_event_loop()
    _ai.set_event_loop(new_loop)
    import aiohttp as _aiohttp
    session = _aiohttp.ClientSession(
        timeout=_aiohttp.ClientTimeout(total=60, connect=10),
        connector=_aiohttp.TCPConnector(limit=100, limit_per_host=20)
    )
    try:
        return new_loop.run_until_complete(_do_request(session, payload, headers))
    finally:
        try:
            new_loop.run_until_complete(session.close())
        except:
            pass
        try:
            new_loop.close()
        except:
            pass


async def _do_request(session, payload, headers):
    """aiohttp 请求体（接收外部 session）"""
    async with session.post(
        f'{DEEPSEEK_BASE_URL}/v1/chat/completions',
        json=payload,
        headers=headers,
    ) as resp:
        status = resp.status
        text = await resp.text()
        if status != 200:
            raise ValueError('HTTP %d: %s' % (status, text[:100]))
        r = json.loads(text)
        return r['choices'][0]['message']['content'] if 'choices' in r \
            else f'AI错误: {r.get("error", {}).get("message", "未知")}'



# ===== 世界模型分析缓存（6 小时 TTL） =====

def get_world_model_analysis(openid, today_str, message, compute_fn):
    """带世界模型缓存的包装器
    每日首次分析走真实计算，缓存 6 小时。此后相同 openid+date+msg 秒回。
    """
    key = _make_cache_key('wm', openid, today_str, message)
    hit = _get_cache(key)
    if hit is not None:
        return hit
    result = compute_fn()
    _set_cache(key, result, ttl=WM_CACHE_TTL)
    return result


# ===== 世界模型工厂 =====
_HAS_DEEP_MODULE = False
_pref_engine = None
_world_model_instance = None


def _dcs_fallback(m):
    return {'scene': 'general', 'confidence': 0.3, 'action': 'general_reply', 'desc': ''}
def _dvc_fallback(p):
    return {}
classify_scene = _dcs_fallback
vertical_comparison = _dvc_fallback

try:
    from preference_engine import PreferenceEngine
    from world_model_deep import classify_scene as _dcs_real, vertical_comparison as _dvc_real
    classify_scene = _dcs_real
    vertical_comparison = _dvc_real
    _HAS_DEEP_MODULE = True
except ImportError:
    _ai_log.debug('Advanced modules not available (world_model_deep, preference_engine)')


def load_deepseek_key():
    """加载 API Key——支持 .env → 环境变量 → OpenClaw 配置 三级fallback"""
    global DEEPSEEK_API_KEY
    env_key = os.environ.get('DEEPSEEK_API_KEY', '')
    if env_key:
        DEEPSEEK_API_KEY = env_key
        return True
    env_path = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('DEEPSEEK_API_KEY='):
                    DEEPSEEK_API_KEY = line.split('=', 1)[1]
                    return True
    for path in [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "C:\\Users\\cqs10\\.openclaw\\openclaw.json"
    ]:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                k = cfg.get('models', {}).get('providers', {}).get('deepseek', {}).get('apiKey', '')
                if k and k != '__OPENCLAW_REDACTED__':
                    DEEPSEEK_API_KEY = k
                    return True
            except Exception as e:
                _ai_log.debug('OpenClaw config not available: %s', e)
    return False


def _get_world_model():
    global _world_model_instance
    if _world_model_instance is None:
        try:
            from sleep_world_model import WorldModelEngine
            _world_model_instance = WorldModelEngine()
        except:
            return None
    return _world_model_instance


# import 时加载缓存
_load_ai_cache()
