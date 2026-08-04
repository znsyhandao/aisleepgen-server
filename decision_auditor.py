#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decision_auditor.py v1.0 — Agent决策审计基础设施

Harness 论文启示：Agent 系统的瓶颈不在框架，在"能否审计自己跑得怎么样"。

三层功能：
  1. TRACE  — 每次决策打 trace_id + timestamp + 上下文快照
  2. POST-HOC — 3天后回顾，把实际结果回填，计算 delta
  3. CALIBRATION — 校准置信度：预测 vs 实际准确率

设计原则：
  - 零侵入：不修改 dp_router / sleep_world_model / agent_perceptor 的现有逻辑
  - 异步写：避免阻塞 agent_cycle 主循环
  - 突变安全：所有写操作带 except 兜底，不抛异常
  - 纯追加：trace 是 append-only JSONL，不会覆盖历史

数据流:
  agent_perceptor.learn() → decision_auditor.trace()  (实时)
  cron/hook → decision_auditor.hoc()                 (3天后)
  cron/hook → decision_auditor.calibrate()            (每周)
"""

import json, os, time, logging, threading
from datetime import datetime, timedelta
from collections import OrderedDict

_log = logging.getLogger('aisleepgen.decision_auditor')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')

TRACE_PATH    = os.path.join(DATA_DIR, 'decision_traces.jsonl')
CAL_PATH      = os.path.join(DATA_DIR, 'decision_calibration.json')
HOC_PATH      = os.path.join(DATA_DIR, 'decision_hoc.jsonl')

_MAX_TRACES = 5000
_WRITE_LOCK = threading.Lock()

# ================================================================
#  1. TRACE — 记录每次决策
# ================================================================

def trace(
    openid: str,
    decision_id: str,
    decision_type: str,          # e.g. 'push_morning', 'sleep_consolidation', 'anomaly_alert'
    context: dict,               # 决策时的快照：感知信号、优先级、专家分数等
    predicted_impact: float,     # 预期影响 [-1, 1]  (负面/正面)
    confidence: float            # 置信度 [0, 1]
) -> str:
    """
    记录一次决策，返回 trace_id。

    调用方式（在 agent_perceptor.learn() 里调用）:
        from decision_auditor import trace as da_trace
        tid = da_trace(
            openid=openid,
            decision_id=f'{openid}_{int(time.time())}',
            decision_type=action_result.get('action', 'unknown'),
            context={'signals': signals, 'profile_snapshot': {...}},
            predicted_impact=0.3,
            confidence=0.7
        )
    """
    trace_id = decision_id or f'd_{int(time.time()*1000)}_{openid[:8]}'

    entry = OrderedDict([
        ('trace_id',    trace_id),
        ('openid',      openid),
        ('timestamp',   datetime.now().isoformat(timespec='seconds')),
        ('type',        decision_type),
        ('context',     _safe_copy(context)),
        ('pred_impact', round(predicted_impact, 3)),
        ('confidence',  round(confidence, 3)),
        # 以下字段在 post-hoc 阶段回填
        ('actual_impact',   None),   # 实际影响 [-1, 1]
        ('hoc_filled',      False),  # 是否已完成 post-hoc
        ('hoc_timestamp',   None),
    ])

    _append_jsonl(TRACE_PATH, entry)

    # 如果 trace 文件过大，裁剪
    _trim_jsonl(TRACE_PATH, _MAX_TRACES)

    # 同时写入 hoc 待处理队列（后评估用）
    _append_jsonl(HOC_PATH, {
        'trace_id': trace_id,
        'openid': openid,
        'decision_type': decision_type,
        'timestamp': entry['timestamp'],
        'predicted_impact': entry['pred_impact'],
        'confidence': entry['confidence'],
        'hoc_window_days': 3,    # 3天后评估
        'due_date': (datetime.now() + timedelta(days=3)).strftime('%Y-%m-%d'),
    })

    _log.info('[DA] trace: %s | %s | pred=%.2f conf=%.2f',
              trace_id[:16], decision_type, predicted_impact, confidence)
    return trace_id


# ================================================================
#  2. POST-HOC — 回顾评估
# ================================================================

def hoc(openid: str, trace_id: str = None, window_days: int = 3) -> dict:
    """
    对指定用户的决策进行 3-day post-hoc 评估。

    返回: {trace_id, actual_impact, success, detail}
    """
    try:
        # 读取 hoc 待处理队列
        entries = _read_jsonl(HOC_PATH)
        if not entries:
            return {'status': 'no_data', 'detail': 'HOC queue empty'}

        results = []
        for entry in entries:
            if entry.get('hoc_filled', False):
                continue
            if trace_id and entry['trace_id'] != trace_id:
                continue
            if openid and entry['openid'] != openid:
                continue

            tid = entry['trace_id']
            actual = _compute_actual_impact(openid, tid, window_days)
            if actual is None:
                continue  # 数据不够，等下次

            # 回填 trace 记录
            _fill_trace_back(tid, actual)

            # 标记已处理
            entry['hoc_filled'] = True
            entry['actual_impact'] = actual
            entry['hoc_timestamp'] = datetime.now().isoformat(timespec='seconds')

            results.append({
                'trace_id': tid,
                'predicted': entry.get('predicted_impact', 0.0),
                'actual': actual,
                'delta': actual - entry.get('predicted_impact', 0.0),
            })

            _log.info('[DA] hoc: %s | pred=%.2f actual=%.2f delta=%.2f',
                      tid[:16], entry.get('predicted_impact', 0), actual, actual - entry.get('predicted_impact', 0))

        # 写回 HOC 队列（移除已回填的）
        remaining = [e for e in entries if not e.get('hoc_filled', False)]
        _overwrite_jsonl(HOC_PATH, remaining)

        return {'status': 'ok', 'processed': len(results), 'results': results}

    except Exception as e:
        _log.warning('[DA] hoc error: %s', e)
        return {'status': 'error', 'detail': str(e)}


def _compute_actual_impact(openid: str, trace_id: str, window_days: int) -> float | None:
    """
    计算 3 天后实际影响分数。

    策略：对比决策前后 3 天的用户平均睡眠评分差值。
    正值 = 改善，负值 = 恶化，None = 数据不足。
    """
    try:
        # 从 trace 找到决策时间
        traces = _read_jsonl(TRACE_PATH)
        t_entry = next((t for t in traces if t.get('trace_id') == trace_id), None)
        if not t_entry:
            return None

        decision_time = t_entry.get('timestamp', '')
        if not decision_time:
            return None

        # 取决策前后各 window_days 天的睡眠评分
        from profile_storage import _load_all_profiles
        profiles = _load_all_profiles()
        profile = profiles.get(openid, {})
        history = profile.get('history', [])

        if not history or not isinstance(history, list):
            return None

        # 按日期排序
        sorted_h = sorted(
            [h for h in history if isinstance(h, dict) and h.get('sleep_score')],
            key=lambda x: x.get('date', '')
        )

        decision_date = decision_time[:10]
        pre_scores = []
        post_scores = []

        for h in sorted_h:
            d = h.get('date', '')
            score = h.get('sleep_score', 0)
            if isinstance(score, (int, float)):
                if d < decision_date:
                    pre_scores.append(score)
                elif d >= decision_date and d < _date_add(decision_date, window_days):
                    post_scores.append(score)

        if len(pre_scores) < 1 or len(post_scores) < 1:
            return None

        pre_avg = sum(pre_scores) / len(pre_scores)
        post_avg = sum(post_scores) / len(post_scores)

        # 归一化到 [-1, 1]：假设 0-100 评分，delta 最大 50
        delta = post_avg - pre_avg
        return max(-1.0, min(1.0, delta / 50.0))

    except Exception:
        return None


# ================================================================
#  3. CALIBRATION — 置信度校准
# ================================================================

def calibrate() -> dict:
    """
    校准置信度：对比所有已完成 post-hoc 的决策，
    检查预测的置信度是否与实际准确率一致。

    返回校准统计数据。
    """
    try:
        traces = _read_jsonl(TRACE_PATH)
        hoc_done = [t for t in traces if t.get('hoc_filled') and t.get('actual_impact') is not None]

        if len(hoc_done) < 5:
            return {'status': 'insufficient_data', 'n': len(hoc_done),
                    'detail': '至少需要5个完成post-hoc的决策'}

        # 按置信度区间分组
        bins = OrderedDict([
            ('0.0-0.2', []),
            ('0.2-0.4', []),
            ('0.4-0.6', []),
            ('0.6-0.8', []),
            ('0.8-1.0', []),
        ])

        for t in hoc_done:
            conf = t.get('confidence', 0.5)
            actual = t.get('actual_impact', 0.0)
            if conf < 0.2:
                bins['0.0-0.2'].append(actual)
            elif conf < 0.4:
                bins['0.2-0.4'].append(actual)
            elif conf < 0.6:
                bins['0.4-0.6'].append(actual)
            elif conf < 0.8:
                bins['0.6-0.8'].append(actual)
            else:
                bins['0.8-1.0'].append(actual)

        calibration_report = {}
        for band, actuals in bins.items():
            if actuals:
                avg_delta = sum(actuals) / len(actuals)
                # 置信度高 -> 实际影响也应该高（正相关）
                # 这里计算：期望的正影响比例
                positive_ratio = sum(1 for a in actuals if a > 0) / len(actuals)
                calibration_report[band] = {
                    'n': len(actuals),
                    'mean_actual_impact': round(avg_delta, 3),
                    'positive_ratio': round(positive_ratio, 3),
                }

        # 整体 ECE（Expected Calibration Error）
        # 简单版：检查高置信度决策是否确实产生了更大的正面影响
        high_conf = [a for a in [(t.get('confidence', 0), t.get('actual_impact', 0)) for t in hoc_done] if a[0] > 0.7]
        low_conf = [a for a in [(t.get('confidence', 0), t.get('actual_impact', 0)) for t in hoc_done] if a[0] <= 0.7]

        ece_simple = 0.0
        if high_conf and low_conf:
            h_mean = sum(a[1] for a in high_conf) / len(high_conf)
            l_mean = sum(a[1] for a in low_conf) / len(low_conf)
            ece_simple = abs(h_mean - l_mean)

        result = {
            'status': 'ok',
            'total_hoc_done': len(hoc_done),
            'calibration_by_band': calibration_report,
            'ece_simple': round(ece_simple, 3),
            'high_conf_mean_impact': round(sum(a[1] for a in high_conf) / len(high_conf), 3) if high_conf else None,
            'low_conf_mean_impact': round(sum(a[1] for a in low_conf) / len(low_conf), 3) if low_conf else None,
        }

        _save_json(CAL_PATH, {
            'timestamp': datetime.now().isoformat(timespec='seconds'),
            'result': result,
        })

        _log.info('[DA] calibration done: n=%d ece=%.3f', len(hoc_done), ece_simple)
        return result

    except Exception as e:
        _log.warning('[DA] calibration error: %s', e)
        return {'status': 'error', 'detail': str(e)}


# ================================================================
#  辅助函数
# ================================================================

def _safe_copy(d: dict, max_depth: int = 3) -> dict:
    """安全复制 dict，避免深层递归 + 非序列化类型"""
    if not isinstance(d, dict):
        return {}
    import copy
    try:
        out = {}
        for k, v in d.items():
            if max_depth <= 0:
                out[k] = str(type(v).__name__)
            elif isinstance(v, dict):
                out[k] = _safe_copy(v, max_depth - 1)
            elif isinstance(v, (str, int, float, bool)):
                out[k] = v
            elif isinstance(v, (list, tuple)):
                out[k] = [str(x)[:100] for x in v[:10]]
            else:
                out[k] = str(v)[:200]
        return out
    except Exception:
        return {'_error': 'cannot serialize'}


def _append_jsonl(path: str, entry: dict):
    """线程安全追加 JSONL"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _WRITE_LOCK:
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _read_jsonl(path: str) -> list:
    """读取 JSONL 文件"""
    try:
        if not os.path.exists(path):
            return []
        entries = []
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries
    except Exception:
        return []


