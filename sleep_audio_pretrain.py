# -*- coding: utf-8 -*-
"""
sleep_audio_pretrain.py v1.0 — 睡眠音频自监督预训练管线
基于 train_toto2_v2.py 方向，升级为 Masked Autoencoder 范式

架构：
  原始音频(16kHz) → 帧(30秒=480000样本) → mel频谱(80mel×938帧)
    → Transformer Encoder (masked 30%)
      → 重建 masked 部分 → 自监督 loss
        → 训练后 dump embedding

依赖：torch, librosa, numpy, scipy, tqdm
训练：支持 CPU / CUDA
"""

import os, sys, json, glob, time, subprocess, struct, warnings
import numpy as np
import librosa
from tqdm import tqdm
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from tqdm import tqdm
warnings.filterwarnings('ignore')

# ===== 配置 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据路径 — 指向 F 盘真实数据
SLEEP_RECORD = r'F:\sleep_record'
ANALYZED_DIR = os.path.join(SLEEP_RECORD, 'analyzed')

# 训练输出
CACHE_DIR = os.path.join(BASE_DIR, '.sleep_pretrain_cache')
MODEL_DIR = os.path.join(BASE_DIR, 'models', 'sleep_audio_pretrain')
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# 音频参数
TARGET_SR = 16000          # 16kHz（标准音频预训练采样率）
SKIP_SECONDS = 600        # 跳过前10分钟（入睡前准备）
SEGMENT_SEC = 30           # 每段30秒（标准的睡眠分期窗口）
SEGMENT_SAMPLES = TARGET_SR * SEGMENT_SEC  # 480000

# Mel 频谱参数
N_MELS = 80                # mel 频带数（标准量）
N_FFT = 1024
HOP_LENGTH = 512           # 约 31ms/frame → 16000/512 = 31.25 fps
WIN_LENGTH = 1024
# 30秒 → 480000/512 = 938 frames
MAX_FRAMES = SEGMENT_SAMPLES // HOP_LENGTH + 1  # ~938

# 模型参数
D_MODEL = 256
N_HEAD = 8
N_LAYERS = 6
MASK_RATIO = 0.30          # 掩码30%
DROPOUT = 0.1

# 训练参数
BATCH_SIZE = 32
LR = 1e-4
N_EPOCHS = 200
WARMUP_STEPS = 1000

# ffmpeg
FFMPEG = r'D:\ffmpeg\bin\ffmpeg.exe'


# ===== 1. 数据预处理：m4a → 16kHz WAV 特征缓存 =====

def find_wav_data_offset(wav_bytes):
    """在WAV字节流中找到data chunk的偏移量"""
    offset = 12
    while offset < len(wav_bytes) - 8:
        chunk_id = wav_bytes[offset:offset+4]
        chunk_size = struct.unpack('<I', wav_bytes[offset+4:offset+8])[0]
        if chunk_id == b'data':
            return offset + 8
        # 对齐到偶数
        offset += 8 + chunk_size + (chunk_size % 2)
    return None


