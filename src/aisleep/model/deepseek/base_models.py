import torch
import torch.nn as nn

# 确认文件存在且包含正确类定义
class Base_Model(nn.Module):  # 类名必须与导入名称完全一致
    def __init__(self):
        super().__init__()
        self.hidden_size = 128  # SleepAdapter类依赖该属性
