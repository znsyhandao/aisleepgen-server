
## 2026-06-13 — SenNet启示5项落地 + 自学习进化引擎 + 乙醛酸循环4启示 + 管线注入

### SenNet 五大启示落地（从衰老图谱→睡眠AI）
- **启示①应激判定**: `sleep_world_model.py` — 应激类型判别（生理/认知/混合）+ HRV基线 → seno_types
- **启示②8种表型**: `sleep_world_model.py` — 8种失眠亚型z-score规则链 (psychophysiological至circadian_misalignment)
- **启示③离线聚类**: `sennet_clustering.py` **新增** — UMAP+GMM/k-means睡眠数据无监督聚类
- **启示④双通道评估**: `sleep_world_model.py` — damage/repair dual_channel 比值(损伤/修复/健康比)
- **启示⑤趋势预测**: `companion_mode.py` + `deepseek_proxy.py` — Companion入睡预测模型+HRV趋势预警

### 启示①'：应变稳态分析（从SenNet启示①衍生）
- **新增**: `sleep_resilience_analysis.py` — 转移熵+恢复速度+脆弱窗口定位
- **真实发现**: 02:30 跨夜脆弱窗口 (5晚中2晚体动异常), 应变稳态评分~57/100

### 启示③'：跨夜策略选择器（从SenNet启示③衍生）
- `companion_mode.py` — record_night_outcome + suggest_strategy 跨夜学习系统

### 自学习进化引擎（闭环自动化）
- **新增**: `sleep_evolve.py` — 自动扫新文件→重分析→惊奇检测→趋势漂移→持久化
- 注入 `daily_local_cron.py` 管线末尾，明早06:30自动触发

### 乙醛酸循环四启示
- **①废弃模块价值**: `sleep_world_model.py` — signal_of_absence字段 (低置信度专家清单)
- **②任务重组降级**: `companion_mode.py` — _determine_companion_tier() 3级降级
- **③备用Plan B**: `deepseek_proxy.py` — _build_fallback_response + _call_deepseek except块注入
- **④代谢瓶颈阻断**: `deepseek_proxy.py` — 超长回复/重复模式截断

### 管线注入
- `daily_local_cron.py` — sleep_evolve.py 在Toto fine-tune后执行
- PIPELINE_MAP.md — 更新末节为 "sleep_evolve.py (自学习进化)"


### 效果仪表盘
- **新增**: `tools/effectiveness_dashboard.py` — 从感知图+user_profile提取干预效果
  - 按用户聚合：总干预次数、完成率、连续天数、今日次数
  - 按干预类型聚合：每种干预的建议次数、完成率、平均效果分、评价
  - 输出结构化 JSON + 摘要 TXT
  - 支持 `--days N` 和 `--openid` 筛选

### 跨 session 记忆注入 prompt
- **新增**: `_handle_chat` 中读取 `coord_result._memory_context`
  - 自动注入最近 7 条情景记忆摘要到 DeepSeek prompt
  - 格式: 日期: 摘要 [标签]
  - 让 AI 对话能跨 session 回顾用户历史状态

### 今日总修复清单
- SAE 特征子空间注入
- code_applier 战略信号桥接 + 概念验证骨架
- 干预效果追踪闭环（感知图初始化 + 枚举器评分 + 预记录）
- 干预推演重排候选
- 时序观测历史初值
- 情景记忆跨 session
- 效果仪表盘
- 跨 session 记忆注入 prompt
- 管线自愈系统（cron_recovery + super_recovery + bat 自动修复）
- 质量检查器 13 项标准

### ③ 干预推演→候选重排闭环
- **断链**: coordinator._predictions 有值但候选排序仍用枚举器原始分
- **修复**: 在 step() 6a 推演后、6b 预记录前，用推演 score 降序重排 candidates
- **验证**: HTTP 响应 intervention_candidates 按推演 score 排序

### ① 时序观测→历史初值闭环
- **断链**: 98 条 / 193KB wm_experience.jsonl 只写不读，每 step 从零开始
- **修复**: _lazy_load 调用 sleep_timeseries.get_observations() 加载最近 3 天时序
  - step() 0.5 阶段：首次 step 时用最近观测初始化 P1 贝叶斯 belief
- **验证**: coordinator 启动时加载 5 条历史观测，P1 初始化为最新状态

