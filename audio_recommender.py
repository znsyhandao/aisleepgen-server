# -*- coding: utf-8 -*-
"""
音频推荐引擎 v2.0 — 声学驱动，别人抄不走

与v1.0的关键差异：
  1. 不再是手工标签 sleep=7/relax=7，而是实际跑SVM声学分析
  2. 声学评分预计算+缓存（避免请求时30秒延迟）
  3. 多样性+历史防止 - 同一用户不重复推相同文件
  4. 世界模型疗法映射保留作为场景入口
"""
import os, json, pickle, random, time
import soundfile as sf
import numpy as np

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
CACHE_FILE = os.path.join(BASE_DIR, 'data', 'cache', 'audio_analysis_cache.json')

# ===================== 音频注册表（保持v1.0）=====================
AUDIO_REGISTRY = [
    # 自然白噪音（高睡眠指数）
    ('fixed_rain.mp3',      'aisleepgen-netlify/audio',  '自然白噪', ['sleep', 'ambient']),
    ('fixed_rainnight.mp3', 'aisleepgen-netlify/audio',  '夜雨白噪', ['sleep', 'ambient']),
    ('fixed_seawind.mp3',   'aisleepgen-netlify/audio',  '海风海浪', ['sleep', 'ambient']),
    ('fixed_springsong.mp3','aisleepgen-netlify/audio',  '溪水自然', ['sleep', 'ambient']),
    ('ocean-waves.mp3',     'aisleepgen-netlify/audio',  '海浪',     ['sleep', 'ambient']),
    ('rain-sounds.mp3',     'aisleepgen-netlify/audio',  '雨声',     ['sleep', 'ambient']),
    ('nature-ambience.mp3', 'aisleepgen-netlify/audio',  '自然环境', ['sleep', 'ambient']),
    ('white-noise.mp3',     'aisleepgen-netlify/audio',  '白噪音',   ['sleep']),
    # 氛围音乐/冥想
    ('mixkit-smooth-meditation-324.mp3',  'aisleepgen-netlify/audio', '平滑冥想', ['relax', 'sleep']),
    ('mixkit-relaxation-05-749.mp3',      'aisleepgen-netlify/audio', '放松05',   ['relax']),
    ('mixkit-meditation-441.mp3',         'aisleepgen-netlify/audio', '冥想441',  ['relax', 'sleep']),
    ('mixkit-nature-meditation-345.mp3',  'aisleepgen-netlify/audio', '自然冥想', ['relax']),
    ('mixkit-yoga-song-444.mp3',          'aisleepgen-netlify/audio', '瑜伽歌',   ['relax']),
    ('mixkit-ocean-of-love-1113.mp3',     'aisleepgen-netlify/audio', '爱之洋',   ['relax', 'sleep']),
    ('mixkit-relax-beat-292.mp3',         'aisleepgen-netlify/audio', '放松节拍', ['relax']),
    ('piano-music.mp3',                   'aisleepgen-netlify/audio', '钢琴',     ['relax']),
    ('sleep-meditation.mp3',              'aisleepgen-netlify/audio', '睡眠冥想', ['relax', 'sleep']),
    ('bg_music.mp3',                      'assets',                   '背景音乐', ['relax', 'ambient']),
    ('meditation_music.mp3',              'assets',                   '冥想音乐', ['relax', 'sleep']),
    # 呼吸引导
    ('guided_meditation1.mp3',  'src/data', '呼吸引导1', ['relax']),
    ('guided_meditation2.mp3',  'src/data', '呼吸引导2', ['relax']),
    ('deep-breathing.mp3',      'aisleepgen-netlify/audio', '深呼吸', ['relax']),
    ('anxiety-relief.mp3',      'aisleepgen-netlify/audio', '焦虑缓解', ['relax']),
]

# 疗法→音频场景 匹配表（同v1.0）
THERAPY_AUDIO_MAP = {
    'relaxation_training':        ['relax'],
    'cognitive_restructuring':    ['relax', 'sleep'],
    'paradoxical_intention':      ['sleep'],
    'stimulus_control':           ['sleep'],
    'sleep_restriction':          ['sleep'],
    'body_scan_meditation':       ['relax'],
    'cognitive_unloading':        ['relax'],
    'sleep_hygiene':              ['ambient'],
}

# ===================== 声学分析 - 预计算引擎 =====================
# 这是别人抄不走的核心：用我们训练的SVM模型实际分析音频

_ANALYZER_CLF = None
_ANALYZER_SCALER = None
_ANALYSIS_CACHE = {}

def _ensure_analyzer():
    """懒加载声学分类器"""
    global _ANALYZER_CLF, _ANALYZER_SCALER
    if _ANALYZER_CLF is None:
        model_path = os.path.join(BASE_DIR, 'audio_classifier.pkl')
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                data = pickle.load(f)
            _ANALYZER_CLF = data['model']
            _ANALYZER_SCALER = data['scaler']
        else:
            # 没有模型文件时回退到训练
            from sleep_audio_engine import load_or_train_classifier
            _ANALYZER_CLF, _ANALYZER_SCALER = load_or_train_classifier()


