#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_explorer.py — AISleepGen 自动算法探索引擎

使命：自动扫描DeepMind/OpenAI/Anthropic等前沿模型的核心数学思想，
评估其对减压睡眠AI的落地价值，生成代码建议。

这不是"想到了去搜"，而是每次 comprehensive_analysis 运行时自动触发：
- 检查 `_algorithm_archive` 中是否有未落地的候选算法
- 如果有，自动生成评估 + 建议代码路径
- 写入 profile，下次干预时可选"这是新算法推荐的"

策略：
1. 知识库沉淀：每次人工讨论的结论存入 `_algorithm_archive`
2. 自动评估：有候选算法时评分可落地性 + 代码复杂度
3. 渐进落地：优先选评分高的落地

数据来源：
- 不联网搜索（依赖至尊宝/小甜甜的认知更新）
- 每次人工讨论后手动写入（通过 set_algorithm_insight）
- 启动时加载本地存档
"""

import os, json, inspect
from datetime import datetime

_ARCHIVE_FILE = os.path.join(os.path.dirname(__file__), 'data', 'algorithm_archive.json')
_ARCHIVE = None


def _load_archive():
    """加载算法知识库"""
    global _ARCHIVE
    if _ARCHIVE is not None:
        return _ARCHIVE
    if os.path.exists(_ARCHIVE_FILE):
        try:
            with open(_ARCHIVE_FILE, 'r', encoding='utf-8') as f:
                _ARCHIVE = json.load(f)
        except:
            _ARCHIVE = {}
    else:
        _ARCHIVE = {}
    return _ARCHIVE


def _save_archive():
    """持久化"""
    if _ARCHIVE is None:
        return
    os.makedirs(os.path.dirname(_ARCHIVE_FILE), exist_ok=True)
    with open(_ARCHIVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(_ARCHIVE, f, ensure_ascii=False, indent=2)


def set_algorithm_insight(name, source, math_core, asg_value, code_hint, lines_needed, priority):
    """至尊宝或小甜甜发现新算法时调用

    参数：
    - name: 算法名（如 "VQ-VAE"）
    - source: 来源（"DeepMind", "OpenAI", "Anthropic", "DeepSeek"）
    - math_core: 核心数学思想简述
    - asg_value: 对AISleepGen的价值描述
    - code_hint: 代码落地的建议路径
    - lines_needed: 预估代码行数
    - priority: 1-5（1=最高）
    """
    archive = _load_archive()
    if name in archive:
        archive[name]['_updated_at'] = datetime.now().isoformat()
        archive[name]['_discussion_count'] = archive[name].get('_discussion_count', 1) + 1
        return

    archive[name] = {
        'source': source,
        'math_core': math_core,
        'asg_value': asg_value,
        'code_hint': code_hint,
        'lines_needed': lines_needed,
        'priority': min(5, max(1, priority)),
        'landed': False,
        '_created_at': datetime.now().isoformat(),
        '_discussion_count': 1,
    }
    _save_archive()


def get_pending_algorithms():
    """获取尚未落地的候选算法，按优先级排序"""
    archive = _load_archive()
    pending = []
    for name, info in archive.items():
        if not info.get('landed', False):
            pending.append((name, info))
    priority_map = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}
    pending.sort(key=lambda x: (priority_map.get(x[1].get('priority', 5), 9),
                                 -x[1].get('_discussion_count', 1),
                                 x[1].get('lines_needed', 999)))
    return pending


def mark_landed(name):
    """标记一个算法为已落地"""
    archive = _load_archive()
    if name in archive:
        archive[name]['landed'] = True
        archive[name]['_landed_at'] = datetime.now().isoformat()
        _save_archive()
        return True
    return False


def get_explorer_summary():
    """生成探索引擎状态摘要（用于注入到prompt或日志）"""
    archive = _load_archive()
    total = len(archive)
    landed = sum(1 for v in archive.values() if v.get('landed'))
    pending = total - landed

    lines = [f'【算法探索引擎】共{total}条洞察，已落地{landed}条，待评估{pending}条']

    if pending:
        lines.append(f'待评估({pending}条):')
        for name, info in get_pending_algorithms()[:5]:
            lines.append(f'  [{info["source"]}] {name} — '
                         f'优先级{info["priority"]}, ~{info["lines_needed"]}行, '
                         f'讨论{info["_discussion_count"]}次')

    return '\n'.join(lines)


def suggest_code_path(profile=None):
    """自动推荐下一个最优的落地路径

    综合优先级、行数、讨论次数，选出一个推荐
    """
    pending = get_pending_algorithms()
    if not pending:
        return {'has_suggestion': False, 'message': '当前无可候选算法，请继续讨论前沿技术'}

    best_name, best_info = pending[0]
    return {
        'has_suggestion': True,
        'name': best_name,
        'source': best_info['source'],
        'math_core': best_info['math_core'],
        'code_hint': best_info['code_hint'],
        'lines_needed': best_info['lines_needed'],
        'message': f'推荐优先落地【{best_name}】（{best_info["source"]}）\n'
                   f'核心思想：{best_info["math_core"]}\n'
                   f'价值：{best_info["asg_value"]}\n'
                   f'路径：{best_info["code_hint"]}\n'
                   f'预估行数：~{best_info["lines_needed"]}行',
    }


# ===== 预置知识库（2026-07-04 半天讨论的全部沉淀） =====
def _seed_archive(force=False):
    """首次运行时注入今天全部讨论成果"""
    archive = _load_archive()
    if archive and not force:
        return  # 已有数据且不强制

    seeds = [
        # DeepMind算法全量扫描
        ('马尔可夫链(4状态)', 'DeepMind/哈萨比斯', '4状态转移矩阵 + 转移概率学习', '从序列模式预测睡眠演化', 'prediction_engine.py markov.py', 50, 1, True),
        ('指数衰减曲线', 'DeepMind/哈萨比斯', '参数e的自然衰减——知识/经验随时间指数折旧', '策略有效性随天数自然衰减', 'intervention_scheduler.py decay.py', 15, 2, True),
        ('反事实推理', 'DeepMind/哈萨比斯', 'counterfactual reasoning——"不做干预会怎样"', '自然基线 vs 干预效果', 'counterfactual.py', 100, 1, True),
        ('最小干预原则', '魔方AI', '不破坏已还原部分', '活跃习惯检测+破坏评分', 'intervention_scheduler.py', 80, 1, True),
        ('执行门槛修正', '行为经济学', 'effort=f(冲动性,方案复杂度)', '低门槛策略优先', 'intervention_scheduler.py', 80, 2, True),
        ('数据飞轮反馈', 'Covariant', '数据质量→系统决策质量的反馈回路', '飞轮健康度→干预频率', 'feedback_loop.py', 100, 2, True),
        ('动态子专家涌现', '表征压缩', '数据驱动专业分工', '自动识别专家类型+注入', 'sleep_world_model.py', 60, 2, True),
        ('状态拓扑(吸引子)', '表征压缩', '高维经验到低维流形的投影', '距好状态吸引子的距离', 'state_topology.py', 100, 1, True),
        ('在线学习(e)', 'f(a,k,e)', '缺失的环境参数在线估计', '维度权重自动学习', 'sleep_world_model.py', 80, 1, True),
        ('自由能最小化', 'Friston/DeepMind', '预测与实际误差的追踪与校准', '误差窗口+一致性检测', 'free_energy_tracker.py', 70, 1, True),
        ('探索-利用(ε-贪婪)', 'Sutton/DeepMind', '带概率的随机探索', '未见策略的试探性推荐', 'exploration_engine.py', 100, 1, True),
        ('GRPO策略梯度', 'DeepSeek/DeepMind', '组内优势估计+策略梯度更新', '好日子vs差日子干预分布', 'recommendation_tracker.py', 80, 2, True),
        ('PopArt自适应归一化', 'DeepMind', '多任务数值尺度差异的归一化', '专家评分Z-score+反向传播', 'sleep_world_model.py', 40, 1, True),
        ('MuZero隐空间轨迹', 'DeepMind', '隐空间动力学学习+回放学习', '拓扑距离空间预测', 'state_topology.py', 80, 1, True),
        ('AlphaGeometry神经符号', 'DeepMind', '符号引擎+大规模模型的混合', '专家分歧时DeepSeek猜测', 'alpha_geometry.py', 30, 2, True),
        ('Dreamer多路径模拟', 'DeepMind', '随机世界模型+多条轨迹模拟', '4策略轨迹比选', 'sleep_world_model.py', 25, 2, True),
        ('BCO行为克隆', 'DeepMind', '从观察结果反推最优策略', '监督学习拟合用户偏好', 'intervention_scheduler.py', 40, 2, True),
        ('MERLIN记忆增强', 'DeepMind', '外部记忆矩阵存罕见状态', '罕见模式学习', 'state_topology.py', 30, 3, True),
        ('NGU内在好奇心', 'DeepMind', '异常状态时内在奖励', '异常→强制探索', 'exploration_engine.py', 10, 2, True),
        # 未落地的候选
        ('VQ-VAE离散隐编码', 'DeepMind', '向量量化实现可解释codebook', '睡眠类型自动发现(聚类而非TOP-K)', 'state_topology.py 加K-means+codebook', 80, 3, False),
        ('CURL对比表示学习', 'DeepMind', '对比学习做无监督表示', '从未标记睡眠日志中学模式', '新文件 contrastive_learning.py', 100, 4, False),
        ('PRM过程奖励模型', 'DeepSeek', '中间步骤推理链奖励', '专家输出结构化推理路径验证', '新文件 process_reward.py', 70, 3, False),
        ('AlphaFold序列→结构', 'DeepMind', '注意力+进化信息的序列到结构映射', '行为序列→模式识别', '需要Transformer, 体量大', 200, 5, False),
        ('Gato多任务统一编码器', 'DeepMind', '单一Transformer处理所有任务', '10专家共享底层特征', '重构量太大', 500, 5, False),
        ('RLHF/DPO偏好对齐', 'Anthropic', '从人类反馈中学习偏好', '用户对干预方案的偏好建模', '新文件 preference_learning.py', 60, 3, False),
        ('Sparse Autoencoders(SAE)', 'Anthropic', '稀疏自编码器做可解释性', '睡眠各维度的可解释分解', '新文件 sleep_sae.py', 100, 4, False),
        ('Constitutional AI', 'Anthropic', '自监督伦理约束', '干预方案的安全约束', 'intervention_scheduler.py 加伦理检查', 40, 3, False),
        ('Chain-of-Thought推理', 'OpenAI', '逐步推理暴露中间步骤', '专家输出trace记录、PRM的基础', '专家analyze中加thinking字段', 60, 3, False),
        ('Q*/planning推理树', 'OpenAI', '推理时的树搜索', '干预方案组合的搜索', '新文件 plan_search.py', 100, 4, False),
        # ═══ 第二轮全量审计：DeepMind剩余 ═══
        ('Perceiver IO通用感知器', 'DeepMind', '跨模态统一Transformer架构', '睡眠数据+环境+行为跨模态联合建模', '新文件 perceiver_adapter.py', 120, 4, False),
        ('Sensory Neurons(感官神经元)', 'DeepMind', '连续学习中的稳定表示', '模型随时间推移不遗忘早期用户画像', 'sleep_world_model.py 加elastic_weight_consolidation', 50, 3, False),
        ('EvoGrad进化梯度', 'DeepMind', '可微进化策略', '干预方案的元学习调参', '新文件 evo_tune.py', 80, 3, False),
        ('RelPath关系路径学习', 'DeepMind', '图中关系路径的端到端学习', '睡眠维度间因果路径发现', 'state_topology.py 加因果边', 60, 3, False),
        ('Synthetic Gradients合成梯度', 'DeepMind', '解耦层间的合成梯度', '各专家可异步更新', 'sleep_world_model.py 加decoupled_updates', 70, 4, False),
        ('World Models世界模型v2', 'DeepMind', '隐空间中的环境预测+行为规划', '综合已有MuZero/Dreamer，统一框架', 'state_topology.py + exploration_engine.py 合并', 100, 3, False),
        # ═══ 第三轮：OpenAI全面 ═══
        ('GPT系列in-context learning', 'OpenAI', '上下文示例的隐式微调', 'few-shot用户画像适配', 'prompt中注入相似用户案例', 30, 1, False),
        ('InstructGPT监督微调+RLHF', 'OpenAI', '人类反馈微调', '用户对干预方案的偏好学习', 'recommendation_tracker.py 加preference信号', 50, 2, False),
        ('CLIP多模态对比学习', 'OpenAI', '图文对比学习', '手环截图OCR+文本对齐', 'device-ocr端点复用', 40, 2, False),
        ('DALL-E扩散模型', 'OpenAI', '去噪扩散概率模型', '睡眠可视化图生成', '新文件 sleep_visualizer.py', 100, 5, False),
        ('Whisper语音识别', 'OpenAI', '多语言语音到文本', '用户语音输入睡眠日志', '微信语音输入复用', 30, 2, False),
        ('Jukebox音乐生成', 'OpenAI', '分层VQ-VAE+自回归', '白噪音/双耳节拍个性化生成', '新文件 audio_therapy_gen.py', 150, 5, False),
        ('Point-E/Gaussian Splatting', 'OpenAI', '点云生成', '睡眠姿势3D可视化', '体量大, 非必需', 300, 5, False),
        ('Embedding API语义搜索', 'OpenAI', '向量嵌入+余弦相似度', '用户历史问题的语义检索', 'dp_router.py 加semantic_memory', 50, 2, False),
        # ═══ 第四轮：Anthropic/Meta ═══
        ('Constitutional AI(自约束)', 'Anthropic', '自监督伦理原则微调', '干预建议不当内容的自动屏蔽', 'intervention_scheduler.py 加safety_filter', 30, 2, False),
        ('RLHF from AI Feedback(RLAIF)', 'Anthropic', 'AI生成偏好数据而非人工', '自动评估干预有效性的自监督', 'feedback_loop.py 加auto_judge', 60, 3, False),
        ('Scaling Monotonicity(涌现)', 'Anthropic', '规模->涌现能力的规律', '更多数据量下哪些规律会涌现', 'auto_explorer.py 加scaling日志', 20, 4, False),
        ('Sparse Autoencoders(可解释)', 'Anthropic', '超宽隐层+稀疏约束的可解释性', '睡眠各维度的稀疏分解', '新文件 explainable_analysis.py', 100, 4, False),
        ('Meta-RL(元强化学习)', 'Meta', '快速适应新任务的RL', '新用户少量数据快速适配', 'intervention_scheduler.py 加meta_adapt层', 80, 3, False),
        ('OPT-IML元学习指令微调', 'Meta', '多任务指令数据集微调', '统一专家指令集', 'prompt模板统一化', 40, 3, False),
        ('FAISS向量搜索', 'Meta', '近似最近邻搜索', '用户聚类+相似案例检索', '新文件 sleep_similarity.py', 60, 2, False),
        ('Noisy Student自训练', 'Google/NoisyStudent', '伪标注+噪声注入的自蒸馏', '未标记睡眠数据的半监督增强', 'feedback_loop.py 加pseudo_label', 70, 4, False),
        ('EfficientNet神经架构搜索', 'Google', '复合缩放CNN架构', '最优专家网络结构搜索', '体量大,后期考虑', 200, 5, False),
        ('Transformer-XL长上下文', 'Google', '循环机制+相对位置编码', '长序列睡眠模式分析', 'prediction_engine.py 加segment_level', 100, 4, False),
        ('Big Transfer(BiT)迁移学习', 'Google', '大规模预训练+微调', '跨用户预训练模型+少量微调', '新文件 cross_user_base.py', 80, 3, False),
        ('Pathways统一架构', 'Google', '稀疏激活+多任务路由', '10专家统一路由', '体量大,后期考虑', 300, 5, False),
        ('Mixture of Adapters', 'Google', '适配器+MoE的轻量微调', '每个用户的轻量适配器', '新文件 personal_adapter.py', 60, 2, False),
        ('Reformer高效Transformer', 'Google', '局部敏感哈希+可逆层', '长序列高效处理', '降低长历史查询延迟', 80, 4, False),
        ('Routing Transformer聚类路由', 'Google', 'k-means聚类代替注意力', '用户分群+群内共享模型', '新文件 user_cluster_model.py', 100, 4, False),
        # ═══ 第五轮：交叉领域 ═══
        ('GFlowNet生成流网络', '多个/新兴', '基于流匹配的概率生成', '干预方案的多样化生成', '新文件 intervention_gfn.py', 100, 4, False),
        ('Diffusion Policy扩散策略', '多个/机器人', '扩散模型做策略规划', '多步干预规划的生成', '新文件 intervention_diffusion.py', 120, 4, False),
        ('世界模型(WorldModels)', '多个/RL', '行动-观察-行动的循环预测', '用户的长期睡眠演化预测', 'prediction_engine.py v5', 100, 3, False),
        ('Neural ODE神经常微分方程', '多个/数学', '连续深度网络的ODE表示', '睡眠节律的连续动力学建模', '新文件 circadian_ode.py', 80, 4, False),
        ('ELBO证据下界(变分推理)', '多个/贝叶斯', '隐变量的变分后验推断', '睡眠模式的不确定性建模', 'prediction_engine.py 加variance_estimation', 60, 3, False),
        ('Causal Discovery因果发现', '多个/因果', '从观测数据发现因果图', '各睡眠维度间的因果网络', '新文件 sleep_causal_graph.py', 100, 3, False),
        ('Bayesian Optimization贝叶斯优化', '多个/优化', '高斯过程+采集函数', '干预方案超参数的自动调优', '新文件 intervention_optimizer.py', 60, 2, False),
    ]

    for seed in seeds:
        name, source, math_core, asg_value, code_hint, lines, priority, landed = seed
        archive[name] = {
            'source': source,
            'math_core': math_core,
            'asg_value': asg_value,
            'code_hint': code_hint,
            'lines_needed': lines,
            'priority': priority,
            'landed': landed,
            '_created_at': '2026-07-04T22:00:00',
            '_discussion_count': 1,
        }
    _save_archive()


# 自动种子化（仅在首次运行时注入知识库）
_seed_archive(force=False)


if __name__ == '__main__':
    print(get_explorer_summary())
    print()
    suggestion = suggest_code_path()
    print(suggestion['message'])
