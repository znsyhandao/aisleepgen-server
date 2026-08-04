#!/usr/bin/env python3
"""
隔离测试：nD-RoPE vs 标准 RoPE 在睡眠时序数据上的收益验证

AISleepGen 输入维度：
  - 时序维度: 时间步 (如 60s 窗口)
  - 频段维度: EEG delta/theta/alpha/beta
  - 用户状态维度: HRV/HR/呼吸频率

测试方法：
  1. 生成模拟睡眠时序数据（含周期模式）
  2. 用标准 RoPE 编码后做位置分类任务
  3. 用 nD-RoPE 编码后做同样任务
  4. 比较准确率差异
"""
import sys, json, math, random, uuid
import torch
import torch.nn as nn
import numpy as np

# 使用 CPU（AISleepGen 本地跑的约束）
device = torch.device('cpu')
print(f'Device: {device}')
print(f'PyTorch: {torch.__version__}')

# ========== 模拟数据生成 ==========

def generate_sleep_data(batch_size=32, seq_len=60, n_channels=3):
    """生成模拟睡眠时段数据"""
    # 实际通道数 >= 3 则生成完整数据，否则只取前 n_channels 个
    t = torch.linspace(0, 4*math.pi, seq_len)
    """
    生成模拟的睡眠时段数据
    每个样本: [seq_len, n_channels]
    - ch0: HRV 序列（呼吸性窦性心律不齐模式）
    - ch1: 体动活动量（随机突发）
    - ch2: 频段功率比（delta/theta 比例变化）
    """
    t = torch.linspace(0, 4*math.pi, seq_len)
    
    data = []
    for _ in range(batch_size):
        # HRV: 正弦波 + noise
        hrv = 0.5 * torch.sin(t + random.random()*2) + 0.3 * torch.randn(seq_len) * 0.1
        # 体动: 随机突发
        motion = torch.zeros(seq_len)
        burst_pos = random.randint(0, seq_len-1)
        motion[max(0,burst_pos-2):min(seq_len,burst_pos+3)] = 0.8
        motion += 0.1 * torch.randn(seq_len)
        # 频段功率比: 缓慢变化（进入深睡阶段）
        band_ratio = 0.3 + 0.5 * torch.sigmoid(torch.linspace(-3, 3, seq_len))
        band_ratio += 0.1 * torch.randn(seq_len) * 0.05
        
        # 动态通道数
        base_channels = [hrv, motion, band_ratio]
        extra = []
        for _ in range(n_channels - 3):
            extra.append(0.5 * torch.sin(t + random.random()) + 0.2 * torch.randn(seq_len))
        all_ch = base_channels + extra
        sample = torch.stack(all_ch, dim=1)
        data.append(sample)
    
    return torch.stack(data)  # [B, T, C]

# ========== 标准 RoPE ==========

class StandardRoPE(nn.Module):
    """标准 1D RoPE（仅时序维度）"""
    def __init__(self, d_model, max_len=2048):
        super().__init__()
        inv_freq = 1.0 / (10000 ** (torch.arange(0, d_model, 2).float() / d_model))
        self.register_buffer('inv_freq', inv_freq)
        self.max_len = max_len
        
    def forward(self, x, positions=None):
        # x: [B, T, D], positions: optional [B, T]
        B, T, D = x.shape
        if positions is None:
            positions = torch.arange(T, device=x.device).unsqueeze(0).expand(B, -1)
        # [T, D/2]
        freqs = positions.float().unsqueeze(-1) * self.inv_freq.unsqueeze(0)  # [B, T, D/2]
        cos = freqs.cos()
        sin = freqs.sin()
        # 应用旋转
        x_rot = x.view(*x.shape[:-1], -1, 2)
        x_out = torch.stack([
            x_rot[..., 0] * cos - x_rot[..., 1] * sin,
            x_rot[..., 0] * sin + x_rot[..., 1] * cos
        ], dim=-1)
        return x_out.view_as(x)

# ========== nD-RoPE ==========

class nD_RoPE(nn.Module):
    """nD-RoPE: 统一高维旋转位置编码"""
    def __init__(self, dim, max_len=2048, n_dims=3):
        super().__init__()
        self.dim = dim
        self.n_dims = n_dims
        freqs = []
        for d in range(n_dims):
            freq = 1.0 / (10000 ** (torch.arange(0, dim, 2).float() / dim))
            freqs.append(freq)
        self.register_buffer('freqs', torch.stack(freqs, dim=0))  # [n_dims, D/2]
        
    def forward(self, x, positions):
        # x: [B, T, D], positions: [B, T, n_dims]
        B, T, D = x.shape
        # 每维角度: [n_dims, B, T, D/2]
        angles = positions.permute(2, 0, 1).unsqueeze(-1) * self.freqs.unsqueeze(1).unsqueeze(2)
        cos = torch.cos(angles).sum(dim=0)  # [B, T, D/2]
        sin = torch.sin(angles).sum(dim=0)
        x_rot = x.view(B, T, -1, 2)
        x_out = torch.stack([
            x_rot[..., 0] * cos - x_rot[..., 1] * sin,
            x_rot[..., 0] * sin + x_rot[..., 1] * cos
        ], dim=-1)
        return x_out.view_as(x)