def convert_to_mel(m4a_path):
    """将 m4a 转为 mel 频谱 (80×938) — 不存 WAV 到磁盘"""
    try:
        r = subprocess.run(
            [FFMPEG, '-i', m4a_path, '-ac', '1', '-ar', str(TARGET_SR),
             '-f', 'wav', '-'],
            capture_output=True, timeout=300)
        if r.returncode != 0 or len(r.stdout) < 100:
            return None
        
        # 解析 WAV — 需要搜索 data chunk，不能硬编码 offset=44
        data_offset = find_wav_data_offset(r.stdout)
        if data_offset is None:
            print(f'  WARN: cannot find data chunk in WAV')
            return None
        data = np.frombuffer(r.stdout, dtype=np.int16, offset=data_offset).astype(np.float32) / 32768.0
        if len(data) <= SKIP_SECONDS * TARGET_SR:
            return None
        
        # 分30秒段
        # 只对长度 > 1小时的音频跳过前10分钟
        if len(data) > 3600 * TARGET_SR:  # > 1小时
            data = data[SKIP_SECONDS * TARGET_SR:]
        
        segments = []
        n_seg = max(1, (len(data) - SEGMENT_SAMPLES) // SEGMENT_SAMPLES + 1)
        for i in range(min(n_seg, 200)):  # 最多200段/文件（防止8小时音频爆内存）
            seg = data[i * SEGMENT_SAMPLES : (i+1) * SEGMENT_SAMPLES]
            if len(seg) < SEGMENT_SAMPLES:
                seg = np.pad(seg, (0, SEGMENT_SAMPLES - len(seg)))
            
            # mel 频谱
            mel = librosa.feature.melspectrogram(
                y=seg, sr=TARGET_SR, n_mels=N_MELS,
                n_fft=N_FFT, hop_length=HOP_LENGTH, win_length=WIN_LENGTH,
                power=2.0)
            mel = librosa.power_to_db(mel, ref=np.max)  # (80, ~938)
            mel = (mel - mel.mean()) / (mel.std() + 1e-8)  # z-normalize per segment
            segments.append(mel)
        
        return np.array(segments, dtype=np.float32)  # (n_seg, 80, 938)
    except Exception as e:
        import traceback
        print(f'  convert_to_mel ERROR for {os.path.basename(m4a_path)}: {e}')
        traceback.print_exc()
        return None


def preprocess_all():
    """全量预处理：遍历所有 m4a，生成 mel 缓存"""
    files = sorted(glob.glob(os.path.join(SLEEP_RECORD, '*.m4a')))
    print(f"=== 预处理 {len(files)} 个文件 ===")
    
    all_features = []  # 存 (features, file_name)
    cache_path = os.path.join(CACHE_DIR, 'mel_cache.npz')
    
    # 检查已有缓存
    if os.path.exists(cache_path):
        print("  已有缓存，跳过预处理")
        return
    
    for fpath in tqdm(files, desc="预处理"):
        fname = os.path.basename(fpath)
        cache_file = os.path.join(CACHE_DIR, fname.replace('.m4a', '.npy'))
        
        if os.path.exists(cache_file):
            mel = np.load(cache_file)
        else:
            mel = convert_to_mel(fpath)
            if mel is not None:
                np.save(cache_file, mel)
        
        if mel is not None:
            all_features.append(mel)
    
    # 保存全量索引
    np.savez(cache_path, 
             features=np.concatenate(all_features) if all_features else np.array([]))
    print(f"  完成: {sum(len(f) for f in all_features)} 段")


# ===== 2. 数据集 =====

class SleepAudioDataset(Dataset):
    """mel 频谱数据集"""
    def __init__(self, cache_path=None):
        if cache_path and os.path.exists(cache_path):
            data = np.load(cache_path)
            self.features = data['features']
        else:
            # 从缓存目录加载所有 .npy
            files = sorted(glob.glob(os.path.join(CACHE_DIR, '*.npy')))
            all_feats = []
            for f in files:
                if 'mel_cache' in f:  # 跳过索引文件本身
                    continue
                try:
                    feats = np.load(f)
                    if len(feats.shape) == 3:
                        all_feats.append(feats)
                except:
                    pass
            self.features = np.concatenate(all_feats) if all_feats else np.array([])
        
        print(f"  数据集: {len(self.features)} 段")
    
    def __len__(self):
        return len(self.features)
    
    def __getitem__(self, idx):
        mel = self.features[idx]  # (80, 938)
        return torch.FloatTensor(mel)  # (80, 938)


# ===== 3. 掩码策略 =====

def mask_spectrogram(mel, mask_ratio=MASK_RATIO):
    """时间维度掩码：随机 mask 30% 的时间帧"""
    B, C, T = mel.shape
    n_mask = max(1, int(T * mask_ratio))
    
    mask = torch.zeros(B, 1, T, device=mel.device, dtype=torch.bool)
    for b in range(B):
        idx = torch.randperm(T, device=mel.device)[:n_mask]
        mask[b, 0, idx] = True
    
    masked_mel = mel.clone()
    masked_mel[mask.expand(-1, C, -1)] = 0.0
    
    return masked_mel, mask


# ===== 4. 模型：Transformer Masked Autoencoder =====

class SinusoidalPosEmb(nn.Module):
    """正弦位置编码"""
    def __init__(self, dim, max_len=2000):
        super().__init__()
        pe = torch.zeros(max_len, dim)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, dim, 2).float() * (-np.log(10000.0) / dim))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        self.register_buffer('pe', pe.unsqueeze(0))
    
    def forward(self, x):
        # x: (B, T, D)
        return x + self.pe[:, :x.size(1)]


