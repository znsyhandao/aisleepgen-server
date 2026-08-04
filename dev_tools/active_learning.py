#!/usr/bin/env python3
"""
主动学习模块 (active_learning.py) — 2026-07-06

问题: 当前feedback只收"rating" (1-5), 不知道用户的意见集中在哪个维度
方案: 在回复中嵌入细粒度prompt, 主动问用户6个维度

维度:
  sleep_quality: 睡眠质量
  stress_level: 压力水平  
  sleep_latency: 入睡时间
  awake_times: 夜间醒来
  mood_improvement: 情绪改善
  recommendation_relevance: 建议相关性

实现方式: 
  不改 deepseek_proxy.py
  在回复的 system prompt 中嵌入 query
  用户回复包含维度时, 采集细粒度信号

架构:
  active_learning.py — 核心逻辑
  data/active_learning/ — 存储细粒度信号
  heartbeat → 分析 active_learning 数据 → 对比 total rating
"""

import os, json, datetime, random

AISLEEP = r"D:\AISleepGen_Optimized"
AL_DIR = os.path.join(AISLEEP, "data", "active_learning")
RADAR = r"D:\super_frontier_radar"
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")

# 6个细粒度维度
DIMENSIONS = {
    "sleep_quality": "睡眠质量",
    "stress_level": "压力水平",
    "sleep_latency": "入睡时间",
    "awake_times": "夜间醒来",
    "mood_improvement": "情绪改善",
    "recommendation_relevance": "建议相关性",
}

# 主动学习 prompt 模板 (嵌入系统回复末尾)
PROMPT_TEMPLATE = """

---
📊 **帮我提升准确率**
你刚提到的哪个方面最重要？回复数字即可：
[1-睡眠质量 2-压力 3-入睡 4-醒来 5-情绪 6-建议]
"""


