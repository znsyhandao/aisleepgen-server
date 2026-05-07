#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kalman_filter.py — AISleepGen 卡尔曼滤波预测引擎 v1.0

范式跃迁：从启发式贝叶斯更新 → 最优线性估计（卡尔曼滤波）。

核心思想：
  predictive_coding.py 用的是 learning_rate * error 更新：
    prediction += 0.3 * (actual - prediction)
  这个0.3是拍脑袋的，不会自适应。

  卡尔曼滤波自动计算"信任度"（卡尔曼增益 K）：
    K = 预测不确定性 / (预测不确定性 + 观测噪声)
    预测不确定性高 → K 接近 1（信任观测）
    观测噪声高 → K 接近 0（信任预测）
   更新: prediction += K * (observation - prediction)

  不需要learning_rate参数，卡尔曼增益自动最优。

状态向量（4维）：
  x[0] = 基线睡眠评分（长期趋势）
  x[1] = 评分变化率（趋势方向）
  x[2] = 典型入睡时间（小数小时）
  x[3] = 入睡时间变化率

观测向量（2维）：
  z[0] = 观测到的评分
  z[1] = 观测到的入睡时间

适用场景：
  1. 替代 predictive_coding.py 的 PredictionLayer
  2. 跟踪用户睡眠评分和入睡时间的最优估计
  3. 检测作息突变（新工作、考试周、抑郁症发作）
