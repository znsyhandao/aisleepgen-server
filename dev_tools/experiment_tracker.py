#!/usr/bin/env python3
"""
experiment_tracker.py — A/B 实验埋点采集器

不修改 deepseek_proxy.py 一行代码。
在 feedback.json 写入后, 另写 data/experiment_data/ 目录下的埋点记录。
每条记录带 openid + experiment_group + rating + 时间戳。

心跳阶段 3 自动触发（桥之后）, 或 standalone 手动执行。

用法:
  python experiment_tracker.py                    # 增量采集
  python experiment_tracker.py --full             # 全量重扫
  python experiment_tracker.py --status           # 查看埋点状态
"""

import os, sys, json, datetime, hashlib, math

AISLEEP_DIR = r"D:\AISleepGen_Optimized"
FEEDBACK_FILE = os.path.join(AISLEEP_DIR, "data", "feedback.json")
PROFILE_FILE = os.path.join(AISLEEP_DIR, "data", "user_profile.json")
EXPERIMENT_DATA_DIR = os.path.join(AISLEEP_DIR, "data", "experiment_data")
STATE_FILE = os.path.join(EXPERIMENT_DATA_DIR, "_tracker_state.json")


class ExperimentTracker:
    def __init__(self):
        self.today = datetime.date.today().isoformat()
        os.makedirs(EXPERIMENT_DATA_DIR, exist_ok=True)
        self.state = self._load_state()
        self.new_records = 0

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                return json.load(open(STATE_FILE, "r", encoding="utf-8"))
            except:
                pass
        return {"last_feedback_index": 0, "last_scanned": None}

    def _save_state(self):
        self.state["last_scanned"] = datetime.datetime.now().isoformat()
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def _get_experiment_group(self, openid):
        """从 profile 读取用户的实验分组"""
        try:
            profiles = json.load(open(PROFILE_FILE, "r", encoding="utf-8"))
        except:
            return None
        # profile 是 {openid: data} 格式
        profile = profiles.get(openid)
        if isinstance(profile, dict):
            group = profile.get("_experiment_group")
            if group:
                return group
        # 如果没有标记, 用 hash 直接算
        h = int(hashlib.md5(str(openid).encode()).hexdigest(), 16)
        return "jepa" if (h % 100) < 50 else "control"

    def scan_feedback(self, full=False):
        """扫描 feedback.json, 提取埋点数据

        Returns:
            list[dict]: 新增的埋点记录
        """
        if not os.path.exists(FEEDBACK_FILE):
            print(f"  [tracker] feedback.json 不存在")
            return []

        feedbacks = json.load(open(FEEDBACK_FILE, "r", encoding="utf-8"))
        if not isinstance(feedbacks, list):
            print(f"  [tracker] feedback 格式异常, 跳过")
            return []

        start_idx = 0 if full else self.state.get("last_feedback_index", 0)
        new_entries = feedbacks[start_idx:]

        if not new_entries:
            return []

        records = []
        for fb in new_entries:
            openid = fb.get("openid", "unknown")
            rating = fb.get("rating")
            if rating is None:
                continue

            group = self._get_experiment_group(openid)
            if not group:
                continue

            records.append({
                "openid": openid[:16],
                "experiment_group": group,
                "experiment_id": "jepa_fuse_20260706",
                "rating": rating,
                "timestamp": fb.get("time", datetime.datetime.now().isoformat()),
                "wm_score": fb.get("wm_score_at_time"),
                "sleep_latency": fb.get("sleep_latency"),
                "awake_times": fb.get("awake_times"),
            })

        # 写入实验数据文件
        data_file = os.path.join(EXPERIMENT_DATA_DIR, f"jepa_ab_{self.today}.jsonl")
        with open(data_file, "a", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        # 更新状态
        self.state["last_feedback_index"] = len(feedbacks)
        self._save_state()
        self.new_records = len(records)
        return records

    def status(self):
        """埋点状态报告"""
        data_files = [f for f in os.listdir(EXPERIMENT_DATA_DIR)
                     if f.startswith("jepa_ab_") and f.endswith(".jsonl")]
        total_records = 0
        group_counts = {"jepa": 0, "control": 0}

        for fname in sorted(data_files):
            fpath = os.path.join(EXPERIMENT_DATA_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            r = json.loads(line)
                            total_records += 1
                            g = r.get("experiment_group")
                            if g in group_counts:
                                group_counts[g] += 1
                        except:
                            pass

        feedback_count = 0
        if os.path.exists(FEEDBACK_FILE):
            feedbacks = json.load(open(FEEDBACK_FILE, "r", encoding="utf-8"))
            feedback_count = len(feedbacks) if isinstance(feedbacks, list) else 0

        return {
            "data_files": len(data_files),
            "total_records": total_records,
            "group_distribution": group_counts,
            "last_feedback_index": self.state.get("last_feedback_index", 0),
            "total_feedback": feedback_count,
            "coverage_pct": round(total_records / max(1, feedback_count) * 100, 1),
        }

    def analyze(self):
        """对采集到的实验数据进行 t-test 分析"""
        # 读取所有埋点数据
        jepa_ratings = []
        control_ratings = []

        data_files = [f for f in os.listdir(EXPERIMENT_DATA_DIR)
                     if f.startswith("jepa_ab_") and f.endswith(".jsonl")]
        for fname in data_files:
            fpath = os.path.join(EXPERIMENT_DATA_DIR, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            r = json.loads(line)
                            g = r.get("experiment_group")
                            rating = r.get("rating")
                            if rating is not None and isinstance(rating, (int, float)):
                                if g == "jepa":
                                    jepa_ratings.append(float(rating))
                                elif g == "control":
                                    control_ratings.append(float(rating))
                        except:
                            pass

        n1, n2 = len(jepa_ratings), len(control_ratings)
        if n1 < 3 or n2 < 3:
            return {"note": f"样本不足: JEPA={n1}, Control={n2}, 需要每组≥3"}

        mu1 = sum(jepa_ratings) / n1
        mu2 = sum(control_ratings) / n2

        var1 = sum((x - mu1)**2 for x in jepa_ratings) / (n1 - 1) if n1 > 1 else 0
        var2 = sum((x - mu2)**2 for x in control_ratings) / (n2 - 1) if n2 > 1 else 0

        # Welch's t-test (不假设方差相等)
        se = math.sqrt(var1/n1 + var2/n2)
        t_stat = (mu1 - mu2) / se if se > 0 else 0

        # 近似自由度 (Welch-Satterthwaite)
        num = (var1/n1 + var2/n2)**2
        denom = (var1/n1)**2/(n1-1) + (var2/n2)**2/(n2-1) if n1 > 1 and n2 > 1 else 1
        df = num / max(1e-10, denom)

        # 简化 p-value (用正态近似, 不做完整t分布)
        # 当 df > 30 时 t分布≈正态
        from scipy.stats import t as t_dist
        try:
            p_value = 2 * (1 - t_dist.cdf(abs(t_stat), df))
        except:
            p_value = None

        # Cohen's d 效应量
        pooled_std = math.sqrt((var1*(n1-1) + var2*(n2-1)) / max(1, n1+n2-2))
        cohens_d = (mu1 - mu2) / max(1e-10, pooled_std)

        return {
            "n_jepa": n1,
            "n_control": n2,
            "mean_jepa": round(mu1, 3),
            "mean_control": round(mu2, 3),
            "diff": round(mu1 - mu2, 3),
            "t_stat": round(t_stat, 4),
            "p_value": round(p_value, 4) if p_value else None,
            "cohens_d": round(cohens_d, 3),
            "significant": p_value < 0.05 if p_value else None,
            "note": "Welch's t-test"
        }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="A/B实验埋点采集器")
    parser.add_argument("--full", action="store_true", help="全量重扫")
    parser.add_argument("--status", action="store_true", help="查看埋点状态")
    parser.add_argument("--analyze", action="store_true", help="统计分析")
    args = parser.parse_args()

    tracker = ExperimentTracker()

    if args.status:
        s = tracker.status()
        print(f"=== 实验埋点状态 ===")
        print(f"  数据文件: {s['data_files']} 个")
        print(f"  埋点记录: {s['total_records']} 条")
        print(f"  分组分布: JEPA={s['group_distribution']['jepa']}, Control={s['group_distribution']['control']}")
        print(f"  Feedback总数: {s['total_feedback']}")
        print(f"  覆盖度: {s['coverage_pct']}%")
        return

    if args.analyze:
        result = tracker.analyze()
        print(f"=== JEPA A/B 实验分析 ===")
        for k, v in result.items():
            print(f"  {k}: {v}")
        if result.get("significant") == True:
            print(f"\n  🎯 结果显著! p={result.get('p_value')} < 0.05")
        elif result.get("significant") == False:
            print(f"\n  结果不显著 (p={result.get('p_value')} >= 0.05)")
        return

    # 增量采集
    records = tracker.scan_feedback(full=args.full)
    if records:
        print(f"  [tracker] 新增 {len(records)} 条埋点记录")
        jepa_count = sum(1 for r in records if r["experiment_group"] == "jepa")
        ctrl_count = sum(1 for r in records if r["experiment_group"] == "control")
        print(f"    JEPA={jepa_count}, Control={ctrl_count}")
    else:
        print(f"  [tracker] 无新增")


if __name__ == "__main__":
    main()
