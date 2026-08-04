import json
import matplotlib.pyplot as plt
from collections import Counter



def plot_label_distribution(label_dist, title):
    plt.figure(figsize=(8,4))
    plt.bar(label_dist.keys(), label_dist.values())
    plt.title(f"{title}标签分布")
    plt.xlabel("标签")
    plt.ylabel("数量")
    plt.show()

def analyze_data(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='strict') as f:  # 明确指定UTF-8编码
            data = [json.loads(line) for line in f]
        
        if not data:
            print("警告: 文件为空")
            return
    
        labels = [item['label'] for item in data]
        text_lens = [len(item['text']) for item in data]
        
        plt.figure(figsize=(12, 5))
        plt.subplot(1, 2, 1)
        Counter(labels).most_common()
        plt.bar(*zip(*Counter(labels).items()))
        plt.title('Label Distribution')
        
        plt.subplot(1, 2, 2)
        plt.hist(text_lens, bins=20)
        plt.title('Text Length Distribution')
        plt.show()
    except UnicodeDecodeError:
        print("错误: 文件编码不是有效的UTF-8")


if __name__ == "__main__":
    analyze_data("data/processed/train_processed.json")
