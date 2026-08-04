# 在文件顶部添加
import os
import psutil  # 添加psutil导入
from exceptions import AudioGenerationError  # 修改为相对导入

# 修改后
from AISleepGen.exceptions import AudioGenerationError  # 完整包路径导入



from pathlib import Path
from ..config import settings

# Replace the hardcoded path with configurable one
config_path = os.path.join(settings.MODEL_DIR, "config.json")

try:
    with open(config_path, "r") as f:
        config = json.load(f)
except FileNotFoundError:
    raise FileNotFoundError(
        f"Model config file not found at {config_path}. "
        f"Please ensure the model files are in the correct location."
    )

os.environ.update({
    "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:16,garbage_collection_threshold:0.9",
    "PYTORCH_MEMORY_STATS": "1",
    "TOKENIZERS_PARALLELISM": "false",
    "PYTORCH_NO_CUDA_MEMORY_CACHING": "1",
    "MAX_CPU_MEMORY": f"{psutil.virtual_memory().total * 0.7:.0f}"  # 限制使用70%总内存

})
# 在文件顶部添加os模块导入
import glob  # 添加glob模块导入
import gc

from generate_demo import TherapeuticAudioGenerator
import json
with open("E:/DeepSeek-V3-0324/config.json", "r") as f:
    print(json.load(f))  # 检查是否能正常解析
import torch  # 添加torch导入
from safetensors import safe_open
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig,BitsAndBytesConfig  # 添加AutoConfig
from accelerate import init_empty_weights, load_checkpoint_and_dispatch
import time
# 修改为从项目根目录导入
import sys
import openai
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
from exceptions import AudioGenerationError  # 需要先定义这个异常类

from integrations.exceptions import AudioGenerationError

from transformers.configuration_utils import PretrainedConfig

from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig

# 禁用CUDA和量化
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
os.environ["DISABLE_QUANTIZATION"] = "1"
os.environ["PYTORCH_MEMORY_STATS"] = "1"  # 启用内存统计



# 在模型加载前添加磁盘空间检查
import shutil

# 在文件顶部添加
import torch
from safetensors import safe_open
# -*- coding: utf-8 -*-

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from importlib.metadata import version, PackageNotFoundError

from accelerate import init_empty_weights, load_checkpoint_and_dispatch

# 检查Python版本
print(f"Python版本: {sys.version}")

# 检查关键依赖库版本
required_packages = {
    'torch': '2.0.0',
    'transformers': '4.30.0',
    'accelerate': '0.20.0'
}

for pkg, min_version in required_packages.items():
    try:
        installed = version(pkg)
        print(f"{pkg}版本: {installed} (需要: >= {min_version})")
        from packaging import version as pkg_version
        if pkg_version.parse(installed) < pkg_version.parse(min_version):
            print(f"警告: {pkg}版本过低!")
    except PackageNotFoundError:
        print(f"未找到依赖包: {pkg}")
    except Exception as e:
        print(f"检查{pkg}版本时出错: {str(e)}")



def load_model_config(model_path):
    # Use test path if running in test environment
    if "test_models" in model_path:
        config_path = os.path.join(model_path, "config.json")
    else:
        config_path = os.path.join(model_path, "config.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found at {config_path}")
    
    with open(config_path, "r") as f:
        return json.load(f)


# 替换原有的quant_config定义
quant_config = None  # 禁用bitsandbytes量化