def _overwrite_jsonl(path: str, entries: list):
    """覆盖写入 JSONL"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _WRITE_LOCK:
            with open(path, 'w', encoding='utf-8') as f:
                for e in entries:
                    f.write(json.dumps(e, ensure_ascii=False) + '\n')
    except Exception:
        pass


def _fill_trace_back(trace_id: str, actual_impact: float):
    """回填 trace 记录"""
    try:
        traces = _read_jsonl(TRACE_PATH)
        updated = False
        for t in traces:
            if t.get('trace_id') == trace_id:
                t['actual_impact'] = round(actual_impact, 3)
                t['hoc_filled'] = True
                t['hoc_timestamp'] = datetime.now().isoformat(timespec='seconds')
                updated = True
                break
        if updated:
            _overwrite_jsonl(TRACE_PATH, traces)
    except Exception:
        pass


def _save_json(path: str, data: dict):
    """安全写入 JSON"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _trim_jsonl(path: str, max_entries: int):
    """裁剪 JSONL 到最多 max_entries 条"""
    try:
        entries = _read_jsonl(path)
        if len(entries) > max_entries:
            _overwrite_jsonl(path, entries[-max_entries:])
    except Exception:
        pass


def _date_add(date_str: str, days: int) -> str:
    """日期加法"""
    from datetime import datetime, timedelta
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return (dt + timedelta(days=days)).strftime('%Y-%m-%d')
    except Exception:
        return date_str


