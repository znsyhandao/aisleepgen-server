import streamlit as st
import torch
import asyncio
import streamlit as st

# Add this before any PyTorch imports
if not hasattr(asyncio, '_get_running_loop'):
    asyncio._get_running_loop = asyncio.get_event_loop

# ... rest of your imports ...

import sys
import os
from pathlib import Path
import warnings
# Add these at the VERY TOP (before any other imports)

os.environ['STREAMLIT_SERVER_WATCH_FILE_SYSTEM'] = '0'
os.environ['STREAMLIT_SERVER_ENABLE_STATIC_SERVER'] = '0'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'


warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, message=".*torch.classes.*")


# Initialize tokenizer with better error handling and offline support
try:
    from aisleep.model.deepseek.official.tokenization import Tokenizer
    try:
        # Try to load from local path first
        tokenizer_path = os.path.join("models", "tokenizer")
        if os.path.exists(tokenizer_path):
            tokenizer = Tokenizer.from_pretrained(tokenizer_path, local_files_only=True)
        else:
            # Fallback to simple tokenizer if not found
            tokenizer = None
            st.warning("Tokenizer files not found locally. Using simple encoding.")
    except Exception as e:
        st.warning(f"Tokenizer initialization failed: {str(e)}. Using simple encoding.")
        tokenizer = None
except ImportError:
    tokenizer = None


# Fix event loop handling

if sys.platform == "win32":
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    if not hasattr(asyncio, '_get_running_loop'):
        asyncio._get_running_loop = asyncio.get_event_loop

# ... rest of your existing imports ...



# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
torch.set_num_threads(1)  # Add this line to prevent threading issues
# Check if the current working directory is correct
print(f"Current working directory: {os.getcwd()}")
# Now import your module
from aisleep.model.deepseek.official.DeepSeek_V3 import DeepSeekModel, ModelConfig

# Fix event loop handling
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ... rest of the existing code ...


# 初始化模型
# ... existing imports and model loading code ...
# ... existing imports ...

# ... existing imports ...

@st.cache_resource
def load_model():
    try:
        config = ModelConfig()
        model = DeepSeekModel(config).eval()

    # Disable gradient for inference
        for param in model.parameters():
            param.requires_grad = False
        
            model.generation_config = {
                'max_length': 512,
                'temperature': 0.7
            }
            return model
    except Exception as e:
        st.error(f"Model loading failed: {str(e)}")
        return None

model = load_model()
if model is None:
    st.stop()  # Stop the app if model fails to load

# Initialize tokenizer with better error handling
try:
    from aisleep.model.deepseek.official.tokenization import Tokenizer
    try:
        tokenizer = Tokenizer()
    except Exception as e:
        st.warning(f"Failed to initialize tokenizer: {str(e)}. Falling back to simple encoding.")
        tokenizer = None
except ImportError:
    tokenizer = None

# ... rest of the existing code ...

if prompt := st.chat_input("输入您的睡眠问题", key="main_chat_input"):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)
    
    with st.spinner("思考中..."):
        if tokenizer is not None:
            try:
                input_ids = tokenizer.encode(prompt, return_tensors='pt')
                output = model.generate(
                    input_ids,
                    max_length=model.generation_config['max_length'],
                    temperature=model.generation_config['temperature']
                )
                response = tokenizer.decode(output[0], skip_special_tokens=True)
            except Exception as e:
                st.warning(f"Generation failed: {str(e)}. Using fallback method.")
                response = {
                    "睡眠质量评分": 0.0,
                    "建议": "根据分析，建议增加深度睡眠时间"
                }
        else:
            # Fallback to ASCII encoding
            input_text = prompt[:input_length].ljust(input_length)
            input_ids = torch.tensor([[ord(c) % 5000 for c in input_text]], dtype=torch.long)
            with torch.no_grad():
                output = model(input_ids)
            
            response = {
                "睡眠质量评分": float(output['hidden_states'][0].mean().item()),
                "建议": "根据分析，建议增加深度睡眠时间"
            }
        
        st.session_state.chat_history.append({"role": "assistant", "content": str(response)})
        st.chat_message("assistant").write(response)
        st.caption(f"推理完成 | 输入长度: {input_length} | 温度: {temperature}")



# ... rest of your working code ...