# 配置量化参数
quant_config = BitsAndBytesConfig(
    load_in_4bit=False,  # 禁用4bit量化
    bnb_4bit_use_double_quant=False,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

print(f"可用CPU核心数: {os.cpu_count()}")
print(f"系统总内存: {psutil.virtual_memory().total / (1024**3):.2f} GB")

with safe_open("E:/DeepSeek-V3-0324/model-00001-of-000163.safetensors", framework="pt") as f:
    print(list(f.keys())[:10])  # 打印前10个权重键名

# 在文件顶部添加
from typing import Optional

def safe_load_model(model_path: str, max_retries: int = 3) -> Optional[dict]:
    """带重试的模型加载"""
    for attempt in range(max_retries):
        try:
            return load_deepseek_model()
        except Exception as e:
            print(f"加载失败(尝试 {attempt+1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                return None
            time.sleep(5)  # 等待后重试


def check_disk_space():
    total, used, free = shutil.disk_usage("E:/")  # 模型所在磁盘
    print(f"磁盘空间: 总共{total//(2**30)}GB, 已用{used//(2**30)}GB, 剩余{free//(2**30)}GB")
    if free < 50 * 1024**3:  # 小于50GB
        raise RuntimeError("磁盘空间不足(需要至少50GB空闲空间)")



# 修改generate_text函数
def generate_text(model_dict, prompt):
    """使用加载的模型生成文本"""
    try:

        
        
        model = model_dict['model']
        tokenizer = model_dict['tokenizer']
        print(f"Tokenizer配置: {tokenizer.special_tokens_map}")
        # 强制设置必要的token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        if tokenizer.eos_token is None:
            tokenizer.eos_token = "</s>"
        
        # 创建输入并生成attention_mask
        inputs = tokenizer(
            prompt,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        ).to(model.device)
                # 在加载tokenizer后添加检查
        print(f"Tokenizer配置: pad_token={tokenizer.pad_token}, eos_token={tokenizer.eos_token}")
        print(f"Tokenizer特殊token: {tokenizer.special_tokens_map}")

        # 测试tokenizer编码解码
        test_text = "测试文本"
        encoded = tokenizer.encode(test_text)
        decoded = tokenizer.decode(encoded)
        print(f"编码解码测试: {test_text} -> {encoded} -> {decoded}")

        # 生成输出
        outputs = model.generate(
            input_ids=inputs.input_ids,
            attention_mask=inputs.attention_mask,
            max_new_tokens=200,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
        
        # 解码时跳过特殊token
        return tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        
    except torch.cuda.OutOfMemoryError:
        gc.collect()
        torch.cuda.empty_cache()
        return "内存不足，请尝试减小输入长度或使用更小模型"
    except Exception as e:
        error_info = {
            "error": str(e),
            "timestamp": time.time(),
            "prompt": prompt,
            "model": model_dict.get('model').__class__.__name__ if model_dict else None
        }
        with open("error_log.json", "a") as f:
            json.dump(error_info, f)
        raise






# 修改自定义配置类定义部分
class DeepSeekVLConfig(PretrainedConfig):
    model_type = "deepseek_vl_v2"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 从config.json中提取关键参数
        self.hidden_size = kwargs.get("hidden_size", 7168)
        self.num_attention_heads = kwargs.get("num_attention_heads", 128)
        self.num_hidden_layers = kwargs.get("num_hidden_layers", 61)
        self.vocab_size = kwargs.get("vocab_size", 129280)
        # 添加其他必要参数...

# 在加载模型前注册配置类
AutoConfig.register("deepseek_vl_v2", DeepSeekVLConfig)



def load_model(model_type="deepseek", model_path=None):
    """统一模型加载接口"""
    loader_map = {
        "deepseek": load_deepseek_model,
        "small": load_small_model,
        "tiny": load_tiny_model,
        "distill": load_distill_model
    }
    
    if model_type not in loader_map:
        raise ValueError(f"不支持的模型类型: {model_type}")
    
    # 如果提供了路径，覆盖默认路径
    if model_path:
        os.environ["MODEL_PATH"] = model_path
    
    return loader_map[model_type]()

# 确保在加载模型前设置正确的模型类型
# 修改load_distill_model函数
def load_distill_model():
    check_disk_space()

    """加载DeepSeek-R1-Distill-Qwen-1.5B模型"""
    local_model_path = r"E:\DeepSeek-R1-Distill-Qwen-1.5B"
    try:
        # 强制完全离线模式
        os.environ.update({
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1"
        })
    

        # 直接加载模型，不自定义配置类 # 添加模型文件完整性检查
        print("检查模型文件完整性...")
        for shard in glob.glob(os.path.join(local_model_path, "model-*-of-*.safetensors")):
            try:
                with safe_open(shard, framework="pt") as f:
                    _ = f.keys()  # 尝试读取文件头
            except Exception as e:
                raise RuntimeError(f"模型分片文件损坏: {shard}, 错误: {str(e)}")
        # 在加载tokenizer时添加fallback设置
        tokenizer = AutoTokenizer.from_pretrained(
            local_model_path,
            pad_token='<pad>',
            eos_token='</s>',
            trust_remote_code=True
        )

        
        model = AutoModelForCausalLM.from_pretrained(
            local_model_path,
            local_files_only=True,
            trust_remote_code=True,
            device_map="auto",
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            offload_folder="./offload"
        )
        
        return {
            'model': model,
            'tokenizer': AutoTokenizer.from_pretrained(
                local_model_path,
                local_files_only=True,
                trust_remote_code=True
            )
        }
        
    except Exception as e:
        print(f"加载失败: {str(e)}")
        raise RuntimeError(f"模型加载失败: {str(e)}")
def check_model_weights(model_path):
    """检查模型权重文件中是否包含aligner相关键"""
    print("检查权重文件中是否包含aligner相关键...")
    for weight_file in glob.glob(os.path.join(model_path, "*.safetensors")):
        try:
            with safe_open(weight_file, framework="pt") as f:
                keys = list(f.keys())
                aligner_keys = [k for k in keys if "aligner" in k.lower()]
                if aligner_keys:
                    print(f"警告: 权重文件 {weight_file} 包含aligner相关键: {aligner_keys}")
                    # 创建不包含这些键的新文件
                    new_file = weight_file + ".clean"

                    # 修复safe_open的写入方式
                    import torch
                    tensors = {k: f.get_tensor(k) for k in keys if "aligner" not in k.lower()}
                    torch.save(tensors, new_file)
                    print(f"已创建清理后的权重文件: {new_file}")
        except Exception as e:
            print(f"检查权重文件 {weight_file} 时出错: {str(e)}")
# 在文件顶部添加云服务配置
def setup_cloud_gpu(provider="auto"):
    """配置云端GPU环境"""
    if provider == "auto":
        # 自动检测可用的云服务
        try:
            import colab
            provider = "colab"
        except:
            try:
                import kaggle
                provider = "kaggle"
            except:
                provider = "none"

    if provider == "colab":
        # Google Colab配置
        from google.colab import drive
        drive.mount('/content/drive')
        os.environ["MODEL_PATH"] = "/content/drive/MyDrive/models"
        return "cuda"
    
    elif provider == "kaggle":
        # Kaggle配置
        os.environ["MODEL_PATH"] = "/kaggle/input/models"
        return "cuda"
    
    elif provider == "aws":
        # AWS SageMaker配置
        os.environ["MODEL_PATH"] = "/opt/ml/model"
        return "cuda"
    
    else:
        raise ValueError("未检测到可用的云服务")

def load_small_model():
    """加载精简版模型"""
    check_disk_space()
    small_model_path = r"E:\DeepSeek-1.3b\Janus-1.3B"

    # 检查并清理权重文件
    check_model_weights(small_model_path)
    clean_model_path = os.path.join(small_model_path, "model.safetensors.clean")
    if not os.path.exists(clean_model_path):
        raise FileNotFoundError("清理后的权重文件不存在")

    try:
        # 检测并配置云端GPU
        device = setup_cloud_gpu()
        # 内存检查
        mem = psutil.virtual_memory()
        min_mem = int(8 * 1024**3 * 1.2)  # 8GB + 20%缓冲
        if mem.available < min_mem:
            gc.collect()
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            time.sleep(10)
            mem = psutil.virtual_memory()
            if mem.available < min_mem:
                raise RuntimeError(f"内存不足(需要{min_mem/1024**3:.1f}GB, 可用{mem.available/1024**3:.1f}GB)")

        # 内存优化配置
        os.environ.update({
            "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:16",# 更小的分片大小
            "MAX_CPU_MEMORY": "6GB",
            "PYTORCH_NO_CUDA_MEMORY_CACHING": "1",
            "TOKENIZERS_PARALLELISM": "false"
        })

        # 检查模型文件
        weight_files = glob.glob(os.path.join(small_model_path, "*.safetensors")) + \
                     glob.glob(os.path.join(small_model_path, "*.bin")) + \
                     glob.glob(os.path.join(small_model_path, "*.pt")) + \
                     glob.glob(os.path.join(small_model_path, "*.pth"))
        if not weight_files:
            raise FileNotFoundError("未找到有效的模型权重文件")

        # 修改配置文件
        config_path = os.path.join(small_model_path, "config.json")
        with open(config_path, "r") as f:
            config_data = json.load(f)
        
        # 清理配置
        config_data = {
            k: v for k, v in config_data.items() 
            if not any(x in k.lower() for x in ["aligner", "adapter", "lora"])
        }
        config_data.update({
            "model_type": "llama",
            "hidden_size": 1024,  # 降低隐藏层大小
            "num_attention_heads": 8,
            "num_hidden_layers": 12,  # 减少层数
            "architectures": ["LlamaForCausalLM"],
            "torch_dtype": "float16",
            "ignore_mismatched_sizes": True
        })
        
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        # 加载模型
        print("开始加载模型权重...")
        start_time = time.time()
        
        gc.collect()
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
        time.sleep(5)

        # 修改模型加载配置
        model = AutoModelForCausalLM.from_pretrained(
            small_model_path,
            trust_remote_code=False,
            device_map="auto" if device == "cuda" else "cpu",
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True,
            offload_folder="./offload",
            max_memory={"cpu": "4GB", "cuda": "16GB"} if device == "cuda" else {"cpu": "4GB"},
            offload_state_dict=True,
            load_in_4bit=True
        )

        # 加载tokenizer
        print("加载tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            small_model_path,
            padding_side="left",
            truncation_side="left"
        )

        # 设置必要的token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token if tokenizer.eos_token else "<pad>"
        if tokenizer.eos_token is None:
            tokenizer.eos_token = "</s>"

        print(f"模型加载完成，耗时: {time.time()-start_time:.2f}秒")
        return {
            'model': model,
            'tokenizer': tokenizer
        }

    except Exception as e:
        print(f"\n小模型加载失败详情:")
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("\n系统资源状态:")
        print(f"内存使用: {psutil.virtual_memory().percent}%")
        print(f"CPU使用: {psutil.cpu_percent()}%")
        if torch.cuda.is_available():
            print(f"GPU内存: {torch.cuda.memory_allocated()/1024**3:.2f}GB/{(torch.cuda.memory_reserved()/1024**3):.2f}GB")
        raise RuntimeError(f"模型加载失败: {str(e)}")



def load_deepseek_model():
    """加载DeepSeek模型(强制完全离线模式)"""

    check_disk_space()

    # 关闭非必要进程
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] in ['chrome.exe', 'Teams.exe', 'OneDrive.exe']:  # 常见耗内存程序
            try:
                proc.kill()
            except Exception:
    try:
        model_path = "E:/DeepSeek-V3-0324"
        print(f"开始加载模型，路径: {model_path}")
        # 添加模型文件完整性检查
        print("检查模型文件完整性...")
        for shard in glob.glob(os.path.join(model_path, "model-*-of-*.safetensors")):
            try:
                with safe_open(shard, framework="pt") as f:
                    _ = f.keys()  # 尝试读取文件头
            except Exception as e:
                raise RuntimeError(f"模型分片文件损坏: {shard}, 错误: {str(e)}")
        os.environ["TRANSFORMERS_VERBOSITY"] = "debug"

        # 强制完全离线模式
        os.environ.update({
            "TRANSFORMERS_OFFLINE": "1",
            "HF_DATASETS_OFFLINE": "1",
            "HF_HUB_OFFLINE": "1",
            "SAFETENSORS_FAST_GPU": "1",
            "DISABLE_QUANTIZATION": "1",
            "PYTORCH_NO_CUDA_MEMORY_CACHING": "1",
            "CUDA_LAUNCH_BLOCKING": "0",
            "MAX_CPU_MEMORY": f"{psutil.virtual_memory().available * 0.8:.0f}"  # 使用80%可用内存
            
        })

        with safe_open("E:/DeepSeek-V3-0324/model-00001-of-000163.safetensors", framework="pt") as f:
            print(f.keys())  # 检查是否能列出所有键名

        # 详细检查分片文件
        shard_files = sorted(glob.glob(os.path.join(model_path, "model-*-of-*.safetensors")))
        print(f"找到{len(shard_files)}个分片文件")


        
        if len(shard_files) != 163:
            missing = set(f"model-{i:05d}-of-000163.safetensors" for i in range(1,164)) - set(os.path.basename(f) for f in shard_files)
            raise FileNotFoundError(f"缺少分片文件: {missing}")

        # 添加哈希校验
        import hashlib
        for shard in shard_files:
            with open(shard, 'rb') as f:
                file_hash = hashlib.md5(f.read()).hexdigest()
                print(f"{os.path.basename(shard)} 哈希: {file_hash}")

        # 检查关键文件（不包括index.json，因为后面会创建）
        required_files = ["config.json", "tokenizer.json"]
        for file in required_files:
            if not os.path.exists(os.path.join(model_path, file)):
                raise FileNotFoundError(f"必需文件缺失: {file}")

        # 改进的index文件处理逻辑
        index_file = os.path.join(model_path, "model.safetensors.index.json")
        if not os.path.exists(index_file):
            print("创建model.safetensors.index.json文件...")
            try:
                index_data = {
                    "metadata": {"total_size": sum(os.path.getsize(f) for f in shard_files)},
                    "weight_map": {f"weight_{i}": os.path.basename(f) 
                                 for i, f in enumerate(shard_files)}
                }
                # 使用临时文件确保原子性写入
                temp_file = index_file + ".tmp"
                with open(temp_file, "w") as f:
                    json.dump(index_data, f, indent=2)
                # 重命名临时文件为正式文件
                os.replace(temp_file, index_file)
                print("index文件创建成功")
            except Exception as e:
                raise RuntimeError(f"创建index文件失败: {str(e)}")

        config_path = "E:/DeepSeek-V3-0324/config.json"
        with open(config_path, "r") as f:
            config = json.load(f)
        if "quantization_config" in config:
            del config["quantization_config"]
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

        # 加载配置
        config = AutoConfig.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=True
        )
        # 更彻底地处理量化配置
        if hasattr(config, 'quantization_config'):
            delattr(config, 'quantization_config')
        config.rope_scaling = None

        # 强制CPU模式
        print(f"当前内存使用: {psutil.virtual_memory().percent}%")
        print("开始加载模型权重...")
        
        try:
            # 添加详细内存监控
           
            gc.collect()     # 加载前强制垃圾回收
            torch.cuda.empty_cache() if torch.cuda.is_available() else None

            # 添加内存压力检查
            if psutil.virtual_memory().percent > 80:
                gc.collect()
                time.sleep(0.5)  # 加载模型前给更多时间回收内存

            print(f"加载前内存状态 - 已用: {psutil.virtual_memory().used/1024**3:.2f}GB, 可用: {psutil.virtual_memory().available/1024**3:.2f}GB")
            # 使用模型并行加载
            from accelerate import init_empty_weights, load_checkpoint_and_dispatch
            
            #使用空权重初始化模型结构
            with init_empty_weights():
                model = AutoModelForCausalLM.from_config(config, trust_remote_code=True)

            os.environ["BITSANDBYTES_NOWELCOME"] = "1"
            os.environ["DISABLE_QUANTIZATION"] = "1"
            
            os.environ["ACCELERATE_USE_CPU"] = "1"
            os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # 禁用CUDA
            # 使用更基础的加载方式
            # 使用更激进的内存优化配置
            # 修改为直接使用 from_pretrained 加载
            # 然后加载模型
            # 修改为更节省内存的加载方式
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                trust_remote_code=True,
                device_map={"": "cpu"},  # 更明确的CPU映射
                torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
                low_cpu_mem_usage=True,
                offload_state_dict=True,  # 启用状态字典卸载
                offload_folder="./offload",  # 指定卸载目录
                max_memory={"cpu": "30GB"}  # 限制最大内存使用
            )

             # 将模型移动到CPU
            model = model.to('cpu')
            print(f"加载后内存使用: {psutil.virtual_memory().percent}%")
            print("模型权重加载完成")

        except Exception as e:
            print(f"模型加载错误详情: {str(e)}")
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"模型权重加载失败: {str(e)}")

        # 加载tokenizer
        print("开始加载tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(
            model_path,
            local_files_only=True,
            trust_remote_code=True
        )
        
        print(f"DeepSeek模型加载完成(CPU模式), 共加载{len(shard_files)}个分片文件")
        return {
            'model': model,
            'tokenizer': tokenizer
        }

    except Exception as e:
        print(f"加载失败详情: {str(e)}")  # 更详细的错误日志
        import traceback
        traceback.print_exc()
        raise RuntimeError(f"模型加载失败: {str(e)}")






