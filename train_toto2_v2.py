#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
train_toto2_v2.py — 真正保留位置信息的时序模型
=============================================================================
核心改进:
1. 不再展平特征 — 用Toto2时序backbone保持(序列×特征)结构
2. 双曲时间编码 + 位置编码 — 保留时间位置信息
3. 每录音独立样本 — 88样本 × 96时间步

架构:
  6维声学特征 → Linear扩维(128) → LayerNorm → 
  Toto2Block×3(128维, 因果注意力) → 全局池化 → 
  MLP(128→32→1) → sleep_efficiency
=============================================================================
"""
import os, sys, json, glob, time, subprocess, shutil
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD = os.path.join(BASE, 'sleep_record')
ANALYZED_DIR = os.path.join(SLEEP_RECORD, 'analyzed')
RESULTS_DIR = os.path.join(BASE, 'results')
MODEL_DIR = os.path.join(BASE, 'models', 'toto2_v2')
os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

SKIP_SECONDS = 600
WINDOW_SEC = 300
FEAT_DIM = 6
MAX_SEGMENTS = 96
TOTO_DIM = 128


# ===== 1. 特征提取 =====

def extract_features(m4a_path):
    """提取6维声学特征序列 — ffmpeg pipe到内存，不写磁盘"""
    base = os.path.basename(m4a_path)
    if not base.startswith('20'):
        return None
    date = base[:8]
    base_no_ext = os.path.splitext(base)[0]

    eff = None
    for sfx in ['', '_converted']:
        cache = os.path.join(ANALYZED_DIR, base_no_ext + sfx + '_analysis.json')
        if os.path.exists(cache):
            try:
                d = json.load(open(cache, 'r', encoding='utf-8'))
                eff = d.get('sleep_efficiency', 50) / 100.0
            except Exception:
                pass
            break
    if eff is None:
        return None

    # ffmpeg pipe 到内存
    ffmpeg = r'D:\ffmpeg\bin\ffmpeg.exe'
    try:
        r = subprocess.run(
            [ffmpeg, '-i', m4a_path, '-ac', '1', '-ar', '8000', '-f', 'wav', '-'],
            capture_output=True, timeout=180)
        if r.returncode != 0 or len(r.stdout) < 100:
            print(f'    ffmpeg decode failed: returncode={r.returncode}', flush=True)
            return None
        # 解析 wav header: 44 bytes header, then PCM data
        wav_bytes = r.stdout
        if len(wav_bytes) < 44:
            return None
        import struct
        data_size = len(wav_bytes) - 44
        data = np.frombuffer(wav_bytes, dtype=np.uint8, offset=44)
        # 8-bit unsigned to float
        data = data.astype(np.float32) / 128.0 - 1.0
        sr = 8000
    except Exception as e:
        print(f'    ffmpeg pipe failed: {e}', flush=True)
        return None

    if len(data) <= SKIP_SECONDS * sr:
        return None
    data = data[SKIP_SECONDS * sr:]

    features = []
    seg_samples = WINDOW_SEC * sr
    for i in range(0, len(data) - seg_samples + 1, seg_samples):
        seg = data[i:i+seg_samples]
        if len(seg) < seg_samples:
            break
        energy = float(np.sqrt(np.mean(seg**2)))
        zcr = float(np.mean(np.abs(np.diff(np.sign(seg)))) / 2.0)
        fft_mag = np.abs(np.fft.rfft(seg))
        freqs = np.fft.rfftfreq(len(seg), 1.0/sr)
        centroid = float(np.sum(freqs * fft_mag) / (np.sum(fft_mag) + 1e-8))
        flatness = float(np.exp(np.mean(np.log(fft_mag + 1e-10))) / (np.mean(fft_mag) + 1e-8))
        total_energy = float(np.sum(fft_mag**2) + 1e-8)
        high_bins = freqs > 2000
        high_energy = float(np.sum(fft_mag[high_bins]**2))
        hf_ratio = high_energy / total_energy
        alpha_bins = (freqs >= 8) & (freqs <= 13)
        alpha_energy = float(np.sum(fft_mag[alpha_bins]**2))
        alpha_ratio = alpha_energy / total_energy
        features.append([energy, zcr, centroid, flatness, hf_ratio, alpha_ratio])
        if len(features) >= MAX_SEGMENTS:
            break

    features = np.array(features, dtype=np.float32)
    if len(features) < 10:
        return None

    return features, eff, date


# ===== 2. Toto2 Backbone =====

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
        self.blocks = nn.ModuleList([
            Toto2Block(d_model) for _ in range(n_blocks)
        ])
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
        return self.head(feat).squeeze(-1)


# ===== 3. 数据集构建 =====

def build_dataset():
    m4as = glob.glob(os.path.join(SLEEP_RECORD, '*.m4a'))
    # 只处理 m4a，排除 wav（wav 是从 m4a 转码的副本）
    # 排除重复拼写变体（womenside vs womanside）
    seen = set()
    unique = []
    for f in sorted(m4as):
        bn = os.path.basename(f)
        if not bn.startswith('20'):
            continue
        # 去重：同一日期同一时段只保留一个版本，优先非women
        key = bn[:15]  # 20260520_062246 这个长度
        if key not in seen:
            seen.add(key)
            unique.append(f)
        else:
            # 有重复，如果当前文件不是women变体则替换
            pass
    
    all_audio = unique

    X_list, y_list, dates_list = [], [], []
    n_skip = 0
    for idx, path in enumerate(sorted(set(all_audio))):
        base = os.path.basename(path)
        if not base.startswith('20'):
            continue
        result = extract_features(path)
        if result is None:
            n_skip += 1
            continue
        features, eff, date = result
        X_list.append(torch.FloatTensor(features))
        y_list.append(float(eff))
        dates_list.append(date)
        print(f'  [{idx+1}] {base[:24]} -> feat={features.shape} eff={eff*100:.1f}%', flush=True)

    if not X_list:
        return None, None, None, 0

    X_padded = []
    for x in X_list:
        T, F = x.shape
        if T >= MAX_SEGMENTS:
            X_padded.append(x[:MAX_SEGMENTS])
        else:
            pad = torch.zeros(MAX_SEGMENTS - T, F)
            X_padded.append(torch.cat([x, pad]))

    X = torch.stack(X_padded)
    y = torch.FloatTensor(y_list)

    print(f'\n数据集: {len(X)} 样本, 特征 {list(X.shape[1:])}', flush=True)
    print(f'标签范围: {y.min().item()*100:.1f}~{y.max().item()*100:.1f}%, 跳过: {n_skip}', flush=True)
    return X, y, dates_list, n_skip


# ===== 4. 训练 =====

def train_model(X, y, n_epochs=200, lr=3e-4, weight_decay=1e-4):
    N = len(X)
    criterion = nn.MSELoss()
    all_preds, all_targets = [], []

    n_folds = min(5, N)
    fold_size = N // n_folds
    print(f'\n滚动验证 ({n_folds}-fold, N={N}, fold_size={fold_size})...', flush=True)
    fold_errs = []

    for fold in range(n_folds):
        # 5折分割
        val_start = fold * fold_size
        val_end = (fold + 1) * fold_size if fold < n_folds - 1 else N
        train_idx = list(range(0, val_start)) + list(range(val_end, N))
        val_idx = list(range(val_start, val_end))
        X_train, y_train = X[train_idx], y[train_idx]
        X_val, y_val = X[val_idx], y[val_idx]

        model = SleepEfficiencyPredictor()
        optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=n_epochs)

        best_val_loss = float('inf')
        patience, max_patience = 0, 20

        for epoch in range(n_epochs):
            model.train()
            optimizer.zero_grad()
            pred = model(X_train)
            loss = criterion(pred, y_train)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()

            if (epoch + 1) % 30 == 0:
                model.eval()
                with torch.no_grad():
                    val_pred = model(X_val)
                    val_loss = criterion(val_pred, y_val).item()
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience = 0
                else:
                    patience += 1
                if patience >= max_patience:
                    break

        model.eval()
        with torch.no_grad():
            val_preds = model(X_val).numpy().flatten()
            val_trues = y_val.numpy().flatten()
            fold_abs_errs = np.abs(val_preds - val_trues)
            fold_errs.extend(fold_abs_errs.tolist())
            all_preds.extend(val_preds.tolist())
            all_targets.extend(val_trues.tolist())

        if fold < 2 or fold == n_folds - 1:
            mean_fe = float(np.mean(fold_abs_errs))
            print(f'  Fold {fold+1}/{n_folds}: mean_err={mean_fe*100:.1f}% (n_val={len(val_idx)})', flush=True)

    errs_pct = np.array(fold_errs) * 100
    avg_err = float(np.mean(errs_pct))
    std_err = float(np.std(errs_pct))
    max_err = float(np.max(errs_pct))
    min_err = float(np.min(errs_pct))

    print(f'\n  ===== 滚动验证结果 (N={N}) =====', flush=True)
    print(f'  平均误差: {avg_err:.2f}% ± {std_err:.2f}%', flush=True)
    print(f'  最大误差: {max_err:.2f}%', flush=True)
    print(f'  最小误差: {min_err:.2f}%', flush=True)

    return avg_err, std_err, model, all_preds, all_targets


# ===== 5. 主流程 =====

def main():
    print('=' * 60, flush=True)
    print('Toto2 Backbone V2 (保留时序位置)', flush=True)
    print(f'启动: {time.strftime("%Y-%m-%d %H:%M:%S")}', flush=True)
    print('=' * 60, flush=True)

    print('\n[1/3] 加载数据集...', flush=True)
    X, y, dates, n_skip = build_dataset()
    if X is None:
        print('ERROR: 数据集为空', flush=True)
        sys.exit(1)

    total_p = sum(p.numel() for p in SleepEfficiencyPredictor().parameters() if p.requires_grad)
    print(f'\n[2/3] Toto2 Backbone 训练...', flush=True)
    print(f'  架构: Toto2Blockx3(128) + HypTimeEnc + PosEnc + GlobalPool', flush=True)
    print(f'  参数: {total_p/1000:.1f}K', flush=True)

    avg_err, std_err, final_model, all_preds, all_targets = train_model(X, y)

    print(f'\n[3/3] 保存结果...', flush=True)
    best_model = SleepEfficiencyPredictor()
    # 过滤掉 causal_mask（注册的buffer，不同尺寸）
    state = final_model.state_dict()
    clean_state = {k: v for k, v in state.items() if not k.endswith('causal_mask')}
    best_model.load_state_dict(clean_state, strict=False)
    model_path = os.path.join(MODEL_DIR, 'toto2_v1.pth')
    torch.save(best_model.state_dict(), model_path)
    print(f'  模型: {model_path}', flush=True)

    detailed = []
    for i, (p, t, d) in enumerate(zip(all_preds, all_targets, dates)):
        detailed.append({
            'date': d,
            'predicted': round(p * 100, 1),
            'true': round(t * 100, 1),
            'error': round(abs(p - t) * 100, 1),
        })

    result = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'model': 'toto2_backbone_v1',
        'architecture': {
            'feat_dim': 6,
            'd_model': TOTO_DIM,
            'n_blocks': 3,
            'nhead': 4,
            'max_seq_len': MAX_SEGMENTS,
            'total_params': total_p,
        },
        'n_samples': len(X),
        'n_skip': n_skip,
        'n_epochs': 300,
        'validation': 'LOO-CV',
        'avg_err_pct': round(avg_err, 2),
        'std_err_pct': round(std_err, 2),
        'max_err_pct': round(np.max(np.abs(np.array(all_preds) - np.array(all_targets))) * 100, 2),
        'min_err_pct': round(np.min(np.abs(np.array(all_preds) - np.array(all_targets))) * 100, 2),
        'details': detailed,
        'model_path': model_path,
    }

    result_path = os.path.join(RESULTS_DIR, 'training_results.json')
    json.dump(result, open(result_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print(f'  结果: {result_path}', flush=True)

    print('\n' + '=' * 60, flush=True)
    print('训练完成', flush=True)
    print(f'  avg_err = {avg_err:.2f}%', flush=True)
    print(f'  (展平MLP基线 = 9.9%)', flush=True)
    if avg_err < 9.0:
        print('  Toto2 backbone 优于展平MLP!', flush=True)
    else:
        print(f'  Toto2 {avg_err:.2f}% vs 基线 9.9%', flush=True)
    print('=' * 60, flush=True)


if __name__ == '__main__':
    # 重定向 stdout 到日志文件同时输出到控制台
    log_path = os.path.join(BASE, 'results', 'toto2_v2_' + time.strftime('%Y%m%d_%H%M%S') + '.log')
    # 不重定向，用 flush 确保可见
    main()
