from aisleep.model.deepseek.models import EEGSleepDataset
from aisleep.model.deepseek.official.DeepSeek_V3 import DeepSeekV3
from aisleep.model.deepseek.official.DeepSeek_V3.inference.model import ModelArgs
from torch.utils.data import DataLoader, random_split
import torch
import torch.nn as nn
from tqdm import tqdm
import time
from torch.utils.tensorboard import SummaryWriter
from torch.cuda.amp import GradScaler, autocast
import torch.cuda
from torch.utils.flop_counter import FlopCounterMode
import random
import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import confusion_matrix, classification_report
import seaborn as sns



class EEGAugmenter:
    def __init__(self):
        # 增强参数配置
        self.noise_scale = 0.01
        self.max_shift = 10
        self.dropout_prob = 0.1
        self.freq_mask_ratio = 0.2  # 新增频域掩码比例
        self.time_warp_scale = 0.1   # 新增时间扭曲强度
        
    def time_warp(self, x):
        """时间扭曲增强，模拟EEG信号的时间尺度变化"""
        length = x.shape[0]
        warp_points = int(length * self.time_warp_scale)
        start = random.randint(0, length - warp_points - 1)
        end = start + warp_points
        scale = 0.8 + random.random() * 0.4  # 缩放系数0.8-1.2
        warped = torch.nn.functional.interpolate(
            x[start:end].unsqueeze(0).unsqueeze(0),
            scale_factor=scale,
            mode='linear'
        ).squeeze()
        x[start:start+len(warped)] = warped
        return x
        
    def freq_mask(self, x):
        """频域增强，模拟EEG频段特征变化"""
        fft = torch.fft.fft(x, dim=0)
        mask = torch.ones_like(fft)
        mask[:int(fft.shape[0]*self.freq_mask_ratio)] = 0
        fft *= mask
        return torch.fft.ifft(fft, dim=0).real
        
    def __call__(self, x):
        # 1. 通道随机丢弃
        if random.random() < self.dropout_prob:
            mask = torch.ones_like(x)
            mask[random.randint(0, x.shape[0]-1)] = 0
            x *= mask
            
        # 2. 时间扭曲增强 (50%概率)
        if random.random() < 0.5:
            x = self.time_warp(x)
            
        # 3. 添加自适应噪声 (噪声强度与信号强度成正比)
        noise = torch.randn_like(x) * self.noise_scale * x.std()
        x += noise
            
        # 4. 随机时间偏移
        shift = random.randint(-self.max_shift, self.max_shift)
        x = torch.roll(x, shifts=shift, dims=0)
            
        # 5. 频域增强 (30%概率)
        if random.random() < 0.3:
            x = self.freq_mask(x)
            
        return x


def visualize_augmentation(original, augmented):
    plt.figure(figsize=(12, 6))
    plt.subplot(2, 1, 1)
    plt.plot(original.numpy().T)
    plt.title("原始EEG信号")
    plt.xlabel("时间点")
    plt.ylabel("幅值")

    plt.subplot(2, 1, 2)
    plt.plot(augmented.numpy().T)
    plt.title("增强后EEG信号")
    plt.xlabel("时间点")
    plt.ylabel("幅值")
    plt.tight_layout()
    plt.savefig("eeg_augmentation_comparison.png")
    plt.close()

