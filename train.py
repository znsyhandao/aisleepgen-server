from aisleep.model.deepseek.models import CNN_SleepModel
import torch

# 初始化并保存模型
model = CNN_SleepModel(input_channels=1)
torch.save(model.state_dict(), "D:/AISleepGen/models/initial_weights.pth")
print("已生成初始权重文件")