print(torch.cuda.is_available())  # 应该返回True



# 内存优化技术组合方案
optimization_strategies = {
    "分片加载": "自动处理163个分片文件",
    "权重卸载": "使用offload_folder临时存储不活跃的权重", 
    "内存映射": "通过low_cpu_mem_usage启用",
    "精度控制": "保持float32平衡精度和内存",
    "分层加载": "按需加载模型层",
    "延迟加载": "使用from_pretrained的延迟加载参数",
    "权重共享": "启用tie_word_embeddings减少内存占用"
}

# 或者使用更小的1.3B模型
# ... 其他代码保持不变 ...

# 修改配置类名以避免冲突
class CustomDeepseekV3Config(PretrainedConfig):
    model_type = "custom_deepseek_v3"  # 使用自定义名称
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # 从config.json中提取关键参数
        self.hidden_size = kwargs.get("hidden_size", 7168)
        self.num_attention_heads = kwargs.get("num_attention_heads", 128)
        self.num_hidden_layers = kwargs.get("num_hidden_layers", 61)
        self.vocab_size = kwargs.get("vocab_size", 129280)
        # 添加其他必要参数...

# 注册配置类时使用自定义名称
AutoConfig.register("custom_deepseek_v3", CustomDeepseekV3Config)



# 移除或注释掉以下自定义配置类
# class MultiModalityConfig(PretrainedConfig):
#     model_type = "multi_modality"
#     ...

