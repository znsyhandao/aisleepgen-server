# -*- coding: utf-8 -*-
"""狡猾的细胞六条映射 vs AISleepGen 已落地/待选算法"""
import sys
sys.path.insert(0, 'D:\\AISleepGen_Optimized')
from auto_explorer import _load_archive

archive = _load_archive()

# 六个映射的工程化定义
mappings = {
    "M1-作弊者与免疫监视": {
        "desc": "算法中必然涌现作弊(过拟合/捷径/奖励hack)→需免疫监视检测异常信号",
        "algo_hints": ["异常检测", "多样性奖励", "对抗训练", "outlier", "免疫", "anti-fraud", "欺诈", "自噬", "pruning"],
    },
    "M2-搭便车与社会免疫": {
        "desc": "多智能体合作必有搭便车→声誉/贡献度/事后惩罚机制",
        "algo_hints": ["声誉", "贡献度", "reputation", "credit assignment", "shapley", "公平", "合作", "peer review"],
    },
    "M3-算法衰老与自噬检查点": {
        "desc": "模型长期更新累积错误→定期回滚+重放+隔离重置",
        "algo_hints": ["回滚", "检查点", "checkpoint", "rollback", "replay", "reset", "reset", "退化", "self-heal", "自愈"],
    },
    "M4-跨架构杂交防御": {
        "desc": "不同架构抗欺骗能力不同→杂交/集成/MoE获得防御多样性",
        "algo_hints": ["MoE", "专家混合", "杂交", "集成", "ensemble", "多模态", "multi-modal", "迁移"],
    },
    "M5-隐蔽后门与免疫探针": {
        "desc": "捷径学习/隐蔽后门在内部形成暗回路→实时可解释性探针",
        "algo_hints": ["可解释", "XAI", "解释性", "探针", "probe", "激活", "activation", "可视化"],
    },
    "M6-带瘤生存与韧性工程": {
        "desc": "追求完全正确不如构建容错生态→容忍小错+多重围堵",
        "algo_hints": ["容错", "fault tolerance", "韧性", "resilience", "围堵", "containment", "退化降级", "graceful", "safety", "安全"],
    },
}

print("=" * 80)
print("狡猾的细胞六条映射 vs AISleepGen 算法库（已落地19 + 待选46）")
print("=" * 80)

for mkey, minfo in mappings.items():
    print(f"\n{'─'*60}")
    print(f"📌 {mkey}: {minfo['desc']}")
    print(f"{'─'*60}")
    
    # 找相关的已落地算法
    landed_hits = []
    pending_hits = []
    
    for name, info in archive.items():
        combined = (name + ' ' + str(info.get('asg_value', '')) + ' ' + str(info.get('code_hint', ''))).lower()
        score = sum(1 for h in minfo['algo_hints'] if h.lower() in combined)
        if score > 0:
            if info.get('landed'):
                landed_hits.append((score, name, info))
            else:
                pending_hits.append((score, name, info))
    
    landed_hits.sort(reverse=True, key=lambda x: x[0])
    pending_hits.sort(reverse=True, key=lambda x: x[0])
    
    if landed_hits:
        print("  已落地:")
        for score, name, info in landed_hits:
            asg = (info.get('asg_value', '') or '')[:60]
            print(f"    [{score}] {name[:45]:45s} {asg}")
    if pending_hits:
        print("  待选:")
        for score, name, info in pending_hits:
            asg = (info.get('asg_value', '') or '')[:60]
            print(f"    [{score}] P{info.get('priority','?')} ~{info.get('lines_needed',0):3d}行 | {name[:40]:40s} {asg}")
    if not landed_hits and not pending_hits:
        print("   (无直接对应的算法记录)")

print("\n\n")
print("=" * 60)
print("待选46条中按映射相关度+优先级排序的前10")
print("=" * 60)

# 计算每条待选算法在映射中的总相关分
pending_scores = []
for name, info in archive.items():
    if info.get('landed'):
        continue
    combined = (name + ' ' + str(info.get('asg_value', '')) + ' ' + str(info.get('code_hint', ''))).lower()
    max_score = 0
    matched_mapping = ''
    for mkey, minfo in mappings.items():
        score = sum(1 for h in minfo['algo_hints'] if h.lower() in combined)
        if score > max_score:
            max_score = score
            matched_mapping = mkey
    
    priority = info.get('priority', 5)
    lines = info.get('lines_needed', 999)
    asg = (info.get('asg_value', '') or '')[:80]
    pending_scores.append((max_score, priority, lines, name, matched_mapping, asg))

# 排：高相关(score>0) + 低优先级数字 + 低行数
pending_scores.sort(key=lambda x: (-x[0], x[1], x[2]))

for i, (score, prio, lines, name, mapping, asg) in enumerate(pending_scores[:15]):
    if score > 0:
        print(f"{i+1:2d}. [{mapping[:10]}] P{prio} ~{lines:3d}行 | {name[:45]:45s}")
        print(f"     {asg}")

print("\n")
print("说明: []内数字=映射相关度, P=优先级(1最高5最低)")
