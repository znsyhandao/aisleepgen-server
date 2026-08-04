#!/usr/bin/env python3
"""PrefetchEngine v1 — 预计算决策缓存

原理: 用户不说话时，后台预测用户今晚最可能问什么，提前算好决策缓存
接入: 在chat请求前优先查缓存，命中直接返回"""

import threading, time, json, os, hashlib
from collections import OrderedDict
from sqlite_db import save_decision as _sqlite_save_dec, load_decision as _sqlite_load_dec

class DecisionCache:
    """决策缓存: LRU + TTL + 预计算"""

    _lock = threading.RLock()
    _cache = OrderedDict()
    _prefetch_queue = {}         # openid → 预计算状态
    _max_size = 200
    _default_ttl = 600           # 10分钟
    _stats = {'hits': 0, 'misses': 0, 'prefetch_hits': 0}

    @classmethod
    def get(cls, openid, query_hash=None):
        """查缓存: 优先内存，退到SQLite，再到预计算队列"""
        key = '%s:%s' % (openid, query_hash or '')
        with cls._lock:
            if key in cls._cache:
                entry = cls._cache[key]
                if time.time() < entry['expires']:
                    cls._cache.move_to_end(key)
                    cls._stats['hits'] += 1
                    return entry['result']
                else:
                    del cls._cache[key]
            # 检查预计算队列
            if openid in cls._prefetch_queue:
                prefetch = cls._prefetch_queue[openid]
                if prefetch.get('ready') and time.time() < prefetch.get('expires', 0):
                    cls._stats['prefetch_hits'] += 1
                    return prefetch['result']
        # SQLite退路（跨进程共享）
        try:
            _sqlite_result = _sqlite_load_dec(openid, query_hash or '')
            if _sqlite_result:
                with cls._lock:
                    cls._stats['hits'] += 1
                return _sqlite_result
        except Exception:
            pass
        cls._stats['misses'] += 1
        return None

    @classmethod
    def set(cls, openid, result, ttl=None, query_hash=None):
        """存入缓存（内存+SQLite双写）"""
        key = '%s:%s' % (openid, query_hash or '')
        with cls._lock:
            if len(cls._cache) >= cls._max_size:
                cls._cache.popitem(last=False)
            cls._cache[key] = {
                'result': result,
                'expires': time.time() + (ttl or cls._default_ttl),
                'created': time.time(),
            }
        # SQLite持久化
        try:
            _sqlite_save_dec(openid, result, ttl or cls._default_ttl, query_hash or '')
        except Exception:
            pass

    @classmethod
    def start_prefetch(cls, openid, profile, horizon_hours=2):
        """启动预计算: 预测用户今晚可能的query，预先算好决策"""
        if openid in cls._prefetch_queue:
            return  # 已有预计算任务

        state = {'openid': openid, 'started': time.time(), 'ready': False}
        cls._prefetch_queue[openid] = state

        def _compute():
            try:
                # 1. 从profile提取用户模式
                history = profile.get('history', []) if isinstance(profile, dict) else []
                if not history or not isinstance(history, list) or len(history) < 1:
                    cls._prefetch_queue.pop(openid, None)
                    return

                # 2. 预测今晚可能的3个问题类型
                recent = [h for h in history[-7:] if isinstance(h, dict)]
                avg_stress = sum(h.get('stress_level', 5) for h in recent) / max(1, len(recent))
                avg_score = sum(h.get('score', 50) for h in recent) / max(1, len(recent))

                if avg_stress > 6:
                    predicted_queries = ['最近压力很大睡不着', '怎么放松']
                elif avg_score < 50:
                    predicted_queries = ['今晚睡眠很差', '如何改善']
                else:
                    predicted_queries = ['今晚状态怎么样', '有什么建议']

                # 3. 预计算一个通用决策缓存
                prefetch_result = {
                    'type': 'prefetch',
                    'analysis': {
                        'avg_stress': round(avg_stress, 1),
                        'avg_score': round(avg_score, 1),
                        'n_history': len(history),
                    },
                    'predicted_queries': predicted_queries,
                    'strategy': 'active_intervention' if avg_stress > 6 else 'maintenance',
                }

                state['result'] = prefetch_result
                state['ready'] = True
                state['expires'] = time.time() + 604800  # 7天
                # 存到cache主表（用set方法触发SQLite）
                cls.set(openid, prefetch_result, ttl=604800)
                for q in predicted_queries:
                    qh = hashlib.md5(q.encode()).hexdigest()[:16]
                    cls.set(openid, prefetch_result, ttl=1800, query_hash=qh)

            except Exception:
                cls._prefetch_queue.pop(openid, None)

        t = threading.Thread(target=_compute, daemon=True, name='Prefetch-%s' % openid[:8])
        t.start()

    @classmethod
    def stats(cls):
        with cls._lock:
            s = dict(cls._stats)
            s['cache_size'] = len(cls._cache)
            s['prefetch_queue'] = len(cls._prefetch_queue)
        hit_rate = s['hits'] / max(1, s['hits'] + s['misses']) * 100
        prefetch_rate = s['prefetch_hits'] / max(1, s['hits']) * 100 if s['hits'] > 0 else 0
        s['hit_rate'] = round(hit_rate, 1)
        s['prefetch_rate'] = round(prefetch_rate, 1)
        return s

    @classmethod
    def summary(cls):
        s = cls.stats()
        return '[DecisionCache] cache=%d hits=%d miss=%d prefetch=%d hit=%.0f%% pre=%.0f%%' % (
            s['cache_size'], s['hits'], s['misses'], s['prefetch_hits'],
            s['hit_rate'], s['prefetch_rate'])


# ===== 自测 =====
if __name__ == '__main__':
    print('=== DecisionCache Test ===\n')

    # 基本缓存
    DecisionCache.set('test1', {'reply': '你好'}, query_hash='hello')
    r = DecisionCache.get('test1', query_hash='hello')
    assert r and r['reply'] == '你好'
    print('Cache hit:', DecisionCache.get('test1', query_hash='hello'))

    # 缓存未命中
    r2 = DecisionCache.get('test1', query_hash='unknown')
    assert r2 is None
    print('Cache miss: None')

    # 预计算
    profile = {'history': [
        {'stress_level': 7, 'score': 40},
        {'stress_level': 8, 'score': 35},
        {'stress_level': 6, 'score': 50},
    ]}
    DecisionCache.start_prefetch('test2', profile)
    import time; time.sleep(0.5)

    prefetched = DecisionCache.get('test2', query_hash='')
    # 预计算可能还未完成
    if prefetched:
        print('Prefetch ready:', prefetched.get('strategy'))
    else:
        print('Prefetch not ready yet')

    s = DecisionCache.stats()
    print('Stats:', DecisionCache.summary())
    print('\nAll tests passed!')
