#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wm_router.py — 可学习的上下文路由网络 v1.0

核心思路：用一个小型可学习网络替代硬编码的关键词匹配，决定：
  1. 当前输入是否需要检索历史案例
  2. 检索哪种类型的案例（酒精型/焦虑型/疼痛型/...）
  3. 检索多少个案例

训练方式：每天凌晨用当天的经验数据，以用户的沉默/继续对话为反馈信号，
  更新路由网络的参数。

关键技术：不依赖外部深度学习框架，用纯numpy实现一个简单的两层MLP。
  当用户量级达到1000+时，可以升级为PyTorch。

架构：
  Input: 16维特征向量(从neural_extractor字段+关键词编码而来)
  → 隐藏层(16→8, ReLU) 
  → 输出层(8→3):
     [retrieve_prob, category_index, top_k_logits]

  可训练参数: ~150个浮点数 (16*8 + 8 + 8*3 + 3 = 163个参数)
  每次推理耗时: < 1ms
"""

import json
import os
import time
import math
import random
from datetime import datetime
import logging

_ai_log = logging.getLogger('aisleepgen.wm_router')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(PROJECT_ROOT, 'data', 'wm_router_params.json')
TRAINING_LOG = os.path.join(PROJECT_ROOT, 'data', 'wm_router_train.jsonl')


# ===== 类别定义 =====
# 睡眠问题的7个元类型（可学习扩展）
CATEGORIES = [
    'alcohol_related',       # 酒精相关
    'digestive_issue',       # 消化不适
    'anxiety_stress',        # 焦虑压力
    'pain_discomfort',       # 疼痛不适
    'sleep_env_habit',       # 睡眠环境/习惯
    'circadian_rhythm',      # 生物钟/作息
    'general_insomnia',      # 一般性失眠
]

CATEGORY_CN = {
    'alcohol_related': '酒精相关',
    'digestive_issue': '消化不适',
    'anxiety_stress': '焦虑压力',
    'pain_discomfort': '疼痛不适',
    'sleep_env_habit': '睡眠环境习惯',
    'circadian_rhythm': '生物钟作息',
    'general_insomnia': '一般性失眠',
}


class WMRouter:
    """可学习的上下文路由网络"""

    def __init__(self):
        self.params = self._load_or_init()
        self._feature_cache = {}

    def _load_or_init(self):
        """加载已有参数或初始化"""
        if os.path.exists(MODEL_PATH):
            try:
                with open(MODEL_PATH, 'r', encoding='utf-8') as f:
                    p = json.load(f)
                _ai_log.info('[Router] Loaded existing params, %d total weights',
                             sum(len(v) for v in p.get('W1', [])))
                return p
            except Exception as e:
                _ai_log.warning('[Router] Load failed: %s, reinit', e)

        # 初始化：引导参数
        # W2的列含义: [retrieve_logit, category_logit, topk_logit]
        # 让W2在特征维度上与类别先验对齐
        W2 = [[random.gauss(0, 0.05) for _ in range(3)] for _ in range(8)]
        # 增强特征2(酒精)到第0类的连接
        # b2[0]=-1.0 (默认不检索), b2[1]=-0.5 (默认一般), b2[2]=0.5 (默认检索1条)
        params = {
            'W1': [[random.gauss(0, 0.1) for _ in range(8)] for _ in range(16)],  # 16→8
            'b1': [0.0] * 8,
            'W2': W2,  # 8→3
            'b2': [-1.0, -0.5, 0.5],  # 默认不检索、一般类别、检索1条
            'feature_bias': {  # 特征维度的直接偏置（不经过隐藏层，直接加到logits）
                # 格式: {feature_dim: [retrieve_bias, category_bias, topk_bias]}
                2: [1.0, 1.0, 0],   # drink_alcohol → 检索+酒精类
                5: [1.0, 1.2, 1],   # digestive → 检索+消化类+多检索一条
                4: [1.0, 1.5, 0],   # anxiety → 检索+焦虑类
                1: [1.0, 2.0, 0],   # has_pain → 检索+疼痛类
                12: [0.5, 0, 0],    # 醒/睡不着 → 弱检索
                14: [0.3, 0, 0],    # 多字段 → 弱检索
            },
            'version': 1,
            'train_count': 0,
            'last_train_date': '',
        }
        self._save(params)
        _ai_log.info('[Router] Initialized fresh params')
        return params

    def _save(self, params=None):
        """保存参数"""
        p = params or self.params
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        with open(MODEL_PATH, 'w', encoding='utf-8') as f:
            json.dump(p, f, ensure_ascii=False)
        return True

    def _relu(self, x):
        return max(0, x)

    def _sigmoid(self, x):
        if x > 20: return 1.0
        if x < -20: return 0.0
        return 1.0 / (1.0 + math.exp(-x))

    def _softmax(self, logits):
        max_l = max(logits)
        exps = [math.exp(l - max_l) for l in logits]
        s = sum(exps)
        return [e / s for e in exps]

    def forward(self, features):
        """前向传播: 输入16维特征 → 输出决策

        Args:
            features: list[float], 16维特征向量

        Returns:
            dict: {
                'retrieve_prob': float,  # 0-1, 是否检索的概率
                'category': str,          # 问题类型
                'top_k': int,             # 检索多少个案例
                'category_probs': dict,   # 各类别概率
            }
        """
        p = self.params
        W1, b1 = p['W1'], p['b1']
        W2, b2 = p['W2'], p['b2']

        # 隐藏层: 16→8 → ReLU
        h = [0.0] * 8
        for i in range(8):
            s = b1[i]
            for j in range(16):
                s += features[j] * W1[j][i]
            h[i] = self._relu(s)

        # 输出层: 8→3
        logits = [0.0] * 3
        for i in range(3):
            s = b2[i]
            for j in range(8):
                s += h[j] * W2[j][i]
            logits[i] = s

        # 应用 feature_bias：某些特征维度直接加偏置到 logits
        fb = p.get('feature_bias', {})
        for feat_dim, biases in fb.items():
            if feat_dim < len(features) and features[feat_dim] > 0.5:
                for i in range(min(len(biases), 3)):
                    logits[i] += biases[i]

        # 解释输出:
        # logits[0] → sigmoid → retrieve_prob (0-1)
        retrieve_prob = self._sigmoid(logits[0])

        # 解释输出:
        # logits[0] → sigmoid → retrieve_prob (0-1)
        # logits[1] → arctan 映射到 0-6 → category 索引
        # 用 arctan(logits[1])/(pi/2) * 6 实现平滑映射
        cat_raw = math.atan(logits[1]) / (math.pi / 2)  # 归一化到 -1 到 1
        cat_norm = (cat_raw + 1) / 2  # 映射到 0 到 1
        cat_idx = max(0, min(6, int(round(cat_norm * 6))))
        category = CATEGORIES[cat_idx]

        # logits[2] → sigmoid → top_k: sigmoid=0→1条, sigmoid=0.5→2条, sigmoid=1→3条
        k_raw = self._sigmoid(logits[2])
        top_k = max(1, min(3, 1 + int(round(k_raw * 2))))

        return {
            'retrieve_prob': round(retrieve_prob, 2),
            'category': category,
            'category_cn': CATEGORY_CN.get(category, category),
            'top_k': top_k,
        }

    def predict(self, fields, raw_text):
        """对外接口：输入neural字段+原始文本 → 检索策略

        Args:
            fields: neural_extractor提取字段
            raw_text: 用户原始输入

        Returns:
            dict: 检索策略
        """
        # 保护fields字段值类型安全（可能混入字符串）
        if isinstance(fields, dict):
            safe_fields = {}
            for k, v in fields.items():
                if isinstance(v, str) and v.replace('.', '', 1).isdigit():
                    safe_fields[k] = float(v) if '.' in v else int(v)
                else:
                    safe_fields[k] = v
            fields = safe_fields
        
        features = self._extract_features(fields, raw_text)
        decision = self.forward(features)

        # 如果检索概率低，返回空策略
        if decision['retrieve_prob'] < 0.3:
            return {
                'should_retrieve': False,
                'category': decision['category'],
                'category_cn': decision['category_cn'],
                'top_k': 0,
                'retrieve_prob': decision['retrieve_prob'],
            }

        return {
            'should_retrieve': True,
            'category': decision['category'],
            'category_cn': decision['category_cn'],
            'top_k': decision['top_k'],
            'retrieve_prob': decision['retrieve_prob'],
        }

    def _extract_features(self, fields, raw_text):
        """从neural字段+原始文本提取16维特征向量

        特征维度:
        0: 夜醒次数(归一化到0-1)
        1: 是否有疼痛
        2: 是否喝酒
        3: 是否喝咖啡因
        4: 焦虑压力相关
        5: 消化不适相关
        6: 打鼾相关
        7: 睡眠时长是否偏短
        8: 情绪是否差
        9: 入睡时长是否偏长
        10: 是否有噩梦
        11: 输入长度(归一化)
        12: 是否包含"醒"/"睡不着"关键词
        13: 是否含具体时间描述(昨晚/凌晨3点等)
        14: 字段数量(归一化到0-1)
        15: 原始文本是否包含多个问题(用标点分隔)
        """
        text = (raw_text or '').lower()
        f = [0.0] * 16

        # 保护：fields可能不是dict（测试用例传入字符串）
        if not isinstance(fields, dict):
            fields = {}

        if fields:
            # 0: awake_times
            at = fields.get('awake_times', 0)
            try:
                f[0] = min(int(at) / 5.0, 1.0) if at else 0
            except (ValueError, TypeError):
                f[0] = 0

            # 1: has_pain
            f[1] = 1.0 if fields.get('has_pain') else 0.0

            # 2: drink alcohol
            f[2] = 1.0 if fields.get('drink') == 'alcohol' else 0.0

            # 3: drink caffeine
            f[3] = 1.0 if fields.get('drink') == 'caffeine' else 0.0

            # 4: anxiety/stress
            cause = str(fields.get('awake_cause', '')).lower()
            f[4] = 1.0 if ('焦虑' in cause or '压力' in cause or 'anxiety' in cause) else 0.0

            # 5: digestive
            f[5] = 1.0 if ('消化' in cause or '肚' in cause or '胃' in cause) else 0.0

            # 6: snore
            f[6] = 1.0 if fields.get('snore_related') else 0.0

            # 7: short duration
            dur = fields.get('total_duration', 0)
            try:
                f[7] = 1.0 if (int(dur) < 360) else 0.0
            except (ValueError, TypeError):
                f[7] = 0

            # 8: bad mood
            mood = str(fields.get('mood', '')).lower()
            f[8] = 1.0 if ('差' in mood or 'bad' in mood or '不好' in mood) else 0.0

            # 9: long sleep latency
            lat = fields.get('sleep_latency', 0)
            try:
                f[9] = 1.0 if (int(lat) > 30) else 0.0
            except (ValueError, TypeError):
                f[9] = 0

        # 10: nightmare
        f[10] = 1.0 if ('噩梦' in text or '梦' in text or 'nightmare' in text) else 0.0

        # 11: text length (normalized)
        f[11] = min(len(text) / 100.0, 1.0)

        # 12: wake_keywords
        f[12] = 1.0 if ('醒' in text or '睡不着' in text) else 0.0

        # 13: time reference
        f[13] = 1.0 if ('昨晚' in text or '凌晨' in text or '半夜' in text or '昨天' in text) else 0.0

        # 14: fields count (normalized)
        field_count = sum(1 for v in (fields or {}).values() if v) if fields else 0
        f[14] = min(field_count / 10.0, 1.0)

        # 15: multiple issues
        separators = sum(1 for c in text if c in '，。；！？')
        f[15] = min(separators / 5.0, 1.0)

        return f

    def train_step(self, features, feedback):
        """单步训练：用用户反馈更新参数

        Args:
            features: 16维特征向量（训练时的输入）
            feedback: dict, {'should_retrieve': bool, 'category': str, 'top_k': int}
                      这是"正确的做法"——由当天的真实经验中提取

        Returns:
            float: loss值
        """
        # 前向
        decision = self.forward(features)

        # 计算loss（简单MSE）
        target_retrieve = 1.0 if feedback['should_retrieve'] else 0.0
        loss_retrieve = (decision['retrieve_prob'] - target_retrieve) ** 2

        target_cat = CATEGORIES.index(feedback['category']) if feedback['category'] in CATEGORIES else 0
        current_cat = CATEGORIES.index(decision['category']) if decision['category'] in CATEGORIES else 0
        loss_cat = (current_cat - target_cat) ** 2 / 36.0  # 归一化到0-1

        target_k = feedback.get('top_k', 2)
        loss_k = (decision['top_k'] - target_k) ** 2 / 4.0  # 归一化到0-1

        loss = loss_retrieve + 0.3 * loss_cat + 0.2 * loss_k

        # 简单的梯度下降：只更新bias
        # （完整梯度需要反向传播，这里做简化版）
        p = self.params
        lr = 0.01

        # 更新b2[0]（retrieve_prob的bias）
        grad_b2_0 = 2 * (decision['retrieve_prob'] - target_retrieve) * \
                    decision['retrieve_prob'] * (1 - decision['retrieve_prob'])
        p['b2'][0] -= lr * grad_b2_0

        # 更新b2[1]（category的bias）  
        grad_b2_1 = 2 * (list(decision['category_probs'].values())[target_cat] - 0.5)
        p['b2'][1] -= lr * 0.1 * grad_b2_1

        p['train_count'] = p.get('train_count', 0) + 1
        self._save(p)

        return round(loss, 4)

    def daily_train(self, days=1, learning_rate=0.01):
        """每日训练：用最近N天的经验数据更新路由网络

        Args:
            days: 使用最近多少天的数据
            learning_rate: 学习率

        Returns:
            dict: 训练统计
        """
        # 从wm_trace读追踪数据 + 从wm_memory读经验数据
        trace_path = os.path.join(PROJECT_ROOT, 'data', 'wm_trace.jsonl')
        memory_path = os.path.join(PROJECT_ROOT, 'data', 'wm_memory.jsonl')

        if not os.path.exists(trace_path):
            return {'error': 'No trace data', 'trained': 0}

        cutoff = time.time() - days * 86400

        # 读追踪数据做训练样本
        samples = []
        memory_map = {}

        # 先从memory读评分
        if os.path.exists(memory_path):
            with open(memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get('ts', 0) >= cutoff:
                            memory_map[entry.get('message', '')[:200]] = entry
                    except Exception:
                        continue

        # 从trace读特征+反馈
        if os.path.exists(trace_path):
            with open(trace_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        trace = json.loads(line.strip())
                        if trace.get('ts', 0) < cutoff:
                            continue

                        message = trace.get('message', '')
                        layers = {l.get('layer', ''): l for l in trace.get('layers', [])}

                        # 特征
                        ne_fields = {}
                        ne = layers.get('neural_extractor', {})
                        if ne.get('fields_count', 0) > 0:
                            ne_fields = {'awake_times': 3} if ne.get('fields_count', 0) > 0 else {}
                        features = self._extract_features(ne_fields, message)

                        # 反馈：如果sync_deepseek_override有结果 → 应该检索
                        sync = layers.get('sync_deepseek_override', {})
                        deepseek_wm = layers.get('deepseek_wm', {})

                        should_retrieve = deepseek_wm.get('has_result', False) or sync.get('result_len', 0) > 0

                        # 自动推断类别
                        category = self._infer_category(ne_fields, message)

                        feedback = {
                            'should_retrieve': should_retrieve,
                            'category': category,
                            'top_k': 2 if should_retrieve else 0,
                        }
                        samples.append((features, feedback))
                    except Exception:
                        continue

        if not samples:
            return {'error': 'No training samples', 'trained': 0}

        # 训练多个epoch
        total_loss = 0
        for epoch in range(min(10, len(samples) * 2)):
            for features, fb in samples:
                loss = self.train_step(features, fb)
                total_loss += loss

        avg_loss = total_loss / (len(samples) * min(10, len(samples) * 2))
        avg_loss = round(avg_loss, 4)

        self.params['last_train_date'] = datetime.now().strftime('%Y-%m-%d')
        self._save()

        # 记录训练日志
        log_entry = {
            'ts': time.time(),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'samples': len(samples),
            'avg_loss': avg_loss,
            'epochs': min(10, len(samples) * 2),
            'params_after': {
                'b2_retrieve': round(self.params['b2'][0], 3),
                'b2_category': round(self.params['b2'][1], 3),
                'b2_topk': round(self.params['b2'][2], 3),
            }
        }
        os.makedirs(os.path.dirname(TRAINING_LOG), exist_ok=True)
        with open(TRAINING_LOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')

        _ai_log.info('[Router] Trained on %d samples, avg_loss=%.4f, b2=(%.3f, %.3f, %.3f)',
                     len(samples), avg_loss,
                     self.params['b2'][0], self.params['b2'][1], self.params['b2'][2])

        return {
            'trained': len(samples),
            'avg_loss': avg_loss,
            'latest_bias': [round(b, 3) for b in self.params['b2']],
        }

    def _infer_category(self, fields, raw_text):
        """从字段+文本推断问题类型（给训练数据自动打标签用）"""
        text = (raw_text or '').lower()
        if isinstance(fields, dict):
            if fields.get('drink') == 'alcohol':
                return 'alcohol_related'
            cause = str(fields.get('awake_cause', '')).lower()
            if any(kw in cause for kw in ['消化', '肚', '胃']):
                return 'digestive_issue'
            if any(kw in cause for kw in ['焦虑', '压力']):
                return 'anxiety_stress'
            if fields.get('has_pain'):
                return 'pain_discomfort'
        if '酒' in text:
            return 'alcohol_related'
        if any(kw in text for kw in ['肚', '胃', '消化']):
            return 'digestive_issue'
        if any(kw in text for kw in ['焦虑', '压力', '紧张']):
            return 'anxiety_stress'
        if any(kw in text for kw in ['痛', '疼']):
            return 'pain_discomfort'
        return 'general_insomnia'

    def stats(self):
        """输出当前路由网络状态"""
        return {
            'version': self.params.get('version', 1),
            'train_count': self.params.get('train_count', 0),
            'last_train': self.params.get('last_train_date', 'never'),
            'bias_retrieve': round(self.params['b2'][0], 3),
            'bias_category': round(self.params['b2'][1], 3),
            'bias_topk': round(self.params['b2'][2], 3),
        }


# ===== 全局实例 =====
_router_instance = None


def get_router():
    """获取/创建路由全局实例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = WMRouter()
    return _router_instance


def predict_strategy(fields, raw_text):
    """快捷调用：获取检索策略"""
    router = get_router()
    return router.predict(fields, raw_text)


def daily_train_router(days=1):
    """每日训练入口（供wm_distill调用）"""
    router = get_router()
    return router.daily_train(days=days)


if __name__ == '__main__':
    print('wm_router.py v1.0')
    router = get_router()
    print(f'Params: {router.stats()}')

    # 测试
    fields = {'awake_times': 3, 'drink': 'alcohol', 'has_pain': True, 'awake_cause': '消化不适'}
    result = predict_strategy(fields, '昨晚喝红酒，肚子不舒服老醒')
    print(f'\nTest prediction:')
    print(f'  should_retrieve: {result["should_retrieve"]}')
    print(f'  category: {result["category_cn"]} ({result["category"]})')
    print(f'  top_k: {result["top_k"]}')
    print(f'  prob: {result.get("retrieve_prob", "?")}')
