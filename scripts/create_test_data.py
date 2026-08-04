import os
import json
import random
from typing import List, Dict

# 创建测试数据目录
os.makedirs("data/raw", exist_ok=True)

# 中文常用词汇库
chinese_words = [
    "人工智能", "深度学习", "机器学习", "神经网络", "算法", 
    "模型", "训练", "推理", "数据集", "特征",
    "准确率", "召回率", "精确度", "优化器", "损失函数",
    "卷积", "循环网络", "注意力", "Transformer", "预训练"
]

# 生成有意义的文本样本
def generate_meaningful_text(min_len=20, max_len=100):
    length = random.randint(min_len, max_len)
    words = random.choices(chinese_words, k=length)
    return "".join(words)

# 生成分类标签说明
label_descriptions = {
    0: "科技",
    1: "教育", 
    2: "娱乐",
    3: "体育",
    4: "财经"
}

# 生成单个数据集
def generate_dataset(num_samples=100) -> List[Dict]:
    return [
        {
            "text": generate_meaningful_text(),
            "label": random.choice(list(label_descriptions.keys())),
            "label_desc": label_descriptions[random.choice(list(label_descriptions.keys()))]
        }
        for _ in range(num_samples)
    ]

# 生成并保存所有数据集
def generate_all_data():
    # 训练集 - 数据量较大
    train_data = generate_dataset(200)
    with open("data/raw/train.json", "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    # 验证集
    valid_data = generate_dataset(50)
    with open("data/raw/valid.json", "w", encoding="utf-8") as f:
        for item in valid_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    # 测试集
    test_data = generate_dataset(50)
    with open("data/raw/test.json", "w", encoding="utf-8") as f:
        for item in test_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print("测试数据已生成:")
    print(f"- 训练集: {len(train_data)}条")
    print(f"- 验证集: {len(valid_data)}条") 
    print(f"- 测试集: {len(test_data)}条")

if __name__ == "__main__":
    generate_all_data()
