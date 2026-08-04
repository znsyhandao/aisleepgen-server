#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ai_client.py — AISleepGen AI 调用层
职责：API Key 热加载 + AI回复缓存 + token 用量追踪 + DeepSeek API 调用。
"""
import os, json, time, hashlib, threading, logging, copy

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_ai_log = logging.getLogger('aisleepgen.ai_client')

DEEPSEEK_API_KEY = None
KIMI_API_KEY = None
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# 同步 HTTP 池
import urllib3
_HTTP_POOL = urllib3.PoolManager(maxsize=50, timeout=urllib3.Timeout(connect=5, read=60))

# 备注：异步 HTTP 不再使用全局 session（每次调用在独立事件循环内新建）

# ===== token 用量追踪（无侵入，只记录不拦截） =====
USAGE_LOG_DIR = os.path.join(PROJECT_ROOT, 'data')
USAGE_LOG_PATH = os.path.join(USAGE_LOG_DIR, 'token_usage.jsonl')
USAGE_ROTATE_BYTES = 100 * 1024 * 1024  # 100MB 轮转
_usages = []
_usages_lock = threading.Lock()
_USAGE_FLUSH_INTERVAL = 30  # 每 30 秒刷一次磁盘


def track_token_usage(openid, model, prompt_tokens, completion_tokens, total_tokens):
    """记录单次 API 调用 token 用量到内存队列（异步刷盘）"""
    record = {
        'ts': time.time(),
        'openid': str(openid)[:16],
        'model': str(model),
        'prompt_tokens': int(prompt_tokens),
        'completion_tokens': int(completion_tokens),
        'total_tokens': int(total_tokens),
        'cost_yuan': round(int(prompt_tokens) * 0.5 / 1_000_000 + int(completion_tokens) * 2 / 1_000_000, 6),
    }
    with _usages_lock:
        _usages.append(record)
    _maybe_flush_usages()


def track_usage_with_openid(openid, model, prompt_tokens, completion_tokens, total_tokens):
    """调用方记录 token 用量（带真实 openid，覆盖 _call_sync 的 'default' 记录）
    用于 call_deepseek_api 返回后，调用方用自己的 openid 覆盖默认的追踪记录。
    """
    track_token_usage(openid, model, prompt_tokens, completion_tokens, total_tokens)


# ===== 外部模型配置（调用方使用） =====
TIERS_CONFIG_PATH = os.path.join(PROJECT_ROOT, 'data', 'model_tiers.json')
_tiers_config = {}
_tiers_mtime = 0


def load_tier_config(tier='free'):
    """从外部 JSON 读取分层配置（实时生效，无需重启）
    tiers: {
      'free':  { 'model': ..., 'max_tokens': 2000, 'temperature': 0.7, 'max_daily_calls': 30 },
      'pro':   { ... },
      'unlimited': { ... },
    }
    """
    global _tiers_config, _tiers_mtime
    try:
        mtime = os.path.getmtime(TIERS_CONFIG_PATH)
        if mtime != _tiers_mtime or not _tiers_config:
            with open(TIERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
                _tiers_config = json.load(f)
            _tiers_mtime = mtime
    except Exception as e:
        _ai_log.warning('Load tiers config failed: %s', e)
        # fallback 到硬编码默认值
        _tiers_config = {
            'free':  {'model': 'deepseek-chat', 'max_tokens': 2000, 'temperature': 0.7, 'max_daily_calls': 30},
            'pro':   {'model': 'deepseek-chat', 'max_tokens': 4000, 'temperature': 0.7, 'max_daily_calls': 500},
            'unlimited': {'model': 'deepseek-chat', 'max_tokens': 8000, 'temperature': 0.7, 'max_daily_calls': 999999},
        }
        _tiers_mtime = 0

    if tier not in _tiers_config:
        tier = 'free'
    return dict(_tiers_config[tier])  # 返回副本，防外部改


def get_tier_from_profile(profile):
    """从用户画像读取 tier，默认 free"""
    if profile and isinstance(profile, dict):
        tier = profile.get('member', {}).get('level', 'free')
        return tier if tier in ('free', 'pro', 'unlimited') else 'free'
    return 'free'


def _maybe_flush_usages(force=False):
    """批量刷 token 用量到 jsonl 文件（含自动轮转）"""
    with _usages_lock:
        if not _usages:
            return
        now = time.time()
        last_flush = getattr(_maybe_flush_usages, '_last_flush', 0)
        if not force and now - last_flush < _USAGE_FLUSH_INTERVAL:
            return
        _maybe_flush_usages._last_flush = now
        batch = _usages[:]
        _usages.clear()
    try:
        os.makedirs(USAGE_LOG_DIR, exist_ok=True)
        # 自动轮转：超过阈值时重命名归档
        if os.path.isfile(USAGE_LOG_PATH) and os.path.getsize(USAGE_LOG_PATH) > USAGE_ROTATE_BYTES:
            rotated = USAGE_LOG_PATH + '.' + time.strftime('%Y%m%d_%H%M%S')
            try:
                os.rename(USAGE_LOG_PATH, rotated)
                _ai_log.info('[Usage] Rotated token log: %s -> %s (%d MB)',
                             USAGE_LOG_PATH, rotated, USAGE_ROTATE_BYTES // 1024 // 1024)
            except Exception:
                pass  # 轮转失败继续写原文件
        with open(USAGE_LOG_PATH, 'a', encoding='utf-8') as f:
            for r in batch:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
    except Exception as e:
        _ai_log.warning('Flush token usage failed: %s', e)
        with _usages_lock:
            _usages[:0] = batch


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
    except Exception as e:
        with _ai_cache_lock:
            _ai_cache = {}
        print('[AICache] 加载缓存失败: {}'.format(e))


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
    """AI 调用入口（带 5 分钟缓存 + token 用量追踪）
    职责单一：调用 API、记录用量、返回回复。不关心调用方是谁。
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
        'max_tokens': 4000,
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
                reply = _call_sync(payload, headers, track_openid=openid, track_model=tier_cfg['model'])
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