### ② 情景记忆跨 session 闭环
- **断链**: end_session → memory.finalize 调用但 _lazy_load 从未读取记忆
- **修复**: _lazy_load 中调用 _memory.get_recent(n=7) 加载最近记忆到 _recent_memories
  - step() 返回值注入 _memory_context 字段（供下游 prompt 注入）
- **额外修复**: coordinator 中 `EpisodeMemory` → `EpisodicMemory`（类名拼写错误导致 _memory 始终为 None）

### 验证
- test_all_closed_flows.py: 全部 3 条闭环验证通过
- 历史观测加载：5 条 ✓
- 情景记忆加载：1 条 ✓
- 推演重排：HTTP 验证通过 ✓

### 修复：干预效果追踪（三个断点）
- **断点1**: coordinator._perception_graph 未初始化 → 枚举器 _pg 永远是 None
  - 修复: world_model_coordinator._lazy_load() 中初始化 self._perception_graph = get_perception_graph()
- **断点2**: inject_into_coordinator_step 传 _memory（EpisodicMemory）而非 _perception_graph（PerceptionGraph）
  - 修复: 改为先取 _perception_graph，fallback 到 _memory
- **断点3**: 0 分即"无数据"与"数据差 0 分"无法区分
  - 修复: 评分逻辑区分 None(默认0.5) vs 0.0(真的0分)
- **新增**: coordinator.step() 6b 阶段在干预推演后自动预记录到感知图（待用户反馈确认）

### 验证
- 单元测试: test_intervention_tracking.py
- 感知图记录验证: step() 后 records=1
- 候选排序正常: rain_sound score=0.75 confidence=0.5（无历史数据默认值）
- SAE 特征测试 5/5 通过

---

## 2026-06-11 — SAE 特征子空间概念验证 + 战略信号-代码落地桥接

### SAE 特征子空间注入（概念证明 v1）
- **新增**: `compliance.py` 中的 `inject_sae_features(response, request)` 函数
  - 受论文 "Unstable Features, Reproducible Subspaces" 启发
  - 基于 stress_type 生成不同激活模式向量
  - 拒绝医疗兜底的响应稳定性 0.92，涉医场景 0.85
  - 特征子空间 ID 基于请求内容确定哈希（相同请求相同 ID）
- **集成**: `deepseek_proxy.py` wfile.write 审计代理链中调用 inject_sae_features
  - 在审计写入前注入 SAE 特征，确保写入日志和返回给用户
  - 修复原有问题：无 audit_warnings 时 data 未随 resp 更新
- **测试**: `tests/test_sae_features.py`（5 项隔离测试）+ `tests/test_sae_e2e.py`（HTTP 端到端验证）
- **开发工具**: `tools/inject_insider_sigs.py` — 战略内参信号注入 ai_action.json

### 代码生成器改进（code_applier.py）
- 新增：对 strategic_insider 源的信号生成概念验证分析（含 skeleton_code）
- 新增：目标文件为空时自动读取 AISleepGen 核心文件供参考
- 新增：分析 prompt 输出 proof_of_concept.skeleton_code（<=30 行骨架代码）
- 修复：`code_applier.py` 现在同时读取 assessments + papers 中的 strategic_insider 条目

### 管线故障恢复系统
- **新增**: `tools/cron_recovery.py` — 管线步骤检查和按依赖补跑
- **新增**: `super_recovery.py` — 一键补跑全部缺失步骤
- **新增**: `tools/insider_quality_checker.py` — 13 项质量标准自动审核
- **新增**: `tools/quality_tracker.py` — 历史评分追踪 + 自适应门槛
- **改进**: `daily_local_cron.bat` — 锁文件清理 + 故障自动修复触发
# Changelog

## 2026-05-27 夜间修复

### 修复
- **Fix: sleep_world_model.py 编译错误** — 3处 `except` 后缺失缩进块导致解析失败
- **Fix: POST /api/clinical-report 崩溃** — `_handle_clinical_report()` 未实现
- **Fix: POST /api/relax-feedback 404** — 路由 + handler 均缺失
- **Fix: 3处 bare `except: pass`** — 改为 `except Exception: pass`

### 新增
- **POST /api/clinical-report** — 根据用户睡眠数据生成临床报告（评分趋势、建议、风险因素）
- **POST /api/relax-feedback** — 记录呼吸训练/放松训练反馈
