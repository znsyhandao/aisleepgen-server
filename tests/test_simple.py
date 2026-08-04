import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))  # Add project root to path

from services.deepseek_client import DeepSeekClient
from settings import settings

client = DeepSeekClient(settings.modelarts_api_key)

# 测试简单问答
response = client.chat("用一句话解释人工智能")
print("【测试结果】")
print(response['choices'][0]['message']['content'])

# 测试代码生成
code_response = client.chat("用Python写一个Hello World")
print("\n【代码生成】")
print(code_response['choices'][0]['message']['content'])
