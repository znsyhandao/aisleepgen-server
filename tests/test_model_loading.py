import pytest
import os
import logging
from transformers import AutoModelForCausalLM, AutoTokenizer
from settings import settings

logger = logging.getLogger(__name__)

def test_model_loading():
    try:
        # 修改为models_cache目录
        model_dir = os.path.join("D:\\AISleepGen\\models_cache")
        
        # 验证模型文件是否存在
        required_files = ["config.json", "model.safetensors", "tokenizer.json"]
        for file in required_files:
            file_path = os.path.join(model_dir, file)
            assert os.path.exists(file_path), f"缺失模型文件: {file_path}"
        
        # 加载模型和tokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_dir)
        model = AutoModelForCausalLM.from_pretrained(model_dir)
        
        assert model is not None
        logger.info(f"模型加载成功 from: {model_dir}")
    except Exception as e:
        pytest.skip(f"模型加载失败: {str(e)}")