class AudioMAE(nn.Module):
    """Masked Autoencoder for Audio Mel Spectrograms"""
    def __init__(self, n_mels=N_MELS, n_frames=MAX_FRAMES, d_model=D_MODEL,
                 n_head=N_HEAD, n_layers=N_LAYERS, dropout=DROPOUT):
        super().__init__()
        
        self.input_proj = nn.Linear(n_mels, d_model)
        self.pos_enc = SinusoidalPosEmb(d_model, max_len=n_frames + 1)
        self.mask_token = nn.Parameter(torch.randn(1, 1, d_model) * 0.02)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_head, dim_feedforward=d_model*4,
            dropout=dropout, activation='gelu', batch_first=True)
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        self.decoder_proj = nn.Linear(d_model, d_model)
        decoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_head, dim_feedforward=d_model*4,
            dropout=dropout, activation='gelu', batch_first=True)
        self.decoder = nn.TransformerEncoder(decoder_layer, num_layers=n_layers // 2)
        
        self.output_proj = nn.Linear(d_model, n_mels)
        
        self.apply(self._init_weights)
    
    def _init_weights(self, m):
        if isinstance(m, nn.Linear):
            nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.constant_(m.bias, 0)
    
    def forward(self, mel):
        """
        mel: (B, 80, T) — mel 频谱
        returns: (B, 80, T) — 重建结果
        """
        B, C, T = mel.shape
        
        # 掩码
        masked_mel, mask = mask_spectrogram(mel, MASK_RATIO)
        
        # 转置: (B, C, T) → (B, T, C)
        x = masked_mel.transpose(1, 2)  # (B, T, 80)
        x = self.input_proj(x)          # (B, T, D)
        x = self.pos_enc(x)             # + 位置编码
        
        # 对 masked 位置替换为 mask_token
        mask_expanded = mask.transpose(1, 2).expand(-1, -1, D_MODEL)  # (B, T, D)
        x = torch.where(mask_expanded, self.mask_token.expand(B, -1, D_MODEL), x)
        
        # Encoder
        x = self.encoder(x)
        
        # Decoder
        x = self.decoder_proj(x)
        x = self.decoder(x)
        
        # 输出: (B, T, C) → (B, C, T)
        out = self.output_proj(x).transpose(1, 2)
        
        # 只在 masked 位置计算 loss
        loss_mask = mask  # (B, 1, T)
        loss = nn.functional.mse_loss(out, mel, reduction='none')
        loss = (loss * loss_mask).sum() / (loss_mask.sum() + 1e-8)
        
        return out, loss, loss_mask


# ===== 5. 训练 =====

def train():
    print("=" * 60)
    print("睡眠音频自监督预训练 v1.0")
    print("=" * 60)
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")
    
    # 数据预处理
    print("\n[1/4] 预处理音频 → Mel频谱...")
    preprocess_all()
    
    # 数据集
    print("\n[2/4] 加载数据集...")
    dataset = SleepAudioDataset(os.path.join(CACHE_DIR, 'mel_cache.npz'))
    if len(dataset) == 0:
        print("  ERROR: 无数据!")
        return
    
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True,
                        num_workers=0, pin_memory=True)
    print(f"  batch_size={BATCH_SIZE}, {len(loader)} batches/epoch")
    
    # 模型
    print("\n[3/4] 初始化模型...")
    model = AudioMAE().to(device)
    total_params = sum(p.numel() for p in model.parameters())
    train_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  参数: {total_params:,} total, {train_params:,} trainable")
    
    optimizer = optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=N_EPOCHS)
    scaler = torch.amp.GradScaler() if device.type == 'cuda' else None
    
    # 训练
    print(f"\n[4/4] 开始训练 ({N_EPOCHS} epochs)...")
    best_loss = float('inf')
    start_time = time.time()
    
    for epoch in range(N_EPOCHS):
        model.train()
        total_loss = 0.0
        n_batches = 0
        
        pbar = tqdm(loader, desc=f"Epoch {epoch+1}/{N_EPOCHS}")
        for batch in pbar:
            batch = batch.to(device, non_blocking=True)
            
            if scaler:
                with torch.amp.autocast(device_type='cuda'):
                    _, loss, _ = model(batch)
                scaler.scale(loss).backward()
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
            else:
                _, loss, _ = model(batch)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
            
            optimizer.zero_grad()
            total_loss += loss.item()
            n_batches += 1
            pbar.set_postfix({'loss': f"{loss.item():.4f}"})
        
        avg_loss = total_loss / n_batches
        scheduler.step()
        lr_now = scheduler.get_last_lr()[0]
        
        elapsed = time.time() - start_time
        print(f"  Epoch {epoch+1:3d}: loss={avg_loss:.4f}  lr={lr_now:.2e}  "
              f"time={elapsed/60:.1f}m")
        
        # 保存最佳
        if avg_loss < best_loss:
            best_loss = avg_loss
            ckpt_path = os.path.join(MODEL_DIR, 'best_model.pt')
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'loss': best_loss,
                'config': {'d_model': D_MODEL, 'n_head': N_HEAD, 
                          'n_layers': N_LAYERS, 'n_mels': N_MELS}
            }, ckpt_path)
            print(f"    ✅ 最佳模型已保存 (loss={best_loss:.4f})")
        
        # 定期保存
        if (epoch + 1) % 20 == 0:
            ckpt_path = os.path.join(MODEL_DIR, f'checkpoint_epoch{epoch+1}.pt')
            torch.save({
                'epoch': epoch,
                'model_state_dict': model.state_dict(),
                'loss': avg_loss,
            }, ckpt_path)
    
    print(f"\n{'='*60}")
    print(f"训练完成! 最佳loss: {best_loss:.4f}")
    print(f"总耗时: {(time.time()-start_time)/60:.1f} 分钟")
    print(f"模型保存: {MODEL_DIR}")
    print(f"{'='*60}")


