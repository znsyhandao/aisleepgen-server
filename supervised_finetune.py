#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
supervised_finetune.py — InstructGPT监督微调 (v7.5+)
原理: OpenAI InstructGPT — 用监督学习从反馈数据中学习"用户偏好"
落地: 从feedback.json学习评分预测，自动调整回复策略

用法:
  from supervised_finetune import update_model, predict_satisfaction, finetune_summary
  update_model(openid, features, rating)
  pred = predict_satisfaction(openid, features)
"""

import json, os, math

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
FT_DIR = os.path.join(PROJECT_ROOT, 'data', 'finetune')
os.makedirs(FT_DIR, exist_ok=True)


def _user_path(openid):
    safe = openid.replace('/', '_').replace('\\', '_')
    return os.path.join(FT_DIR, '%s.json' % safe)


def _load(openid):
    path = _user_path(openid)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'theta': None, 'samples': 0, 'history': []}


def _save(openid, data):
    with open(_user_path(openid), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _extract_features(stack):
    """从评分堆栈（如RLAIF/DMO的调整量序列）提取特征向量

    特征:
    0: 最近一次调整量
    1: 平均调整量
    2: 调整量方差
    3: 调整次数
    4: 正调整/总调整比例
    """
    if not stack or not isinstance(stack, (list, dict)):
        return None

    if isinstance(stack, dict):
        values = [v for v in stack.values() if isinstance(v, (int, float))]
    else:
        values = [v for v in stack if isinstance(v, (int, float))]

    if len(values) < 1:
        return None

    n = len(values)
    mu = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n if n > 1 else 0

    return [
        values[-1],                             # 最近调整
        mu,                                     # 平均调整
        math.sqrt(max(0, var)),                 # 标准差
        n,                                      # 次数
        sum(1 for v in values if v > 0) / n,   # 正向比例
    ]


def _predict(theta, features):
    """线性模型: theta[0] + sum(theta[i]*features[i]) → sigmoid → 0-1"""
    if theta is None or not features:
        return 0.5
    z = theta[0]
    for i in range(min(len(theta) - 1, len(features))):
        z += theta[i + 1] * features[i]
    # sigmoid
    if z > 10:
        return 1.0
    if z < -10:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _logistic_loss(theta, features, target):
    """逻辑回归的负对数似然"""
    pred = _predict(theta, features)
    eps = 1e-10
    return -(target * math.log(max(eps, pred)) + (1 - target) * math.log(max(eps, 1 - pred)))


def _train_sgd(theta, features, target, lr=0.1):
    """SGD一步训练"""
    if not features:
        return theta

    pred = _predict(theta, features)
    error = pred - target

    new_theta = list(theta)
    # bias
    new_theta[0] -= lr * error * 2
    # weights
    for i in range(min(len(features), len(theta) - 1)):
        new_theta[i + 1] -= lr * error * features[i]

    return new_theta


def update_model(openid, features, rating):
    """从一次反馈更新监督模型

    Args:
        openid: str
        features: list[float] — 特征向量
        rating: int/float — 1-5用户评分
    """
    if not openid or not features:
        return

    data = _load(openid)
    theta = data.get('theta')
    if not theta or len(theta) < len(features) + 1:
        theta = [0.0] * (len(features) + 1)

    # 归一化rating到0-1
    target = max(0.0, min(1.0, (rating - 1) / 4.0))

    theta = _train_sgd(theta, features, target)

    data['theta'] = [round(t, 4) for t in theta]
    data['samples'] += 1
    data['history'].append({'features': features, 'rating': rating, 'target': round(target, 2)})

    # 保留最近100条
    if len(data['history']) > 100:
        data['history'] = data['history'][-100:]

    _save(openid, data)


def predict_satisfaction(openid, features):
    """预测用户对当前策略的满意度

    Returns: float 0-1
    """
    if not openid or not features:
        return 0.5
    data = _load(openid)
    theta = data.get('theta')
    if not theta or len(theta) < len(features) + 1:
        theta = [0.0] * (len(features) + 1)
    return round(_predict(theta, features), 3)


def finetune_summary(openid):
    """模型摘要"""
    data = _load(openid)
    return {
        'samples': data['samples'],
        'theta': [round(t, 3) for t in data.get('theta', [])],
        'theta_nonzero': sum(1 for t in data.get('theta', []) if abs(t) > 0.01),
    }


# ===== 自测 =====
if __name__ == '__main__':
    print('=== Supervised Finetune Test ===\n')

    # 训练：从一堆负反馈学习
    features = [0.1, 0.2, 0.05, 1, 1.0]
    for _ in range(5):
        update_model('test_sft', features, 2)  # 低评分
    for _ in range(5):
        update_model('test_sft', features, 4)  # 变高评分

    pred = predict_satisfaction('test_sft', features)
    print('Test 1 (trained): pred=%.3f' % pred)
    # 应该>0.5因为有高评分训练了5次

    # 新用户
    pred2 = predict_satisfaction('test_sft2', features)
    print('Test 2 (new user): pred=%.3f' % pred2)
    assert pred2 == 0.5

    sm = finetune_summary('test_sft')
    print('Test 3 (summary): samples=%d, theta=%s' % (sm['samples'], sm['theta']))
    assert sm['samples'] == 10

    # 清理
    import os as _os
    for _f in ['test_sft.json', 'test_sft2.json']:
        _p = _os.path.join(FT_DIR, _f)
        if _os.path.exists(_p):
            _os.remove(_p)

    print('\nAll tests passed!')
