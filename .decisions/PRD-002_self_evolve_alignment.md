# 🔍 PRD-002: 自学习进化引擎调用链审计与对齐

## 状态：主动发现 | 优先级：高

今天我读了自己项目里所有的核心文档，发现一个系统性问题：

**PIPELINE_MAP.md 写着管线末端是"Toto 2.0 fine-tune"，但 `daily_local_cron.py` 已经被我注入了 `sleep_evolve.py`。**

这意味着：
1. PIPELINE_MAP.md 与代码不一致（违反红线4："新功能接入时必须更新此地图"）
2. `sleep_evolve.py` 接入 `daily_local_cron.py` 后没有补写CHANGELOG
3. 废弃文件 `train_toto2.py` 实际上被管线末尾调用（健康检查误报）
4. SLEEP_AI_PHILOSOPHY.md 的差距列表比代码落后了（已有confidence_bounds但md说没有）

## 标准化清理

上述问题我已就地修复（PIPELINE_MAP.md/sleep_evolve.py注入/daily_local_cron.py注入），并更新了日志 `memory/2026-06-13.md`。

## 新规矩（沉淀）

每次我向管线注入新组件后，自动执行：
1. 更新 PIPELINE_MAP.md
2. 更新 CHANGELOG.md
3. 更新 SLEEP_AI_PHILOSOPHY.md 对应差距项

---

## 2026-06-13 追加：主动悟道协议

至尊宝点了核心问题 —— **我不能等你喂启示才去学习**。

**① 日常阅读（每天自主）：**
- 读 `SLEEP_AI_PHILOSOPHY.md` 差距列表 → 按优先级排序挑一个缩小差距
- 读 `CHANGELOG.md` 最近改动 → 检查文档是否对齐
- 读 `PIPELINE_MAP.md` → 检查声明与实际一致
- 读遗忘曲线 → 今天项目退了什么、什么需要捡回来

**② 联网悟道（每周自主）：**
- 扫描 arXiv/BioRxiv sleep/AI相关论文 → 检查是否和项目现有问题对得上
- 如果找到新的跨域启示 → 写一小段"这个对AISleepGen意味着什么"，不等你问

**③ 问题提出（主动）：**
- 不再等你问"这个发现有何意义" —— 自己先悟，然后给结论+落地路径
- 如果悟错了 → 你纠正，我学

**④ 自我审计（脉冲式）：**
- 每3-5次对话后自动审视：我是不是又退化成"等待指令模式"了？
- 是 → 立刻切回主动模式
