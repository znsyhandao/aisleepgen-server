#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wm_trace.py — 世界模型执行追踪器 v1.0

职责：记录每次 chat 请求经过的每一层，生成可观测的追踪日志。

使用方式：
  from wm_trace import WMTrace
  trace = WMTrace(openid, message)
  trace.layer('neural_extractor', fields=extracted_fields, elapsed_ms=12)
  trace.layer('deepseek_wm', result=wm_result, elapsed_ms=2850)
  trace.layer('fallback', reply=fallback_text)
  trace.commit()  # 写入 data/wm_trace.jsonl
"""

import json
import os
import time
from datetime import datetime

TRACE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'wm_trace.jsonl')


class WMTrace:
    def __init__(self, openid, message):
        self.openid = openid[:8]
        self.message = (message or '')[:200]
        self.layers = []
        self.start_ts = time.time()
        self._start = time.time()

    def layer(self, name, **kwargs):
        """记录一个处理层
        name: 层名（如 'neural_extractor', 'deepseek_wm', 'memory_retrieval', 'fallback'）
        kwargs: 该层的输出/关键数据
        """
        elapsed = round((time.time() - self._start) * 1000, 1)
        entry = {
            'layer': name,
            'elapsed_ms': elapsed,
            'ts': time.time(),
        }
        # 只保留关键字段，避免日志爆炸
        for k in ('fields_count', 'fields_keys', 'has_result', 'result_len', 'score', 'quality',
                   'similar_count', 'errors', 'fallback', 'deepseek_ok'):
            if k in kwargs:
                entry[k] = kwargs[k]
        self.layers.append(entry)
        self._start = time.time()

    def summary(self):
        """生成单行摘要"""
        total = round((time.time() - self.start_ts) * 1000, 1)
        layer_names = ' → '.join(l.get('layer', '?') for l in self.layers)
        has_errors = any(l.get('errors') for l in self.layers)
        err_tag = ' ⚠️' if has_errors else ''
        return f'[{total:.0f}ms] {layer_names}{err_tag}'

    def commit(self):
        """写入追踪日志"""
        total_ms = round((time.time() - self.start_ts) * 1000, 1)
        record = {
            'ts': time.time(),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'openid': self.openid,
            'message': self.message,
            'total_ms': total_ms,
            'layers': self.layers,
            'summary': self.summary(),
        }
        os.makedirs(os.path.dirname(TRACE_PATH), exist_ok=True)
        with open(TRACE_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return record


def latest_traces(n=10):
    """读取最近 N 条追踪记录"""
    if not os.path.exists(TRACE_PATH):
        return []
    traces = []
    with open(TRACE_PATH, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    traces.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return traces[-n:]


def summary_stats(n=50):
    """打印最近 N 条追踪的统计摘要"""
    traces = latest_traces(n)
    if not traces:
        print('No traces found')
        return
    
    total = len(traces)
    avg_ms = sum(t.get('total_ms', 0) for t in traces) / total
    # 各层命中率
    layer_counts = {}
    for t in traces:
        seen = set()
        for l in t.get('layers', []):
            name = l.get('layer', '?')
            if name not in seen:
                layer_counts[name] = layer_counts.get(name, 0) + 1
                seen.add(name)
    
    print(f'=== WM Trace Stats (last {total} requests) ===')
    print(f'Avg time: {avg_ms:.0f}ms')
    print(f'Layers:')
    for name, count in sorted(layer_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        print(f'  {name}: {pct:.0f}% ({count}/{total})')
    print()
    # 最近3条详细摘要
    print('Recent:')
    for t in traces[-3:]:
        print(f'  {t.get("summary", "?")}')
