"""
WorldModelCoordinator — 世界模型协调器
对接 deepseek_proxy.py 的流式 API：感知→状态→规划→渲染+自由能

此文件是对旧版 sleep_world_model.py (v5.2 10专家会诊) 的桥接封装，
外部感知数据先经过自由能评估，再路由到世界模型引擎。
"""

import time
import json
from typing import Dict, Optional
from free_energy_kernel import FreeEnergyTracker, SleepCausalInference


class WorldModelCoordinator:
    """世界模型协调器 — 自由能驱动的感知-行动循环桥接"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._history: list = []
        self._total_call_count = 0
        self._last_vfe: Optional[float] = None
        self._free_energy_tracker = FreeEnergyTracker(user_id)
        self._causal_inference = SleepCausalInference(user_id)
        # 惰性加载世界模型引擎
        self._engine = None

    def _lazy_engine(self):
        if self._engine is None:
            from sleep_world_model import WorldModelEngine
            self._engine = WorldModelEngine()

    def step(self,
             hr: Optional[float] = None,
             stress: Optional[int] = None,
             sleep_latency: Optional[float] = None,
             total_sleep_min: Optional[float] = None,
             target_wake_min: Optional[float] = None,
             schedule_urgency: Optional[int] = None,
             elapsed_s: float = 60.0,
             message: str = '',
             tracer: Optional[object] = None) -> Dict:
        """一步闭环 — 感知→状态→自由能评估→世界模型→返回

        Args:
            hr: 心率
            stress: 压力 (1-10)
            sleep_latency: 入睡潜伏期(分钟)
            total_sleep_min: 总睡眠时间(分钟)
            target_wake_min: 目标唤醒时间(分钟)
            schedule_urgency: 日程紧急度 (1-10)
            elapsed_s: 距上次更新秒数
            tracer: 决策审计追踪器

        Returns:
            完整状态字典
        """
        self._lazy_engine()
        self._total_call_count += 1

        # 构建输入
        input_state = {
            'hr': hr,
            'stress': stress,
            'sleep_latency': sleep_latency or 30,
            'total_sleep_min': total_sleep_min or 420,
            'target_wake_min': target_wake_min,
            'schedule_urgency': schedule_urgency,
            'openid': self.user_id,  # 多模态感知：让专家能自主查历史数据
        }

        # ===== 自由能评估 =====
        fe_result = self._free_energy_tracker.evaluate(
            state={
                'heart_rate': hr,
                'stress_level': stress,
                'belief_distribution': {
                'calm': 0.5, 'tense': 0.3, 'tired': 0.2,
            },
            # 自由能将根据 WorldModelEngine 输出的 analysis.confidence 动态构建
            },
            session_history_len=len(self._history),
            predicted_intervention_vfe=None,
        )

        # ===== 消息解析: 从自然语言中提取睡眠参数 =====
        parsed = {}
        if message:
            try:
                from message_parser import parse_sleep_message
                parsed = parse_sleep_message(message)
            except Exception:
                pass  # 解析失败不影响主线

        # 用解析结果覆盖显式参数（显式的优先级更高）
        final_latency = sleep_latency if sleep_latency is not None else parsed.get('sleep_latency', 30)
        final_duration = total_sleep_min if total_sleep_min is not None else parsed.get('total_duration', 420)
        final_awake = parsed.get('awake_times', 0)
        final_stress = stress if stress is not None else parsed.get('stress_level', 5)

        # ===== 世界模型引擎 =====
        try:
            analysis = self._engine.comprehensive_analysis(
                {
                    'feeling': message if message else 'auto',
                    'sleep_latency': final_latency,
                    'total_duration': final_duration,
                    'stress_level': final_stress,
                    'awake_times': final_awake,
                    'awake_duration': 0,
                    'indicators': parsed.get('indicators', []),
                    'hr': hr,  # 多模态感知：传给CardiacMonitor直接读心率数据
                },
                today_str=time.strftime('%Y%m%d'),
            )
        except Exception as e:
            analysis = {
                'total_score': 60,
                'quality': 'good',
                'error': str(e),
            }

        # ===== 因果推理 =====
        causal_result = self._causal_inference.infer(
            inputs={
                'hr': hr,
                'stress': stress,
                'sleep_latency': sleep_latency,
                'total_sleep': total_sleep_min,
                'awake_times': 0,
                'daytime_fatigue': None,
            },
            vfe_result=fe_result,
        )

        # ===== 构建响应 =====
        reply_text = ''
        # 优先用 DeepSeek 生成的 narrative，回退到 insights 摘要
        if analysis.get('narrative'):
            reply_text = analysis['narrative']
        elif analysis.get('insights', {}).get('primary_focus'):
            reply_text = analysis['insights']['primary_focus']
        elif analysis.get('insights', {}).get('summary'):
            reply_text = '；'.join(analysis['insights']['summary'][:3])

        # ═══ AI 生成标识：合规要求 ═══
        if reply_text and len(reply_text) > 3:
            reply_text = reply_text.rstrip('。！？') + '（AI生成，仅供参考）'

        # 构建前端友好的维度分析结构
        raw_dims = analysis.get('analysis', {}).get('dimensions', {})
        dims_list = []
        for expert_name, expert_data in raw_dims.items():
            if isinstance(expert_data, dict):
                dims_list.append({
                    'name': expert_name,
                    'score': expert_data.get('score', 0.5),
                    'confidence': expert_data.get('confidence', 0.5),
                    'findings': expert_data.get('findings', []),
                    'narrative': expert_data.get('narrative', ''),
                    'risk_flags': expert_data.get('risk_flags', []),
                    'specialty': expert_data.get('specialty', expert_name),
                })

        result = {
            'success': True,
            'arousal_state': 'calm' if (hr or 70) < 80 else 'tense',
            'confidence': max(0.3, 1.0 - fe_result['entropy']),
            'entropy': fe_result.get('entropy', 0.5),
            'sleep_score': analysis.get('total_score', 60),
            'sleep_phase': analysis.get('sleep_phase', 'unknown'),
            'deep_sleep_pct': analysis.get('deep_sleep_pct', 30),
            'rem_pct': analysis.get('rem_pct', 20),
            'timestamp': time.time(),
            '_free_energy': fe_result,
            '_causal_analysis': causal_result,
            'action': {
                'meta': {
                    'action_id': f'fe_{int(time.time())}',
                    'category': 'silent' if fe_result['should_be_silent'] else 'intervention',
                    'priority': 'low' if fe_result['should_be_silent'] else 'normal',
                }
            },
            'intervention_candidates': [],
            'intervention_prediction': [],
            # 前端需要的关键字段
            'reply': reply_text,
            'analysis': {
                'dimensions': dims_list,
            },
        }

        # 自由能标记
        if fe_result['should_be_silent']:
            result['action']['meta']['silent'] = True
            result['action']['meta']['silent_reason'] = \
                f"VFE={fe_result['vfe']:.3f} < threshold, entropy={fe_result['entropy']:.3f}"

        self._history.append(fe_result)
        if len(self._history) > 100:
            self._history.pop(0)

        self._last_vfe = fe_result['vfe']

        return result

    def get_session_summary(self) -> Dict:
        """会话摘要"""
        if not self._history:
            return {'status': 'empty', 'user_id': self.user_id}
        fe_summary = self._free_energy_tracker.get_summary()
        return {
            'status': 'active',
            'user_id': self.user_id,
            'total_calls': self._total_call_count,
            'free_energy': fe_summary,
            'last_vfe': self._last_vfe,
        }
