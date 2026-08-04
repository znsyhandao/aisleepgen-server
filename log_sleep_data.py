# -*- coding: utf-8 -*-
"""
log_sleep_data.py — 记录每天的面部特征、预测分、真实分
突变动力学：失败不阻塞主流程，数据积累是自动的

记录格式 (sleep_data_log.json):
{
  "20260509": {
    "date": "20260509",
    "features": {"roi_grad_forehead_jaw": 35.38, ...},
    "predicted_score": 4.5,
    "real_score": null,  # 用户反馈后填充
    "feedback_at": null
  }
}
"""

import os, json, time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE, 'sleep-skin features', 'sleep_data_log.json')

def ensure_log():
    """确保日志文件存在"""
    if not os.path.exists(LOG_PATH):
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        return {}
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except:
        return {}


def save_log(data):
    """原子写入日志"""
    tmp = LOG_PATH + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LOG_PATH)  # 原子替换


def log_prediction(features, predicted_score):
    """
    记录一次预测。由 /api/sleep-from-face 在返回结果前调用。
    
    参数:
        features: dict, 8维特征值
        predicted_score: float, 模型预测评分
    返回: str date_str
    """
    try:
        today = datetime.now().strftime('%Y%m%d')
        data = ensure_log()
        
        if today not in data:
            data[today] = {
                'date': today,
                'features': {k: round(v, 4) for k, v in features.items()},
                'predicted_score': round(predicted_score, 2),
                'real_score': None,
                'feedback_at': None,
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
        else:
            # 保留已有 real_score，更新 features（同一日可多次拍照，取最后一次）
            existing_real = data[today].get('real_score')
            data[today].update({
                'features': {k: round(v, 4) for k, v in features.items()},
                'predicted_score': round(predicted_score, 2),
                'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            })
            if existing_real is not None:
                data[today]['real_score'] = existing_real
        
        save_log(data)
        return today
    except Exception as e:
        # 日志记录失败不阻塞主流程
        return None


def submit_feedback(date_str, real_score):
    """
    用户提交真实评分后调用。
    
    参数:
        date_str: str, 'YYYYMMDD'
        real_score: float, 1-10
    """
    try:
        data = ensure_log()
        if date_str not in data:
            return {'error': '日期无预测记录'}
        data[date_str]['real_score'] = round(float(real_score), 1)
        data[date_str]['feedback_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_log(data)
        return {'ok': True, 'date': date_str}
    except Exception as e:
        return {'error': str(e)}


def get_stats():
    """获取数据统计"""
    data = ensure_log()
    total = len(data)
    with_feedback = sum(1 for v in data.values() if v.get('real_score') is not None)
    return {
        'total_days': total,
        'with_feedback': with_feedback,
        'days': sorted(data.keys()),
    }


# 与 face_analyzer.py FEATS 保持一致的8维核心特征名
CORE_FEATURE_NAMES = [
    'roi_grad_forehead_jaw', 'roi_forehead_jaw_ratio',
    'hsv_H_std', 'freq_high_low_ratio',
    'hsv_S_mean', 'roi_forehead_L',
    'gabor_mean_00', 'gabor_std_00',
]

def get_training_data():
    """
    获取可用于训练的数据（已标真实分的日期）。
    自动从32维特征中提取8维核心特征，兼容新旧格式。
    """
    data = ensure_log()
    X, y, dates = [], [], []
    for d in sorted(data.keys()):
        entry = data[d]
        if entry.get('real_score') is not None and entry.get('features'):
            feats = entry['features']
            # 如果是32维宽特征，只提取8维核心
            if len(feats) > 20:
                core = []
                for name in CORE_FEATURE_NAMES:
                    core.append(feats.get(name, 0.0))
                X.append(core)
            else:
                X.append(list(feats.values()))
            y.append(entry['real_score'])
            dates.append(d)
    return X, y, dates


if __name__ == '__main__':
    print('=== sleep_data_log 测试 ===')
    
    # 模拟一次预测记录
    test_feats = {'roi_grad_forehead_jaw': 35.38, 'roi_forehead_jaw_ratio': 1.55,
                  'hsv_H_std': 24.19, 'freq_high_low_ratio': 0.73,
                  'hsv_S_mean': 98.86, 'roi_forehead_L': 99.89,
                  'gabor_mean_00': 1.07, 'gabor_std_00': 16.4}
    
    d = log_prediction(test_feats, 4.5)
    print(f'记录预测: date={d}')
    
    # 提交真实评分
    r = submit_feedback('20260509', 4.0)
    print(f'提交反馈: {r}')
    
    # 统计
    print(f'统计: {get_stats()}')
    
    # 训练数据
    X, y, dates = get_training_data()
    print(f'训练数据: {len(X)} 条')
    if X:
        print(f'  日期: {dates}')
        print(f'  评分: {y}')