class ActiveLearning:
    def __init__(self):
        self.now = datetime.datetime.now()
        os.makedirs(AL_DIR, exist_ok=True)

    def get_prompt_suffix(self, experiment_group="control"):
        """返回要追加到回复末尾的prompt"""
        if experiment_group == "jepa":
            return PROMPT_TEMPLATE
        return ""  # 对照组不加prompt

    def parse_feedback(self, text, openid="unknown"):
        """解析用户回复, 提取细粒度维度评分"""
        if not text:
            return None

        result = {"openid": openid[:16], "raw": text[:100], "dimensions": {}, "timestamp": self.now.isoformat()}

        # 维度编号映射 {编号: 中文名}
        index_to_cn = {
            "1": "睡眠质量", "2": "压力水平", "3": "入睡时间",
            "4": "夜间醒来", "5": "情绪改善", "6": "建议相关性",
        }
        cn_to_en = {v: k for k, v in DIMENSIONS.items()}

        # 解析 "1 3 5" 格式 (用户只回复数字)
        nums_in_text = [c for c in text.strip() if c.isdigit()]
        for num in nums_in_text:
            cn_name = index_to_cn.get(num)
            if cn_name and cn_name in cn_to_en:
                en_name = cn_to_en[cn_name]
                result["dimensions"][en_name] = 4  # 回复数字默认4星(正面)
                # 但如果是"1"且是唯一回复 → 表示最关心的维度, 标记为关注
                if len(nums_in_text) == 1:
                    result["dimensions"][en_name] = 5  # 主动提的=最重要

        # 解析 "睡眠4星 压力3星 建议5星" 格式
        cn_to_en = {v: k for k, v in DIMENSIONS.items()}
        for cn_name, en_name in cn_to_en.items():
            for prefix_len in [4, 2]:
                prefix = cn_name[:prefix_len]
                if prefix in text:
                    idx = text.index(prefix) + len(prefix)
                    remaining = text[idx:idx+5]
                    nums = [c for c in remaining if c.isdigit()]
                    if nums:
                        score = int(nums[0])
                        if 1 <= score <= 5:
                            result["dimensions"][en_name] = score
                    break

        # 解析 "睡眠质量: 4" 格式
        import re
        cn_to_en = {v: k for k, v in DIMENSIONS.items()}
        for cn_name, en_name in cn_to_en.items():
            for sep in [":", "：", "=", "星"]:
                pattern = re.compile(rf"{cn_name}\s*{re.escape(sep)}\s*(\d+)")
                m = pattern.search(text)
                if m:
                    score = int(m.group(1))
                    if 1 <= score <= 5:
                        result["dimensions"][en_name] = score
                    break

        if result["dimensions"]:
            result["avg_score"] = round(sum(result["dimensions"].values()) / len(result["dimensions"]), 1)
            self._save(result)
            return result
        return None

    def _save(self, record):
        """保存细粒度信号"""
        today = self.now.strftime("%Y-%m-%d")
        path = os.path.join(AL_DIR, f"signals_{today}.jsonl")
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def analyze(self, days=3):
        """分析近期主动学习数据"""
        records = []
        for fname in sorted(os.listdir(AL_DIR)):
            if not fname.endswith(".jsonl"):
                continue
            fpath = os.path.join(AL_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            records.append(json.loads(line))
                        except:
                            pass

        # 按维度统计
        dim_scores = {}
        for r in records:
            for dim, score in r.get("dimensions", {}).items():
                if dim not in dim_scores:
                    dim_scores[dim] = []
                dim_scores[dim].append(score)

        if not dim_scores:
            return {"note": "无细粒度信号数据", "total_records": len(records)}

        analysis = {"total_records": len(records)}
        worst_dim = None
        worst_score = 6

        for dim, scores in sorted(dim_scores.items()):
            avg = sum(scores) / len(scores)
            analysis[dim] = {"avg": round(avg, 2), "n": len(scores)}
            if avg < worst_score:
                worst_score = avg
                worst_dim = dim

        analysis["worst_dimension"] = worst_dim
        analysis["worst_score"] = round(worst_score, 2)
        analysis["all_avg"] = round(
            sum(s["avg"] for s in analysis.values() if isinstance(s, dict) and "avg" in s) /
            max(1, sum(1 for s in analysis.values() if isinstance(s, dict) and "avg" in s)), 2
        )
        return analysis

    def status(self):
        """当前状态"""
        files = [f for f in os.listdir(AL_DIR) if f.endswith(".jsonl")]
        total = 0
        for fname in files:
            fpath = os.path.join(AL_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                total += sum(1 for _ in f)
        return {"signal_files": len(files), "total_signals": total}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="主动学习模块")
    parser.add_argument("--parse", metavar="TEXT", type=str, help="解析用户回复")
    parser.add_argument("--analyze", action="store_true", help="分析细粒度信号")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--prompt", choices=["control", "jepa"], default="control",
                       help="获取prompt后缀")
    args = parser.parse_args()

    al = ActiveLearning()

    if args.parse:
        result = al.parse_feedback(args.parse)
        if result and result.get("dimensions"):
            print(f"解析成功: {result['dimensions']}")
        elif result:
            print("未提取到维度评分")
        else:
            print("无法解析")

    if args.analyze:
        a = al.analyze()
        print("=== 主动学习分析 ===")
        for k, v in a.items():
            if isinstance(v, dict):
                print(f"  {k}: avg={v.get('avg','?')}, n={v.get('n','?')}")
            else:
                print(f"  {k}: {v}")
        if a.get("worst_dimension"):
            print(f"\n  ⚠️ 最弱维度: {a['worst_dimension']} (评分 {a['worst_score']})")

    if args.status:
        s = al.status()
        print(f"信号文件: {s['signal_files']} 个")
        print(f"信号总数: {s['total_signals']} 条")

    if args.prompt:
        if args.prompt == "jepa":
            print(al.get_prompt_suffix("jepa"))
        else:
            print("(对照组: 无prompt)")


if __name__ == "__main__":
    main()