def call_kimi_api(messages, cache_ctx=None):
    """Kimi API 调用（兼容 call_deepseek_api 接口）
    参数同 call_deepseek_api，但只走同步。
    """
    if cache_ctx:
        oid, msg = cache_ctx.get('openid'), cache_ctx.get('message')
        if oid and msg:
            key = _make_cache_key('kimi', oid, msg)
            hit = _get_cache(key)
            if hit is not None:
                return hit

    if not KIMI_API_KEY:
        return None

    payload = {
        'model': 'moonshot-v1-8k',
        'messages': messages,
        'max_tokens': 4000,
        'temperature': 0.7,
    }
    headers = {
        'Authorization': f'Bearer {KIMI_API_KEY}',
        'Content-Type': 'application/json',
    }

    try:
        data = json.dumps(payload, ensure_ascii=False).encode()
        resp = _HTTP_POOL.request(
            'POST', 'https://api.moonshot.cn/v1/chat/completions',
            body=data, headers=headers, timeout=30)
        r = json.loads(resp.data.decode())
        reply = r['choices'][0]['message']['content']
    except Exception as e:
        _ai_log.error('Kimi API call failed: %s', e)
        return None

    if cache_ctx and reply is not None:
        oid, msg = cache_ctx.get('openid'), cache_ctx.get('message')
        if oid and msg:
            key = _make_cache_key('kimi', oid, msg)
            _set_cache(key, reply)
    return reply


def load_kimi_key():
    """从环境变量或 .env 加载 Kimi API Key。返回 key 字符串或空"""
    global KIMI_API_KEY
    env_key = os.environ.get('KIMI_API_KEY', '')
    if env_key:
        KIMI_API_KEY = env_key
        return KIMI_API_KEY
    # 尝试 .env 文件
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('KIMI_API_KEY='):
                    KIMI_API_KEY = line.split('=', 1)[1].strip()
                    return KIMI_API_KEY
    _ai_log.warning('KIMI_API_KEY not configured')
    return ''


def _call_sync(payload, headers):
    """同步 urllib3 调用（记录 token 用量）"""
    data = json.dumps(payload, ensure_ascii=False).encode()
    resp = _HTTP_POOL.request(
        'POST', f'{DEEPSEEK_BASE_URL}/v1/chat/completions',
        body=data, headers=headers)
    r = json.loads(resp.data.decode())
    # 无侵入：从 API response 读取 token 用量并记录
    usage = r.get('usage')
    if usage and isinstance(usage, dict):
        track_token_usage(
            'default', payload.get('model', 'unknown'),
            usage.get('prompt_tokens', 0),
            usage.get('completion_tokens', 0),
            usage.get('total_tokens', 0),
        )
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
        except Exception:
            pass  # 安全：session 关闭失败不必阻塞
        try:
            new_loop.close()
        except Exception:
            pass  # 安全：event loop 关闭失败不必阻塞


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
        # 无侵入：从 API response 读取 token 用量并记录
        usage = r.get('usage')
        if usage and isinstance(usage, dict):
            track_token_usage(
                'default', payload.get('model', 'unknown'),
                usage.get('prompt_tokens', 0),
                usage.get('completion_tokens', 0),
                usage.get('total_tokens', 0),
            )
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
        except ImportError:
            return None
        except Exception as e:
            print('[WorldModel] 初始化失败: {}'.format(e))
            return None
    return _world_model_instance


# import 时加载缓存和API Key
_load_ai_cache()
load_kimi_key()
load_deepseek_key()