# ========== 分类测试 ==========

class SleepClassifier(nn.Module):
    """简单分类器：从编码后的序列预测睡眠阶段"""
    def __init__(self, d_model, n_classes=3):
        super().__init__()
        self.proj = nn.Linear(d_model, d_model)
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.classifier = nn.Linear(d_model, n_classes)
        
    def forward(self, x):
        # x: [B, T, D]
        x = self.proj(x)
        x = x.permute(0, 2, 1)  # [B, D, T]
        x = self.pool(x).squeeze(-1)  # [B, D]
        return self.classifier(x)

def test_rope_vs_ndrope(seq_len=60, d_model=32, n_channels=3, n_classes=3,
                         train_steps=300, lr=0.01):
    """主测试函数"""
    print(f'\n=== 测试参数: seq_len={seq_len}, d_model={d_model}, n_channels={n_channels} ===')
    
    # 生成固定测试集
    torch.manual_seed(42)
    np.random.seed(42)
    test_batch = generate_sleep_data(128, seq_len, n_channels)
    test_labels = torch.randint(0, n_classes, (128,))
    # 位置编码的多维坐标: [批次, 时间步, 3维]
    test_pos = torch.zeros(128, seq_len, 3)
    test_pos[:, :, 0] = torch.arange(seq_len).float()  # 时序位置
    test_pos[:, :, 1] = torch.arange(seq_len).float() / seq_len  # 归一化时序
    test_pos[:, :, 2] = torch.stack([torch.sin(torch.arange(seq_len).float()/10) for _ in range(128)])  # 周期位置
    
    results = {}
    
    for name, pe_layer in [
        ('RoPE (1D)', StandardRoPE(d_model, seq_len)),
        ('nD-RoPE (3D)', nD_RoPE(d_model, seq_len, n_dims=3)),
    ]:
        print(f'\n--- {name} ---')
        model = SleepClassifier(d_model, n_classes).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        loss_fn = nn.CrossEntropyLoss()
        
        losses = []
        for step in range(train_steps):
            batch = generate_sleep_data(32, seq_len, n_channels)
            labels = torch.randint(0, n_classes, (32,))
            
            # 投影到 d_model
            x = batch.view(32, seq_len, n_channels).float()
            # 线性投影到 d_model 维度
            proj = nn.Linear(n_channels, d_model)
            x = proj(x)
            
            # 应用位置编码
            if 'nD-RoPE' in name:
                pos = torch.zeros(32, seq_len, 3)
                pos[:, :, 0] = torch.arange(seq_len).float()
                pos[:, :, 1] = torch.arange(seq_len).float() / seq_len
                pos[:, :, 2] = torch.sin(torch.arange(seq_len).float()/10).unsqueeze(0).expand(32, -1)
                x = pe_layer(x, pos)
            else:
                x = pe_layer(x)
            
            out = model(x)
            loss = loss_fn(out, labels)
            
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
            
            if (step + 1) % 100 == 0:
                print(f'  Step {step+1}: loss={loss.item():.4f}')
        
        # 测试集评估
        with torch.no_grad():
            x_test = test_batch.view(128, seq_len, n_channels).float()
            proj = nn.Linear(n_channels, d_model)
            x_test = proj(x_test)
            
            if 'nD-RoPE' in name:
                x_test = pe_layer(x_test, test_pos)
            else:
                x_test = pe_layer(x_test)
            
            test_out = model(x_test)
            preds = test_out.argmax(dim=1)
            acc = (preds == test_labels).float().mean().item()
        
        print(f'  Test accuracy: {acc*100:.1f}%')
        results[name] = {
            'test_accuracy': round(acc * 100, 1),
            'final_loss': round(losses[-1], 4),
        }
    
    return results

# ========== 运行 ==========

print('=' * 60)
print('  nD-RoPE vs RoPE 隔离测试 — 睡眠时序数据')
print('=' * 60)

results = test_rope_vs_ndrope(seq_len=60, d_model=32, n_channels=3)
results2 = test_rope_vs_ndrope(seq_len=120, d_model=64, n_channels=5)

print('\n' + '=' * 60)
print('  结果汇总')
print('=' * 60)
all_results = {'seq60_dim32_ch3': results, 'seq120_dim64_ch5': results2}
print(json.dumps(all_results, indent=2))

# 收益判断
for test_name, r in all_results.items():
    rope_acc = r.get('RoPE (1D)', {}).get('test_accuracy', 0)
    nd_acc = r.get('nD-RoPE (3D)', {}).get('test_accuracy', 0)
    gain = nd_acc - rope_acc
    print(f'\n{test_name}:')
    print(f'  RoPE:   {rope_acc}%')
    print(f'  nD-RoPE: {nd_acc}%')
    if gain >= 2.0:
        print(f'  ✅ 收益 +{gain:.1f}% > 2% 阈值 → 值得实现')
    elif gain > 0:
        print(f'  ⚠️ 收益 +{gain:.1f}% 但 < 2% → 需要更大规模测试确认')
    else:
        print(f'  ❌ 无收益 ({gain:+.1f}%) → 不建议实现')
