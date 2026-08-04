#!/usr/bin/env python3
"""
user_embedding.py — 个性化用户嵌入 (2026-07-06 14:57)

为什么:
  当前 system = 一条规则适合所有人 → R²天花板 0.85
  有嵌入后 = 每人有自己的基线 → R²可推至 0.9+

原理:
  每个用户的睡眠模式是个人化的、可预测的
  "用户嵌入向量"压缩用户近期行为到64维
  嵌入是 LightGBM 的额外特征 → 模型学到"Bob的睡眠模式" vs "Alice的"
  
实现:
  不用深度学习、不改红线、纯 numpy 操作
  每次新数据到达时增量更新

文件:
  data/user_embeddings/{openid}.npy — 每个用户的64维向量
  data/user_embeddings/latest.npy — 临时加载缓存
"""

import os, json, datetime
import numpy as np

AISLEEP = r"D:\AISleepGen_Optimized"
FEEDBACK_PATH = os.path.join(AISLEEP, "data", "feedback.json")
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
EMBED_DIR = os.path.join(AISLEEP, "data", "user_embeddings")
MODEL_DIR = os.path.join(AISLEEP, "data", "ml_models")
DIM = 64   # 嵌入维度


class UserEmbeddingEngine:
    """
    个性化用户嵌入引擎
    
    嵌入 = 用户最近N条feedback的 weighted moving average
    权重: 最近的 feedback 权重更大 (指数衰减)
    维度: 64 (从6+个维度 + 评分映射)
    
    用法:
      emb = UserEmbeddingEngine()
      vec = emb.get_embedding("test_user")  # 64维向量
      vec = emb.update_and_get("test_user", feedback_dict)  # 更新+返回
    """
    
    def __init__(self):
        os.makedirs(EMBED_DIR, exist_ok=True)
    
    def _embed_path(self, openid: str) -> str:
        return os.path.join(EMBED_DIR, f"{openid.replace('/', '_')}.npy")
    
    def load(self, openid: str) -> np.ndarray:
        """加载用户嵌入, 不存在则返回零向量"""
        path = self._embed_path(openid)
        if os.path.exists(path):
            return np.load(path)
        return np.zeros(DIM, dtype=np.float32)
    
    def save(self, openid: str, vec: np.ndarray):
        path = self._embed_path(openid)
        np.save(path, vec.astype(np.float32))
    
    def feedback_to_vec(self, fb: dict) -> np.ndarray:
        """从单条feedback提取特征向量 (6维+→64维投影)"""
        base = np.array([
            fb.get("wm_score_at_time", 50) / 100.0,
            fb.get("sleep_latency", 30) / 120.0,
            fb.get("awake_times", 1) / 10.0,
            fb.get("total_duration", 7) / 10.0,
            fb.get("stress_level", 5) / 10.0,
            1.0 if fb.get("pain") else 0.0,
        ], dtype=np.float32)
        
        # 用均匀哈希投影到64维 (随机投影, 保持距离)
        # 等价于一个固定的随机矩阵
        if not hasattr(self, "_R"):
            rng = np.random.RandomState(42)
            self._R = rng.randn(6, DIM).astype(np.float32) / np.sqrt(6)
        
        return base @ self._R  # 6维 → 64维
    
    def get_embedding(self, openid: str) -> np.ndarray:
        """获取用户嵌入"""
        return self.load(openid)
    
    def update_and_get(self, openid: str, fb: dict) -> np.ndarray:
        """用新feedback更新用户嵌入, 返回更新后的64维向量"""
        old_emb = self.load(openid)
        new_vec = self.feedback_to_vec(fb)
        
        # 指数移动平均 (新feedback权重0.3)
        decay = 0.7
        updated = decay * old_emb + (1 - decay) * new_vec
        
        self.save(openid, updated)
        return updated
    
    def build_all_embeddings(self) -> dict:
        """从所有feedback重建全部用户嵌入"""
        feedback = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        fb = feedback if isinstance(feedback, list) else []
        
        # 按用户分组
        user_data = {}
        for f in fb:
            uid = f.get("openid", "default")
            if uid not in user_data:
                user_data[uid] = []
            user_data[uid].append(f)
        
        embeddings = {}
        for uid, records in user_data.items():
            # 按时序排列
            records.sort(key=lambda x: x.get("timestamp", ""))
            emb = np.zeros(DIM, dtype=np.float32)
            for r in records:
                vec = self.feedback_to_vec(r)
                emb = 0.7 * emb + 0.3 * vec
            self.save(uid, emb)
            embeddings[uid] = emb
        
        return embeddings
    
    def add_embedding_features(self, features: list, openid: str) -> list:
        """把64维嵌入拼接到特征向量后"""
        emb = self.get_embedding(openid)
        return features + emb.tolist()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="用户嵌入引擎")
    parser.add_argument("--build", action="store_true", help="重建所有嵌入")
    parser.add_argument("--show", type=str, help="显示指定用户的嵌入")
    args = parser.parse_args()
    
    eng = UserEmbeddingEngine()
    
    if args.build:
        embs = eng.build_all_embeddings()
        print(f"重建完成: {len(embs)} 用户")
        for uid, vec in embs.items():
            print(f"  {uid}: 64维, norm={np.linalg.norm(vec):.3f}")
    
    if args.show:
        emb = eng.get_embedding(args.show)
        print(f"{args.show} 嵌入: 64维, norm={np.linalg.norm(emb):.3f}")
        print(f"  前8维: {emb[:8].tolist()}")


if __name__ == "__main__":
    main()
