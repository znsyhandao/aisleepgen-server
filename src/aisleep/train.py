import os
import sys
import time
import random
import logging
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from sklearn.metrics import confusion_matrix, classification_report

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, random_split
from torch.utils.tensorboard import SummaryWriter
from torch.cuda.amp import GradScaler, autocast
from torch.utils.flop_counter import FlopCounterMode

from aisleep.model.deepseek.models import EEGSleepDataset
from aisleep.model.deepseek.official.DeepSeek_V3 import DeepSeekV3
from aisleep.model.deepseek.official.DeepSeek_V3.inference.model import ModelArgs

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EEGAugmenter:
    def __init__(self):
        self.noise_scale = 0.01
        self.max_shift = 10
        self.dropout_prob = 0.1
        self.freq_mask_ratio = 0.2
        self.time_warp_scale = 0.1

    def time_warp(self, x):
        length = x.shape[0]
        warp_points = int(length * self.time_warp_scale)
        start = random.randint(0, length - warp_points - 1)
        end = start + warp_points
        scale = 0.8 + random.random() * 0.4
        warped = torch.nn.functional.interpolate(
            x[start:end].unsqueeze(0).unsqueeze(0),
            scale_factor=scale,
            mode='linear'
        ).squeeze()
        x[start:start+len(warped)] = warped
        return x
        
    def freq_mask(self, x):
        fft = torch.fft.fft(x, dim=0)
        mask = torch.ones_like(fft)
        mask[:int(fft.shape[0]*self.freq_mask_ratio)] = 0
        fft *= mask
        return torch.fft.ifft(fft, dim=0).real
        
    def __call__(self, x):
        if random.random() < self.dropout_prob:
            mask = torch.ones_like(x)
            mask[random.randint(0, x.shape[0]-1)] = 0
            x *= mask
            
        if random.random() < 0.5:
            x = self.time_warp(x)
            
        noise = torch.randn_like(x) * self.noise_scale * x.std()
        x += noise
            
        shift = random.randint(-self.max_shift, self.max_shift)
        x = torch.roll(x, shifts=shift, dims=0)
            
        if random.random() < 0.3:
            x = self.freq_mask(x)
            
        return x

def visualize_augmentation(original, augmented):
    plt.figure(figsize=(12, 6))
    plt.subplot(2, 1, 1)
    plt.plot(original.numpy().T)
    plt.title("Original EEG")
    plt.subplot(2, 1, 2)
    plt.plot(augmented.numpy().T)
    plt.title("Augmented EEG")
    plt.tight_layout()
    plt.savefig("eeg_augmentation_comparison.png")
    plt.close()

def main():
    # 初始化
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    writer = SummaryWriter('runs/deepseekv3_experiment')
    
    # 数据准备
    dataset = EEGSleepDataset(
        data_path="D:/AISleepGen/data/edf",
        transform=EEGAugmenter()
    )
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    train_loader = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        num_workers=4,
        pin_memory=True
    )
    val_loader = DataLoader(val_dataset, batch_size=8)
    
    # 模型初始化
    model_args = ModelArgs(
        max_batch_size=8,
        max_seq_len=4096,
        vocab_size=102400,
        dim=2048,
        n_layers=27
    )
    model = DeepSeekV3(model_args).to(device)
    
    # 训练配置
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, 
        max_lr=1e-3,
        steps_per_epoch=len(train_loader),
        epochs=100
    )
    scaler = GradScaler()
    
    # 训练循环
    best_val_loss = float('inf')
    for epoch in range(100):
        model.train()
        train_loss = 0
        
        for batch in tqdm(train_loader, desc=f"Epoch {epoch+1}"):
            inputs, labels = [x.to(device) for x in batch]
            
            optimizer.zero_grad()
            with autocast():
                outputs = model(inputs)
                loss = criterion(outputs, labels)
            
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            
            train_loss += loss.item()
        
        # 验证
        model.eval()
        val_loss, correct = 0, 0
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                outputs = model(inputs)
                val_loss += criterion(outputs, labels).item()
                correct += (outputs.argmax(1) == labels).sum().item()
        
        # 记录指标
        avg_train_loss = train_loss / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)
        accuracy = correct / len(val_dataset)
        
        logger.info(f"Epoch {epoch+1} - Train Loss: {avg_train_loss:.4f} | Val Loss: {avg_val_loss:.4f} | Acc: {accuracy:.2%}")
        
        # 模型保存
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            torch.save(model.state_dict(), "best_model.pth")
    
    writer.close()

if __name__ == "__main__":
    main()
