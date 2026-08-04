# -*- coding: utf-8 -*-
"""face_analyzer v5 — Ensemble + 因果链 + 睡眠数据桥

v5 新增（范式3移植：因果链+多假设）：
  - SkinSleepBridge: 皮肤-睡眠数据桥
  - SkinCausalChain: 护肤因果链
  - SkinCausalEngine: 因果诊断引擎
  - 在 analyze() 返回中嵌入 causal_insights

数据源：
  - sleep_all_days.json (睡眠评分 + 手环数据)
  - band_sleep_data.json / band_sleep_data_verified.json (华为手环11pro)
  - band_sleep_data_v2.json (二期手环数据，格式可扩展)

移植自 sleep_diagnosis.py 的 CausalDiagnosisEngine，
独立重实现，不 import 任何睡眠分析代码。
"""
import os, sys, json, base64, time
from datetime import datetime, timedelta
from typing import List, Optional
import warnings
warnings.filterwarnings('ignore')
import cv2, numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
FEATS = ['roi_grad_forehead_jaw','roi_forehead_jaw_ratio','hsv_H_std',
         'freq_high_low_ratio','hsv_S_mean','roi_forehead_L',
         'gabor_mean_00','gabor_std_00']

# ===== 集成模型 =====
_ENSEMBLE = None
def _load_ensemble():
    global _ENSEMBLE
    if _ENSEMBLE: return _ENSEMBLE
    p = os.path.join(BASE, 'sleep-skin features', 'ensemble_model_v1.json')
    try:
        with open(p, 'r') as f: _ENSEMBLE = json.load(f)
    except Exception as e:
        print(f'[face] load ensemble error: {e}')
        _ENSEMBLE = None
    return _ENSEMBLE

# =============== PBT: Skin-Sleep Bridge + Causal Chain (v5) ===============