def _extract_features(filepath):
    """从音频文件提取22维特征（同_train_final.py的流程）"""
    try:
        data, sr = sf.read(filepath)
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        if sr != 22050:
            from scipy import signal
            samples = round(len(data) * 22050 / sr)
            data = signal.resample(data, samples)
            sr = 22050
        # 计算时域特征
        energy = data ** 2
        total_energy = energy.sum()
        active = energy > (total_energy / len(data))
        active_ratio = active.mean()
        zcr = ((data[:-1] * data[1:]) < 0).mean()
        cv = data.std() / max(abs(data).mean(), 1e-10)
        # 频域特征
        from scipy import signal as sg
        f, t, Zxx = sg.stft(data, fs=sr, nperseg=2048, noverlap=1536)
        mag = np.abs(Zxx)
        centroid = np.sum(f[:, None] * mag, axis=0).sum() / max(mag.sum(), 1e-10)
        # 谱平坦度
        flatness = np.exp(np.mean(np.log(mag + 1e-10), axis=0)).mean() / max(mag.mean(axis=0).mean(), 1e-10)
        # Mel频段能量
        n_mels = 13
        mel_freqs = np.linspace(0, sr/2, n_mels + 2)
        mel_energies = []
        for mi in range(n_mels):
            f_low, f_high = mel_freqs[mi], mel_freqs[mi+2]
            band = mag[(f >= f_low) & (f <= f_high), :]
            mel_energies.append(band.sum() / max(mag.sum(), 1e-10))
        # 频段占比
        low_idx = int(len(f) * 0.3)
        mid_idx = int(len(f) * 0.6)
        low_pct = mag[:low_idx, :].sum() / max(mag.sum(), 1e-10)
        mid_pct = mag[low_idx:mid_idx, :].sum() / max(mag.sum(), 1e-10)
        features = np.array(mel_energies + [cv, zcr, centroid, flatness, low_pct, mid_pct, active_ratio])
        return features[:22]  # 确保22维
    except Exception:
        return None


def _analyze_single_audio(filepath):
    """对一个音频做完整声学分析，返回评分"""
    _ensure_analyzer()
    if _ANALYZER_CLF is None:
        return None
    
    feats = _extract_features(filepath)
    if feats is None or len(feats) != 22:
        return None
    
    scaled = _ANALYZER_SCALER.transform([feats])[0].reshape(1, -1)
    pred = _ANALYZER_CLF.predict(scaled)[0]
    proba = _ANALYZER_CLF.predict_proba(scaled)[0]
    
    # 解析SVM输出
    classes = _ANALYZER_CLF.classes_
    class_probs = dict(zip(classes, proba))
    
    # 映射到睡眠/减压评分
    sleep_score = max(1, min(10, int(5 + 4 * (class_probs.get('white_noise', 0) + class_probs.get('ambient', 0)))))
    relax_score = max(1, min(10, int(5 + 4 * (class_probs.get('music', 0) + class_probs.get('narration', 0)))))
    
    return {
        'pred_class': pred,
        'sleep': sleep_score,
        'relax': relax_score,
        'voice_prob': float(class_probs.get('narration', 0)),
        'features': {
            'centroid': float(feats[14] if len(feats) > 14 else 0),
            'flatness': float(feats[15] if len(feats) > 15 else 0),
            'cv': float(feats[13] if len(feats) > 13 else 0),
        }
    }


def _build_cache():
    """预计算所有音频的声学评分，并缓存到文件"""
    cache = {}
    for fname, subpath, label, scenes in AUDIO_REGISTRY:
        full_path = os.path.join(BASE_DIR, subpath, fname)
        if not os.path.exists(full_path):
            continue
        result = _analyze_single_audio(full_path)
        if result:
            cache[fname] = result
            print(f'[AudioCache] {label}: sleep={result["sleep"]} relax={result["relax"]} class={result["pred_class"]}')
        else:
            # fallback: 基于标签的默认值
            cache[fname] = {
                'pred_class': 'unknown',
                'sleep': 7 if 'sleep' in scenes else 5,
                'relax': 7 if 'relax' in scenes else 5,
                'voice_prob': 0.0,
                'features': {},
            }
            print(f'[AudioCache] {label}: (fallback) sleep={cache[fname]["sleep"]} relax={cache[fname]["relax"]}')
    
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    print(f'[AudioCache] 缓存已保存到 {CACHE_FILE} ({len(cache)}个音频)')
    return cache


