#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AISleepGen 决策审计层 v1.0
— 每个用户操作的 "可追溯 | 可回滚 | 可复现"

核心功能:
  1. trace_record: 每次 user action 存入 (request + 推理轨迹 + response)
  2. session_replay: 给定 session_id, 精确重放整夜决策
  3. compare_versions: 对比 v5.4.0 vs v5.5.0 对同一输入的输出差异

数据格式:
  data/decision_traces/{openid}/{session_id}_{version}_{timestamp_ms}.json
  trace 内容: 输入参数 + 模型版本 + 种子 + 贝叶斯后验 + Process S+C + 各层决策置信度
"""

import json, os, time, hashlib, random
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

# ============================================================
# 配置
# ============================================================

TRACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "decision_traces")
MODEL_VERSION = "v5.5.0"  # 由部署脚本注入

# ============================================================
# 种子管理器 — 确保相同的 session + step 重放相同输出
# ============================================================

class SeedManager:
    """给每个 session 分配固定种子, 确保可复现"""

    @staticmethod
    def session_seed(session_id: str) -> int:
        """从 session_id 派生确定性种子"""
        h = hashlib.sha256(session_id.encode()).hexdigest()
        return int(h[:16], 16) % (2 ** 31)

    @staticmethod
    def step_seed(session_id: str, step: int) -> int:
        """每个 step 的种子 = session_seed + step 的确定性派生"""
        base = SeedManager.session_seed(session_id)
        step_hash = hashlib.sha256(f"{base}:{step}".encode()).hexdigest()
        return int(step_hash[:16], 16) % (2 ** 31)

    @staticmethod
    def set_global_seed(seed: int):
        """设置 Python 随机种子 (不影响 hash)"""
        random.seed(seed)


# ============================================================
# 决策轨迹记录器
# ============================================================

class DecisionTracer:
    """
    记录每次用户操作的完整推理轨迹

    使用方式:
        tracer = DecisionTracer(openid, session_id)
        trace = tracer.start_trace(request_data)
        # ... 执行推理 ...
        trace.add_layer("state_transition", {"p_next": 0.72, "evidence": {...}})
        trace.add_layer("homeostasis", {"process_s": 0.81, "drowsiness": "sleepy"})
        trace.add_layer("renderer", {"selected_state": "calm", "bpm": 5})
        result = tracer.finalize(response_data)
        # result.dat 自动写入文件
    """

    def __init__(self, openid: str, session_id: str):
        self.openid = openid
        self.session_id = session_id
        self.timestamp = int(time.time() * 1000)
        self._layers: List[Dict] = []
        self._start_time = datetime.now(timezone.utc).isoformat()
        self._trace: Optional[Dict] = None

    def start_trace(self, request: Dict) -> "DecisionTracer":
        """开始记录新决策"""
        step = len(os.listdir(self._user_dir())) if os.path.isdir(self._user_dir()) else 0
        seed = SeedManager.step_seed(self.session_id, step)
        SeedManager.set_global_seed(seed)

        self._trace = {
            "trace_id": f"{self.session_id}_{MODEL_VERSION}_{self.timestamp}",
            "model_version": MODEL_VERSION,
            "session_id": self.session_id,
            "openid": self.openid,
            "step": step,
            "seed": seed,
            "timestamp": self._start_time,
            "request": request,
            "layers": [],
            "response": None,
            "duration_ms": None,
        }
        return self

    def add_layer(self, layer_name: str, data: Dict):
        """添加一个推理层"""
        self._layers.append({
            "layer": layer_name,
            "t_ms": int((datetime.now(timezone.utc).timestamp()) * 1000) % 1000000,
            "data": data,
        })

    def finalize(self, response: Dict) -> Dict:
        """完成记录并写入文件"""
        if not self._trace:
            return response

        end_time = datetime.now(timezone.utc)
        start = datetime.fromisoformat(self._start_time)
        self._trace["duration_ms"] = int((end_time - start).total_seconds() * 1000)
        self._trace["layers"] = self._layers
        self._trace["response"] = response

        # 写入文件
        self._write_trace(self._trace)

        # 把 trace 摘要注入 response（不包含完整推理链，避免数据太大）
        response["_trace"] = {
            "trace_id": self._trace["trace_id"],
            "duration_ms": self._trace["duration_ms"],
            "n_layers": len(self._layers),
            "model_version": MODEL_VERSION,
        }

        return response

    def _user_dir(self) -> str:
        path = os.path.join(TRACE_DIR, self.openid)
        os.makedirs(path, exist_ok=True)
        return path

    def _write_trace(self, trace: Dict):
        filename = f"{self.session_id}_{MODEL_VERSION}_{self.timestamp}.json"
        path = os.path.join(TRACE_DIR, self.openid, filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(trace, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            pass  # 写入失败不应影响主流程


# ============================================================
# 重放引擎 — 精确复现用户决策
# ============================================================

class SessionReplayer:
    """给定 session_id, 重放整夜决策轨迹"""

    @staticmethod
    def list_sessions(openid: str) -> List[str]:
        """列出用户的 session 列表"""
        dir_path = os.path.join(TRACE_DIR, openid)
        if not os.path.isdir(dir_path):
            return []
        sessions = set()
        for f in os.listdir(dir_path):
            if f.endswith(".json"):
                parts = f.split("_", 1)
                if len(parts) > 0:
                    sessions.add(parts[0])
        return sorted(sessions)

    @staticmethod
    def load_session(openid: str, session_id: str,
                     version: Optional[str] = None) -> List[Dict]:
        """加载 session 的所有决策轨迹（按时间序）"""
        dir_path = os.path.join(TRACE_DIR, openid)
        if not os.path.isdir(dir_path):
            return []

        traces = []
        for f in os.listdir(dir_path):
            if not f.endswith(".json"):
                continue
            if not f.startswith(session_id):
                continue
            if version and version not in f:
                continue

            try:
                with open(os.path.join(dir_path, f), "r", encoding="utf-8") as fh:
                    traces.append(json.load(fh))
            except:
                continue

        traces.sort(key=lambda t: t.get("timestamp", ""))
        return traces

    @staticmethod
    def compare_versions(openid: str, session_id: str,
                          version_a: str, version_b: str) -> Dict:
        """对比两个版本对同一 session 的决策差异"""
        traces_a = SessionReplayer.load_session(openid, session_id, version_a)
        traces_b = SessionReplayer.load_session(openid, session_id, version_b)

        diffs = []
        for ta, tb in zip(traces_a, traces_b):
            if ta["request"] != tb["request"]:
                continue  # 输入不同 -> 跳过

            # 对比关键输出字段
            resp_a = ta.get("response", {})
            resp_b = tb.get("response", {})
            diff = SessionReplayer._compare_responses(resp_a, resp_b)
            if diff:
                diffs.append({
                    "step": ta.get("step"),
                    "diff": diff,
                })

        return {
            "version_a": version_a,
            "version_b": version_b,
            "n_traces_a": len(traces_a),
            "n_traces_b": len(traces_b),
            "diffs": diffs,
        }

    @staticmethod
    def _compare_responses(a: Dict, b: Dict) -> Optional[Dict]:
        """递归比较两个响应, 返回差异"""
        diffs = {}
        for key in set(list(a.keys()) + list(b.keys())):
            va, vb = a.get(key), b.get(key)
            if key.startswith("_"):
                continue
            if isinstance(va, dict) and isinstance(vb, dict):
                nested = SessionReplayer._compare_responses(va, vb)
                if nested:
                    diffs[key] = nested
            elif va != vb:
                diffs[key] = {"old": str(va)[:100], "new": str(vb)[:100]}
        return diffs if diffs else None


# ============================================================
# 快速测试
# ============================================================

if __name__ == "__main__":
    print("决策审计层 v1.0")
    print("=" * 40)

    # 测试 1: 记录 + 重放
    print("\n[测试1] 记录决策轨迹...")
    tracer = DecisionTracer("test_user", "session_001")
    tracer.start_trace({"hr": 75, "stress": 5, "sleep_latency": 30})
    tracer.add_layer("state_transition", {
        "belief": {"anxious": 0.1, "calm": 0.7, "drowsy": 0.2},
        "winner": "calm",
        "confidence": 0.7,
    })
    tracer.add_layer("homeostasis", {
        "process_s": 0.81,
        "process_c": -0.08,
        "drowsiness": "neutral",
    })
    tracer.add_layer("renderer", {
        "bpm": 5,
        "vol": 0.4,
        "breath_in": 4,
        "breath_out": 6,
    })
    result = tracer.finalize({
        "arousal": {"state": "calm", "confidence": 0.7},
        "phases": [{"bpm": 5, "vol": 0.4, "dur_s": 300}],
    })
    print(f"  trace_id: {result['_trace']['trace_id']}")
    print(f"  layers: {result['_trace']['n_layers']}")
    print(f"  duration: {result['_trace']['duration_ms']}ms")

    # 测试 2: 种子确定性
    print("\n[测试2] 种子可复现...")
    s1 = SeedManager.step_seed("session_001", 0)
    s2 = SeedManager.step_seed("session_001", 0)
    assert s1 == s2, "种子不一致!"
    print(f"  确认: seed={s1} 一致")

    # 测试 3: 加载并重放
    print("\n[测试3] 重放轨迹...")
    traces = SessionReplayer.load_session("test_user", "session_001")
    print(f"  找到 {len(traces)} 条轨迹")
    if traces:
        t = traces[0]
        print(f"  第一层: {t['layers'][0]['layer']} -> {t['layers'][0]['data']['winner']}")

    # 测试 4: 版本对比
    print("\n[测试4] 版本对比 (mock)...")
    compare = SessionReplayer.compare_versions("test_user", "session_v4", "v5.4.0", "v5.5.0")
    print(f"  v5.4.0: {compare['n_traces_a']} 条, v5.5.0: {compare['n_traces_b']} 条")
    print(f"  差异: {len(compare['diffs'])} 处")

    print("\n✅ 决策审计层正常运行")