# 修改load_tiny_model函数
def load_tiny_model():
    local_model_path = r"E:\DeepSeek-1.3b\deepseek-vl2-small"
    
    try:
        # 定义预期的文件哈希值
        expected_hashes = {
            "model-00001-of-000004.safetensors": "139D33A759915D128D03DFB87202F06F",
            # 添加其他文件的预期哈希值
        }

        # 检查文件完整性
        print("正在验证模型文件完整性...")
        for filename, expected_hash in expected_hashes.items():
            filepath = os.path.join(local_model_path, filename)
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"模型文件缺失: {filename}")
                
            # 计算实际哈希值
            import hashlib
            with open(filepath, 'rb') as f:
                actual_hash = hashlib.md5(f.read()).hexdigest().upper()
            
            if actual_hash != expected_hash:
                raise ValueError(f"文件校验失败: {filename}\n预期: {expected_hash}\n实际: {actual_hash}")
        
        print("所有模型文件校验通过")

   
        # ... file integrity check code remains the same ...

        # Replace DeepseekVLV2Processor with standard AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            local_model_path,
            trust_remote_code=True
        )
        
        # Replace DeepseekVLV2ForCausalLM with standard AutoModelForCausalLM
        model = AutoModelForCausalLM.from_pretrained(
            local_model_path,
            trust_remote_code=True,
            device_map="auto",
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True
        )
        
        return {
            'model': model,
            'tokenizer': tokenizer
        }
        
    except Exception as e:
        print(f"加载失败: {str(e)}")
        raise RuntimeError(f"模型加载失败: {str(e)}")