if __name__ == "__main__":
    augmenter = EEGAugmenter()
    test_data = torch.randn(4096)  # 模拟EEG数据
    for i in range(5):
        augmented = augmenter(test_data.clone())
        print(f"测试{i+1} - 原始/增强数据差异: {torch.norm(test_data-augmented):.4f}")
        visualize_augmentation(test_data, augmented)

    # 初始化TensorBoard
    writer = SummaryWriter('runs/deepseekv3_experiment')
    
    # 数据加载
    dataset = EEGSleepDataset(
        data_path="D:/AISleepGen/data/edf",
        transform=EEGAugmenter()
    )
    
    # 增强测试
    if len(dataset) > 0:
        original = dataset[0][0]
        augmented = EEGAugmenter()(original.clone())
        visualize_augmentation(original, augmented)
        print("\n增强效果统计验证:")
        print(f"原始形状: {original.shape} 增强后形状: {augmented.shape}")
        print(f"均值变化: {original.mean():.4f} → {augmented.mean():.4f}")
        print(f"标准差变化: {original.std():.4f} → {augmented.std():.4f}")
        # 在增强测试部分添加
        print("\n增强效果详细分析:")
        print(f"原始信号峰度: {torch.kurtosis(original):.4f}")
        print(f"增强信号峰度: {torch.kurtosis(augmented):.4f}")
        print(f"原始信号过零率: {(torch.diff(original.sign()) != 0).sum().item()}")
        print(f"增强信号过零率: {(torch.diff(augmented.sign()) != 0).sum().item()}")

    # 数据拆分
    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])
    
    # 数据加载器
        # 修改数据加载部分
    train_loader = DataLoader(
        train_dataset,
        batch_size=8,
        shuffle=True,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
        collate_fn=lambda x: (
            x[0].view(x[0].size(0), -1).pin_memory().to(device, non_blocking=True),
            x[1].pin_memory().to(device, non_blocking=True)
        ) if sample_input.dim() != 2 else None
    )
    val_loader = DataLoader(val_dataset, batch_size=8)
    print(f"成功加载 {len(dataset)} 个样本")

    # 检查数据形状
    sample_input, sample_label = next(iter(train_loader))
    print(f"输入数据形状: {sample_input.shape}, 标签形状: {sample_label.shape}")
    
    # 调整数据形状
    if sample_input.dim() != 2:
        original_shape = sample_input.shape
        train_loader = DataLoader(train_dataset, batch_size=8, shuffle=True,
                               collate_fn=lambda x: (x[0].view(x[0].size(0), -1), x[1]))
        val_loader = DataLoader(val_dataset, batch_size=8,
                             collate_fn=lambda x: (x[0].view(x[0].size(0), -1), x[1]))
        print(f"调整输入形状从 {original_shape} 到 {next(iter(train_loader))[0].shape}")

    # 模型初始化
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_args = ModelArgs(
        max_batch_size=8,
        max_seq_len=4096,
        vocab_size=102400,
        dim=2048,
        n_layers=27
    )
    model = DeepSeekV3(model_args).to(device)
    print("DeepSeekV3模型结构:", model)

    # 在模型初始化后添加
    def load_checkpoint(path):
        checkpoint = torch.load(path)
        model.load_state_dict(checkpoint['model_state'])
        optimizer.load_state_dict(checkpoint['optimizer_state'])
        scheduler.load_state_dict(checkpoint['scheduler_state'])
        scaler.load_state_dict(checkpoint['scaler_state'])
        return checkpoint['epoch'], checkpoint['best_val_loss']


    # 性能分析
    def count_parameters(model):
        return sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    print(f"模型可训练参数数量: {count_parameters(model):,}")

    # FLOPs计算
    flop_counter = FlopCounterMode(model, depth=1)
    with flop_counter:
        dummy_input = torch.randn(1, 4096).to(device)
        model(dummy_input)
    print(f"模型FLOPs: {flop_counter.get_total_flops()/1e9:.2f} GFLOPs")

    # 模型测试
    try:
        test_input = torch.randn(8, 4096).to(device)
        output = model(test_input)
        print("模型测试输出形状:", output.shape)
    except Exception as e:
        print("模型测试失败:", e)
        exit()


    # 修改测试模式配置
    # 在测试模式配置后添加
# 测试模式配置 (放在训练配置部分)
test_mode = True
max_test_batches = 5
test_metrics = {
    'batch_times': [],
    'loss_values': [],
    'grad_norms': []
}