# ===== 6. 提取 Embedding（下游任务用） =====

def extract_embeddings():
    """用训好的模型提取全量 embedding"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    
    ckpt_path = os.path.join(MODEL_DIR, 'best_model.pt')
    if not os.path.exists(ckpt_path):
        print("未找到训练好的模型，先训练")
        return
    
    checkpoint = torch.load(ckpt_path, map_location=device)
    config = checkpoint.get('config', {})
    
    model = AudioMAE(
        n_mels=config.get('n_mels', N_MELS),
        d_model=config.get('d_model', D_MODEL),
        n_head=config.get('n_head', N_HEAD),
        n_layers=config.get('n_layers', N_LAYERS)
    ).to(device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    
    # 用 encoder 输出作为 embedding
    # 简单实现：去掉最后的 decoder 和 output_proj
    embedding_model = model.encoder
    
    dataset = SleepAudioDataset(os.path.join(CACHE_DIR, 'mel_cache.npz'))
    all_embeds = []
    
    with torch.no_grad():
        for i in range(len(dataset)):
            mel = dataset[i].unsqueeze(0).to(device)
            x = mel.transpose(1, 2)
            x = model.input_proj(x)
            x = model.pos_enc(x)
            emb = model.encoder(x)  # (1, T, D)
            emb = emb.mean(dim=1)    # 全局均值池化 → (1, D)
            all_embeds.append(emb.cpu().numpy())
    
    all_embeds = np.concatenate(all_embeds)
    out_path = os.path.join(MODEL_DIR, 'embeddings.npy')
    np.save(out_path, all_embeds)
    print(f"Embedding 已保存: {out_path} ({all_embeds.shape})")


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--extract', action='store_true', help='只提取 embedding')
    args = parser.parse_args()
    
    if args.extract:
        extract_embeddings()
    else:
        train()