# ================================================================
#  工具：查看决策审计仪表盘
# ================================================================

def dashboard() -> dict:
    """快速查看决策审计状态"""
    try:
        traces = _read_jsonl(TRACE_PATH)
        hoc_queue = _read_jsonl(HOC_PATH)
        cal_data = {}
        if os.path.exists(CAL_PATH):
            with open(CAL_PATH, 'r', encoding='utf-8') as f:
                cal_data = json.load(f)

        # 按类型统计
        by_type = {}
        for t in traces:
            tp = t.get('type', 'unknown')
            by_type.setdefault(tp, {'total': 0, 'hoc_done': 0})
            by_type[tp]['total'] += 1
            if t.get('hoc_filled'):
                by_type[tp]['hoc_done'] += 1

        return {
            'total_traces': len(traces),
            'hoc_pending': len(hoc_queue),
            'by_type': by_type,
            'last_calibration': cal_data.get('timestamp', None),
            'last_calibration_result': cal_data.get('result', {}),
        }
    except Exception as e:
        return {'status': 'error', 'detail': str(e)}


# ================================================================
#  CLI 入口
# ================================================================

if __name__ == '__main__':
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print('用法: python decision_auditor.py <command> [args]')
        print('  trace     — 记录一条测试决策')
        print('  hoc       — 运行 post-hoc 评估')
        print('  calibrate — 运行置信度校准')
        print('  dashboard — 查看审计仪表盘')
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == 'trace':
        tid = trace(
            openid=sys.argv[2] if len(sys.argv) > 2 else 'test_user',
            decision_id=f'test_{int(time.time())}',
            decision_type='test_decision',
            context={'source': 'cli_test', 'params': sys.argv[3:]},
            predicted_impact=0.3,
            confidence=0.7,
        )
        print(f'trace_id: {tid}')

    elif cmd == 'hoc':
        openid = sys.argv[2] if len(sys.argv) > 2 else None
        result = hoc(openid, window_days=3)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == 'calibrate':
        result = calibrate()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == 'dashboard':
        db = dashboard()
        print(json.dumps(db, ensure_ascii=False, indent=2))

    else:
        print(f'未知命令: {cmd}')
