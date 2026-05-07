#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
agent_gateway.py — AISleepGen Agent Gateway v1.0

语义协议层：让外部AI Agent能直接调用AISleepGen全部核心能力。
不依赖Flask——纯Python类，可被REST API包装，也可被其他Agent直接import调用。

能力注册表 | 参数校验 | 上下文管理 | 追踪ID
"""

import json, os, time, uuid, logging, threading
from datetime import datetime

_ag_log = logging.getLogger('aisleepgen.agent_gateway')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 能力注册表 ====================

CAPABILITY_SCHEMAS = {
    # ===== 查询能力 =====
    "query_belief": {
        "description": "查询用户当前POMDP信念状态",
        "params": {"openid": {"type": "str", "required": True}},
        "returns": {
            "belief": {
                "expected_score": "float (0-100)",
                "entropy": "float (0-1)",
                "confidence": "float (0-1)",
                "most_likely_state": "str",
                "state_distribution": "dict"
            },
            "short_term": {
                "trend": "str (up/down/flat)",
                "trend_velocity": "float",
                "short_term_score": "float",
                "volatility": "float"
            }
        }
    },
    "query_prediction": {
        "description": "获取用户今晚睡眠预测",
        "params": {"openid": {"type": "str", "required": True}},
        "returns": {
            "predicted_score": "float",
            "confidence_interval": "float",
            "confidence": "float",
            "trend_direction": "str",
            "anomaly_score": "float"
        }
    },
    "query_intervention": {
        "description": "获取推荐干预方案",
        "params": {
            "openid": {"type": "str", "required": True},
            "context": {"type": "dict", "required": False}
        },
        "returns": {
            "recommended_action": "str",
            "score": "float",
            "reasoning": "str",
            "rl_q_values": "dict"
        }
    },
    "query_temporal_state": {
        "description": "查询用户时序状态",
        "params": {"openid": {"type": "str", "required": True}},
        "returns": {
            "state_context": "str (恶化/反弹/回落/改善/持平)",
            "velocity": "float",
            "acceleration": "float",
            "volatility": "float",
            "periodicity": "str"
        }
    },
    "query_experiment_results": {
        "description": "获取A/B实验结果",
        "params": {"experiment_id": {"type": "str", "required": False}},
        "returns": {
            "experiments": "list[dict]",
            "active_experiments": "list[dict]",
            "winner_config": "dict"
        }
    },
    # ===== 上报能力 =====
    "report_observation": {
        "description": "上报新的用户观测数据（外部传感器/对话）",
        "params": {
            "openid": {"type": "str", "required": True},
            "observation_type": {"type": "str", "required": True, "enum": ["text", "survey", "sensor", "feedback"]},
            "data": {
                "type": "dict",
                "required": True,
                "fields": {
                    "text": {"type": "str", "required": False},
                    "score": {"type": "float", "required": False},
                    "emotion": {"type": "str", "required": False},
                    "bedtime": {"type": "str", "required": False},
                    "duration": {"type": "float", "required": False},
                    "hrv": {"type": "float", "required": False},
                    "movement": {"type": "float", "required": False}
                }
            }
        },
        "returns": {
            "belief_updated": "bool",
            "new_expected_score": "float",
            "pomdp_entropy": "float",
            "triggered_intervention": "bool"
        }
    },
    "report_intervention_outcome": {
        "description": "报告干预效果",
        "params": {
            "openid": {"type": "str", "required": True},
            "intervention": {"type": "str", "required": True},
            "outcome": {"type": "str", "required": True, "enum": ["effective", "neutral", "counter"]},
            "score_delta": {"type": "float", "required": False}
        },
        "returns": {
            "recorded": "bool",
            "rl_updated": "bool",
            "ab_recorded": "bool"
        }
    },
    # ===== 控制能力 =====
    "request_decision": {
        "description": "让系统做一次完整决策（外部Agent调用）",
        "params": {
            "openid": {"type": "str", "required": True},
            "context": {
                "type": "dict",
                "required": False,
                "fields": {
                    "user_message": {"type": "str", "required": False},
                    "trigger": {"type": "str", "required": False, "enum": ["chat", "analyze", "schedule", "auto"]}
                }
            }
        },
        "returns": {
            "decision": {
                "action": "str",
                "reasoning": "str",
                "confidence": "float"
            },
            "decision_chain": {
                "rl_choice": "str",
                "pomdp_choice": "str",
                "cd_choice": "str",
                "winner": "str"
            },
            "pomdp_context": "str",
            "intervention": "dict (可选)"
        }
    },
    "create_ab_experiment": {
        "description": "创建A/B实验（外部Agent可以发起实验）",
        "params": {
            "name": {"type": "str", "required": True},
            "config_a": {"type": "dict", "required": True},
            "config_b": {"type": "dict", "required": True},
            "split_ratio": {"type": "float", "required": False}
        },
        "returns": {
            "experiment_id": "str",
            "status": "str",
            "started_at": "str"
        }
    },
    # ===== 诊断能力 =====
    "query_system_status": {
        "description": "获取系统整体状态",
        "params": {},
        "returns": {
            "version": "str",
            "total_users": "int",
            "active_experiments": "int",
            "total_clusters": "int",
            "pomdp_params": "dict",
            "rl_params": "dict",
            "safeguard_status": "str"
        }
    },
    "query_user_profile": {
        "description": "获取用户完整画像",
        "params": {"openid": {"type": "str", "required": True}},
        "returns": {
            "summary": "str",
            "cluster_id": "int",
            "total_interactions": "int",
            "recent_trend": "str",
            "rl_policy": "dict"
        }
    },
    # ===== 叙事能力 (v6.3.0) =====
    "generate_story": {
        "description": "获取用户睡眠故事（叙事引擎）",
        "params": {
            "openid": {"type": "str", "required": True},
            "context": {"type": "dict", "required": False}
        },
        "returns": {
            "story": "str",
            "has_data": "bool",
            "mode": "str"
        }
    },
    # ===== 决策解释能力 (v6.4.0) =====
    "explain_decision": {
        "description": "获取决策的自然语言解释",
        "params": {
            "openid": {"type": "str", "required": True},
            "decision_result": {"type": "dict", "required": False}
        },
        "returns": {
            "summary": "str",
            "trigger": "str",
            "evidence": "str",
            "expected_impact": "str",
            "alternatives": "str",
            "confidence": "str"
        }
    }
}

# ==================== AgentResponse Schema版本 ====================

AGENT_PROTOCOL_VERSION = "1.0"

# ==================== AgentGateway ====================


class AgentGateway:
    """Agent能力网关

    纯Python类，不依赖Flask。
    所有能力函数通过dict dispatch调用。

    用法:
        gateway = AgentGateway()
        result = gateway.handle_request({
            "version": "1.0",
            "agent_id": "my-coach",
            "capability": "query_belief",
            "params": {"openid": "user_abc"},
            "context": {"trace_id": "..."}
        })
    """

    def __init__(self):
        self._version = AGENT_PROTOCOL_VERSION
        self._lock = threading.Lock()
        # 懒加载模块缓存
        self._modules = {}
        _ag_log.info("[Gateway] AgentGateway v%s initialized with %d capabilities",
                     self._version, len(CAPABILITY_SCHEMAS))

    # ==================== 公共接口 ====================

    def handle_request(self, request: dict) -> dict:
        """入口：外部Agent发送请求，Gateway分发到对应能力函数"""
        t0 = time.time()
        # 1. 参数校验
        error = self._validate_request(request)
        if error:
            return self._error_response(request, error, t0)

        capability = request["capability"]
        params = request.get("params", {})
        trace_id = self._get_trace_id(request)

        # 2. 内置能力（不注册在CAPABILITY_SCHEMAS中，由handle_request直接处理）
        if capability == "list_capabilities":
            data = self.list_capabilities()
            return self._success_response(request, data, t0, capability)
        if capability == "get_capability_schema":
            target = params.get("capability", "")
            if not target:
                return self._error_response(request, "缺少必填参数: 'capability'", t0)
            try:
                data = self.get_capability_schema(target)
                return self._success_response(request, data, t0, capability)
            except ValueError as e:
                return self._error_response(request, str(e), t0)

        # 2b. 检查能力是否存在
        if capability not in CAPABILITY_SCHEMAS:
            return self._error_response(
                request,
                f"未知能力: '{capability}'。可用能力: {', '.join(sorted(CAPABILITY_SCHEMAS.keys()))}",
                t0
            )

        # 3. 参数校验（根据能力注册表）
        param_error = self._validate_params(capability, params)
        if param_error:
            return self._error_response(request, param_error, t0)

        # 4. 调用能力函数
        try:
            data = self._dispatch(capability, params)
            duration = round((time.time() - t0) * 1000, 1)
            return {
                "version": self._version,
                "success": True,
                "data": data,
                "error": None,
                "meta": {
                    "trace_id": trace_id,
                    "duration_ms": duration,
                    "capability": capability,
                    "schema_version": self._version
                }
            }
        except Exception as e:
            duration = round((time.time() - t0) * 1000, 1)
            _ag_log.exception("[Gateway] capability=%s failed: %s", capability, e)
            return {
                "version": self._version,
                "success": False,
                "data": None,
                "error": str(e),
                "meta": {
                    "trace_id": trace_id,
                    "duration_ms": duration,
                    "capability": capability,
                    "schema_version": self._version
                }
            }

    def call_capability(self, capability: str, params: dict) -> dict:
        """直接调用能力（同进程内使用），返回data部分"""
        if capability not in CAPABILITY_SCHEMAS:
            raise ValueError(f"未知能力: '{capability}'")
        return self._dispatch(capability, params)

    def list_capabilities(self) -> list:
        """能力清单（外部Agent用来发现）"""
        result = []
        for name, schema in sorted(CAPABILITY_SCHEMAS.items()):
            result.append({
                "name": name,
                "description": schema["description"],
                "params": self._schema_to_short(schema["params"]),
                "returns": schema["returns"]
            })
        return result

    def get_capability_schema(self, capability: str) -> dict:
        """获取某个能力的JSON Schema"""
        if capability not in CAPABILITY_SCHEMAS:
            raise ValueError(f"未知能力: '{capability}'")
        schema = CAPABILITY_SCHEMAS[capability]
        return {
            "name": capability,
            "description": schema["description"],
            "params": self._schema_to_json_schema(schema["params"]),
            "returns": schema["returns"]
        }

    def get_version(self) -> str:
        return self._version

    # ==================== 内部校验 ====================

    def _validate_request(self, req: dict) -> str:
        """校验请求结构"""
        if not isinstance(req, dict):
            return "请求必须是JSON对象"
        if "capability" not in req:
            return "缺少必填字段: 'capability'"
        if "params" not in req:
            req["params"] = {}
        if not isinstance(req["capability"], str) or not req["capability"].strip():
            return "'capability' 必须是有效的字符串"
        if "params" in req and not isinstance(req["params"], dict):
            return "'params' 必须是JSON对象"
        return ""

    def _validate_params(self, capability: str, params: dict) -> str:
        """根据能力注册表校验参数"""
        schema = CAPABILITY_SCHEMAS[capability]
        param_schema = schema["params"]

        for key, spec in param_schema.items():
            if spec.get("required", False) and key not in params:
                return f"缺少必填参数: '{key}'"
            if key in params:
                expected_type = spec.get("type", "any")
                val = params[key]
                if expected_type == "str" and not isinstance(val, str):
                    return f"参数 '{key}' 必须是字符串，得到 {type(val).__name__}"
                if expected_type == "float":
                    if not isinstance(val, (int, float)):
                        return f"参数 '{key}' 必须是数字，得到 {type(val).__name__}"
                if expected_type == "int":
                    if not isinstance(val, int) or isinstance(val, bool):
                        return f"参数 '{key}' 必须是整数，得到 {type(val).__name__}"
                if expected_type == "dict" and not isinstance(val, dict):
                    return f"参数 '{key}' 必须是对象，得到 {type(val).__name__}"
                if "enum" in spec and val not in spec["enum"]:
                    return f"参数 '{key}' 必须是 {spec['enum']} 之一，得到 '{val}'"
        return ""

    def _get_trace_id(self, req: dict) -> str:
        ctx = req.get("context", {}) or {}
        return ctx.get("trace_id", str(uuid.uuid4())[:8])

    def _success_response(self, req: dict, data: dict, t0: float, capability: str = "") -> dict:
        duration = round((time.time() - t0) * 1000, 1)
        return {
            "version": self._version,
            "success": True,
            "data": data,
            "error": None,
            "meta": {
                "trace_id": self._get_trace_id(req),
                "duration_ms": duration,
                "capability": capability or req.get("capability", "unknown"),
                "schema_version": self._version
            }
        }

    def _error_response(self, req: dict, error_msg: str, t0: float) -> dict:
        duration = round((time.time() - t0) * 1000, 1)
        return {
            "version": self._version,
            "success": False,
            "data": None,
            "error": error_msg,
            "meta": {
                "trace_id": self._get_trace_id(req),
                "duration_ms": duration,
                "capability": req.get("capability", "unknown"),
                "schema_version": self._version
            }
        }

    def _schema_to_short(self, schema: dict) -> dict:
        """将参数schema简化为type标注"""
        result = {}
        for key, spec in schema.items():
            if spec.get("type") == "dict" and "fields" in spec:
                result[key] = self._schema_to_short(spec["fields"])
            else:
                result[key] = spec.get("type", "any") + (" (必填)" if spec.get("required") else " (可选)")
        return result

    def _schema_to_json_schema(self, schema: dict) -> dict:
        """将参数schema转为JSON Schema格式"""
        props = {}
        required = []
        for key, spec in schema.items():
            if spec.get("type") == "dict" and "fields" in spec:
                props[key] = self._schema_to_json_schema(spec["fields"])
            else:
                js = {"type": spec.get("type", "string")}
                if "enum" in spec:
                    js["enum"] = spec["enum"]
                if "description" in spec:
                    js["description"] = spec["description"]
                props[key] = js
            if spec.get("required"):
                required.append(key)
        return {"type": "object", "properties": props, "required": required}

    # ==================== 能力分发核心 ====================

    def _dispatch(self, capability: str, params: dict) -> dict:
        """根据能力名称分发到具体实现"""
        dispatch_map = {
            "query_belief": self._do_query_belief,
            "query_prediction": self._do_query_prediction,
            "query_intervention": self._do_query_intervention,
            "query_temporal_state": self._do_query_temporal_state,
            "query_experiment_results": self._do_query_experiment_results,
            "report_observation": self._do_report_observation,
            "report_intervention_outcome": self._do_report_intervention_outcome,
            "request_decision": self._do_request_decision,
            "create_ab_experiment": self._do_create_ab_experiment,
            "query_system_status": self._do_query_system_status,
            "query_user_profile": self._do_query_user_profile,
            "generate_story": self._do_generate_story,
            "explain_decision": self._do_explain_decision,
        }
        fn = dispatch_map.get(capability)
        if fn is None:
            raise ValueError(f"未实现的能力: '{capability}'")
        return fn(params)

    # ==================== 模块加载 ====================

    def _get_module(self, name: str):
        """懒加载模块"""
        if name not in self._modules:
            import importlib
            self._modules[name] = importlib.import_module(name)
        return self._modules[name]

    # ==================== 能力实现 ====================

    def _do_query_belief(self, params: dict) -> dict:
        """查询用户POMDP信念状态"""
        openid = params["openid"]
        pm = self._get_module("pomdp_learner")
        e = pm.get_engine()

        belief = e.get_belief(openid)
        expected_score = belief.get("expected_score", 45.0)
        normalized_entropy = belief.get("normalized_entropy", belief.get("entropy", 1.0))
        confidence = 1.0 - normalized_entropy

        belief_probs = belief.get("belief_probs", [])
        if belief_probs:
            max_idx = max(range(len(belief_probs)), key=lambda i: belief_probs[i])
            most_likely_state = pm.STATE_NAMES[max_idx]
            state_distribution = dict(zip(pm.STATE_NAMES, [round(p, 4) for p in belief_probs]))
        else:
            most_likely_state = "unknown"
            state_distribution = {}

        # 短期上下文
        short_term = {}
        try:
            wm = self._get_module("working_memory").get_working_memory()
            ts = wm.temporal_signature(openid)
            sc = wm.state_context(openid)
            short_term = {
                "trend": ts.get("velocity", "flat") if ts.get("velocity", 0) > 0 else "flat" if ts.get("velocity", 0) == 0 else "down",
                "trend_velocity": ts.get("velocity", 0),
                "short_term_score": ts.get("volatility", 0),
                "volatility": ts.get("volatility", 0)
            }
        except Exception:
            pass

        # 修正trend为up/down/flat字符串
        vel = short_term.get("trend_velocity", 0)
        if vel > 0.5:
            short_term["trend"] = "up"
        elif vel < -0.5:
            short_term["trend"] = "down"
        else:
            short_term["trend"] = "flat"

        return {
            "belief": {
                "expected_score": expected_score,
                "entropy": round(normalized_entropy, 4),
                "confidence": round(confidence, 4),
                "most_likely_state": most_likely_state,
                "state_distribution": state_distribution
            },
            "short_term": short_term
        }

    def _do_query_prediction(self, params: dict) -> dict:
        """获取用户今晚睡眠预测"""
        openid = params["openid"]

        try:
            # 尝试 behavior_predictor (v5.)
            bp = self._get_module("behavior_predictor")
            predictor = bp.BehaviorPredictor()
            tonight = predictor.predict_tonight(openid)
            trend = predictor.predict_trend(openid)
            anomaly = predictor.anomaly_score(openid)
        except Exception:
            tonight = {}
            trend = {}
            anomaly = 0

        # Fallback: prediction_engine
        if not tonight or not isinstance(tonight, dict) or "predicted_score" not in tonight:
            try:
                pe = self._get_module("prediction_engine")
                # 尝试获取用户profile
                profile = {"openid": openid, "history": []}
                tmp = pe.predict_tonight(profile, openid)
                if isinstance(tmp, dict):
                    tonight = tmp
                else:
                    tonight = {"predicted_score": 50}
            except Exception:
                tonight = {"predicted_score": 50}

        # Safety: ensure tonight is always a dict
        if not isinstance(tonight, dict):
            tonight = {"predicted_score": 50}

        # 统一返回值格式
        score = tonight.get("predicted_score", tonight.get("score", tonight.get("prediction", 50)))
        confidence = tonight.get("confidence", tonight.get("confidence_level", "low"))
        if isinstance(confidence, str):
            conf_map = {"high": 0.9, "medium": 0.6, "low": 0.3}
            conf_val = conf_map.get(confidence, 0.5)
        else:
            conf_val = float(confidence)

        trend_dir = "flat"
        trend_dict = {}
        if isinstance(trend, dict):
            trend_dir = trend.get("direction", trend.get("trend", "flat"))
            trend_dict = trend
        elif isinstance(trend, str):
            trend_dir = trend

        ci = tonight.get("confidence_interval", tonight.get("interval", 15))
        return {
            "predicted_score": float(score),
            "confidence_interval": float(ci),
            "confidence": conf_val,
            "trend_direction": trend_dir,
            "anomaly_score": float(anomaly)
        }

    def _do_query_intervention(self, params: dict) -> dict:
        """获取推荐干预方案"""
        openid = params["openid"]
        context = params.get("context", {})

        # 1) Online RL 决策
        try:
            rl = self._get_module("online_rl").get_online_rl()
            ctx = {"score": context.get("score", 50), "pomdp_entropy": context.get("entropy", 0.5)}
            rl_action = rl.act(openid, ctx)
        except Exception:
            rl_action = "skip"
            ctx = {}

        # 2) POMDP decide 用于推理
        pm = self._get_module("pomdp_learner")
        e = pm.get_engine()
        pomdp_decision = e.decide(openid)

        # 3) Sleep Coach 干预建议
        try:
            sc = self._get_module("sleep_coach")
            profile = {"openid": openid, "history": context.get("history", []), "sleep_coach": {}}
            emotion = context.get("emotion", "neutral")
            suggestions = sc.get_daily_suggestion(profile, emotion)
        except Exception:
            suggestions = None

        # 4) Conscious Decider
        try:
            cd = self._get_module("conscious_decider").get_decider()
            cd_decision = cd.decide(openid, context.get("trigger", "chat"), context)
            cd_action = cd_decision.get("action", "skip")
            cd_reason = cd_decision.get("reason", "")
        except Exception:
            cd_action = "skip"
            cd_reason = ""

        # 构建返回值
        decision_source = "rl"
        if suggestions:
            action_title = suggestions.get("title", rl_action)
            reasoning = suggestions.get("reason", f"RL建议: {rl_action}, POMDP: {pomdp_decision.get('action', '')}")
        else:
            action_title = cd_action
            reasoning = cd_reason or f"RL: {rl_action}, POMDP: {pomdp_decision.get('action', '')}"

        # 获取RL Q值
        q_values = {}
        try:
            if hasattr(rl, 'get_policy_summary'):
                summary = rl.get_policy_summary(openid)
                q_values = summary if isinstance(summary, dict) else {}
        except Exception:
            pass

        return {
            "recommended_action": action_title,
            "score": pomdp_decision.get("confidence", 0.5),
            "reasoning": reasoning,
            "rl_q_values": q_values
        }

    def _do_query_temporal_state(self, params: dict) -> dict:
        """查询用户时序状态"""
        openid = params["openid"]
        wm = self._get_module("working_memory").get_working_memory()

        ts = wm.temporal_signature(openid)
        sc = wm.state_context(openid)

        # 处理state_context编码问题
        if isinstance(sc, bytes):
            sc = sc.decode('utf-8', errors='replace')
        state_str = str(sc).strip()

        # 将中文映射到标准状态
        state_map = {
            "恶化": "恶化",
            "反弹": "反弹",
            "回落": "回落",
            "改善": "改善",
            "持平": "持平",
            "平静": "持平"
        }
        state_context = state_str
        for ch_key, ch_val in state_map.items():
            if ch_key in state_str:
                state_context = ch_val
                break

        # 确定周期
        periodicity = ts.get("periodicity", "unknown")
        return {
            "state_context": state_context,
            "velocity": ts.get("velocity", 0),
            "acceleration": ts.get("acceleration", 0),
            "volatility": ts.get("volatility", 0),
            "periodicity": periodicity
        }

    def _do_query_experiment_results(self, params: dict) -> dict:
        """获取A/B实验结果"""
        experiment_id = params.get("experiment_id")
        ab = self._get_module("ab_framework")

        experiments = ab.list_experiments()
        active = [e for e in experiments if e.get("status") == "running"]

        winner = {}
        try:
            winner = ab.load_winner_config()
        except Exception:
            pass

        # 如果指定了experiment_id，过滤
        target_experiments = experiments
        if experiment_id:
            target_experiments = [e for e in experiments if e.get("experiment_id") == experiment_id]

        return {
            "experiments": target_experiments,
            "active_experiments": active,
            "winner_config": winner
        }

    def _do_report_observation(self, params: dict) -> dict:
        """上报新的用户观测数据"""
        openid = params["openid"]
        obs_type = params["observation_type"]
        data = params.get("data", {})

        pm = self._get_module("pomdp_learner")
        e = pm.get_engine()

        # 获取之前的belief
        before = e.get_belief(openid)
        before_score = before.get("expected_score", 50)

        # 根据观测类型调用POMDP observe
        if obs_type == "text":
            text = data.get("text", "")
            e.observe(openid, text=text)
        elif obs_type == "survey":
            score = data.get("score", 50)
            bedtime = data.get("bedtime", "")
            mood = data.get("emotion", "neutral")
            e.observe_survey(openid, score, bedtime=bedtime, mood=mood)
        elif obs_type == "sensor":
            text_parts = []
            if data.get("hrv") is not None:
                text_parts.append(f"心率变异性:{data['hrv']}")
            if data.get("movement") is not None:
                text_parts.append(f"体动:{data['movement']}")
            if data.get("duration") is not None:
                text_parts.append(f"睡眠时长:{data['duration']}h")
            if data.get("score") is not None:
                e.observe(openid, score=data["score"])
            elif text_parts:
                e.observe(openid, text=", ".join(text_parts))
        elif obs_type == "feedback":
            score = data.get("score", 50)
            e.observe(openid, score=score)

        # 获取更新后的belief
        after = e.get_belief(openid)
        after_score = after.get("expected_score", 50)
        after_entropy = after.get("normalized_entropy", after.get("entropy", 1))
        belief_updated = abs(before_score - after_score) > 0.1

        # 检查是否触发了干预
        triggered = False
        try:
            decision = e.decide(openid)
            triggered = decision.get("action") in ("push", "probe", "in_chat")
        except Exception:
            pass

        return {
            "belief_updated": belief_updated,
            "new_expected_score": after_score,
            "pomdp_entropy": after_entropy,
            "triggered_intervention": triggered
        }

    def _do_report_intervention_outcome(self, params: dict) -> dict:
        """报告干预效果"""
        openid = params["openid"]
        intervention_name = params["intervention"]
        outcome = params["outcome"]
        score_delta = params.get("score_delta")

        recorded = False
        rl_updated = False
        ab_recorded = False

        # 1) 记录到实验日志
        try:
            el = self._get_module("experiment_log").get_log()
            from experiment_log import Experiment as ExpCls
            exp = ExpCls(
                openid=openid,
                intervention_type=intervention_name,
                hypothesis="user feedback",
                intervention_data={"outcome": outcome, "score_delta": score_delta}
            )
            exp.experiment_id = f"gw_{int(time.time())}_{openid[:8]}"
            el.record_designed(exp)
            recorded = True
        except Exception:
            pass

        # 2) 更新RL（奖励反馈）
        try:
            rl = self._get_module("online_rl").get_online_rl()
            reward_map = {"effective": 1.0, "neutral": 0.0, "counter": -1.0}
            reward = reward_map.get(outcome, 0.0)
            if score_delta is not None:
                reward = min(1.5, max(-1.5, reward + score_delta / 100.0))
            rl.update(openid, intervention_name, reward, {"score": 50})
            rl_updated = True
        except Exception:
            pass

        # 3) 记录A/B outcome
        try:
            ab = self._get_module("ab_framework")
            active = ab.list_experiments()
            for exp in active:
                if exp.get("status") == "running":
                    try:
                        arm = ab.get_assignment(openid, exp["experiment_id"])
                        ab.record_outcome(exp["experiment_id"], openid, arm, {
                            "score": (score_delta or 0) + 50,
                            "timestamp": time.time(),
                            "outcome": outcome
                        })
                        ab_recorded = True
                    except Exception:
                        pass
        except Exception:
            pass

        return {
            "recorded": recorded,
            "rl_updated": rl_updated,
            "ab_recorded": ab_recorded
        }

    def _do_request_decision(self, params: dict) -> dict:
        """让系统做一次完整决策"""
        openid = params["openid"]
        ctx = params.get("context", {})
        user_message = ctx.get("user_message", "")
        trigger = ctx.get("trigger", "auto")

        # === 1. Online RL ===
        rl_action = "skip"
        try:
            rl = self._get_module("online_rl").get_online_rl()
            rl_ctx = {"score": 50, "pomdp_entropy": 0.5, "trend": "flat", "last_effect": "none"}
            rl_action = rl.act(openid, rl_ctx)
        except Exception:
            pass

        # === 2. POMDP Decide ===
        pomdp_action = "probe"
        pomdp_confidence = 0.5
        try:
            pm = self._get_module("pomdp_learner")
            e = pm.get_engine()
            pomdp_dec = e.decide(openid)
            pomdp_action = pomdp_dec.get("action", "probe")
            pomdp_confidence = pomdp_dec.get("confidence", 0.5)
        except Exception:
            pass

        # === 3. Conscious Decider ===
        cd_action = "skip"
        cd_reason = ""
        try:
            cd = self._get_module("conscious_decider").get_decider()
            cd_ctx = {"message": user_message, "session_count": 1, "urgency": "medium", "mode": "push"}
            cd_dec = cd.decide(openid, trigger, cd_ctx)
            cd_action = cd_dec.get("action", "skip")
            cd_reason = cd_dec.get("reason", "")
        except Exception:
            pass

        # === 4. 投票决定winner ===
        chains = {
            "rl_choice": rl_action,
            "pomdp_choice": pomdp_action,
            "cd_choice": cd_action
        }
        # 简单多数投票
        votes = {}
        for a in chains.values():
            votes[a] = votes.get(a, 0) + 1
        if votes:
            winner = max(votes, key=votes.get)
        else:
            winner = "skip"

        # === 5. POMDP上下文（用于LLM prompt）===
        pomdp_context = ""
        try:
            cpb = self._get_module("chat_prompt_builder")
            pomdp_context = cpb.build_pomdp_context(openid)
        except Exception:
            pass

        # === 6. 干预建议 ===
        intervention = None
        if winner in ("push", "probe", "in_chat"):
            try:
                sc = self._get_module("sleep_coach")
                profile = {"openid": openid, "history": [], "sleep_coach": {}}
                emotion = ctx.get("emotion", "neutral")
                sugg = sc.get_daily_suggestion(profile, emotion)
                intervention = sugg if sugg else None
            except Exception:
                pass

        return {
            "decision": {
                "action": winner,
                "reasoning": cd_reason or f"投票结果: RL={rl_action}, POMDP={pomdp_action}, CD={cd_action}",
                "confidence": pomdp_confidence
            },
            "decision_chain": {
                "rl_choice": rl_action,
                "pomdp_choice": pomdp_action,
                "cd_choice": cd_action,
                "winner": winner
            },
            "pomdp_context": pomdp_context,
            "intervention": intervention
        }

    def _do_create_ab_experiment(self, params: dict) -> dict:
        """创建A/B实验"""
        name = params["name"]
        config_a = params["config_a"]
        config_b = params["config_b"]
        split_ratio = params.get("split_ratio", 0.5)

        ab = self._get_module("ab_framework")
        eid = ab.create_experiment(name, config_a, config_b, split_ratio=split_ratio)
        ab.start_experiment(eid)

        return {
            "experiment_id": eid,
            "status": "running",
            "started_at": datetime.now().isoformat()
        }

    def _do_query_system_status(self, params: dict) -> dict:
        """获取系统整体状态"""
        version = "v6.5.0"

        total_users = 0
        try:
            wm = self._get_module("working_memory").get_working_memory()
            total_users = len(wm.get_all_openids())
        except Exception:
            pass

        active_experiments = 0
        try:
            ab = self._get_module("ab_framework")
            exps = ab.list_experiments()
            active_experiments = len([e for e in exps if e.get("status") == "running"])
        except Exception:
            pass

        total_clusters = 0
        try:
            pm = self._get_module("population_manager")
            mgr = pm.get_population_manager()
            clusters = mgr.get_clusters() if hasattr(mgr, 'get_clusters') else []
            total_clusters = len(clusters) if isinstance(clusters, list) else 0
        except Exception:
            pass

        pomdp_params = {}
        try:
            pom = self._get_module("pomdp_learner")
            pomdp_params = {
                "forget_factor": pom._engine.forget_factor if hasattr(pom, '_engine') and pom._engine else pom.ALearner.forget_factor,
                "alpha0": pom.ALearner.alpha0,
                "n_states": pom.N_STATES,
                "n_obs": pom.N_OBS
            }
        except Exception:
            pass

        rl_params = {}
        try:
            rl = self._get_module("online_rl").get_online_rl()
            rl_params = {
                "alpha": rl.alpha,
                "gamma": rl.gamma,
                "epsilon": rl.epsilon
            }
        except Exception:
            pass

        safeguard_status = "unknown"
        try:
            ds = self._get_module("dynamic_safeguards")
            sg = ds.DynamicSafeguards()
            status = sg.check("_gateway_probe")
            safeguard_status = status.get("summary", "unknown")
        except Exception:
            pass

        return {
            "version": version,
            "total_users": total_users,
            "active_experiments": active_experiments,
            "total_clusters": total_clusters,
            "pomdp_params": pomdp_params,
            "rl_params": rl_params,
            "safeguard_status": safeguard_status
        }

    def _do_query_user_profile(self, params: dict) -> dict:
        """获取用户完整画像"""
        openid = params["openid"]

        summary = ""
        try:
            wm = self._get_module("working_memory").get_working_memory()
            sc = wm.state_context(openid)
            summary = str(sc) if sc else "暂无数据"
        except Exception:
            summary = "暂无数据"

        cluster_id = -1
        try:
            pm = self._get_module("population_manager")
            mgr = pm.get_population_manager()
            if hasattr(mgr, 'get_user_cluster'):
                cluster_id = mgr.get_user_cluster(openid)
        except Exception:
            pass

        total_interactions = 0
        recent_trend = "flat"
        try:
            wm = self._get_module("working_memory").get_working_memory()
            ts = wm.temporal_signature(openid)
            vel = ts.get("velocity", 0)
            if vel > 0.5:
                recent_trend = "up"
            elif vel < -0.5:
                recent_trend = "down"
            else:
                recent_trend = "flat"

            # 尝试从WM获取计数
            if hasattr(wm, 'recent'):
                data = wm.recent(openid, n=100)
                if data:
                    total_interactions = len(data)
        except Exception:
            pass

        rl_policy = {}
        try:
            rl = self._get_module("online_rl").get_online_rl()
            rl_policy = rl.get_policy_summary(openid) if hasattr(rl, 'get_policy_summary') else {}
        except Exception:
            pass

        return {
            "summary": summary,
            "cluster_id": cluster_id,
            "total_interactions": total_interactions,
            "recent_trend": recent_trend,
            "rl_policy": rl_policy
        }

    # ==================== 叙事能力 (v6.3.0) ====================

    def _do_generate_story(self, params: dict) -> dict:
        """生成用户睡眠故事"""
        openid = params["openid"]
        context = params.get("context", {})
        try:
            ne = self._get_module("narrative_engine").get_narrative_engine()
            result = ne.generate_story(openid, context)
            return {
                "story": result["story"],
                "has_data": result["has_data"],
                "mode": result["mode"],
            }
        except Exception as e:
            return {"story": "", "has_data": False, "error": str(e)}

    # ==================== 决策解释能力 (v6.4.0) ====================

    def _do_explain_decision(self, params: dict) -> dict:
        """生成决策的自然语言解释"""
        openid = params["openid"]
        decision_result = params.get("decision_result", {})
        try:
            de = self._get_module("decision_explainer").get_decision_explainer()
            explanation = de.explain(openid, decision_result)
            return {
                "summary": explanation["summary"],
                "trigger": explanation["trigger"],
                "evidence": explanation["evidence"],
                "expected_impact": explanation["expected_impact"],
                "alternatives": explanation["alternatives"],
                "confidence": explanation["confidence"],
            }
        except Exception as e:
            return {"summary": "", "error": str(e)}


# ==================== 单例 ====================

_GATEWAY_LOCK = threading.Lock()
_GATEWAY_INSTANCE = None


def get_gateway() -> AgentGateway:
    """获取单例Gateway实例"""
    global _GATEWAY_INSTANCE
    if _GATEWAY_INSTANCE is None:
        with _GATEWAY_LOCK:
            if _GATEWAY_INSTANCE is None:
                _GATEWAY_INSTANCE = AgentGateway()
    return _GATEWAY_INSTANCE
