from fastapi import FastAPI
from safetensors.torch import load_file
from src.aisleep.model.deepseek.official.DeepSeek_V3.model import DeepSeekModel
from src.aisleep.model.deepseek.official.DeepSeek_V3.config import ModelConfig
import os

app = FastAPI()

# 配置文件路径
CONFIG_PATH = "E:/DeepSeek-V3-0324/config.json"
MODEL_DIR = "E:/DeepSeek-V3-0324"


# 加载模型配置
model_config = ModelConfig.from_json(CONFIG_PATH)

# 修改配置以减少内存需求
model_config.vocab_size = 50000  # 减小词汇表大小
model_config.hidden_size = 4096  # 减小隐藏层大小

print("Model Config:", model_config)

expected_shards = 163  # 预期的分片文件数量
actual_shards = len([f for f in os.listdir(MODEL_DIR) if f.endswith(".safetensors")])
print(f"Expected shards: {expected_shards}, Actual shards: {actual_shards}")


# 初始化模型
model = DeepSeekModel(model_config)

# 加载分片权重
state_dict = {}
loaded_files = []  # 用于记录成功加载的分片文件
try:
    for file_name in sorted(os.listdir(MODEL_DIR)):
        if file_name.endswith(".safetensors"):
            file_path = os.path.join(MODEL_DIR, file_name)
            print(f"Loading shard: {file_name}")  # 打印正在加载的分片文件
            shard_state_dict = load_file(file_path)
            state_dict.update(shard_state_dict)  # 合并权重
            loaded_files.append(file_name)  # 记录成功加载的文件
    print("All shards loaded successfully!")
except Exception as e:
    print(f"Error loading shard: {e}")

# 检查是否所有分片文件都被加载
expected_shards = len([f for f in os.listdir(MODEL_DIR) if f.endswith(".safetensors")])
print(f"Expected shards: {expected_shards}, Loaded shards: {len(loaded_files)}")
if len(loaded_files) < expected_shards:
    print("Warning: Some shard files may be missing or corrupted!")

# 加载权重到模型
try:
    model.load_state_dict(state_dict)
    model.eval()
    print("Model loaded successfully!")
except Exception as e:
    model = None
    print(f"Error loading model: {e}")

@app.get("/")
def read_root():
    return {"message": "Welcome to FastAPI!"}

@app.get("/api/v1/deep-test")
def deep_test():
    if model is None:
        return {"status": "error", "message": "Model not loaded"}
    
    try:
        # 示例输入
        dummy_input = torch.randint(0, model_config.vocab_size, (1, 128))  # 假设输入是 token IDs
        output = model(dummy_input)  # 推理
        return {
            "status": "success",
            "hidden_states": output["hidden_states"].tolist(),
            "meditation_features": output["meditation_features"].tolist()
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}