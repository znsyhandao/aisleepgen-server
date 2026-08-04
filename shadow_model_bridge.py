# -*- coding: utf-8 -*-
"""
shadow_model_bridge.py — LightGBM shadow model 接入
突变动力学设计：不改变现有预测流程，后台运行68维模型记录结果

流程：
  1. 当 face_analyzer 做预测时，shadow 模式同时跑
  2. shadow 结果记录到 shadow_predictions.json
  3. 不改变现有API输出，API消费者无感知
  4. 收集足够对比数据后，人工决定是否切换

突变动力学：失败不阻塞主预测流程，所有异常静默捕获
"""
import os, sys, json, pickle, time
import numpy as np
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
FEATURES_CSV = os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')
MODEL_PATH = os.path.join(BASE, 'sleep-skin features', 'lgb_eff_v1.pkl')
RESULT_PATH = os.path.join(BASE, 'sleep-skin features', 'lgb_result_v1.json')
SHADOW_LOG = os.path.join(BASE, 'sleep-skin features', 'shadow_predictions.json')

# 模型懒加载
_model = None
_feature_cols = None

def _lazy_load():
    global _model, _feature_cols
    if _model is not None:
        return True
    
    if not os.path.exists(MODEL_PATH) or not os.path.exists(RESULT_PATH):
        return False
    
    try:
        with open(RESULT_PATH, encoding='utf-8') as f:
            meta = json.load(f)
        _feature_cols = meta.get('feature_cols', [])
        
        with open(MODEL_PATH, 'rb') as f:
            _model = pickle.load(f)
        return True
    except Exception:
        return False


def shadow_predict(features_8d_dict, image_date=None):
    """
    Shadow 模式预测。由 face_analyzer 预测后调用。
    
    参数:
        features_8d_dict: dict, face_analyzer 的8维特征
        image_date: str, 照片日期 YYYYMMDD，用于日志
    
    返回: dict {lgb_pred, lgb_eff_pct, lgb_conf, note}
        lgb_pred: None 表示 shadow 不可用（模型未加载或日特征缺失）
        lgb_eff_pct: float 预测睡眠效率百分比
        lgb_conf: str 置信度
        note: str 说明
    """
    if not _lazy_load():
        return {'lgb_pred': None, 'note': '模型未就绪'}
    
    try:
        # 从8维特征到68维需要当日CSV数据
        # 最佳实践：用当天的面部照片聚合特征
        if image_date and os.path.exists(FEATURES_CSV):
            df = pd.read_csv(FEATURES_CSV)
            day_data = df[df['date'].astype(str) == str(image_date)]
            day_data = day_data[day_data['face_detected'] == True]
            
            if len(day_data) > 0:
                # 构建68维特征向量
                X = []
                for c in _feature_cols:
                    if c.startswith('face_') and c.endswith('_mean'):
                        raw_name = c.replace('face_', '').replace('_mean', '')
                        vals = day_data[raw_name].dropna()
                        X.append(float(vals.mean()) if len(vals) > 0 else 0.0)
                    elif c.startswith('face_') and c.endswith('_std'):
                        raw_name = c.replace('face_', '').replace('_std', '')
                        vals = day_data[raw_name].dropna()
                        X.append(float(vals.std()) if len(vals) > 1 else 0.0)
                    else:
                        X.append(0.0)
                
                X_arr = np.array([X], dtype=float)
                X_arr = np.nan_to_num(X_arr, nan=0.0)
                
                raw_pred = float(_model.predict(X_arr)[0])
                eff_pct = round(raw_pred * 100, 1)
                
                # 置信度评估：基于当日照片数
                n_photos = len(day_data)
                if n_photos >= 5:
                    conf = 'high'
                elif n_photos >= 2:
                    conf = 'medium'
                else:
                    conf = 'low'
                
                result = {
                    'lgb_pred': round(raw_pred, 4),
                    'lgb_eff_pct': eff_pct,
                    'lgb_conf': conf,
                    'n_photos': n_photos,
                    'note': f'{n_photos}张照片聚合预测',
                    'effective': True,
                }
                
                # 记录到影子日志
                _log_shadow(image_date, result, features_8d_dict)
                return result
        
        return {'lgb_pred': None, 'note': '当日无面部数据'}
    
    except Exception as e:
        return {'lgb_pred': None, 'note': f'shadow异常: {str(e)[:60]}'}


def _log_shadow(date_str, result, original_features):
    """记录影子预测到日志文件"""
    try:
        if os.path.exists(SHADOW_LOG):
            with open(SHADOW_LOG, encoding='utf-8') as f:
                log = json.load(f)
        else:
            log = {'predictions': []}
        
        log['predictions'].append({
            'date': date_str,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'lgb_eff_pct': result.get('lgb_eff_pct'),
            'lgb_conf': result.get('lgb_conf'),
            'n_photos': result.get('n_photos'),
            'original_8d_features': {k: round(v, 2) for k, v in original_features.items()},
        })
        
        # 最多保留200条
        if len(log['predictions']) > 200:
            log['predictions'] = log['predictions'][-200:]
        
        # 统计摘要
        effective = [p for p in log['predictions'] if p.get('lgb_eff_pct')]
        log['summary'] = {
            'total_predictions': len(log['predictions']),
            'shadow_available': len(effective),
            'shadow_unavailable': len(log['predictions']) - len(effective),
        }
        if effective:
            vals = [p['lgb_eff_pct'] for p in effective]
            log['summary']['shadow_eff_range'] = f"{min(vals):.1f}~{max(vals):.1f}%"
            log['summary']['shadow_eff_mean'] = round(sum(vals)/len(vals), 1)
        
        with open(SHADOW_LOG, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_shadow_stats():
    """获取影子预测统计数据"""
    if not os.path.exists(SHADOW_LOG):
        return {'status': '无影子预测数据'}
    try:
        with open(SHADOW_LOG, encoding='utf-8') as f:
            return json.load(f)
    except:
        return {'status': '读取失败'}


# ===== 单次测试 =====
if __name__ == '__main__':
    print("=" * 60)
    print("Shadow Model Bridge 测试")
    print("=" * 60)
    
    # 模拟face_analyzer输出
    test_feats = {
        'roi_grad_forehead_jaw': 3.78,
        'roi_forehead_jaw_ratio': 3.78,
        'hsv_H_std': 24.19,
        'freq_high_low_ratio': 0.73,
        'hsv_S_mean': 98.86,
        'roi_forehead_L': 99.89,
        'gabor_mean_00': 1.07,
        'gabor_std_00': 16.4,
    }
    
    result = shadow_predict(test_feats, '20260520')
    print(f"\nShadow 预测: {json.dumps(result, indent=2, ensure_ascii=False)}")
    
    stats = get_shadow_stats()
    print(f"\n影子日志统计:")
    s = stats.get('summary', {})
    for k, v in s.items():
        print(f"  {k}: {v}")
    
    print(f"\n✅ Shadow bridge 测试完成")
