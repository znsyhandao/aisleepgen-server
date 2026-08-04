import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from services.deepseek_client import DeepSeekClient

def test_api_call():
    client = DeepSeekClient()
    
    # 测试简单问答
    response = client.chat_completion([
        {"role": "user", "content": "用Python实现快速排序"}
    ])
    print("【简单问答测试】")
    print(response['choices'][0]['message']['content'])
    
    # 测试多轮对话
    multi_turn = client.chat_completion([
        {"role": "system", "content": "你是一个Python专家"},
        {"role": "user", "content": "如何优化这个排序算法?"},
        {"role": "assistant", "content": "可以使用内置的sorted函数"},
        {"role": "user", "content": "那时间复杂度是多少?"}
    ])
    print("\n【多轮对话测试】")
    print(multi_turn['choices'][0]['message']['content'])

if __name__ == "__main__":
    test_api_call()