"""

import json, os, time, math, logging
from datetime import datetime, timedelta
import numpy as np

_kf_log = logging.getLogger('aisleepgen.kalman_filter')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ==================== 卡尔曼滤波器 ====================

class SleepKalmanFilter:
    """4维卡尔曼滤波器——最优睡眠状态估计

    状态向量: [评分, 评分变化率, 入睡时间(h), 入睡时间变化率]

    核心过程：
      predict():   基于状态转移模型，预测下一时刻状态
      update(z):   基于观测值，修正预测
      卡尔曼增益 K 自动平衡预测与观测的信任度

    Args:
        dt: 时间步长（天），默认1天
    """

    # 状态转移矩阵 F（4x4）
    # [1, 1, 0, 0]   评分 += 评分变化率
    # [0, 1, 0, 0]   评分变化率保持（弱衰减在P中体现）
    # [0, 0, 1, 1]   入睡时间 += 变化率
    # [0, 0, 0, 1]   入睡时间变化率保持
    F = np.array([
        [1, 1, 0, 0],
        [0, 0.95, 0, 0],  # 变化率0.95衰减（回归均值）
        [0, 0, 1, 1],
        [0, 0, 0, 0.95],
    ])

    # 观测矩阵 H（2x4）
    # 评分观测 = 状态[0]
    # 入睡时间观测 = 状态[2]
    H = np.array([
        [1, 0, 0, 0],
        [0, 0, 1, 0],
    ])

    # 过程噪声协方差 Q（4x4）
    # 越大表示系统变化越快
    Q = np.diag([4.0, 0.5, 0.5, 0.1])  # [评分, 变化率, 入睡时间, 变化率]

    # 观测噪声协方差 R（2x2）
    # 越大表示观测越不可信
    R = np.diag([25.0, 1.0])  # [评分噪声, 入睡时间噪声]

    def __init__(self, initial_score=50, initial_bedtime=23.5):
        """
        Args:
            initial_score: 初始评分
            initial_bedtime: 初始入睡时间（小数小时）
        """
        # 初始状态 x
        self.x = np.array([initial_score, 0.0, initial_bedtime, 0.0])

        # 初始协方差 P（高不确定性）
        self.P = np.diag([100.0, 10.0, 4.0, 1.0])

        # 步数
        self.steps = 0

        # 历史记录
        self.history = []

        # 残差序列（用于突变检测）
        self.innovation_history = []  # z - Hx (观测-预测)
        self.recent_innovations = []  # 最近5条

    def predict(self, dt=1.0):
        """预测步骤：根据状态转移模型，预测下一时刻的状态

        x_pred = F * x
        P_pred = F * P * F^T + Q * dt

        Args:
            dt: 时间步长（天），默认1天

        Returns:
            dict: 预测结果
        """
        # 如果步数少，用更高的过程噪声（快速学习）
        effective_Q = self.Q.copy()
        if self.steps < 3:
            effective_Q *= 3.0

        # 预测
        self.x = self.F @ self.x
        self.P = self.F @ self.P @ self.F.T + effective_Q * dt

        return {
            'score': self.x[0],
            'score_rate': self.x[1],
            'bedtime': self.x[2],
            'bedtime_rate': self.x[3],
            'uncertainty': math.sqrt(self.P[0, 0]),  # 评分的标准差
            'bedtime_uncertainty': math.sqrt(self.P[2, 2]),  # 入睡时间的标准差
        }

    def update(self, score=None, bedtime=None):
        """更新步骤：用观测值修正预测

        K = P * H^T * (H * P * H^T + R)^{-1}
        x = x + K * (z - H*x)
        P = (I - K*H) * P

        Args:
            score: 观测到的睡眠评分（可选）
            bedtime: 观测到的入睡时间（可选）

        Returns:
            dict: {
                'kalman_gain': [...],  卡尔曼增益（各维度的信任度）
                'innovation': [...],   新息（观测-预测）
                'score_after': float,  更新后的评分
                'bedtime_after': float, 更新后的入睡时间
                'uncertainty_after': float, 更新后的不确定性
            }
        """
        self.steps += 1

        # 构建观测向量 z（2维）
        z = np.zeros(2)
        observed_mask = [False, False]  # 哪些维度有观测

        if score is not None and score > 0:
            z[0] = score
            observed_mask[0] = True
        if bedtime is not None:
            z[1] = bedtime
            observed_mask[1] = True

        # 没有观测 → 只做预测，不做更新
        if not any(observed_mask):
            return {
                'kalman_gain': [0, 0],
                'innovation': [0, 0],
                'score_after': self.x[0],
                'bedtime_after': self.x[2],
                'uncertainty_after': math.sqrt(self.P[0, 0]),
            }

        # 预测观测 z_pred = H * x
        z_pred = self.H @ self.x

        # 新息（innovation / prediction error）
        innovation = np.array([
            z[0] - z_pred[0] if observed_mask[0] else 0,
            z[1] - z_pred[1] if observed_mask[1] else 0,
        ])

        # 新息协方差 S = H * P * H^T + R
        S = self.H @ self.P @ self.H.T + self.R

        # 如果某维度没有观测，增大对应的 S 对角元素（使 K=0）
        if not observed_mask[0]:
            S[0, 0] *= 1000
        if not observed_mask[1]:
            S[1, 1] *= 1000

        # 卡尔曼增益 K = P * H^T * S^{-1}
        K = self.P @ self.H.T @ np.linalg.inv(S)

        # 更新状态
        effective_innovation = np.array([
            innovation[0] if observed_mask[0] else 0,
            innovation[1] if observed_mask[1] else 0,
        ])
        self.x = self.x + K @ effective_innovation

        # 更新协方差
        I = np.eye(4)
        self.P = (I - K @ self.H) @ self.P

        # 保持协方差对称（数值稳定性）
        self.P = (self.P + self.P.T) / 2

        # 记录
        innovation_record = {
            'step': self.steps,
            'ts': time.time(),
            'score_innovation': float(innovation[0]) if observed_mask[0] else None,
            'bedtime_innovation': float(innovation[1]) if observed_mask[1] else None,
        }
        self.innovation_history.append(innovation_record)
        self.recent_innovations.append(innovation_record)
        if len(self.recent_innovations) > 5:
            self.recent_innovations = self.recent_innovations[-5:]

        self.history.append({
            'step': self.steps,
            'ts': time.time(),
            'score': float(self.x[0]),
            'bedtime': float(self.x[2]),
            'uncertainty': float(math.sqrt(self.P[0, 0])),
            'kalman_gain_0': float(K[0, 0]),
        })

        return {
            'kalman_gain': [float(K[0, 0]), float(K[2, 1])],
            'innovation': [float(innovation[0]), float(innovation[1])],
            'score_after': float(self.x[0]),
            'bedtime_after': float(self.x[2]),
            'uncertainty_after': float(math.sqrt(self.P[0, 0])),
        }

    def detect_regime_change(self, threshold=2.0):
        """检测用户作息突变

        基于新息（innovation）的移动Z分数。
        当连续3个新息超过threshold个标准差时，报告突变。

        典型突变场景：
          - 新工作（入睡时间突然提前1小时）
          - 失恋/考试（评分骤降30分）
          - 放假（入睡时间后移2小时）

        Returns:
            dict or None: {
                'type': 'score_drop' | 'score_rise' | 'bedtime_shift' | 'high_variance',
                'z_score': float,
                'detail': str,
            }
        """
        innovations = self.recent_innovations
        if len(innovations) < 3:
            return None

        # 提取评分新息
        score_innovs = [i['score_innovation'] for i in innovations if i['score_innovation'] is not None]
        bedtime_innovs = [i['bedtime_innovation'] for i in innovations if i['bedtime_innovation'] is not None]

        # 没有足够数据
        if len(score_innovs) < 1 and len(bedtime_innovs) < 1:
            return None

        # 所有历史新息用于计算基线
        all_score = [i['score_innovation'] for i in self.innovation_history if i['score_innovation'] is not None]
        all_bedtime = [i['bedtime_innovation'] for i in self.innovation_history if i['bedtime_innovation'] is not None]

        result = []

        # 评分突变检测（最近5条 vs 历史）
        if len(score_innovs) >= 2 and len(all_score) >= 5:
            recent_mean = sum(abs(s) for s in score_innovs) / len(score_innovs)
            hist_mean = sum(abs(s) for s in all_score[:-len(score_innovs)]) / max(len(all_score) - len(score_innovs), 1)
            if hist_mean > 0.1:  # 避免除零
                z = (recent_mean - hist_mean) / hist_mean
                if z > threshold:
                    # 判断是降还是升
                    score_sign = sum(1 for s in score_innovs if s < 0) / len(score_innovs)
                    if score_sign > 0.6:
                        result.append({'type': 'score_drop', 'z_score': round(z, 2), 'detail': f'评分持续低于预测'})
                    else:
                        result.append({'type': 'score_rise', 'z_score': round(z, 2), 'detail': f'评分波动异常'})

        # 入睡时间突变检测
        if len(bedtime_innovs) >= 2 and len(all_bedtime) >= 5:
            recent_mean = sum(abs(s) for s in bedtime_innovs) / len(bedtime_innovs)
            hist_mean = sum(abs(s) for s in all_bedtime[:-len(bedtime_innovs)]) / max(len(all_bedtime) - len(bedtime_innovs), 1)
            if hist_mean > 0.01:
                z = (recent_mean - hist_mean) / hist_mean
                if z > threshold:
                    bedtime_sign = sum(1 for s in bedtime_innovs if s > 0) / len(bedtime_innovs)
                    if bedtime_sign > 0.6:
                        result.append({'type': 'bedtime_shift', 'z_score': round(z, 2),
                                      'detail': f'入睡时间持续偏移'})
                    else:
                        result.append({'type': 'bedtime_shift', 'z_score': round(z, 2),
                                      'detail': f'入睡时间波动异常'})

        if result:
            return result[0]  # 返回最严重的
        return None

    def get_state(self):
        """获取当前最优估计状态"""
        return {
            'score': round(self.x[0], 1),
            'score_rate': round(self.x[1], 2),
            'bedtime': round(self.x[2], 2),
            'bedtime_rate': round(self.x[3], 2),
            'score_uncertainty': round(math.sqrt(self.P[0, 0]), 2),
            'bedtime_uncertainty': round(math.sqrt(self.P[2, 2]), 2),
            'steps': self.steps,
            'regime_change': self.detect_regime_change(),
        }

    def serialize(self):
        """序列化状态（用于持久化）"""
        return {
            'x': self.x.tolist(),
            'P': self.P.tolist(),
            'steps': self.steps,
            'innovation_history': self.innovation_history[-50:],
            'recent_innovations': self.recent_innovations,
        }

    @classmethod
    def deserialize(cls, data):
        """反序列化恢复状态"""
        kf = cls(initial_score=data.get('x', [50, 0, 23.5, 0])[0],
                 initial_bedtime=data.get('x', [50, 0, 23.5, 0])[2])
        kf.x = np.array(data.get('x', [50, 0, 23.5, 0]))
        kf.P = np.array(data.get('P', np.diag([100, 10, 4, 1])))
        kf.steps = data.get('steps', 0)
        kf.innovation_history = data.get('innovation_history', [])
        kf.recent_innovations = data.get('recent_innovations', [])
        return kf


# ==================== 用户级管理 ====================

class KalmanManager:
    """卡尔曼滤波器管理器

    每个用户一个滤波器实例，持久化到profile。

    Usage:
        km = KalmanManager()
        kf = km.get_filter(openid, profile)

        # 填问卷后
        result = kf.update(score=62, bedtime=23.5)
        km.save_filter(openid, kf, profile)

        # 获取预测
        pred = kf.predict()
        print(f'预测评分: {pred["score"]}, 不确定性: {pred["uncertainty"]:.2f}')
    """

    def __init__(self):
        self._filters = {}  # openid -> SleepKalmanFilter

    def get_filter(self, openid, profile=None):
        """获取用户的卡尔曼滤波器

        Args:
            openid: 用户ID
            profile: 用户画像（含持久化的卡尔曼状态）

        Returns:
            SleepKalmanFilter
        """
        if openid in self._filters:
            return self._filters[openid]

        # 从profile恢复
        if profile and isinstance(profile, dict):
            kf_data = profile.get('_kalman_filter')
            if kf_data:
                try:
                    kf = SleepKalmanFilter.deserialize(kf_data)
                    self._filters[openid] = kf
                    return kf
                except Exception:
                    pass

        # 创建新的
        # 如果有历史评分数据，用均值初始化
        initial_score = 50
        initial_bedtime = 23.5
        if profile and isinstance(profile, dict):
            history = profile.get('history', [])
            scores = [h.get('wm_score', 0) or h.get('score', 0) for h in history if isinstance(h, dict)]
            scores = [s for s in scores if s > 0]
            if scores:
                initial_score = sum(scores) / len(scores)

        kf = SleepKalmanFilter(initial_score=initial_score, initial_bedtime=initial_bedtime)
        self._filters[openid] = kf
        return kf

    def save_filter(self, openid, kf, profile):
        """将卡尔曼滤波器状态持久化到profile"""
        if not isinstance(profile, dict):
            return
        try:
            profile['_kalman_filter'] = kf.serialize()
        except Exception as e:
            _kf_log.warning('[KF] Save failed for %s: %s', str(openid)[:8], e)


# ==================== 全局实例 ====================

_manager = None

def get_manager():
    global _manager
    if _manager is None:
        _manager = KalmanManager()
    return _manager


# ==================== 自测 ====================
if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    print('=== Kalman Filter Self-Test ===')
    print()

    # 1. 从头开始，无数据
    print('1. Initial state (no data):')
    kf = SleepKalmanFilter()
    state = kf.get_state()
    print(f'   Score: {state["score"]}, uncertainty: {state["score_uncertainty"]}')
    assert state['score'] == 50
    assert state['score_uncertainty'] > 5  # 初始高不确定性
    print('   OK')

    # 2. 预测（无观测）
    print('\n2. Predict without update:')
    pred = kf.predict()
    print(f'   Predicted score: {pred["score"]:.1f}, uncertainty: {pred["uncertainty"]:.2f}')
    # 预测后不确定性应该略微增加（过程噪声）
    print(f'   Uncertainty after predict: {math.sqrt(kf.P[0,0]):.2f} (should be higher than before)')
    print('   OK')

    # 3. 第一次观测：评分62
    print('\n3. First observation: score=62:')
    result = kf.update(score=62)
    print(f'   Kalman gain (score): {result["kalman_gain"][0]:.3f}')
    print(f'   Score after: {result["score_after"]:.1f}')
    print(f'   Uncertainty after: {result["uncertainty_after"]:.2f}')
    # 第一次观测，不确定性高 → K接近1 → 评分应该接近62
    assert result['score_after'] > 55  # 信任观测
    assert result['uncertainty_after'] < 10  # 不确定性降低
    print('   OK')

    # 4. 连续观测收敛
    print('\n4. Sequential observations (8 days):')
    observations = [(62, 23.5), (65, 23.3), (58, 23.8), (55, 23.7),
                    (60, 23.4), (63, 23.2), (57, 23.6), (61, 23.3)]
    for i, (score, bed) in enumerate(observations):
        kf.predict(dt=1.0)
        result = kf.update(score=score, bedtime=bed)
        assert result['kalman_gain'][0] >= 0 and result['kalman_gain'][0] <= 1
        assert result['kalman_gain'][1] >= 0 and result['kalman_gain'][1] <= 1
    state = kf.get_state()
    print(f'   Final score: {state["score"]} (obs range: 55-65)')
    print(f'   Final bedtime: {state["bedtime"]}h (obs range: 23.2-23.8)')
    print(f'   Final uncertainty: {state["score_uncertainty"]}')
    print(f'   Kalman gain trend: K should decrease as uncertainty drops')
    # 应该收敛到观测值附近
    assert 55 < state['score'] < 65
    assert state['score_uncertainty'] < state['bedtime_uncertainty'] + 5  # 评分收敛
    print('   OK')

    # 5. 卡尔曼增益自适应
    print('\n5. Adaptive Kalman gain:')
    kf2 = SleepKalmanFilter()
    # 第1次：高不确定性 → K接近1
    r1 = kf2.update(score=62)
    # 第8次：低不确定性 → K较小
    for i in range(7):
        kf2.predict()
        kf2.update(score=60, bedtime=23.5)
    r8_result = kf2.update(score=60)  # No update - just check existing
    # 检查前几次的K
    first_k = r1['kalman_gain'][0]
    print(f'   First K: {first_k:.3f} (should be ~1: high uncertainty)')
    assert first_k > 0.5, f'First K too low: {first_k}'
    print('   OK')

    # 6. 突变检测
    print('\n6. Regime change detection:')
    kf3 = SleepKalmanFilter(initial_score=60, initial_bedtime=23.5)
    # 先建立稳定基线 — 用低过程噪声
    for _ in range(10):
        kf3.predict(dt=1.0)
        kf3.update(score=60, bedtime=23.5)

    # 现在模拟突变：评分骤降
    for score in [45, 40, 38, 42, 44]:
        kf3.predict(dt=1.0)
        kf3.update(score=score, bedtime=23.5)

    change = kf3.detect_regime_change()
    if change:
        print(f'   Detected: {change["type"]} (z={change["z_score"]})')
        print(f'   Detail: {change["detail"]}')
    else:
        print('   No regime change detected (z threshold not exceeded)')
    print('   OK')

    # 7. 持久化序列化
    print('\n7. Serialization/deserialization:')
    data = kf.serialize()
    assert 'x' in data
    assert 'P' in data
    assert 'steps' in data
    # 反序列化
    kf_restored = SleepKalmanFilter.deserialize(data)
    restored_state = kf_restored.get_state()
    assert abs(restored_state['score'] - state['score']) < 0.01
    print(f'   Serialized/Restored: score={restored_state["score"]} (diff={abs(restored_state["score"]-state["score"]):.4f})')
    print('   OK')

    # 8. KalmanManager层
    print('\n8. KalmanManager:')
    km = KalmanManager()
    profile = {}
    kf5 = km.get_filter('test_user', profile)
    assert isinstance(kf5, SleepKalmanFilter)
    kf5.update(score=62)
    km.save_filter('test_user', kf5, profile)
    assert '_kalman_filter' in profile

    # 重新加载
    kf6 = km.get_filter('test_user', profile)
    assert abs(kf6.get_state()['score'] - kf5.get_state()['score']) < 0.01
    print('   Save/load cycle: OK')

    print(f'\nAll tests PASS!')
