
# src/model/deepseek_model.py
import torch
import torch.nn as nn
import sys
import os
from tqdm import tqdm
from torch.optim.lr_scheduler import ReduceLROnPlateau

# ... existing imports ...


print("PyTorch version:", torch.__version__)
print("CUDA available:", torch.cuda.is_available())

# Fix local import (assuming Base_Model is in a local module)
#from ..deepseek.models import Base_Model  # Modified import path


# Add this path configuration at the top
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


from deepseek.models import Base_Model  # <-- This import was missing



# Fix local import (assuming Base_Model is in a local module)
#from ..deepseek.models import Base_Model  # Modified import path

# 修改后的注意力层定义（增加维度转换）
class Custom_Model(Base_Model):
    
    def __init__(self, input_size, hidden_size, num_classes):
        super(Custom_Model, self).__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.attention = nn.MultiheadAttention(embed_dim=hidden_size, num_heads=4, batch_first=True)

        self.fc = nn.Linear(hidden_size, num_classes)
    def forward(self, x):
        out, _ = self.lstm(x) #保持形状（32，10，256）
        
        
        out, _ = self.attention(out, out, out)#直接使用原维度
        
        out = self.fc(out[:, -1, :])
        return out


def train_model(train_loader, val_loader, config):
    """
    训练模型并保存权重。
    """
    model = Custom_Model(config['input_size'], config['hidden_size'], config['num_classes'])
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=config['learning_rate'])

    scheduler = ReduceLROnPlateau(optimizer, 'min', patience=2, min_lr=1e-5)
        
    best_loss = float('inf')
    early_stop_counter = 0
    history = {'train_loss': [], 'val_loss': [], 'train_acc': [], 'val_acc': []}
    
    for epoch in range(config['num_epochs']):


         # Training phase
        model.train()
        running_loss = 0.0
        correct = 0
        total = 0
        for inputs, labels in tqdm(train_loader, desc=f'Epoch {epoch+1} Training'):
            outputs = model(inputs)
            loss = criterion(outputs, labels)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item()
            _, predicted = torch.max(outputs.data, 1)
            total += labels.size(0)
            correct += (predicted == labels).sum().item()

        train_loss = running_loss/len(train_loader)
        train_acc = correct/total
        history['train_loss'].append(train_loss)
        history['train_acc'].append(train_acc)


 # Validation phase
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        
        with torch.no_grad():
            for inputs, labels in val_loader:
                outputs = model(inputs)
                val_loss += criterion(outputs, labels).item()
                _, predicted = torch.max(outputs.data, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        val_loss /= len(val_loader)
        val_acc = correct/total
        history['val_loss'].append(val_loss)
        history['val_acc'].append(val_acc)
        
        # Update learning rate
        scheduler.step(val_loss)
        
        # Early stopping check
        if val_loss < best_loss:
            best_loss = val_loss
            torch.save(model.state_dict(), config['model_path'])
            early_stop_counter = 0
        else:
            early_stop_counter += 1
            if early_stop_counter >= config.get('patience', 5):
                print(f'Early stopping at epoch {epoch+1}')
                break

        # Print statistics
        print(f'Epoch {epoch+1}/{config["num_epochs"]}')
        print(f'Train Loss: {train_loss:.4f} | Acc: {train_acc:.2%}')
        print(f'  Val Loss: {val_loss:.4f} | Acc: {val_acc:.2%}')
        print(f'LR: {optimizer.param_groups[0]["lr"]:.2e}')
    
    return model, history

if __name__ == "__main__":
    # 基础配置示例
    config = {
        'input_size': 128,
        'hidden_size': 256,
        'num_classes': 5,
        'num_epochs': 50,
        'learning_rate': 1e-3,
        'model_path': 'best_model.pth',
        'patience': 5,       # 新增的早停参数
        'min_lr': 1e-5,      # 新增的学习率下限
        'verbose': True       # 新增的日志控制
    }
    
    # 如果已有基础配置，只需更新新增参数：
    config.update({
        'patience': 5,
        'min_lr': 1e-5,
        'verbose': True
    })
    
    print("Import test succeeded!")
    print("PyTorch version:", torch.__version__)
    
    # 实际使用时需要加载真实数据
    # train_loader, val_loader = get_data_loaders()
    # train_model(train_loader, val_loader, config)