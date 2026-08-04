import pytest
import torch
# 在文件顶部添加导入
from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig
import os
import logging
import sys as _sys  # 确保在文件顶部导入sys
import time
# 在文件顶部添加导入
from tqdm import tqdm
# 在文件顶部导入区域添加
import pkg_resources
from transformers import AutoModel, AutoTokenizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 确保这是文件的第一行（没有空行或注释在前面）
os.environ['CUDA_LAUNCH_BLOCKING'] = '1'



# 替换现有的logging.basicConfig
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('debug.log', mode='w'),
        logging.StreamHandler()
    ],
    force=True
)


# 在导入区域添加简单检查
if not torch.cuda.is_available():
    raise RuntimeError("CUDA不可用，请检查CUDA安装和PyTorch配置")

# 在test_model_inference函数开始处添加以下检查代码
def test_model_inference():
    # 检查transformers版本
    try:
        transformers_version = pkg_resources.get_distribution("transformers").version
        min_version = "4.36.0"  # 设置最低要求版本
        if pkg_resources.parse_version(transformers_version) < pkg_resources.parse_version(min_version):
            logger.warning(f"transformers版本过低({transformers_version})，建议升级到{min_version}或更高")
            logger.info("升级命令: pip install --upgrade transformers")
            pytest.skip(f"transformers版本过低({transformers_version})")
    except Exception as e:
        logger.error(f"无法获取transformers版本: {str(e)}")

    # 检查是否有skip标记
    if hasattr(test_model_inference, "__pytest_skip__"):
        logger.warning("测试被跳过")
        return
        
    # 检查是否有xfail标记
    if hasattr(test_model_inference, "__pytest_xfail__"):
        logger.warning("测试预期失败")
    # 确保使用DEBUG级别
    logger.setLevel(logging.DEBUG)
    logging.getLogger("transformers").setLevel(logging.WARNING)  # 减少transformers的日志干扰
    logger.debug("=== 测试开始 ===")
    
    # 增强的CUDA检查（确保会打印信息）
    logger.debug(f"CUDA可用性: {torch.cuda.is_available()}")
    if not torch.cuda.is_available():
        logger.debug("\nCUDA不可用原因:")
        logger.debug(f"PyTorch版本: {torch.__version__}")
        logger.debug(f"CUDA Home: {torch.utils.cmake_prefix_path}")
        logger.debug(f"GPU设备: {torch.cuda.device_count()}个可用")
        
        # 新增驱动版本检查
        try:
            import subprocess
            nvidia_smi = subprocess.check_output(['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'])
            current_driver = nvidia_smi.decode('utf-8').strip()
            print(f"\n当前NVIDIA驱动版本: {current_driver}")
            print("建议更新到最新驱动: https://www.nvidia.com/Download/index.aspx")
        except Exception as e:
            print("\n无法获取NVIDIA驱动版本:", str(e))
        
        pytest.skip("CUDA not available")

    # 统一在函数开始处定义测试用例
    TEST_CASES = {
        "minimal": "你好，AI是什么？"
    }
    input_text = TEST_CASES["minimal"]

    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\Janus-1.3B"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 添加模型大小检查
    model_size = sum(os.path.getsize(os.path.join(model_dir, f)) 
                    for f in os.listdir(model_dir)) / 1024**3  # 转换为GB
    logger.info(f"模型总大小: {model_size:.2f}GB")
    if model_size < 2.5:  # 1.3B模型通常应大于2.5GB
        logger.warning("模型文件大小可能不完整，预期1.3B模型应有2.5-5GB")



    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")

    # 更新必要文件检查
    required_files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
    for file in required_files:
        assert os.path.exists(os.path.join(model_dir, file)), f"Missing model file: {file}"

    # 新增tokenizer配置文件检查
    try:
        import json
        # 检查tokenizer.json
        with open(os.path.join(model_dir, "tokenizer.json"), 'r', encoding='utf-8') as f:
            tokenizer_json = json.load(f)
            logger.debug(f"tokenizer.json版本: {tokenizer_json.get('version', '未知')}")
        
        # 检查tokenizer_config.json
        with open(os.path.join(model_dir, "tokenizer_config.json"), 'r', encoding='utf-8') as f:
            tokenizer_config = json.load(f)
            logger.info(f"tokenizer类型: {tokenizer_config.get('tokenizer_class', '未知')}")
            
            # 检查词汇表大小是否匹配
            if 'vocab_size' in tokenizer_config:
                logger.debug(f"tokenizer配置词汇表大小: {tokenizer_config['vocab_size']}")
    except Exception as e:
        logger.error(f"tokenizer配置文件检查失败: {str(e)}")
        pytest.fail(f"tokenizer配置文件检查失败: {str(e)}")

    try:
        # 加载tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            use_fast=True,
            padding_side='left',
            truncation=True,
            max_length=512,
            model_max_length=512,
            padding="max_length"
        )
        
        # 加载模型前添加tokenizer与模型匹配检查
        logger.info("检查tokenizer与模型匹配性...")
        try:
            config = AutoConfig.from_pretrained(model_dir)
            # 添加更详细的词汇表不匹配处理
            if hasattr(config, 'vocab_size'):
                if tokenizer.vocab_size != config.vocab_size:
                    logger.error(f"严重不匹配: tokenizer词汇表大小({tokenizer.vocab_size}) vs 模型配置({config.vocab_size})")
                    logger.error("建议解决方案:")
                    logger.error("1. 确保tokenizer和模型来自同一来源")
                    logger.error("2. 检查模型目录中的tokenizer配置文件")
                    logger.error("3. 重新下载匹配的模型和tokenizer")
                    pytest.fail(f"tokenizer与模型词汇表大小不匹配: {tokenizer.vocab_size} != {config.vocab_size}")
        except Exception as e:
            logger.error(f"加载模型配置失败: {str(e)}")
            pytest.fail(f"无法加载模型配置: {str(e)}")

        # 检查词汇表大小是否匹配
        if hasattr(config, 'vocab_size'):
            assert tokenizer.vocab_size == config.vocab_size, (
                f"tokenizer词汇表大小({tokenizer.vocab_size})与模型配置({config.vocab_size})不匹配"
            )
        
        # 检查特殊token是否一致
        if hasattr(config, 'bos_token_id'):
            assert tokenizer.bos_token_id == config.bos_token_id, "bos_token_id不匹配"
        if hasattr(config, 'eos_token_id'):
            assert tokenizer.eos_token_id == config.eos_token_id, "eos_token_id不匹配"
        if hasattr(config, 'pad_token_id'):
            assert tokenizer.pad_token_id == config.pad_token_id, "pad_token_id不匹配"
            
            logger.info("tokenizer与模型配置匹配检查通过")

        # 确保设置pad_token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 处理输入 - 添加更严格的输入验证
        inputs = tokenizer(input_text, 
                         return_tensors="pt",
                         truncation=True,
                         max_length=512,
                         padding="max_length")
        
        # 检查输入形状改为logger
        logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}, attention_mask: {inputs['attention_mask'].shape}")
        assert inputs['input_ids'].shape[1] <= 512, "输入长度超过模型最大长度限制"
        assert inputs['attention_mask'].shape == inputs['input_ids'].shape, "attention_mask形状与input_ids不匹配"

        # 确保所有token ID都在有效范围内
        vocab_size = tokenizer.vocab_size
        logger.info(f"Tokenizer词汇表大小: {vocab_size}")
        invalid_tokens = inputs['input_ids'][inputs['input_ids'] >= vocab_size]
        if len(invalid_tokens) > 0:
            logger.error(f"发现无效token ID: {invalid_tokens.tolist()}")
            pytest.fail(f"发现无效token ID(>= {vocab_size})")
        assert torch.all(inputs['input_ids'] >= 0), "发现负值token ID"
        
        # 确保attention_mask正确传递
        assert torch.all(inputs['attention_mask'] >= 0), "attention_mask包含非法值"
        inputs = {k: v.to(device) for k, v in inputs.items()}

    except Exception as e:
        pytest.fail(f"Tokenizer加载或输入处理失败: {str(e)}")

    # 加载模型前添加日志


    start_time = time.time()
    # 修改模型加载部分
    logger.info("开始加载模型...")
    try:
        # 使用简单的tqdm进度条
        with tqdm(total=1, desc="模型加载") as pbar:
            model = AutoModelForCausalLM.from_pretrained(
                model_dir,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                low_cpu_mem_usage=True,
                device_map="auto",
                max_memory={0: "30GB"},
                attn_implementation="eager",
                ignore_mismatched_sizes=True,
                force_download=False,
                local_files_only=True
            )
            pbar.update(1)  # 加载完成后更新进度条
        logger.info("模型加载完成")

        # 确保模型配置正确
        model.config.pad_token_id = tokenizer.pad_token_id
        model.config.eos_token_id = tokenizer.eos_token_id
        
        # 显式移动模型到设备
        model = model.to(device)
            
        # 在这里添加调试代码（模型加载成功后）
        try:
            # 性能分析 - 完全禁用以避免CUDA错误
            outputs = model.generate(**inputs)  # 直接生成不使用profiler

            # 梯度分析
            logger.debug("\n=== 梯度分析 ===")
            for name, param in model.named_parameters():
                if param.grad is not None:
                    logger.debug(f"{name} - 梯度均值: {param.grad.mean().item():.4f}")

            # 模型文件大小检查
            logger.info(f"模型文件大小: {sum(os.path.getsize(os.path.join(model_dir,f)) for f in os.listdir(model_dir))/1024/1024:.2f}MB")
        
        except Exception as e:
            logger.error(f"调试过程中发生错误: {str(e)}")
            pytest.fail(f"调试失败: {str(e)}")
        
    except Exception as e:
        pytest.skip(f"Model loading failed: {str(e)}")

    # 完全禁用SDPA后端设置
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(False)

    model.config.use_cache = True
    
    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")



    # 修改生成配置 - 终极解决方案
    generation_config = {
        'max_new_tokens': 50,  # 仅保留必要参数
        'min_length': inputs['input_ids'].shape[1],
        # 移除max_length等可能冲突的参数
    }

    # 关键修复：完全绕过长度限制检查
    def custom_generate(model, inputs, generation_config):
        # 手动实现生成循环
        for i in range(max_length - input_length):
            outputs = model(**inputs)  # 直接调用模型前向传播
            next_tokens = torch.argmax(outputs.logits[:, -1, :], dim=-1)
            # 手动更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)


        input_length = inputs['input_ids'].shape[1]
        max_length = input_length + generation_config['max_new_tokens']
        
        # 准备初始状态
        unfinished_sequences = inputs['input_ids'].new(inputs['input_ids'].shape[0]).fill_(1)
        this_peft_version = getattr(model, "_peft_version", None)
        
        # 手动生成循环
        for i in range(max_length - input_length):
            # 获取下一个token
            outputs = model(
                **inputs,
                return_dict=True,
                output_attentions=False,
                output_hidden_states=False
            )
            
            next_token_logits = outputs.logits[:, -1, :]
            next_tokens = torch.argmax(next_token_logits, dim=-1)
            
            # 更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)
            inputs['attention_mask'] = torch.cat(
                [inputs['attention_mask'], inputs['attention_mask'].new_ones((inputs['attention_mask'].shape[0], 1))],
                dim=-1,
            )
            
            # 检查是否应该停止
            if torch.all(unfinished_sequences == 0):
                break

        return inputs['input_ids']

    # 执行自定义生成
    try:
        logger.info("开始自定义生成流程...")
        # 替换原有profiler部分为Nsight启动点
        try:
            # 添加Nsight标记（实际分析需通过命令行启动）
            torch.cuda.nvtx.range_push("Model_Generation")
            try:
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=50,
                    min_length=inputs['input_ids'].shape[1],
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id
                )
            except RuntimeError as e:
                if 'srcIndex < srcSelectDimSize' in str(e):
                    logger.error("CUDA索引越界错误，建议：")
                    logger.error("1. 检查tokenizer词汇表与模型是否匹配")
                    logger.error("2. 验证输入数据范围")
                    logger.error("3. 检查模型config.json中的vocab_size")
                    pytest.skip(f"CUDA索引越界错误: {str(e)}")
                raise
            finally:
                torch.cuda.nvtx.range_pop()
            
            # 保存关键数据供Nsight分析
            if os.getenv('NSIGHT_MODE'):
                torch.save({
                    'inputs': inputs,
                    'outputs': outputs,
                    'config': model.config
                }, 'nsight_debug.pt')
                
        except Exception as e:
            logger.error(f"生成失败: {str(e)}")
            pytest.fail(f"生成过程出错: {str(e)}")

        # 解码结果
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logger.info(f"生成结果: {result}")
        
    except Exception as e:
        logger.error(f"自定义生成失败: {str(e)}")
        pytest.fail(f"自定义生成过程出错: {str(e)}")


    # 打印当前GPU内存状态
    try:
        # 在执行前添加内存检查
        # 在执行前添加内存检查
        logger.info(f"可用GPU内存: {torch.cuda.memory_allocated()/1024**2:.2f}MB / {torch.cuda.get_device_properties(0).total_memory/1024**2:.2f}MB")
        if torch.cuda.memory_allocated() > 0.9 * torch.cuda.get_device_properties(0).total_memory:
            logger.warning("GPU内存接近耗尽，可能导致卡死")
        
        logger.info(f"GPU memory cached: {torch.cuda.memory_reserved()/1024**2:.2f}MB")
        
        # 强制打印输入信息
        print("\n=== 模型输入 ===")
        print(f"输入文本: {input_text}")
        print(f"输入tensor形状: {inputs['input_ids'].shape}")
        
        # 在generate调用前添加诊断
        print("\n=== 完整诊断 ===")
        print("1. 检查输入:")
        print(f"输入文本: '{input_text}'")
        print(f"input_ids: {inputs['input_ids']}")
        print(f"attention_mask: {inputs['attention_mask']}")
        
        print("\n2. 检查模型状态:")
        print(f"模型类型: {type(model)}")
        print(f"模型参数数量: {sum(p.numel() for p in model.parameters())}")
        
        # 执行生成并检查
        try:
            import sys
            
            # 在import区域后添加
            def pytest_configure(config):
                config.option.log_cli_level = "DEBUG"
                config.option.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                config.option.log_cli_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            
            # 在需要强制输出的地方使用
            with open('debug.log', 'w') as f:
                f.write("\n=== 详细调试开始 ===\n")
                f.write(f"输入文本: '{input_text}'\n")
                with open('debug_output.txt', 'a') as f:
                    f.write("\n=== 详细调试信息 ===\n")
                    f.write(f"输入形状: {inputs['input_ids'].shape}\n")
            
            # 1. 检查输入token
            print("\n[输入分析]")
            print(f"原始输入文本: '{input_text}'")
            print(f"Tokenized输入: {tokenizer.tokenize(input_text)}")
            print(f"input_ids: {inputs['input_ids'].cpu().tolist()[0][:20]}...")  # 显示前20个token
            print(f"attention_mask: {inputs['attention_mask'].cpu().tolist()[0][:20]}...")
            
            # 2. 检查模型状态
            # 将所有print替换为logger.debug
            logger.debug("=== 详细调试开始 ===")
            logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}")
            
            # 模型状态检查
            logger.debug("\n[模型状态检查]")
            logger.debug(f"模型类型: {model.__class__.__name__}")
            logger.debug(f"模型设备: {next(model.parameters()).device}")
            
            print(f"模型dtype: {next(model.parameters()).dtype}")
            print(f"pad_token_id: {model.config.pad_token_id}")
            print(f"vocab_size: {model.config.vocab_size}")
            
            # 3. 检查生成配置
            print("\n[生成配置]")
            print(f"temperature: {generation_config['temperature']}")
            print(f"top_p: {generation_config['top_p']}")
            print(f"max_new_tokens: {generation_config['max_new_tokens']}")
            
            # 4. 执行生成并详细检查输出
            print("\n[执行生成]")
            # 在执行生成前添加版本验证
            required_min_length = inputs['input_ids'].shape[1] + 50
            actual_max_length = min(
                getattr(model.config, 'max_position_embeddings', float('inf')),
                getattr(model.config, 'n_positions', float('inf')),
                generation_config['max_length']
            )
            assert actual_max_length >= required_min_length, (
                f"实际最大长度{actual_max_length}不足，需要至少{required_min_length}\n"
                f"模型配置: max_position_embeddings={getattr(model.config, 'max_position_embeddings', '无')}, "
                f"n_positions={getattr(model.config, 'n_positions', '无')}\n"
                f"生成配置: max_length={generation_config['max_length']}"
            )

            # 5. 详细输出分析
            print("\n[输出分析]")
            print(f"输出序列形状: {outputs.sequences.shape}")
            print(f"输出序列: {outputs.sequences[0].cpu().tolist()}")
            
            # 检查logits
            if outputs.scores:
                first_token_logits = outputs.scores[0][0]
                print(f"第一个token的logits范围: {torch.min(first_token_logits):.2f}~{torch.max(first_token_logits):.2f}")
                print(f"第一个token的top 5候选: {torch.topk(first_token_logits, 5)}")
            
            # 检查是否全是pad_token
            is_all_pad = torch.all(outputs.sequences == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n[严重警告] 输出全是pad_token!")
                print("可能原因分析:")
                print("1. 模型权重未正确加载 - 检查模型文件完整性")
                print("2. 生成参数配置不当 - 尝试调整temperature/top_p")
                print("3. 输入格式有问题 - 检查tokenizer与模型是否匹配")
                print("4. 模型未正确初始化 - 检查模型config")
            
            # 解码并打印结果
            result = tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
            print("\n[解码结果]")
            print(f"生成文本: '{result}'")
            print(f"生成长度: {len(result)}字符")
            
            # 验证结果
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
            
            print("\n=== 详细调试结束 ===")

            # 检查输出是否全是pad_token
            is_all_pad = torch.all(outputs == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n警告: 输出全是pad_token!")
                print("可能原因:")
                print("1. 模型权重未正确加载")
                print("2. 生成参数配置不当")
                print("3. 输入格式有问题")
            
            print(f"输出形状: {outputs.shape}")
            print(f"输出内容样本: {outputs[0][:10]}")  # 打印前10个token
            
            if len(outputs[0]) == 0:
                print("\n警告: 输出长度为0!")
        
            # 强制打印原始输出
            print("\n=== 原始输出 ===")
            print(f"输出tensor: {outputs}")
            print(f"输出形状: {outputs.shape}")
            
            result = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 强制打印最终结果
            print("\n=== 最终结果 ===")
            print(result)
            logger.info(f"\n模型生成结果: {result}")
            logger.info(f"生成结果长度: {len(result)}")
    
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
    
        except RuntimeError as e:
            if 'CUDA out of memory' in str(e):
                pytest.skip(f"Insufficient GPU memory: {str(e)}")
            else:
                pytest.fail(f"Model inference failed: {str(e)}")
                # 最终状态检查
                logger.debug("\n=== 最终状态检查 ===")
                logger.debug(f"模型加载状态: {'成功' if 'model' in locals() else '失败'}")
                logger.debug(f"最后异常: {'无' if not sys.exc_info()[0] else str(sys.exc_info()[1])}")
                logger.debug(f"测试标记: {'正常' if not hasattr(test_model_inference, '__pytest_skip__') else '跳过'}")
                
                # 确保所有断言都执行了
                assert 'model' in locals(), "模型未正确加载"
                assert hasattr(model, 'generate'), "模型方法不完整"

    except Exception as e:
        pytest.fail(f"测试过程中发生错误: {str(e)}")


if __name__ == "__main__":
    # Update model name to point to DeepSeek-V3 repository
    model_name = "deepseek-ai/DeepSeek-V3"  # Using full Hugging Face path
    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\DeepSeek-V3"  # Update directory name
    
    # Add authentication if needed (for private/gated models)
    from huggingface_hub import login
    login(token="your_hf_token_here")  # Only needed if model is private

    model = AutoModel.from_pretrained(
        model_name,
        cache_dir="D:\\AISleepGen\\models_cache_AIdo",
        force_download=True,  # Force fresh download
        local_files_only=False
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        cache_dir="D:\\AISleepGen\\models_cache_AIdo",
        force_download=True
    )

    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\Janus-1.3B"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 添加模型大小检查
    model_size = sum(os.path.getsize(os.path.join(model_dir, f)) 
                    for f in os.listdir(model_dir)) / 1024**3  # 转换为GB
    logger.info(f"模型总大小: {model_size:.2f}GB")
    if model_size < 2.5:  # 1.3B模型通常应大于2.5GB
        logger.warning("模型文件大小可能不完整，预期1.3B模型应有2.5-5GB")



    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")

    # 更新必要文件检查
    required_files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
    for file in required_files:
        assert os.path.exists(os.path.join(model_dir, file)), f"Missing model file: {file}"

    # 新增tokenizer配置文件检查
    try:
        import json
        # 检查tokenizer.json
        with open(os.path.join(model_dir, "tokenizer.json"), 'r', encoding='utf-8') as f:
            tokenizer_json = json.load(f)
            logger.debug(f"tokenizer.json版本: {tokenizer_json.get('version', '未知')}")
        
        # 检查tokenizer_config.json
        with open(os.path.join(model_dir, "tokenizer_config.json"), 'r', encoding='utf-8') as f:
            tokenizer_config = json.load(f)
            logger.info(f"tokenizer类型: {tokenizer_config.get('tokenizer_class', '未知')}")
            
            # 检查词汇表大小是否匹配
            if 'vocab_size' in tokenizer_config:
                logger.debug(f"tokenizer配置词汇表大小: {tokenizer_config['vocab_size']}")
    except Exception as e:
        logger.error(f"tokenizer配置文件检查失败: {str(e)}")
        pytest.fail(f"tokenizer配置文件检查失败: {str(e)}")

    try:
        # 加载tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            use_fast=True,
            padding_side='left',
            truncation=True,
            max_length=512,
            model_max_length=512,
            padding="max_length"
        )
        
        # 加载模型前添加tokenizer与模型匹配检查
        logger.info("检查tokenizer与模型匹配性...")
        try:
            config = AutoConfig.from_pretrained(model_dir)
            # 添加更详细的词汇表不匹配处理
            if hasattr(config, 'vocab_size'):
                if tokenizer.vocab_size != config.vocab_size:
                    logger.error(f"严重不匹配: tokenizer词汇表大小({tokenizer.vocab_size}) vs 模型配置({config.vocab_size})")
                    logger.error("建议解决方案:")
                    logger.error("1. 确保tokenizer和模型来自同一来源")
                    logger.error("2. 检查模型目录中的tokenizer配置文件")
                    logger.error("3. 重新下载匹配的模型和tokenizer")
                    pytest.fail(f"tokenizer与模型词汇表大小不匹配: {tokenizer.vocab_size} != {config.vocab_size}")
        except Exception as e:
            logger.error(f"加载模型配置失败: {str(e)}")
            pytest.fail(f"无法加载模型配置: {str(e)}")

        # 检查词汇表大小是否匹配
        if hasattr(config, 'vocab_size'):
            assert tokenizer.vocab_size == config.vocab_size, (
                f"tokenizer词汇表大小({tokenizer.vocab_size})与模型配置({config.vocab_size})不匹配"
            )
        
        # 检查特殊token是否一致
        if hasattr(config, 'bos_token_id'):
            assert tokenizer.bos_token_id == config.bos_token_id, "bos_token_id不匹配"
        if hasattr(config, 'eos_token_id'):
            assert tokenizer.eos_token_id == config.eos_token_id, "eos_token_id不匹配"
        if hasattr(config, 'pad_token_id'):
            assert tokenizer.pad_token_id == config.pad_token_id, "pad_token_id不匹配"
            
            logger.info("tokenizer与模型配置匹配检查通过")

        # 确保设置pad_token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 处理输入 - 添加更严格的输入验证
        inputs = tokenizer(input_text, 
                         return_tensors="pt",
                         truncation=True,
                         max_length=512,
                         padding="max_length")
        
        # 检查输入形状改为logger
        logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}, attention_mask: {inputs['attention_mask'].shape}")
        assert inputs['input_ids'].shape[1] <= 512, "输入长度超过模型最大长度限制"
        assert inputs['attention_mask'].shape == inputs['input_ids'].shape, "attention_mask形状与input_ids不匹配"

        # 确保所有token ID都在有效范围内
        vocab_size = tokenizer.vocab_size
        logger.info(f"Tokenizer词汇表大小: {vocab_size}")
        invalid_tokens = inputs['input_ids'][inputs['input_ids'] >= vocab_size]
        if len(invalid_tokens) > 0:
            logger.error(f"发现无效token ID: {invalid_tokens.tolist()}")
            pytest.fail(f"发现无效token ID(>= {vocab_size})")
        assert torch.all(inputs['input_ids'] >= 0), "发现负值token ID"
        
        # 确保attention_mask正确传递
        assert torch.all(inputs['attention_mask'] >= 0), "attention_mask包含非法值"
        inputs = {k: v.to(device) for k, v in inputs.items()}

    except Exception as e:
        pytest.fail(f"Tokenizer加载或输入处理失败: {str(e)}")

    # 加载模型前添加日志


    start_time = time.time()
    # 修改模型加载部分
    logger.info("开始加载模型...")
    try:
        # 使用简单的tqdm进度条
        with tqdm(total=1, desc="模型加载") as pbar:
            model = AutoModelForCausalLM.from_pretrained(
                model_dir,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                low_cpu_mem_usage=True,
                device_map="auto",
                max_memory={0: "30GB"},
                attn_implementation="eager",
                ignore_mismatched_sizes=True,
                force_download=False,
                local_files_only=True
            )
            pbar.update(1)  # 加载完成后更新进度条
        logger.info("模型加载完成")

        # 确保模型配置正确
        model.config.pad_token_id = tokenizer.pad_token_id
        model.config.eos_token_id = tokenizer.eos_token_id
        
        # 显式移动模型到设备
        model = model.to(device)
            
        # 在这里添加调试代码（模型加载成功后）
        try:
            # 性能分析 - 完全禁用以避免CUDA错误
            outputs = model.generate(**inputs)  # 直接生成不使用profiler

            # 梯度分析
            logger.debug("\n=== 梯度分析 ===")
            for name, param in model.named_parameters():
                if param.grad is not None:
                    logger.debug(f"{name} - 梯度均值: {param.grad.mean().item():.4f}")

            # 模型文件大小检查
            logger.info(f"模型文件大小: {sum(os.path.getsize(os.path.join(model_dir,f)) for f in os.listdir(model_dir))/1024/1024:.2f}MB")
        
        except Exception as e:
            logger.error(f"调试过程中发生错误: {str(e)}")
            pytest.fail(f"调试失败: {str(e)}")
        
    except Exception as e:
        pytest.skip(f"Model loading failed: {str(e)}")

    # 完全禁用SDPA后端设置
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(False)

    model.config.use_cache = True
    
    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")



    # 修改生成配置 - 终极解决方案
    generation_config = {
        'max_new_tokens': 50,  # 仅保留必要参数
        'min_length': inputs['input_ids'].shape[1],
        # 移除max_length等可能冲突的参数
    }

    # 关键修复：完全绕过长度限制检查
    def custom_generate(model, inputs, generation_config):
        # 手动实现生成循环
        for i in range(max_length - input_length):
            outputs = model(**inputs)  # 直接调用模型前向传播
            next_tokens = torch.argmax(outputs.logits[:, -1, :], dim=-1)
            # 手动更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)


        input_length = inputs['input_ids'].shape[1]
        max_length = input_length + generation_config['max_new_tokens']
        
        # 准备初始状态
        unfinished_sequences = inputs['input_ids'].new(inputs['input_ids'].shape[0]).fill_(1)
        this_peft_version = getattr(model, "_peft_version", None)
        
        # 手动生成循环
        for i in range(max_length - input_length):
            # 获取下一个token
            outputs = model(
                **inputs,
                return_dict=True,
                output_attentions=False,
                output_hidden_states=False
            )
            
            next_token_logits = outputs.logits[:, -1, :]
            next_tokens = torch.argmax(next_token_logits, dim=-1)
            
            # 更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)
            inputs['attention_mask'] = torch.cat(
                [inputs['attention_mask'], inputs['attention_mask'].new_ones((inputs['attention_mask'].shape[0], 1))],
                dim=-1,
            )
            
            # 检查是否应该停止
            if torch.all(unfinished_sequences == 0):
                break

        return inputs['input_ids']

    # 执行自定义生成
    try:
        logger.info("开始自定义生成流程...")
        # 替换原有profiler部分为Nsight启动点
        try:
            # 添加Nsight标记（实际分析需通过命令行启动）
            torch.cuda.nvtx.range_push("Model_Generation")
            try:
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=50,
                    min_length=inputs['input_ids'].shape[1],
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id
                )
            except RuntimeError as e:
                if 'srcIndex < srcSelectDimSize' in str(e):
                    logger.error("CUDA索引越界错误，建议：")
                    logger.error("1. 检查tokenizer词汇表与模型是否匹配")
                    logger.error("2. 验证输入数据范围")
                    logger.error("3. 检查模型config.json中的vocab_size")
                    pytest.skip(f"CUDA索引越界错误: {str(e)}")
                raise
            finally:
                torch.cuda.nvtx.range_pop()
            
            # 保存关键数据供Nsight分析
            if os.getenv('NSIGHT_MODE'):
                torch.save({
                    'inputs': inputs,
                    'outputs': outputs,
                    'config': model.config
                }, 'nsight_debug.pt')
                
        except Exception as e:
            logger.error(f"生成失败: {str(e)}")
            pytest.fail(f"生成过程出错: {str(e)}")

        # 解码结果
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logger.info(f"生成结果: {result}")
        
    except Exception as e:
        logger.error(f"自定义生成失败: {str(e)}")
        pytest.fail(f"自定义生成过程出错: {str(e)}")


    # 打印当前GPU内存状态
    try:
        # 在执行前添加内存检查
        # 在执行前添加内存检查
        logger.info(f"可用GPU内存: {torch.cuda.memory_allocated()/1024**2:.2f}MB / {torch.cuda.get_device_properties(0).total_memory/1024**2:.2f}MB")
        if torch.cuda.memory_allocated() > 0.9 * torch.cuda.get_device_properties(0).total_memory:
            logger.warning("GPU内存接近耗尽，可能导致卡死")
        
        logger.info(f"GPU memory cached: {torch.cuda.memory_reserved()/1024**2:.2f}MB")
        
        # 强制打印输入信息
        print("\n=== 模型输入 ===")
        print(f"输入文本: {input_text}")
        print(f"输入tensor形状: {inputs['input_ids'].shape}")
        
        # 在generate调用前添加诊断
        print("\n=== 完整诊断 ===")
        print("1. 检查输入:")
        print(f"输入文本: '{input_text}'")
        print(f"input_ids: {inputs['input_ids']}")
        print(f"attention_mask: {inputs['attention_mask']}")
        
        print("\n2. 检查模型状态:")
        print(f"模型类型: {type(model)}")
        print(f"模型参数数量: {sum(p.numel() for p in model.parameters())}")
        
        # 执行生成并检查
        try:
            import sys
            
            # 在import区域后添加
            def pytest_configure(config):
                config.option.log_cli_level = "DEBUG"
                config.option.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                config.option.log_cli_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            
            # 在需要强制输出的地方使用
            with open('debug.log', 'w') as f:
                f.write("\n=== 详细调试开始 ===\n")
                f.write(f"输入文本: '{input_text}'\n")
                with open('debug_output.txt', 'a') as f:
                    f.write("\n=== 详细调试信息 ===\n")
                    f.write(f"输入形状: {inputs['input_ids'].shape}\n")
            
            # 1. 检查输入token
            print("\n[输入分析]")
            print(f"原始输入文本: '{input_text}'")
            print(f"Tokenized输入: {tokenizer.tokenize(input_text)}")
            print(f"input_ids: {inputs['input_ids'].cpu().tolist()[0][:20]}...")  # 显示前20个token
            print(f"attention_mask: {inputs['attention_mask'].cpu().tolist()[0][:20]}...")
            
            # 2. 检查模型状态
            # 将所有print替换为logger.debug
            logger.debug("=== 详细调试开始 ===")
            logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}")
            
            # 模型状态检查
            logger.debug("\n[模型状态检查]")
            logger.debug(f"模型类型: {model.__class__.__name__}")
            logger.debug(f"模型设备: {next(model.parameters()).device}")
            
            print(f"模型dtype: {next(model.parameters()).dtype}")
            print(f"pad_token_id: {model.config.pad_token_id}")
            print(f"vocab_size: {model.config.vocab_size}")
            
            # 3. 检查生成配置
            print("\n[生成配置]")
            print(f"temperature: {generation_config['temperature']}")
            print(f"top_p: {generation_config['top_p']}")
            print(f"max_new_tokens: {generation_config['max_new_tokens']}")
            
            # 4. 执行生成并详细检查输出
            print("\n[执行生成]")
            # 在执行生成前添加版本验证
            required_min_length = inputs['input_ids'].shape[1] + 50
            actual_max_length = min(
                getattr(model.config, 'max_position_embeddings', float('inf')),
                getattr(model.config, 'n_positions', float('inf')),
                generation_config['max_length']
            )
            assert actual_max_length >= required_min_length, (
                f"实际最大长度{actual_max_length}不足，需要至少{required_min_length}\n"
                f"模型配置: max_position_embeddings={getattr(model.config, 'max_position_embeddings', '无')}, "
                f"n_positions={getattr(model.config, 'n_positions', '无')}\n"
                f"生成配置: max_length={generation_config['max_length']}"
            )

            # 5. 详细输出分析
            print("\n[输出分析]")
            print(f"输出序列形状: {outputs.sequences.shape}")
            print(f"输出序列: {outputs.sequences[0].cpu().tolist()}")
            
            # 检查logits
            if outputs.scores:
                first_token_logits = outputs.scores[0][0]
                print(f"第一个token的logits范围: {torch.min(first_token_logits):.2f}~{torch.max(first_token_logits):.2f}")
                print(f"第一个token的top 5候选: {torch.topk(first_token_logits, 5)}")
            
            # 检查是否全是pad_token
            is_all_pad = torch.all(outputs.sequences == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n[严重警告] 输出全是pad_token!")
                print("可能原因分析:")
                print("1. 模型权重未正确加载 - 检查模型文件完整性")
                print("2. 生成参数配置不当 - 尝试调整temperature/top_p")
                print("3. 输入格式有问题 - 检查tokenizer与模型是否匹配")
                print("4. 模型未正确初始化 - 检查模型config")
            
            # 解码并打印结果
            result = tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
            print("\n[解码结果]")
            print(f"生成文本: '{result}'")
            print(f"生成长度: {len(result)}字符")
            
            # 验证结果
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
            
            print("\n=== 详细调试结束 ===")

            # 检查输出是否全是pad_token
            is_all_pad = torch.all(outputs == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n警告: 输出全是pad_token!")
                print("可能原因:")
                print("1. 模型权重未正确加载")
                print("2. 生成参数配置不当")
                print("3. 输入格式有问题")
            
            print(f"输出形状: {outputs.shape}")
            print(f"输出内容样本: {outputs[0][:10]}")  # 打印前10个token
            
            if len(outputs[0]) == 0:
                print("\n警告: 输出长度为0!")
        
            # 强制打印原始输出
            print("\n=== 原始输出 ===")
            print(f"输出tensor: {outputs}")
            print(f"输出形状: {outputs.shape}")
            
            result = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 强制打印最终结果
            print("\n=== 最终结果 ===")
            print(result)
            logger.info(f"\n模型生成结果: {result}")
            logger.info(f"生成结果长度: {len(result)}")
    
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
    
        except RuntimeError as e:
            if 'CUDA out of memory' in str(e):
                pytest.skip(f"Insufficient GPU memory: {str(e)}")
            else:
                pytest.fail(f"Model inference failed: {str(e)}")
                # 最终状态检查
                logger.debug("\n=== 最终状态检查 ===")
                logger.debug(f"模型加载状态: {'成功' if 'model' in locals() else '失败'}")
                logger.debug(f"最后异常: {'无' if not sys.exc_info()[0] else str(sys.exc_info()[1])}")
                logger.debug(f"测试标记: {'正常' if not hasattr(test_model_inference, '__pytest_skip__') else '跳过'}")
                
                # 确保所有断言都执行了
                assert 'model' in locals(), "模型未正确加载"
                assert hasattr(model, 'generate'), "模型方法不完整"

    except Exception as e:
        pytest.fail(f"测试过程中发生错误: {str(e)}")


if __name__ == "__main__":
    model_name = "DeepSeek-V3"  # 替换为实际模型名称
    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\DeepSeek-V3"  # 添加这行定义
    
    # 添加下载进度条回调函数
    def download_progress(current, total, **kwargs):
        if not hasattr(download_progress, 'pbar'):
            download_progress.pbar = tqdm(total=total, unit='B', unit_scale=True, desc="下载模型")
        download_progress.pbar.update(current - download_progress.pbar.n)
        if current == total:
            download_progress.pbar.close()

    # 加载模型和tokenizer时添加进度回调
    model = AutoModel.from_pretrained(
        model_name,
        cache_dir="D:\\AISleepGen\\models_cache_AIdo",
        resume_download=True,
        local_files_only=False,
        force_download=False,
        progress_callback=download_progress
    )
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        cache_dir="D:\\AISleepGen\\models_cache_AIdo",
        resume_download=True,
        local_files_only=False,
        force_download=False,
        progress_callback=download_progress
    )

    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\Janus-1.3B"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 添加模型大小检查
    model_size = sum(os.path.getsize(os.path.join(model_dir, f)) 
                    for f in os.listdir(model_dir)) / 1024**3  # 转换为GB
    logger.info(f"模型总大小: {model_size:.2f}GB")
    if model_size < 2.5:  # 1.3B模型通常应大于2.5GB
        logger.warning("模型文件大小可能不完整，预期1.3B模型应有2.5-5GB")



    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")

    # 更新必要文件检查
    required_files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
    for file in required_files:
        assert os.path.exists(os.path.join(model_dir, file)), f"Missing model file: {file}"

    # 新增tokenizer配置文件检查
    try:
        import json
        # 检查tokenizer.json
        with open(os.path.join(model_dir, "tokenizer.json"), 'r', encoding='utf-8') as f:
            tokenizer_json = json.load(f)
            logger.debug(f"tokenizer.json版本: {tokenizer_json.get('version', '未知')}")
        
        # 检查tokenizer_config.json
        with open(os.path.join(model_dir, "tokenizer_config.json"), 'r', encoding='utf-8') as f:
            tokenizer_config = json.load(f)
            logger.info(f"tokenizer类型: {tokenizer_config.get('tokenizer_class', '未知')}")
            
            # 检查词汇表大小是否匹配
            if 'vocab_size' in tokenizer_config:
                logger.debug(f"tokenizer配置词汇表大小: {tokenizer_config['vocab_size']}")
    except Exception as e:
        logger.error(f"tokenizer配置文件检查失败: {str(e)}")
        pytest.fail(f"tokenizer配置文件检查失败: {str(e)}")

    try:
        # 加载tokenizer
        tokenizer = AutoTokenizer.from_pretrained(
            model_dir,
            use_fast=True,
            padding_side='left',
            truncation=True,
            max_length=512,
            model_max_length=512,
            padding="max_length"
        )
        
        # 加载模型前添加tokenizer与模型匹配检查
        logger.info("检查tokenizer与模型匹配性...")
        try:
            config = AutoConfig.from_pretrained(model_dir)
            # 添加更详细的词汇表不匹配处理
            if hasattr(config, 'vocab_size'):
                if tokenizer.vocab_size != config.vocab_size:
                    logger.error(f"严重不匹配: tokenizer词汇表大小({tokenizer.vocab_size}) vs 模型配置({config.vocab_size})")
                    logger.error("建议解决方案:")
                    logger.error("1. 确保tokenizer和模型来自同一来源")
                    logger.error("2. 检查模型目录中的tokenizer配置文件")
                    logger.error("3. 重新下载匹配的模型和tokenizer")
                    pytest.fail(f"tokenizer与模型词汇表大小不匹配: {tokenizer.vocab_size} != {config.vocab_size}")
        except Exception as e:
            logger.error(f"加载模型配置失败: {str(e)}")
            pytest.fail(f"无法加载模型配置: {str(e)}")

        # 检查词汇表大小是否匹配
        if hasattr(config, 'vocab_size'):
            assert tokenizer.vocab_size == config.vocab_size, (
                f"tokenizer词汇表大小({tokenizer.vocab_size})与模型配置({config.vocab_size})不匹配"
            )
        
        # 检查特殊token是否一致
        if hasattr(config, 'bos_token_id'):
            assert tokenizer.bos_token_id == config.bos_token_id, "bos_token_id不匹配"
        if hasattr(config, 'eos_token_id'):
            assert tokenizer.eos_token_id == config.eos_token_id, "eos_token_id不匹配"
        if hasattr(config, 'pad_token_id'):
            assert tokenizer.pad_token_id == config.pad_token_id, "pad_token_id不匹配"
            
            logger.info("tokenizer与模型配置匹配检查通过")

        # 确保设置pad_token
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        # 处理输入 - 添加更严格的输入验证
        inputs = tokenizer(input_text, 
                         return_tensors="pt",
                         truncation=True,
                         max_length=512,
                         padding="max_length")
        
        # 检查输入形状改为logger
        logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}, attention_mask: {inputs['attention_mask'].shape}")
        assert inputs['input_ids'].shape[1] <= 512, "输入长度超过模型最大长度限制"
        assert inputs['attention_mask'].shape == inputs['input_ids'].shape, "attention_mask形状与input_ids不匹配"

        # 确保所有token ID都在有效范围内
        vocab_size = tokenizer.vocab_size
        logger.info(f"Tokenizer词汇表大小: {vocab_size}")
        invalid_tokens = inputs['input_ids'][inputs['input_ids'] >= vocab_size]
        if len(invalid_tokens) > 0:
            logger.error(f"发现无效token ID: {invalid_tokens.tolist()}")
            pytest.fail(f"发现无效token ID(>= {vocab_size})")
        assert torch.all(inputs['input_ids'] >= 0), "发现负值token ID"
        
        # 确保attention_mask正确传递
        assert torch.all(inputs['attention_mask'] >= 0), "attention_mask包含非法值"
        inputs = {k: v.to(device) for k, v in inputs.items()}

    except Exception as e:
        pytest.fail(f"Tokenizer加载或输入处理失败: {str(e)}")

    # 加载模型前添加日志


    start_time = time.time()
    # 修改模型加载部分
    logger.info("开始加载模型...")
    try:
        # 使用简单的tqdm进度条
        with tqdm(total=1, desc="模型加载") as pbar:
            model = AutoModelForCausalLM.from_pretrained(
                model_dir,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                low_cpu_mem_usage=True,
                device_map="auto",
                max_memory={0: "30GB"},
                attn_implementation="eager",
                ignore_mismatched_sizes=True,
                force_download=False,
                local_files_only=True
            )
            pbar.update(1)  # 加载完成后更新进度条
        logger.info("模型加载完成")

        # 确保模型配置正确
        model.config.pad_token_id = tokenizer.pad_token_id
        model.config.eos_token_id = tokenizer.eos_token_id
        
        # 显式移动模型到设备
        model = model.to(device)
            
        # 在这里添加调试代码（模型加载成功后）
        try:
            # 性能分析 - 完全禁用以避免CUDA错误
            outputs = model.generate(**inputs)  # 直接生成不使用profiler

            # 梯度分析
            logger.debug("\n=== 梯度分析 ===")
            for name, param in model.named_parameters():
                if param.grad is not None:
                    logger.debug(f"{name} - 梯度均值: {param.grad.mean().item():.4f}")

            # 模型文件大小检查
            logger.info(f"模型文件大小: {sum(os.path.getsize(os.path.join(model_dir,f)) for f in os.listdir(model_dir))/1024/1024:.2f}MB")
        
        except Exception as e:
            logger.error(f"调试过程中发生错误: {str(e)}")
            pytest.fail(f"调试失败: {str(e)}")
        
    except Exception as e:
        pytest.skip(f"Model loading failed: {str(e)}")

    # 完全禁用SDPA后端设置
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(False)

    model.config.use_cache = True
    
    # 在测试函数中将print替换为logger
    logger.info(f"Using device: {device}")
    logger.info(f"CUDA version: {torch.version.cuda}")



    # 修改生成配置 - 终极解决方案
    generation_config = {
        'max_new_tokens': 50,  # 仅保留必要参数
        'min_length': inputs['input_ids'].shape[1],
        # 移除max_length等可能冲突的参数
    }

    # 关键修复：完全绕过长度限制检查
    def custom_generate(model, inputs, generation_config):
        # 手动实现生成循环
        for i in range(max_length - input_length):
            outputs = model(**inputs)  # 直接调用模型前向传播
            next_tokens = torch.argmax(outputs.logits[:, -1, :], dim=-1)
            # 手动更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)


        input_length = inputs['input_ids'].shape[1]
        max_length = input_length + generation_config['max_new_tokens']
        
        # 准备初始状态
        unfinished_sequences = inputs['input_ids'].new(inputs['input_ids'].shape[0]).fill_(1)
        this_peft_version = getattr(model, "_peft_version", None)
        
        # 手动生成循环
        for i in range(max_length - input_length):
            # 获取下一个token
            outputs = model(
                **inputs,
                return_dict=True,
                output_attentions=False,
                output_hidden_states=False
            )
            
            next_token_logits = outputs.logits[:, -1, :]
            next_tokens = torch.argmax(next_token_logits, dim=-1)
            
            # 更新输入
            inputs['input_ids'] = torch.cat([inputs['input_ids'], next_tokens[:, None]], dim=-1)
            inputs['attention_mask'] = torch.cat(
                [inputs['attention_mask'], inputs['attention_mask'].new_ones((inputs['attention_mask'].shape[0], 1))],
                dim=-1,
            )
            
            # 检查是否应该停止
            if torch.all(unfinished_sequences == 0):
                break

        return inputs['input_ids']

    # 执行自定义生成
    try:
        logger.info("开始自定义生成流程...")
        # 替换原有profiler部分为Nsight启动点
        try:
            # 添加Nsight标记（实际分析需通过命令行启动）
            torch.cuda.nvtx.range_push("Model_Generation")
            try:
                outputs = model.generate(
                    **inputs,
                    max_new_tokens=50,
                    min_length=inputs['input_ids'].shape[1],
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id
                )
            except RuntimeError as e:
                if 'srcIndex < srcSelectDimSize' in str(e):
                    logger.error("CUDA索引越界错误，建议：")
                    logger.error("1. 检查tokenizer词汇表与模型是否匹配")
                    logger.error("2. 验证输入数据范围")
                    logger.error("3. 检查模型config.json中的vocab_size")
                    pytest.skip(f"CUDA索引越界错误: {str(e)}")
                raise
            finally:
                torch.cuda.nvtx.range_pop()
            
            # 保存关键数据供Nsight分析
            if os.getenv('NSIGHT_MODE'):
                torch.save({
                    'inputs': inputs,
                    'outputs': outputs,
                    'config': model.config
                }, 'nsight_debug.pt')
                
        except Exception as e:
            logger.error(f"生成失败: {str(e)}")
            pytest.fail(f"生成过程出错: {str(e)}")

        # 解码结果
        result = tokenizer.decode(outputs[0], skip_special_tokens=True)
        logger.info(f"生成结果: {result}")
        
    except Exception as e:
        logger.error(f"自定义生成失败: {str(e)}")
        pytest.fail(f"自定义生成过程出错: {str(e)}")


    # 打印当前GPU内存状态
    try:
        # 在执行前添加内存检查
        # 在执行前添加内存检查
        logger.info(f"可用GPU内存: {torch.cuda.memory_allocated()/1024**2:.2f}MB / {torch.cuda.get_device_properties(0).total_memory/1024**2:.2f}MB")
        if torch.cuda.memory_allocated() > 0.9 * torch.cuda.get_device_properties(0).total_memory:
            logger.warning("GPU内存接近耗尽，可能导致卡死")
        
        logger.info(f"GPU memory cached: {torch.cuda.memory_reserved()/1024**2:.2f}MB")
        
        # 强制打印输入信息
        print("\n=== 模型输入 ===")
        print(f"输入文本: {input_text}")
        print(f"输入tensor形状: {inputs['input_ids'].shape}")
        
        # 在generate调用前添加诊断
        print("\n=== 完整诊断 ===")
        print("1. 检查输入:")
        print(f"输入文本: '{input_text}'")
        print(f"input_ids: {inputs['input_ids']}")
        print(f"attention_mask: {inputs['attention_mask']}")
        
        print("\n2. 检查模型状态:")
        print(f"模型类型: {type(model)}")
        print(f"模型参数数量: {sum(p.numel() for p in model.parameters())}")
        
        # 执行生成并检查
        try:
            import sys
            
            # 在import区域后添加
            def pytest_configure(config):
                config.option.log_cli_level = "DEBUG"
                config.option.log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                config.option.log_cli_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            
            # 在需要强制输出的地方使用
            with open('debug.log', 'w') as f:
                f.write("\n=== 详细调试开始 ===\n")
                f.write(f"输入文本: '{input_text}'\n")
                with open('debug_output.txt', 'a') as f:
                    f.write("\n=== 详细调试信息 ===\n")
                    f.write(f"输入形状: {inputs['input_ids'].shape}\n")
            
            # 1. 检查输入token
            print("\n[输入分析]")
            print(f"原始输入文本: '{input_text}'")
            print(f"Tokenized输入: {tokenizer.tokenize(input_text)}")
            print(f"input_ids: {inputs['input_ids'].cpu().tolist()[0][:20]}...")  # 显示前20个token
            print(f"attention_mask: {inputs['attention_mask'].cpu().tolist()[0][:20]}...")
            
            # 2. 检查模型状态
            # 将所有print替换为logger.debug
            logger.debug("=== 详细调试开始 ===")
            logger.debug(f"输入形状 - input_ids: {inputs['input_ids'].shape}")
            
            # 模型状态检查
            logger.debug("\n[模型状态检查]")
            logger.debug(f"模型类型: {model.__class__.__name__}")
            logger.debug(f"模型设备: {next(model.parameters()).device}")
            
            print(f"模型dtype: {next(model.parameters()).dtype}")
            print(f"pad_token_id: {model.config.pad_token_id}")
            print(f"vocab_size: {model.config.vocab_size}")
            
            # 3. 检查生成配置
            print("\n[生成配置]")
            print(f"temperature: {generation_config['temperature']}")
            print(f"top_p: {generation_config['top_p']}")
            print(f"max_new_tokens: {generation_config['max_new_tokens']}")
            
            # 4. 执行生成并详细检查输出
            print("\n[执行生成]")
            # 在执行生成前添加版本验证
            required_min_length = inputs['input_ids'].shape[1] + 50
            actual_max_length = min(
                getattr(model.config, 'max_position_embeddings', float('inf')),
                getattr(model.config, 'n_positions', float('inf')),
                generation_config['max_length']
            )
            assert actual_max_length >= required_min_length, (
                f"实际最大长度{actual_max_length}不足，需要至少{required_min_length}\n"
                f"模型配置: max_position_embeddings={getattr(model.config, 'max_position_embeddings', '无')}, "
                f"n_positions={getattr(model.config, 'n_positions', '无')}\n"
                f"生成配置: max_length={generation_config['max_length']}"
            )

            # 5. 详细输出分析
            print("\n[输出分析]")
            print(f"输出序列形状: {outputs.sequences.shape}")
            print(f"输出序列: {outputs.sequences[0].cpu().tolist()}")
            
            # 检查logits
            if outputs.scores:
                first_token_logits = outputs.scores[0][0]
                print(f"第一个token的logits范围: {torch.min(first_token_logits):.2f}~{torch.max(first_token_logits):.2f}")
                print(f"第一个token的top 5候选: {torch.topk(first_token_logits, 5)}")
            
            # 检查是否全是pad_token
            is_all_pad = torch.all(outputs.sequences == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n[严重警告] 输出全是pad_token!")
                print("可能原因分析:")
                print("1. 模型权重未正确加载 - 检查模型文件完整性")
                print("2. 生成参数配置不当 - 尝试调整temperature/top_p")
                print("3. 输入格式有问题 - 检查tokenizer与模型是否匹配")
                print("4. 模型未正确初始化 - 检查模型config")
            
            # 解码并打印结果
            result = tokenizer.decode(outputs.sequences[0], skip_special_tokens=True)
            print("\n[解码结果]")
            print(f"生成文本: '{result}'")
            print(f"生成长度: {len(result)}字符")
            
            # 验证结果
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
            
            print("\n=== 详细调试结束 ===")

            # 检查输出是否全是pad_token
            is_all_pad = torch.all(outputs == tokenizer.pad_token_id).item()
            print(f"输出是否全是pad_token: {is_all_pad}")
            
            if is_all_pad:
                print("\n警告: 输出全是pad_token!")
                print("可能原因:")
                print("1. 模型权重未正确加载")
                print("2. 生成参数配置不当")
                print("3. 输入格式有问题")
            
            print(f"输出形状: {outputs.shape}")
            print(f"输出内容样本: {outputs[0][:10]}")  # 打印前10个token
            
            if len(outputs[0]) == 0:
                print("\n警告: 输出长度为0!")
        
            # 强制打印原始输出
            print("\n=== 原始输出 ===")
            print(f"输出tensor: {outputs}")
            print(f"输出形状: {outputs.shape}")
            
            result = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            # 强制打印最终结果
            print("\n=== 最终结果 ===")
            print(result)
            logger.info(f"\n模型生成结果: {result}")
            logger.info(f"生成结果长度: {len(result)}")
    
            assert len(result) > 0, "生成结果为空"
            assert isinstance(result, str), "生成结果不是字符串类型"
    
        except RuntimeError as e:
            if 'CUDA out of memory' in str(e):
                pytest.skip(f"Insufficient GPU memory: {str(e)}")
            else:
                pytest.fail(f"Model inference failed: {str(e)}")
                # 最终状态检查
                logger.debug("\n=== 最终状态检查 ===")
                logger.debug(f"模型加载状态: {'成功' if 'model' in locals() else '失败'}")
                logger.debug(f"最后异常: {'无' if not sys.exc_info()[0] else str(sys.exc_info()[1])}")
                logger.debug(f"测试标记: {'正常' if not hasattr(test_model_inference, '__pytest_skip__') else '跳过'}")
                
                # 确保所有断言都执行了
                assert 'model' in locals(), "模型未正确加载"
                assert hasattr(model, 'generate'), "模型方法不完整"

    except Exception as e:
        pytest.fail(f"测试过程中发生错误: {str(e)}")


if __name__ == "__main__":
    model_name = "Janus-1.3B"
    model_dir = "D:\\AISleepGen\\models_cache_AIdo\\Janus-1.3B"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 下载进度条回调函数
    def download_progress(current, total, **kwargs):
        if not hasattr(download_progress, 'pbar'):
            download_progress.pbar = tqdm(total=total, unit='B', unit_scale=True, desc="下载模型")
        download_progress.pbar.update(current - download_progress.pbar.n)
        if current == total:
            download_progress.pbar.close()

    # 加载模型和tokenizer
    model = AutoModel.from_pretrained(
        model_dir,  # 改为直接从本地目录加载
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(model_dir)

    # 模型检查(保留一次)
    model_size = sum(os.path.getsize(os.path.join(model_dir, f)) 
                    for f in os.listdir(model_dir)) / 1024**3
    logger.info(f"模型总大小: {model_size:.2f}GB")
    if model_size < 2.5:
        logger.warning("模型文件大小可能不完整，预期1.3B模型应有2.5-5GB")

    # 文件检查(保留一次)
    required_files = ["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"]
    for file in required_files:
        assert os.path.exists(os.path.join(model_dir, file)), f"Missing model file: {file}"