# 测试循环 (放在训练循环中)
if test_mode:
    print("\n=== 开始系统测试 ===")
    
    # 1. 数据加载测试
    print("1. 数据加载器测试")
    sample = next(iter(train_loader))
    print(f"Batch形状: inputs={sample[0].shape}, labels={sample[1].shape}")
    
    # 2. 模型前向传播测试
    print("2. 模型前向传播测试")
    test_output = model(sample[0].to(device))
    print(f"模型输出形状: {test_output.shape}")
    
    # 3. 损失计算测试
    print("3. 损失计算测试")
    loss = criterion(test_output, sample[1].to(device))
    print(f"初始loss值: {loss.item():.4f}")

    # 训练过程中的测试验证
    for i, batch in enumerate(itertools.islice(train_loader, max_test_batches)):
        inputs, labels = [x.to(device) for x in batch]
        
        # 输入数据验证
        if i == 0:
            print(f"\n测试模式 - 输入数据验证:")
            print(f"输入形状: {inputs.shape} 范围: [{inputs.min():.4f}, {inputs.max():.4f}]")
            print(f"标签分布: {torch.bincount(labels)}")
        
        # 前向传播
        outputs = model(inputs)
        loss = criterion(outputs, labels)
        
        # 输出验证
        if i == 0:
            print(f"输出形状: {outputs.shape} 范围: [{outputs.min():.4f}, {outputs.max():.4f}]")
            print(f"初始loss值: {loss.item():.4f}")
        
        # 反向传播和梯度验证
        loss.backward()
        grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        if i == 0:
            print(f"裁剪后梯度范数: {grad_norm:.4f}")
        
        # 记录测试指标
        test_metrics['batch_times'].append(time.time() - batch_start)
        test_metrics['loss_values'].append(loss.item())
        test_metrics['grad_norms'].append(grad_norm)
    
    # 测试结果摘要
    print("\n测试模式结果摘要:")
    print(f"平均batch时间: {sum(test_metrics['batch_times'])/len(test_metrics['batch_times']):.4f}s")
    print(f"平均loss值: {sum(test_metrics['loss_values'])/len(test_metrics['loss_values']):.4f}")
    print(f"平均梯度范数: {sum(test_metrics['grad_norms'])/len(test_metrics['grad_norms']):.4f}")
    print("学习率变化:", [f"{g['lr']:.2e}" for g in optimizer.param_groups])
    
    # 测试完成后退出
    exit()


    # 在训练循环前添加
    print("\n=== 开始系统测试 ===")
    print("1. 数据加载器测试")
    sample = next(iter(train_loader))
    print(f"Batch形状: inputs={sample[0].shape}, labels={sample[1].shape}")

    print("2. 模型前向传播测试")
    test_output = model(sample[0].to(device))
    print(f"模型输出形状: {test_output.shape}")

    print("3. 损失计算测试")
    loss = criterion(test_output, sample[1].to(device))
    print(f"初始loss值: {loss.item():.4f}")


    # 在训练开始前添加恢复逻辑
    resume_path = "best_deepseekv3_sleep_model.pth"  # 可改为用户指定路径
    if os.path.exists(resume_path):
        print(f"\n发现检查点文件，从 {resume_path} 恢复训练...")
        start_epoch, best_val_loss = load_checkpoint(resume_path)
    else:
        start_epoch = 0


    # 训练配置
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=0.01)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=1e-3,
        steps_per_epoch=len(train_loader),
        epochs=100,
        pct_start=0.3,
        anneal_strategy='cos'
    )
    scaler = GradScaler()
    max_grad_norm = 1.0
    warmup_epochs = 5
    best_val_loss = float('inf')
    patience = 3
    no_improve = 0

    # 在训练配置后添加测试模式开关
    test_mode = True  # 设为False关闭测试模式
    max_test_batches = 5  # 测试模式下最大batch数


    # 训练循环
    for epoch in range(100):
        # 学习率warmup
        if epoch < warmup_epochs:
            lr_scale = min(1.0, float(epoch + 1) / warmup_epochs)
            for param_group in optimizer.param_groups:
                param_group['lr'] = lr_scale * 1e-4

        model.train()
        train_loss = 0
        start_time = time.time()
        
        try:
            # 测试模式下简化数据加载
            loader = train_loader if not test_mode else \
                    itertools.islice(train_loader, max_test_batches)
            
            for i, batch in enumerate(tqdm(loader, desc=f"Epoch {epoch+1}")):
                try:
                    batch_start = time.time()
                    inputs, labels = [x.to(device, non_blocking=True) for x in batch]
                    
                    # 测试模式下验证输入数据
                    if test_mode and i == 0:
                        print(f"\n测试模式 - 输入数据验证:")
                        print(f"输入形状: {inputs.shape} 范围: [{inputs.min():.4f}, {inputs.max():.4f}]")
                        print(f"标签分布: {torch.bincount(labels)}")
                    
                    optimizer.zero_grad(set_to_none=True)
                    
                    with autocast():
                        outputs = model(inputs)
                        loss = criterion(outputs, labels)
                    
                    # 测试模式下验证模型输出
                    if test_mode and i == 0:
                        print(f"输出形状: {outputs.shape} 范围: [{outputs.min():.4f}, {outputs.max():.4f}]")
                        print(f"初始loss值: {loss.item():.4f}")
                    
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    
                    # 梯度裁剪和验证
                    grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
                    if test_mode and i == 0:
                        print(f"裁剪后梯度范数: {grad_norm:.4f}")
                    
                    scaler.step(optimizer)
                    scaler.update()
                    scheduler.step()

                    train_loss += loss.item()
                    batch_time = time.time() - batch_start
                    writer.add_scalar('Timing/Batch_Time', batch_time, epoch * len(train_loader) + i)
                    
                    # 测试模式下简化统计记录
                    if not test_mode and i % 100 == 0:
                        grad_norms = [p.grad.norm().item() 
                                    for p in model.parameters() 
                                    if p.grad is not None]
                        if grad_norms:
                            writer.add_scalar('Gradient/Norm', sum(grad_norms)/len(grad_norms), epoch * len(train_loader) + i)
                
                except RuntimeError as e:
                    if 'CUDA out of memory' in str(e):
                        torch.cuda.empty_cache()
                        print(f"Batch {i}内存不足，跳过并清理缓存")
                        continue
                    raise

        except Exception as e:
            print(f"训练在epoch {epoch}中断: {str(e)}")
            torch.save({
                'epoch': epoch,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'loss': train_loss / (i+1 if i>0 else 1)
            }, f"crash_recovery_epoch{epoch}.pth")
            raise




        # 每个epoch结束后记录权重统计
        weights = [p.data.abs().mean().item() for p in model.parameters()]
        writer.add_scalar('Weight/Mean', sum(weights)/len(weights), epoch)
        writer.add_histogram('Weight/Distribution', torch.tensor(weights), epoch)


        # 在验证阶段前初始化
        all_preds = []
        all_labels = []
        # 在验证阶段收集预测概率
        all_probs = []
        # 验证阶段
        model.eval()
        val_loss, correct, total = 0, 0, 0
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs, labels = inputs.to(device), labels.to(device)
                with autocast():
                    outputs = model(inputs)
                    loss = criterion(outputs, labels)
                    probs = torch.softmax(outputs, dim=1)
                all_probs.append(probs.cpu())

                val_loss += loss.item()
                preds = outputs.argmax(1)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(labels.cpu().numpy())
                total += labels.size(0)
                correct += (preds == labels).sum().item()

        # 计算指标
        avg_train_loss = train_loss / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)
        accuracy = correct / total
        
        # 日志记录
        log_msg = (f"Epoch {epoch+1}:\n"
                  f"  训练损失: {avg_train_loss:.4f}\n"
                  f"  验证损失: {avg_val_loss:.4f}\n"
                  f"  验证准确率: {accuracy:.2%}\n"
                  f"  学习率: {optimizer.param_groups[0]['lr']:.2e}\n"
                  f"  正确样本数: {correct}/{total}")
        print(log_msg)

        # TensorBoard记录
        writer.add_scalar('Metrics/Train_Loss', avg_train_loss, epoch)
        writer.add_scalar('Metrics/Val_Loss', avg_val_loss, epoch)
        writer.add_scalar('Metrics/Accuracy', accuracy, epoch)
        writer.add_scalar('Metrics/Correct_Samples', correct, epoch)
        writer.add_scalar('Params/Learning_Rate', optimizer.param_groups[0]['lr'], epoch)

        # 显存监控
        if torch.cuda.is_available():
            mem_info = torch.cuda.memory_stats(device)
            writer.add_scalar('Memory/Allocated', mem_info['allocated_bytes.all.current']/1e6, epoch)
            writer.add_scalar('Memory/Reserved', mem_info['reserved_bytes.all.current']/1e6, epoch)

        # 模型保存
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            no_improve = 0
            # 添加训练集指标和更多元数据
            torch.save({
                'epoch': epoch,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'scheduler_state': scheduler.state_dict(),
                'scaler_state': scaler.state_dict(),
                'train_loss': avg_train_loss,
                'val_loss': avg_val_loss,
                'accuracy': accuracy,
                'confusion_matrix': confusion_matrix(all_labels, all_preds),
                'flops': flop_counter.get_total_flops(),
                'config': model_args.__dict__,
                'class_names': ['清醒','浅睡','深睡','REM'],
                'git_hash': os.popen('git rev-parse HEAD').read().strip() if os.path.exists('.git') else None
            }, f"best_deepseekv3_sleep_model_epoch{epoch}.pth")
            # 同时保存精简版模型
            torch.save(model.state_dict(), f"best_deepseekv3_sleep_model_lite_epoch{epoch}.pth")
        # 替换现有的早停逻辑
        else:
            no_improve += 1
            # 添加学习率衰减后的早停判断
            current_lr = optimizer.param_groups[0]['lr']
            min_lr = 1e-6  # 最小学习率阈值
            
            if no_improve >= patience and current_lr <= min_lr:
                print(f"早停触发 - 验证损失未改善达{patience}个epoch且学习率已降至最低")
                # 保存最终检查点
                torch.save({
                    'epoch': epoch,
                    'model_state': model.state_dict(),
                    'optimizer_state': optimizer.state_dict(),
                    'final_val_loss': avg_val_loss
                }, "final_checkpoint.pth")
                break
            elif no_improve >= patience:
                print(f"重置早停计数器 - 学习率从{current_lr:.2e}降至{current_lr*0.5:.2e}")
                no_improve = 0  # 重置计数器
            # 学习率衰减


        # 定期检查点
        if (epoch + 1) % 5 == 0:
            torch.save({
                'epoch': epoch,
                'model_state': model.state_dict(),
                'optimizer_state': optimizer.state_dict(),
                'loss': avg_val_loss
            }, f'checkpoint_epoch_{epoch+1}.pth')
        # 每个epoch结束后添加
        if epoch % 5 == 0:  # 每5个epoch保存一次
            cm = confusion_matrix(all_labels, all_preds)
            plt.figure(figsize=(10,8))
            sns.heatmap(cm, annot=True, fmt='d')
            plt.title(f"Confusion Matrix - Epoch {epoch}")
            writer.add_figure('Confusion_Matrix', plt.gcf(), epoch)
            plt.close()
            
            print("\n分类报告:")
            print(classification_report(all_labels, all_preds, target_names=['清醒','浅睡','深睡','REM']))
            writer.add_text('Classification_Report', classification_report(all_labels, all_preds, target_names=['清醒','浅睡','深睡','REM']), epoch)
    
            # 每10个epoch绘制ROC曲线
        if epoch % 10 == 0:
            from sklearn.preprocessing import label_binarize
            from sklearn.metrics import roc_curve, auc
            
            probs = torch.cat(all_probs).numpy()
            y_true = label_binarize(all_labels, classes=[0,1,2,3])
            
            plt.figure(figsize=(10,8))
            for i in range(4):
                fpr, tpr, _ = roc_curve(y_true[:,i], probs[:,i])
                roc_auc = auc(fpr, tpr)
                plt.plot(fpr, tpr, label=f'Class {i} (AUC = {roc_auc:.2f})')
            
            plt.plot([0,1],[0,1],'k--')
            plt.xlim([0.0,1.0])
            plt.ylim([0.0,1.05])
            plt.xlabel('False Positive Rate')
            plt.ylabel('True Positive Rate')
            plt.title('ROC Curve')
            plt.legend(loc="lower right")
            writer.add_figure('ROC_Curve', plt.gcf(), epoch)
            plt.close()
            # 测试模式下简化验证流程

            if test_mode:
                print("\n测试模式结果摘要:")
                print(f"平均batch时间: {(time.time()-start_time)/min(len(train_loader), max_test_batches):.4f}s")
                print(f"最终loss值: {train_loss/min(len(train_loader), max_test_batches):.4f}")
                print("学习率变化:", [f"{g['lr']:.2e}" for g in optimizer.param_groups])
                break  # 测试模式下只运行一个epoch
    
    # 在训练结束后添加
    print("\n训练完成，开始模型优化...")
    try:
        # 量化模型
        quantized_model = torch.quantization.quantize_dynamic(
            model, {nn.Linear}, dtype=torch.qint8
        )
        torch.save(quantized_model.state_dict(), "quantized_deepseekv3_sleep_model.pth")
        print("成功生成8位量化模型")
    except Exception as e:
        print(f"模型量化失败: {str(e)}")

    # 添加ONNX导出
    try:
        dummy_input = torch.randn(1, 4096).to(device)
        torch.onnx.export(
            model,
            dummy_input,
            "deepseekv3_sleep_model.onnx",
            input_names=["eeg_input"],
            output_names=["sleep_stage"],
            dynamic_axes={
                'eeg_input': {0: 'batch_size'},
                'sleep_stage': {0: 'batch_size'}
            }
        )
        print("成功导出ONNX模型")
    except Exception as e:
        print(f"ONNX导出失败: {str(e)}")



    
    writer.close()
