"""
log_sleep_data.py - 记录每日睡眠面部特征和评分

用法：
    1. 记录新样本（预测后立即调用）：
        python log_sleep_data.py --date 2026-05-10 --pred 5.2 --features "{'lab_L_mean': 62.3, ...}"
    
    2. 更新某天的真实评分：
        python log_sleep_data.py --update --date 2026-05-10 --real 6
    
    特征格式：JSON 字符串，包含与模型训练时完全相同的 8 个特征键名。
"""

import os
import sys
import json
import argparse
import pandas as pd
from datetime import datetime

# 配置文件路径（根据你的实际位置修改）
DATA_DIR = "./data"
CSV_PATH = os.path.join(DATA_DIR, "sleep_log.csv")
os.makedirs(DATA_DIR, exist_ok=True)

# 定义 8 个特征列名（必须与 face_analyzer 输出的特征键名一致）
FEATURE_COLS = [
    "fatigue_brow_texture",
    "roi_grad_forehead_jaw",
    "roi_forehead_jaw_ratio",
    "hsv_H_std",            # 示例，替换为你实际使用的8个特征
    "hsv_S_p75",
    "freq_high_low_ratio",
    "lab_redness",
    "glcm_contrast"
]

def init_csv():
    """如果 CSV 不存在，创建空表头"""
    if not os.path.exists(CSV_PATH):
        df = pd.DataFrame(columns=["date"] + FEATURE_COLS + ["pred_score", "real_score"])
        df.to_csv(CSV_PATH, index=False)

def add_record(date, pred_score, features_dict, real_score=None):
    """新增一条记录（或覆盖已存在的同一天记录，以最新为准）"""
    init_csv()
    df = pd.read_csv(CSV_PATH)
    
    # 检查日期是否已存在
    if date in df["date"].values:
        print(f"⚠️ 日期 {date} 已存在，将覆盖原有记录。")
        df = df[df["date"] != date]
    
    new_row = {"date": date, "pred_score": pred_score, "real_score": real_score}
    for col in FEATURE_COLS:
        new_row[col] = features_dict.get(col, None)
    
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df.to_csv(CSV_PATH, index=False)
    print(f"✅ 已记录 {date} 的数据 (pred={pred_score}, real={real_score})")

def update_real_score(date, real_score):
    """更新指定日期的真实评分"""
    init_csv()
    df = pd.read_csv(CSV_PATH)
    if date not in df["date"].values:
        print(f"❌ 日期 {date} 不存在，请先添加预测记录。")
        return
    df.loc[df["date"] == date, "real_score"] = real_score
    df.to_csv(CSV_PATH, index=False)
    print(f"✅ 已更新 {date} 的真实评分为 {real_score}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="日期 YYYY-MM-DD")
    parser.add_argument("--pred", type=float, help="预测评分")
    parser.add_argument("--features", type=str, help="JSON 格式的特征字典")
    parser.add_argument("--real", type=float, help="真实评分")
    parser.add_argument("--update", action="store_true", help="仅更新真实评分（不需要 --pred 和 --features）")
    args = parser.parse_args()
    
    if args.update:
        if args.real is None:
            print("❌ 请提供 --real 参数")
            sys.exit(1)
        update_real_score(args.date, args.real)
    else:
        if args.pred is None or args.features is None:
            print("❌ 请提供 --pred 和 --features")
            sys.exit(1)
        features = json.loads(args.features)
        add_record(args.date, args.pred, features, args.real)

if __name__ == "__main__":
    main()