# ... rest of the file remains the same ...










def safe_model_load(model_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            # 添加更严格的内存检查
            mem = psutil.virtual_memory()
            required_mem = 16 * 1024**3  # 16GB最低要求
            if mem.available < required_mem:
                print(f"内存不足(需要{required_mem/1024**3:.1f}GB, 可用{mem.available/1024**3:.1f}GB)")
                gc.collect()
                time.sleep(5)  # 等待内存回收
            
            return AutoModelForCausalLM.from_pretrained(
                model_path,
                trust_remote_code=True,
                device_map="auto",
                torch_dtype=torch.float16,
                low_cpu_mem_usage=True,
                offload_state_dict=True,
                offload_folder="./offload",
                max_memory={"cpu": "8GB"}  # 限制内存使用
            )
        except Exception as e:
            print(f"加载失败(尝试 {attempt+1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                raise
            time.sleep(10)  # 等待后重试






try:
    from deepseek import DeepSeekGenerator
except ImportError:
    try:
        from deepseek.api import AudioGenerator as DeepSeekGenerator
    except ImportError:
        class MockDeepSeekGenerator:
            def generate(self, duration, bpm, style):
                print("WARNING: Using mock DeepSeek generator")
                return np.random.rand(duration * 44100, 2) * 0.1
        DeepSeekGenerator = MockDeepSeekGenerator

# ... rest of your existing code ...

class AgentCoordinator:
    def __init__(self):
        self.agents = []
        self.communication_log = []
    
    def register_agent(self, agent):
        """注册新的智能体"""
        if agent not in self.agents:
            self.agents.append(agent)
            # 让新智能体连接到所有现有智能体
            for existing_agent in self.agents[:-1]:
                agent.connect_to_peer(existing_agent)
                existing_agent.connect_to_peer(agent)
    
    def broadcast(self, sender, message):
        """协调广播消息"""
        self.communication_log.append({
            'sender': sender,
            'message': message,
            'timestamp': time.time()
        })
        for agent in self.agents:
            if agent != sender:
                agent.receive_message(sender, message)
    
    def collective_learning(self):
        """组织集体学习会话"""
        for agent in self.agents:
            knowledge = agent.share_knowledge()
            self.broadcast(agent, knowledge)

class EnhancedAudioGenerator(TherapeuticAudioGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        openai.api_key = "你的API密钥"  # 添加这行
        self.deepseek_api_key = "你的DeepSeek API密钥"  # 新增DeepSeek API密钥

        self.logger = logging.getLogger(__name__)
        self.peer_agents = []  # 存储其他智能体引用
        self.knowledge_base = {}  # 存储学习到的知识
        try:
            self.deepseek = DeepSeekGenerator()
            self.logger.info("DeepSeek生成器初始化成功")
        except Exception as e:
            self.logger.error(f"DeepSeek初始化失败: {str(e)}")
            raise AudioGenerationError("无法初始化AI生成引擎")
    
    def generate_with_ai(self, style="relaxing"):
        """使用DeepSeek生成音乐"""
        self.logger.info(f"开始生成{style}风格音乐...")
        try:
            # ... 原有代码保持不变 ...
            self.logger.info("音乐生成完成")
            return self
        except Exception as e:
            self.logger.error(f"生成失败: {str(e)}")
            raise AudioGenerationError("AI音乐生成失败")
    

    # ... 保留已有导入和类定义 ...

    def spectral_analysis(self):
        """频谱分析实现"""
        try:
            self.logger.info("正在进行频谱分析...")
            # 计算FFT频谱
            spectrum = np.fft.rfft(self.audio, axis=0)
            freq = np.fft.rfftfreq(len(self.audio), d=1.0/self.sr)
            
            # 记录频谱特征
            self.spectral_data = {
                'peak_freq': freq[np.argmax(np.abs(spectrum))],
                'energy_ratio': np.sum(np.abs(spectrum[1000:]))/np.sum(np.abs(spectrum))
            }
            return self.spectral_data
            
        except Exception as e:
            self.logger.error(f"频谱分析失败: {str(e)}")
            raise AudioGenerationError("频谱分析失败")

    def dynamic_range_compression(self, threshold=0.8, ratio=4):
        """动态范围压缩实现"""
        try:
            self.logger.info("应用动态范围压缩...")
            # 计算信号幅度
            amplitude = np.abs(self.audio)
            # 压缩超过阈值的部分
            gain_reduction = np.where(
                amplitude > threshold,
                (amplitude - threshold) / ratio,
                0
            )
            self.audio = np.sign(self.audio) * (amplitude - gain_reduction)
            return self
            
        except Exception as e:
            self.logger.error(f"动态压缩失败: {str(e)}")
            raise AudioGenerationError("动态压缩处理失败")

    def analyze_music(self, audio_path):
        """分析音乐特征"""
        try:
            # 加载音频
            audio, sr = librosa.load(audio_path, sr=self.sr)
            
            # 提取特征
            features = {
                'tempo': librosa.beat.tempo(y=audio)[0],
                'chroma': librosa.feature.chroma_stft(y=audio, sr=sr),
                'mfcc': librosa.feature.mfcc(y=audio, sr=sr),
                'spectral_contrast': librosa.feature.spectral_contrast(y=audio, sr=sr)
            }
            return features
            
        except Exception as e:
            self.logger.error(f"音乐分析失败: {str(e)}")
            raise AudioGenerationError("音乐特征提取失败")

    def generate_similar(self, reference_path, creativity=0.3):
        """基于参考音乐生成类似音乐"""
        try:
            # 分析参考音乐
            features = self.analyze_music(reference_path)
            
            # 生成参数
            params = {
                'bpm': features['tempo'],
                'style': self._match_style(features['chroma']),
                'creativity': creativity
            }
            
            # 使用AI生成
            return self.generate_with_ai(**params)
            
        except Exception as e:
            self.logger.error(f"相似音乐生成失败: {str(e)}")
            raise AudioGenerationError("音乐生成失败")


    def enhance_audio(self):
        """音效增强处理"""
        # 实现你的音效增强算法
        try:
            self.logger.info("开始音效增强处理")
            # 1. 频谱分析
            self.spectral_analysis()
            

            
            # 1. 动态范围压缩
            compressed = np.tanh(self.audio * 0.8) * 0.95
            
            # 2. 高频增强
            sos = signal.butter(4, 4000, 'hp', fs=self.sr, output='sos')
            high_pass = signal.sosfilt(sos, compressed)
            # 添加频谱分析
            self.spectral_analysis() 
            # 添加动态压缩
            self.dynamic_range_compression()
            
            # 3. 混合处理结果
            self.audio = compressed * 0.7 + high_pass * 0.3
            self.audio = np.clip(self.audio, -0.99, 0.99)
            
            self.logger.info("音效增强完成")
            return self
            
        except Exception as e:
            self.logger.error(f"音效增强失败: {str(e)}")
            raise AudioGenerationError("音效处理失败")
        
        pass

    # 极简加载方案(牺牲性能保稳定)
    def load_minimal_model():
        from transformers import pipeline
        return pipeline(
            "text-generation",
            model="E:/DeepSeek-V3-0324",
            device="cpu",
            torch_dtype=torch.float32,
            framework="pt"
        )
    



    
    def connect_to_peer(self, peer):
        """连接到其他智能体"""
        if peer not in self.peer_agents:
            self.peer_agents.append(peer)
            self.logger.info(f"已连接到智能体: {peer}")
    
    def broadcast_message(self, message):
        """向所有连接的智能体广播消息"""
        for agent in self.peer_agents:
            try:
                agent.receive_message(self, message)
            except Exception as e:
                self.logger.error(f"向{agent}发送消息失败: {str(e)}")
    
    def receive_message(self, sender, message):
        """接收来自其他智能体的消息"""
        self.logger.info(f"收到来自{sender}的消息: {message}")
        # 在这里可以添加消息处理逻辑
        self.learn_from_message(message)
    
    def learn_from_message(self, message):
        """从消息中学习并更新知识库"""
        if isinstance(message, dict) and 'knowledge' in message:
            self.knowledge_base.update(message['knowledge'])
            self.logger.info("已更新知识库")
    
    def share_knowledge(self):
        """分享当前知识库"""
        return {
            'sender': str(self),
            'knowledge': self.knowledge_base
        }


    
    def query_openai(self, prompt, model="gpt-4"):
        """与OpenAI API交互的封装方法"""
        try:
            import openai
            response = openai.ChatCompletion.create(
                model=model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response['choices'][0]['message']['content']
        except Exception as e:
            self.logger.error(f"OpenAI API调用失败: {str(e)}")
            raise AudioGenerationError("AI服务调用失败")


    def query_llama(self, prompt, model="meta-llama/Meta-Llama-3-8B"):
        """与本地Llama3模型交互的封装方法"""
        try:
            from transformers import pipeline
            llama = pipeline("text-generation", model=model)
            return llama(prompt)[0]['generated_text']
        except Exception as e:
            self.logger.error(f"Llama3模型调用失败: {str(e)}")
            raise AudioGenerationError("本地模型调用失败")



    def query_deepseek(self, prompt, model="deepseek-chat"):
        """本地部署的DeepSeek模型交互方法"""
        try:
            # 加载本地模型
            model_dict = load_deepseek_model()  

            return generate_text(model_dict, prompt)
        except Exception as e:
            self.logger.error(f"本地DeepSeek模型调用失败: {str(e)}")
            raise AudioGenerationError("本地模型调用失败")



    def query_ai(self, prompt, provider="deepseek"):
        """统一AI查询接口"""
        if provider.lower() == "deepseek":
            return self.query_deepseek(prompt)
        elif provider.lower() == "openai":
            return self.query_openai(prompt)
        elif provider.lower() == "llama":
            return self.query_llama(prompt)
        else:
            raise ValueError(f"不支持的AI提供商: {provider}")









# ... 保留现有模型加载代码 ...

if __name__ == "__main__":
    local_model_path=r"E:\DeepSeek-1.3b\Janus-1.3B"  # 修改为你的本地路径
    try:
        print("加载Janus-1.3B模型..")
        # 在加载模型前添加文件检查
        required_files = ["config.json", "model.safetensors", "tokenizer.json"]
        for file in required_files:
            if not os.path.exists(os.path.join(local_model_path, file)):
                raise FileNotFoundError(f"必需文件缺失: {file}")
            
        # 在加载模型前修改config.json
        config_path = os.path.join(local_model_path, "config.json")
        with open(config_path, "r") as f:
            config_data = json.load(f)
        config_data["model_type"] = "llama"  # 修改为已知类型
        with open(config_path, "w") as f:
            json.dump(config_data, f)


        # 优先尝试加载主模型
       # model_dict = safe_load_model("E:/DeepSeek-V3-0324")
        
       # if model_dict is None:
       #     print("主模型加载失败，尝试加载小模型...")
        model_dict = load_small_model()  # 回退到小模型
        if model_dict is None:
            print("小模型加载失败，尝试加载tiny模型...")
       # model_dict = load_tiny_model()  # 最后尝试tiny模型
       # if model_dict is None:
       #     print("小模型加载失败，尝试加载tiny模型...")




        
        # 确保tokenizer能正确加载
        try:
            tokenizer = AutoTokenizer.from_pretrained(
                local_model_path,
                padding_side="left",
                truncation_side="left",
                revision="main"
            )
        except Exception as e:
            print(f"Tokenizer加载失败: {str(e)}")
            raise RuntimeError("无法加载tokenizer")

        # 添加最终系统资源检查
        if psutil.virtual_memory().percent > 90:
            gc.collect()
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
            print("警告: 内存使用超过90%，已尝试释放内存")


        # 生成文本
        response = generate_text(model_dict, "你好，介绍一下你自己")
        print(response)
        
        # 模型加载成功后再执行智能体测试
        print("\n模型加载成功，开始智能体测试...")
        

        # 创建协调器和多个智能体实例
        #coordinator = AgentCoordinator()
        
        #agent1 = EnhancedAudioGenerator()
        #agent2 = EnhancedAudioGenerator()
        
        # 注册智能体
        #coordinator.register_agent(agent1)
        #coordinator.register_agent(agent2)
        
        # 测试模型推理
        test_prompt = "你好，介绍一下你自己"
        print(f"\n测试提示: {test_prompt}")
        response = generate_text(model_dict, test_prompt)
        print(f"模型回复: {response}")
        
    except Exception as e:
        print(f"运行出错: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)  # 出错时退出程序
    finally:
        print("程序结束。")