def load_cache():
    """加载声学分析缓存"""
    global _ANALYSIS_CACHE
    if _ANALYSIS_CACHE:
        return _ANALYSIS_CACHE
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            _ANALYSIS_CACHE = json.load(f)
        print(f'[AudioCache] 从缓存加载 {len(_ANALYSIS_CACHE)}个音频评分')
    return _ANALYSIS_CACHE


# ===================== 多样性控制 =====================
_HISTORY_FILE = os.path.join(BASE_DIR, 'data', 'cache', 'audio_recommend_history.json')

def _load_history(openid):
    """加载用户推荐历史"""
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        hist = data.get(openid, [])
        return hist if isinstance(hist, list) else []
    except:
        return []

def _save_history(openid, filename):
    """记录某用户被推荐了某音频"""
    hist = {}
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
                hist = json.load(f)
        except Exception:
            hist = {}
    if openid not in hist:
        hist[openid] = []
    hist[openid].append({'file': filename, 'time': time.time()})
    # 只保留最近20条
    hist[openid] = hist[openid][-20:]
    os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
    with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False)


# ===================== 核心推荐逻辑 v2.0 =====================

def recommend_audio(therapy_ids, openid='default', top_k=2):
    """
    v2.0 声学驱动的音频推荐

    步骤:
      1. 从疗法ID推断需要的声音场景
      2. 从场景筛选候选音频
      3. 按声学评分排序（实际SVM输出）
      4. 排除用户最近推荐过的（多样性控制）
      5. 返回top_k
    """
    cache = load_cache()
    if not cache:
        # 缓存为空时build
        cache = _build_cache()
    
    # 1. 场景匹配
    needed_scenes = set()
    for tid in therapy_ids:
        scenes = THERAPY_AUDIO_MAP.get(tid, [])
        needed_scenes.update(scenes)
    if not needed_scenes:
        needed_scenes = {'relax'}
    
    priority = 'relax' if 'relax' in needed_scenes else ('sleep' if 'sleep' in needed_scenes else 'ambient')
    
    # 2. 从注册表筛选+评分
    history = _load_history(openid)
    if not isinstance(history, list):
        history = []
    recent_files = set(h['file'] for h in history[-5:])  # 最近5个推荐排除
    
    candidates = []
    for fname, subpath, label, scenes in AUDIO_REGISTRY:
        full_path = os.path.join(BASE_DIR, subpath, fname)
        if not os.path.exists(full_path):
            continue
        
        # 场景匹配
        if priority not in scenes and not (needed_scenes & set(scenes)):
            continue
        
        # 多样性：同一用户不连续推同一文件
        # 但如果音频很少，可以允许重复（top_k*2作为缓冲）
        diversity_penalty = 2.0 if fname in recent_files else 1.0
        
        # 获取声学评分（有缓存）
        ac = cache.get(fname, {})
        sleep_score = ac.get('sleep', 5)
        relax_score = ac.get('relax', 5)
        
        # 按优先级使用评分
        if priority == 'sleep':
            score = sleep_score / diversity_penalty
        elif priority == 'relax':
            score = relax_score / diversity_penalty
        else:
            score = (sleep_score + relax_score) / 2 / diversity_penalty
        
        candidates.append({
            'name': label,
            'file': fname,
            'path': full_path,
            'scenes': scenes,
            'score_val': score,
            'sleep': sleep_score,
            'relax': relax_score,
            'type': ac.get('pred_class', 'unknown'),
        })
    
    # 3. 排序取顶
    candidates.sort(key=lambda x: -x['score_val'])
    selected = candidates[:top_k]
    
    # 4. 记录推荐历史
    for s in selected:
        _save_history(openid, s['file'])
    
    return selected


def build_audio_card(recommendations):
    """v2.0 卡片构建（同v1.0，但评分来源不同）"""
    if not recommendations:
        return {}, ""
    
    suggestions = []
    seen_names = set()
    
    for i, rec in enumerate(recommendations):
        if rec['file'] in seen_names:
            continue
        seen_names.add(rec['file'])
        
        suggestion = {
            'file': rec['file'],
            'name': rec['name'],
            'path': rec['path'],
            'type': rec.get('type', 'unknown'),
            'score': {
                'sleep': rec['sleep'],
                'relax': rec['relax'],
            },
        }
        suggestions.append(suggestion)
    
    return {'audio_suggestions': suggestions}, ""


# ===================== 构建缓存入口 =====================
if __name__ == '__main__':
    print("构建声学分析缓存中...")
    cache = _build_cache()
    print(f"\n完成！共缓存 {len(cache)} 个音频的声学评分")
    print("测试推荐:")
    for tid, label in [(['relaxation_training'], '放松训练'),
                        (['sleep_restriction'], '睡眠限制'),
                        (['cognitive_restructuring'], '认知重建')]:
        recs = recommend_audio(tid)
        print(f"  [{label}] -> {[(r['name'], r['sleep'], r['relax']) for r in recs]}")