class SkinSleepBridge:
    """加载睡眠数据并匹配日期"""
    def __init__(self):
        self._cache = {}
        self._db_path = r'F:\sleep-skin image database'
        self._folder_notes = {}
        for fn in ['sleep_all_days.json','band_sleep_data.json',
                   'band_sleep_data_v2.json','band_sleep_data_verified.json',
                   'sleep_huawei_data.json']:
            fp = os.path.join(self._db_path, fn)
            if os.path.exists(fp):
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        self._cache[fn] = json.load(f)
                except:
                    pass
        self._scan_folder_notes()

    def _scan_folder_notes(self):
        for d in sorted(os.listdir(self._db_path)):
            day_dir = os.path.join(self._db_path, d)
            if not os.path.isdir(day_dir) or not d.isdigit() or len(d) != 8:
                continue
            for fn in os.listdir(day_dir):
                if 'sleep_quality_of' not in fn and '睡眠质量' not in fn:
                    continue
                fp = os.path.join(day_dir, fn)
                text = ''
                try:
                    with open(fp, 'r', encoding='utf-8-sig') as fh:
                        text = fh.read().strip()
                except:
                    try:
                        with open(fp, 'r', encoding='gbk') as fh:
                            text = fh.read().strip()
                    except:
                        pass
                if text:
                    self._folder_notes[d] = text

    def get_sleep_score(self, day: str):
        """先查JSON，再查文件夹笔记中的'X分'或'打分X'模式"""
        for fn in ['sleep_all_days.json','band_sleep_data.json',
                   'band_sleep_data_v2.json','band_sleep_data_verified.json']:
            data = self._cache.get(fn, {})
            entry = data.get(day, {})
            if not isinstance(entry, dict):
                continue
            score = entry.get('sleep_score')
            if score is not None:
                try:
                    return float(score) / 10.0 if score > 10 else float(score)
                except:
                    pass
        # 回退到文件夹笔记
        note = self._folder_notes.get(day, '')
        if note:
            import re
            # 阿拉伯数字模式
            for pat in [r'(\d+\.?\d*)\s*分', r'打分(\d+)']:
                m = re.search(pat, note)
                if m:
                    try:
                        v = float(m.group(1))
                        return v / 10.0 if v > 10 else v
                    except:
                        pass
            # 中文数字模式: 零一二三四五六七八九十
            cn_map = {'零':0,'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
            cn_m = re.search(r'[零一二三四五六七八九十]+分', note)
            if cn_m:
                cn_str = cn_m.group(0).replace('分','')
                if cn_str in cn_map:
                    v = cn_map[cn_str]
                    return v / 10.0 if v > 10 else v
        return None

    def get_deep_sleep_min(self, day: str):
        data = self._cache.get('sleep_all_days.json', {})
        entry = data.get(day, {})
        if isinstance(entry, dict):
            v = entry.get('deep_min')
            if v is not None:
                return float(v)
        return None

    def get_subjective_note(self, day: str) -> str:
        data = self._cache.get('sleep_all_days.json', {})
        entry = data.get(day, {})
        if isinstance(entry, dict):
            note = entry.get('subjective_note', '')
            if note:
                return note
        note = self._folder_notes.get(day, '')
        if note:
            return note[:80]
        return ''



    def get_bed_and_wake(self, day: str) -> dict:
        data = self._cache.get('sleep_all_days.json', {})
        entry = data.get(day, {})
        if isinstance(entry, dict):
            return {'bed': entry.get('bed_time',''), 'wake': entry.get('wake_time','')}
        return {}

    def get_band_percentages(self, day: str) -> list:
        for fn in ['band_sleep_data_verified.json','band_sleep_data.json']:
            data = self._cache.get(fn, {})
            entry = data.get(day, {})
            if isinstance(entry, dict):
                pcts = entry.get('percentages', [])
                if pcts:
                    return pcts
        return []

    def history(self, center_day: str, window: int = 7) -> dict:
        try:
            from datetime import datetime, timedelta
            cd = datetime.strptime(center_day, '%Y%m%d')
        except:
            cd = datetime.now()
        result = {'scores': [], 'deep_min': [], 'days': []}
        for offset in range(-window + 1, 1):
            d = (cd + timedelta(days=offset)).strftime('%Y%m%d')
            s = self.get_sleep_score(d)
            dp = self.get_deep_sleep_min(d)
            result['scores'].append(s)
            result['deep_min'].append(dp)
            result['days'].append(d)
        return result


class SkinCausalChain:
    """护肤因果链"""
    def __init__(self, chain_id, root_cause, primary_dimension,
                 confidence=0.5, alternative_hypotheses=None):
        self.chain_id = chain_id
        self.root_cause = root_cause
        self.primary_dimension = primary_dimension
        self.links = []
        self.confidence = confidence
        self.alternative_hypotheses = alternative_hypotheses or []
        self.created_at = datetime.now().strftime('%Y%m%d_%H%M%S')

    def to_dict(self) -> dict:
        return {
            'chain_id': self.chain_id,
            'root_cause': self.root_cause,
            'primary_dimension': self.primary_dimension,
            'links': self.links,
            'confidence': round(self.confidence, 3),
            'alternative_hypotheses': self.alternative_hypotheses,
            'created_at': self.created_at,
        }


class SkinCausalEngine:
    """护肤因果诊断引擎"""
    def __init__(self):
        self.bridge = SkinSleepBridge()

    def analyze_trend(self, day, current_score, features):
        """分析趋势和根因"""
        hist = self.bridge.history(day, 7)
        scores = [s for s in hist['scores'] if s is not None]
        deeps = [d for d in hist['deep_min'] if d is not None]
        note = self.bridge.get_subjective_note(day)
        bands = self.bridge.get_band_percentages(day)

        chains = []

        # Chain 1: score decline detection
        if len(scores) >= 3:
            recent_3 = sum(scores[-3:]) / 3
            earlier_3 = sum(scores[:3]) / 3
            if earlier_3 > 0 and recent_3 < earlier_3 * 0.85:
                decline_pct = round((earlier_3 - recent_3) / earlier_3 * 100, 1)
                chain = SkinCausalChain(
                    chain_id='decline_' + day,
                    root_cause='score_drop_' + str(decline_pct) + 'pct',
                    primary_dimension='trend',
                    confidence=min(0.9, 0.5 + len(scores) * 0.02))
                chain.links = [
                    {'event': 'earlier_avg=' + str(round(earlier_3,1)),
                     'dimension': 'trend', 'time': 'recent',
                     'source': 'history', 'confidence': 0.7},
                    {'event': 'recent_avg=' + str(round(recent_3,1)),
                     'dimension': 'trend', 'time': 'now',
                     'source': 'history', 'confidence': 0.7},
                ]
                if deeps and len(deeps) >= 2:
                    late_deep = sum(deeps[-2:]) / 2
                    avg_deep = sum(deeps) / len(deeps)
                    if late_deep < avg_deep * 0.8:
                        chain.links.append({
                            'event': 'deep_sleep_' + str(int(late_deep)) + 'min',
                            'dimension': 'sleep',
                            'time': 'recent', 'source': 'sleep_bridge',
                            'confidence': 0.6})
                if note:
                    chain.links.append({
                        'event': note[:50], 'dimension': 'subjective',
                        'time': 'self', 'source': 'note', 'confidence': 0.4})
                if current_score < 6.0:
                    alt = {
                        'hypothesis': 'score might be from sun exposure or skin irritation, not solely sleep',
                        'confidence': 0.5,
                        'evidence': ['score=' + str(current_score)]
                    }
                    chain.alternative_hypotheses.append(alt)
                chains.append(chain.to_dict())

        # Chain 2: deep sleep deficiency
        if deeps and len(deeps) >= 2:
            last_deep = deeps[-1]
            if last_deep < 90:
                avg_deep = sum(deeps) / len(deeps)
                chain2 = SkinCausalChain(
                    chain_id='dsleep_' + day,
                    root_cause='deep_sleep_below_90min_may_affect_skin',
                    primary_dimension='sleep_deep',
                    confidence=0.6)
                chain2.links = [
                    {'event': 'last_deep=' + str(int(last_deep)) + 'min',
                     'dimension': 'deep_min', 'time': 'last_night',
                     'source': 'sleep_bridge', 'confidence': 0.7},
                    {'event': 'avg_deep=' + str(int(avg_deep)) + 'min',
                     'dimension': 'deep_min_avg', 'time': 'history',
                     'source': 'sleep_bridge', 'confidence': 0.6},
                ]
                if current_score <= 6.5:
                    chain2.links.append({
                        'event': 'skin_score=' + str(current_score),
                        'dimension': 'score', 'time': 'now',
                        'source': 'analysis', 'confidence': 0.5})
                chains.append(chain2.to_dict())

        # Chain 3: band anomaly
        if bands:
            bad = [p for p in bands if p is not None and p < 50]
            if bad:
                chain3 = SkinCausalChain(
                    chain_id='band_' + day,
                    root_cause='band_detected_abnormal_sleep_segments',
                    primary_dimension='band_anomaly',
                    confidence=0.55)
                chain3.links = [
                    {'event': 'bad_segments=' + str(len(bad)),
                     'dimension': 'band', 'time': 'last_night',
                     'source': 'huawei_band', 'confidence': 0.5}]
                chains.append(chain3.to_dict())

        if chains:
            confs = [c['confidence'] for c in chains]
            overall_conf = sum(confs) / len(confs) * 0.7 + 0.15
        else:
            overall_conf = 0.0

        return {
            'chains': chains,
            'n_chains': len(chains),
            'overall_confidence': round(overall_conf, 3),
            'bridge': {
                'sleep_scores': [s for s in scores[-5:]],
                'deep_minutes': [d for d in deeps[-5:]],
                'has_note': bool(note),
                'has_band': bool(bands),
            }
        }


_SKIN_BRIDGE = None
_SKIN_ENGINE = None

def _skin_bridge():
    global _SKIN_BRIDGE
    if _SKIN_BRIDGE is None:
        _SKIN_BRIDGE = SkinSleepBridge()
    return _SKIN_BRIDGE

def _skin_engine():
    global _SKIN_ENGINE
    if _SKIN_ENGINE is None:
        _SKIN_ENGINE = SkinCausalEngine()
    return _SKIN_ENGINE



def _predict(feats_dict):
    """Ensemble: Ridge + Lasso + PCA+LR 加权平均"""
    m = _load_ensemble()
    if not m or 'features' not in m: return None
    fs = m['features']
    scaler_mean = m.get('scaler_mean', m.get('scale_mean', [0]*len(fs)))
    scaler_scale = m.get('scaler_scale', m.get('scale_std', [1]*len(fs)))
    xs = []
    for i, f in enumerate(fs):
        v = feats_dict.get(f, 0.0)
        me = scaler_mean[i] if i < len(scaler_mean) else 0
        sc = scaler_scale[i] if i < len(scaler_scale) else 1
        xs.append((v - me) / sc)
    x = np.array(xs)
    ridge_int = m.get('ridge_intercept', 0)
    if isinstance(ridge_int, list): ridge_int = ridge_int[0] if ridge_int else 0
    ridge_coefs = m.get('ridge_coefs', [])
    lasso_int = m.get('lasso_intercept', 0)
    if isinstance(lasso_int, list): lasso_int = lasso_int[0] if lasso_int else 0
    lasso_coefs = m.get('lasso_coefs', [])
    ridge = ridge_int + sum(x[i]*ridge_coefs[i] for i in range(len(fs)) if i < len(ridge_coefs))
    lasso = lasso_int + sum(x[i]*lasso_coefs[i] for i in range(len(fs)) if i < len(lasso_coefs))
    # PCA model — if pca_components exists, include it
    if 'pca_components' in m:
        pc = np.array(m['pca_components']); pm = np.array(m['pca_mean'])
        xp = (x - pm).dot(pc.T)
        lr_int = m.get('lr_intercept', 0)
        if isinstance(lr_int, list): lr_int = lr_int[0] if lr_int else 0
        lr_coefs = m.get('lr_coefs', [])
        pca_val = lr_int + sum(xp[i]*lr_coefs[i] for i in range(len(lr_coefs)) if i < len(lr_coefs))
        raw = np.array([ridge, lasso, pca_val])
    else:
        raw = np.array([ridge, lasso])
    # 修剪：去掉超过 2 个标准差的 outlier，只取收敛的
    clip_low, clip_high = 1.0, 10.0
    raw = np.clip(raw, clip_low, clip_high)
    median_val = float(np.median(raw))
    mad = float(np.median(np.abs(raw - median_val)))  # 中位数绝对偏差
    if mad < 0.5: mad = 0.5
    valid = raw[np.abs(raw - median_val) <= 2.0 * mad]  # 去 outlier
    if len(valid) == 0: valid = raw
    score = float(np.mean(valid))
    return round(max(1, min(10, score)), 1)

# ===== 白平衡 =====
_WB = None
def _get_wb():
    global _WB
    if _WB: return _WB
    # 优先从白纸参考照加载（有的话更准）
    wd = os.path.join(BASE, 'sleep-skin image database')
    try:
        for d in sorted(os.listdir(wd)):
            dd = os.path.join(wd, d)
            if not os.path.isdir(dd): continue
            for fn in sorted(os.listdir(dd)):
                if 'whitebalance' not in fn.lower(): continue
                if not fn.lower().endswith(('.jpg','.jpeg','.png')): continue
                i = cv2.imread(os.path.join(dd,fn))
                if i is None: continue
                h,w = i.shape[:2]
                c = i[h//2-h//8:h//2+h//8,w//2-w//8:w//2+w//8].astype(float)
                b,g,r = cv2.mean(c)[:3]
                if g > 0:
                    _WB = {'r_scale': 1.0/(r/g), 'b_scale': 1.0/(b/g), 'source': 'ref'}
                    print(f'[face] wb ref loaded from {d}/{fn}: r={_WB["r_scale"]:.3f} b={_WB["b_scale"]:.3f}')
                    break
            if _WB: break
    except:
        pass

    # 没有白纸参考照时使用灰度世界自动白平衡
    if not _WB:
        _WB = {'source': 'grayworld'}
        print('[face] wb using gray-world auto (no ref card)')
    return _WB

def _wb(img):
    """白平衡：有参考照时用参考值，没有则计算当前帧的灰度世界"""
    try:
        w = _get_wb()
        f = img.astype(float)

        if w.get('source') == 'grayworld':
            # 灰度世界假设：R/G/B 三个通道的平均值应相等
            avg_r = np.mean(f[:,:,2])
            avg_g = np.mean(f[:,:,1])
            avg_b = np.mean(f[:,:,0])
            if avg_g > 0:
                f[:,:,2] *= avg_g / avg_r
                f[:,:,0] *= avg_g / avg_b
        else:
            # 有白纸参考照：使用固定的通道缩放
            f[:,:,2] *= w['r_scale']
            f[:,:,0] *= w['b_scale']

        return np.clip(f, 0, 255).astype(np.uint8)
    except Exception as e:
        print(f'[face] wb error: {e}')
        return img

# ===== 人脸检测 =====
def _detect(img):
    try:
        hsv = cv2.cvtColor(img,cv2.COLOR_BGR2HSV)
        yc = cv2.cvtColor(img,cv2.COLOR_BGR2YCrCb)
        m = cv2.bitwise_and(cv2.inRange(hsv,(0,20,60),(30,150,255)),cv2.inRange(yc,(0,133,77),(255,173,127)))
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(7,7))
        m = cv2.morphologyEx(cv2.morphologyEx(m,cv2.MORPH_CLOSE,k),cv2.MORPH_OPEN,k)
        cs,_ = cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        if not cs: return None,None,None
        mc = max(cs,key=cv2.contourArea)
        x,y,w,h = cv2.boundingRect(mc)
        if w/h > 2 or w/h < 0.3: return None,None,None
        return img[y:y+h//3*2,x:x+w], img[y:y+h,x:x+w], (int(x),int(y),int(w),int(h))
    except Exception as e:
        print(f'[face] detect error: {e}')
        return None,None,None

# ===== 特征提取 =====
def _extract(roi, full):
    if full is None or full.size == 0: return {}
    h,w = full.shape[:2]
    gray = cv2.cvtColor(full,cv2.COLOR_BGR2GRAY)
    lab = cv2.cvtColor(full,cv2.COLOR_BGR2LAB)
    L = lab[:,:,0].astype(float)
    Lf = L[:h//3,w//4:3*w//4]; Lj = L[2*h//3:,w//4:3*w//4]
    def sm(a): return float(np.mean(a)) if a.size > 0 else 0.0
    fl = sm(Lf); jl = sm(Lj)
    hsv = cv2.cvtColor(full,cv2.COLOR_BGR2HSV)
    H = hsv[:,:,0].astype(float); S = hsv[:,:,1].astype(float)
    rg = cv2.resize(gray,(256,256))
    fs = np.fft.fftshift(np.fft.fft2(rg))
    mp = np.abs(fs)
    fhl = float(mp[128-64:128+64,128-64:128+64].sum() / (mp.sum()+1e-6))
    gm,gs = 0.0,0.0
    try:
        from skimage.filters import gabor
        gr,_ = gabor(rg,0.1,0)
        gm = float(np.mean(np.abs(gr))); gs = float(np.std(np.abs(gr)))
    except Exception as e:
        print(f'[face] gabor error: {e}')
    pass
    return {'roi_grad_forehead_jaw': fl-jl, 'roi_forehead_jaw_ratio': fl/(jl+1e-6),
            'hsv_H_std': float(np.std(H)) if H.size>0 else 0, 'freq_high_low_ratio': fhl,
            'hsv_S_mean': sm(S), 'roi_forehead_L': fl,
            'gabor_mean_00': gm, 'gabor_std_00': gs}

# ===== 主入口 =====
def analyze(image_data):
    t0 = time.time()
    try:
        if isinstance(image_data,str):
            if image_data.startswith('data:'): image_data = image_data.split(',',1)[1]
            ib = base64.b64decode(image_data)
        elif isinstance(image_data,bytes): ib = image_data
        else: return {'error':'不支持的图片格式','face_detected':False}
        npb = np.frombuffer(ib,np.uint8)
        img = cv2.imdecode(npb,cv2.IMREAD_COLOR)
        if img is None: return {'error':'图片解码失败','face_detected':False}
        img = _wb(img)
        roi,full,bbox = _detect(img)
        if roi is None: return {'error':'未检测到人脸','face_detected':False}
        feats = _extract(roi,full)
        score = _predict(feats)
        if score is None: score = 5.0
        top = {k: feats.get(k,0) for k in FEATS}
        el = round((time.time()-t0)*1000)
        
        # ── Shadow model: LightGBM 后台预测（不改变API输出）──
        _shadow_result = None
        try:
            from shadow_model_bridge import shadow_predict
            _shadow_result = shadow_predict(top, time.strftime('%Y%m%d'))
        except Exception:
            pass
        
        # 因果链
        causal = {}
        try:
            day_str = time.strftime('%Y%m%d')
            engine = _skin_engine()
            causal = engine.analyze_trend(day_str, score, top)
        except Exception as ce:
            causal = {'error': str(ce)}
        
        return {'predicted_score':score,'face_detected':True,
                'bbox':dict(zip(['x','y','w','h'],bbox)) if bbox else None,
                'features':{k:round(v,2) for k,v in top.items()},
                'insights':[{'aspect':'overall','level':'fair','text':'预测评分 ' + str(score) + '，面部可见疲劳迹象'}],
                'elapsed_ms':el,'model':'ensemble_v5',
                '_shadow_lgb': _shadow_result.get('lgb_eff_pct') if _shadow_result else None,
                '_shadow_conf': _shadow_result.get('lgb_conf') if _shadow_result else None,
                'causal_insights': causal,
                }
    except Exception as e:
        return {'error':str(e),'face_detected':False,'elapsed_ms':int((time.time()-t0)*1000)}

def analyze_from_path(img_path):
    with open(img_path,'rb') as f: return analyze(f.read())

# ===== 训练（仅运行时触发） =====
if __name__ == '__main__':
    import pandas as pd
    CSV = os.path.join(BASE, 'sleep-skin features', 'facial_features_v9.csv')
    SCORES = {'20260418':3,'20260419':8,'20260420':8,'20260421':6,'20260422':5,'20260423':7,'20260424':7,'20260425':4,
              '20260428':3,'20260429':7,'20260501':5,'20260502':5,'20260503':7,'20260427':5,'20260504':5,'20260505':6,
              '20260506':4,'20260507':5,'20260508':4,'20260509':4,'20260430':4}
    MALE = {'20260427','20260503','20260506','20260507','20260508','20260509'}
    df = pd.read_csv(CSV, low_memory=False)
    df = df[df['face_detected']==True].copy()
    df['date'] = df['date'].astype(str).str.strip()
    df['gender'] = df['date'].apply(lambda d: 'M' if d in MALE else 'F')
    df['score'] = df['date'].map(SCORES).astype(float)
    df = df[df['score'].notna()].copy()
    daily = df[df['gender']=='F'].groupby('date')[FEATS].mean().dropna()
    daily['score'] = daily.index.map(SCORES)
    daily = daily.dropna()
    X = daily[FEATS].values.astype(float); y = daily['score'].values.astype(float)
    print(f'Samples: {len(daily)} days')
    # 交给 _train_ensemble.py 做训练
    print('Run scripts/_train_ensemble.py to retrain the ensemble model.')
    print('Current model loaded:', _load_ensemble() is not None)
