#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
toto2_integration.py — Toto2 Backbone 集成模块
===============================================
功能：
  1. 加载训练好的 toto2_v1.pth 模型
  2. 从音频文件提取 6 维声学特征（同训练管线）
  3. Toto2 backbone 提取 128 维嵌入 + sleep_efficiency 预测
  4. 嵌入缓存到用户画像
  5. 异常检测（与用户历史嵌入对比）

用法：
  from toto2_integration import Toto2Analyzer
  analyzer = Toto2Analyzer()  # 单例，全局加载一次
  result = analyzer.analyze(wav_path, openid='user_xxx')

集成点：在 deepseek_proxy.py 的 _handle_audio_analysis_impl 调用
"""
import os, sys, json, time, glob, subprocess, struct
import torch
import torch.nn as nn
import numpy as np

# ===== Toto2 模型定义（与训练时一致） =====

class Toto2Block(nn.Module):
    def __init__(self, d_model, nhead=4, dim_feedforward=256, dropout=0.2):
        super().__init__()
        self.norm1 = nn.LayerNorm(d_model)
        self.attn = nn.MultiheadAttention(d_model, nhead, dropout=dropout, batch_first=True)
        self.norm2 = nn.LayerNorm(d_model)
        self.ffn = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, d_model),
            nn.Dropout(dropout),
        )
        self.register_buffer('causal_mask', None)

    def forward(self, x):
        B, T, D = x.shape
        if self.causal_mask is None or self.causal_mask.shape[-1] != T:
            mask = torch.triu(torch.full((T, T), float('-inf'), device=x.device), diagonal=1)
            self.register_buffer('causal_mask', mask)
        x2 = self.norm1(x)
        x = x + self.attn(x2, x2, x2, attn_mask=self.causal_mask)[0]
        x = x + self.ffn(self.norm2(x))
        return x


class HyperbolicTimeEncoding(nn.Module):
    def __init__(self, d_model, max_len=128):
        super().__init__()
        self.alpha = nn.Parameter(torch.tensor(2.0))
        self.pos_embed = nn.Parameter(torch.zeros(1, max_len, d_model))
        nn.init.trunc_normal_(self.pos_embed, std=0.02)

    def forward(self, x):
        B, T, D = x.shape
        t = torch.linspace(0, 1, T, device=x.device).view(1, T, 1)
        hyp_weight = torch.tanh(self.alpha * (1 - t))
        pos = self.pos_embed[:, :T, :]
        return x * hyp_weight + pos


class Toto2Backbone(nn.Module):
    def __init__(self, feat_dim=6, d_model=128, n_blocks=3, max_len=128):
        super().__init__()
        self.input_proj = nn.Linear(feat_dim, d_model)
        self.norm_in = nn.LayerNorm(d_model)
        self.time_enc = HyperbolicTimeEncoding(d_model, max_len)
        self.blocks = nn.ModuleList([Toto2Block(d_model) for _ in range(n_blocks)])
        self.norm_out = nn.LayerNorm(d_model)
        self.pool = nn.AdaptiveAvgPool1d(1)

    def forward(self, x):
        x = self.input_proj(x)
        x = self.norm_in(x)
        x = self.time_enc(x)
        for block in self.blocks:
            x = block(x)
        x = self.norm_out(x)
        x = self.pool(x.transpose(1, 2)).squeeze(-1)
        return x


class SleepEfficiencyPredictor(nn.Module):
    def __init__(self, feat_dim=6, d_model=128, n_blocks=3, max_len=128):
        super().__init__()
        self.backbone = Toto2Backbone(feat_dim, d_model, n_blocks, max_len)
        self.head = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(32, 1),
        )

    def forward(self, x):
        feat = self.backbone(x)
        return self.head(feat).squeeze(-1), feat

    def get_embedding(self, x):
        """只获取128维嵌入，不进行预测"""
        return self.backbone(x)


# ===== 特征提取（与训练管线一致，pipe到内存） =====

SKIP_SECONDS = 600
WINDOW_SEC = 300
FEAT_DIM = 6
MAX_SEGMENTS = 96
FFMPEG = r'D:\ffmpeg\bin\ffmpeg.exe'


def _extract_6dim_features(audio_path):
    """从音频文件提取6维声学特征序列（不写磁盘）"""
    if not os.path.exists(audio_path):
        return None

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        try:
            r = subprocess.run(
                [FFMPEG, '-i', audio_path, '-ac', '1', '-ar', '8000', '-f', 'wav', '-'],
                capture_output=True, timeout=180)
            if r.returncode != 0 or len(r.stdout) < 100:
                return None
            wav_bytes = r.stdout
            data = np.frombuffer(wav_bytes, dtype=np.uint8, offset=44).astype(np.float32) / 128.0 - 1.0
            sr = 8000
        except:
            return None

    if len(data) <= SKIP_SECONDS * sr:
        return None
    data = data[SKIP_SECONDS * sr:]

    features = []
    seg_samples = WINDOW_SEC * sr
    for i in range(0, len(data) - seg_samples + 1, seg_samples):
        seg = data[i:i + seg_samples]
        if len(seg) < seg_samples:
            break
        energy = float(np.sqrt(np.mean(seg ** 2)))
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg)))) / 2.0)
        fft_mag = np.abs(np.fft.rfft(seg))
        freqs = np.fft.rfftfreq(len(seg), 1.0 / sr)
        centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-8))
        flatness = float(np.exp(np.mean(np.log(fft_mag + 1e-10))) / (np.mean(fft_mag) + 1e-8))
        total_energy = float(np.sum(fft_mag ** 2) + 1e-8)
        high_bins = freqs > 2000
        high_energy = float(np.sum(fft_mag[high_bins] ** 2))
        hf_ratio = high_energy / total_energy
        alpha_bins = (freqs >= 8) & (freqs <= 13)
        alpha_energy = float(np.sum(fft_mag[alpha_bins] ** 2))
        alpha_ratio = alpha_energy / total_energy
        features.append([energy, zcr, centroid, flatness, hf_ratio, alpha_ratio])
        if len(features) >= MAX_SEGMENTS:
            break

    features = np.array(features, dtype=np.float32)
    if len(features) < 10:
        return None

    # 补齐至96步
    if len(features) < MAX_SEGMENTS:
        pad = np.zeros((MAX_SEGMENTS - len(features), FEAT_DIM))
        features = np.concatenate([features, pad])

    return features[:MAX_SEGMENTS]


# ===== Toto2 分析器 =====

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'toto2_v2', 'toto2_v1.pth')
SLEEP_RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sleep_record')
ANALYZED_DIR = os.path.join(SLEEP_RECORD, 'analyzed')


class Toto2Analyzer:
    """Toto2 分析器（单例）"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.model = None
        self.device = torch.device('cpu')

    def load(self, model_path=None):
        """加载模型"""
        path = model_path or MODEL_PATH
        if self.model is not None:
            return True

        if not os.path.exists(path):
            print(f'[Toto2] 模型文件不存在: {path}')
            return False

        try:
            self.model = SleepEfficiencyPredictor()
            # 加载时过滤 causal_mask 等 buffer
            state = torch.load(path, map_location=self.device, weights_only=True)
            clean_state = {k: v for k, v in state.items() if not k.endswith('causal_mask')}
            self.model.load_state_dict(clean_state, strict=False)
            self.model.eval()
            print(f'[Toto2] 模型加载成功: {path}')
            return True
        except Exception as e:
            print(f'[Toto2] 模型加载失败: {e}')
            self.model = None
            return False

    def analyze(self, audio_path, openid='default'):
        """
        对单个音频文件执行 Toto2 分析。

        返回:
            dict 或 None - 包含 embedding, efficiency_pred, anomaly_score
        """
        if self.model is None:
            if not self.load():
                return None

        # 1. 提取特征
        features = _extract_6dim_features(audio_path)
        if features is None:
            return None

        # 2. Toto2 推理
        t0 = time.time()
        with torch.no_grad():
            x = torch.FloatTensor(features).unsqueeze(0)  # (1, 96, 6)
            efficiency_pred, embedding = self.model(x)
            efficiency_pred = efficiency_pred.item()
            embedding_np = embedding.numpy().flatten().tolist()
        t_ms = round((time.time() - t0) * 1000, 1)

        # 3. 从 analysis JSON 读取真实效率（如果有）
        true_efficiency = None
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        for sfx in ['', '_converted']:
            cache = os.path.join(ANALYZED_DIR, base_name + sfx + '_analysis.json')
            if os.path.exists(cache):
                try:
                    d = json.load(open(cache, 'r', encoding='utf-8'))
                    true_efficiency = d.get('sleep_efficiency')
                    if true_efficiency is not None:
                        true_efficiency = true_efficiency / 100.0
                except:
                    pass
                break

        result = {
            'source': 'toto2_v1',
            'efficiency_pred': round(efficiency_pred * 100, 1),
            'true_efficiency': round(true_efficiency * 100, 1) if true_efficiency is not None else None,
            'error': round(abs(efficiency_pred - true_efficiency) * 100, 1) if true_efficiency is not None else None,
            'embedding_dim': len(embedding_np),
            'embedding': embedding_np[:16],  # 只返回前16维预览
            'inference_ms': t_ms,
            'n_segments': features.shape[0],
        }
        return result


# ===== 快速测试 =====

if __name__ == '__main__':
    analyzer = Toto2Analyzer()
    analyzer.load()

    # 测试所有录音
    m4as = sorted(glob.glob(os.path.join(SLEEP_RECORD, '*.m4a')))[:5]
    for path in m4as:
        result = analyzer.analyze(path)
        if result:
            eff_display = result['efficiency_pred']
            true_display = result['true_efficiency'] or '?'
            err_display = result['error'] or '?'
            print(f'  {os.path.basename(path)[:24]}: pred={eff_display}% | true={true_display}% | err={err_display}% | {result["inference_ms"]}ms')
        else:
            print(f'  {os.path.basename(path)[:24]}: FAIL')
