import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))  # 添加项目根目录到Python路径

from services.deepseek_optimizer import DeepSeekOptimizer
from services.deepseek_client import DeepSeekClient

# 1. 初始化优化器
optimizer = DeepSeekOptimizer()

# 2. 定义评估函数（根据您的需求定制）
def code_quality_evaluator(text: str) -> float:
    """增强版代码质量评估"""
    score = 0
    
    # 语法结构检查
    keywords = ['def ', 'return ', 'for ', 'if ', 'while ', 'try ']
    score += sum(0.1 for kw in keywords if kw in text)
    
    # 代码规范检查
    if text.count('\n    ') > 2:  # 缩进规范
        score += 0.2
    if '# ' in text:  # 注释检查
        score += 0.2
        
    # 运行时安全检查
    if 'import os\n' in text or 'import sys\n' in text:
        score -= 0.3  # 扣减危险导入
        
    return min(1.0, max(0, score))

# 3. 运行优化生成
result = optimizer.optimize_generation(
    messages=[
        {"role": "system", "content": "你是一个专业的Python程序员"},
        {"role": "user", "content": "实现一个快速排序算法，要求添加详细注释"}
    ],
    eval_func=code_quality_evaluator,
    n_iter=10  # 增加迭代次数提高优化效果
)

# 4. 输出优化结果
print(f"【最优参数】温度: {result['temperature']:.2f} 评分: {result['score']:.2f}")
print("【生成代码】")
print(result['response']['choices'][0]['message']['content'])


from services.deepseek_client import DeepSeekClient

client = DeepSeekClient()
response = client.chat_completion([
    {"role": "user", "content": "解释量子计算"}
])