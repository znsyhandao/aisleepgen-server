# AISleepGen 进化路线：问诊模式 → 陪伴模式

## 目标
从"用户输入→分析→输出"的线性问诊，改为"持续感知→累积模型→主动介入"的循环陪伴。

## 三阶段

### P0（7天）——带上记忆，告别每次从零开始

**核心改动**：
1. **sleep_memory 存储** — 每个用户维护 `sleep_state.json`（最近7次报告指标、当前置信度、常诉困扰、干预历史）
2. **LLM prompt 首行注入个人趋势** — 报告生成前，先把用户历史趋势拼接成自然语言段
3. **chat session 间保留最近3条上下文** — 不用全局历史，只传 "最近3次用户说过的睡眠相关事实"

**改动范围**：
- 后端：1个新模块（`sleep_memory.py`）+ deepseek_proxy.py 的 `_handle_chat_report` 入口注入
- 前端：不需要

### P1（14天）——主动感知，不等用户开口

**核心改动**：
1. **睡前简报（wx 订阅消息）** — 基于当日用户数据和历史趋势，每晚20:30推送一条"状态简报+今晚建议"
2. **报告个人化** — 报告首段不再是"您的睡眠时长8小时..."，而是"比上周，您的深睡+12%，中断-2次——这是近两周最佳"

**改动范围**：
- 后端：1个 cron 调度模块 + `_generate_evening_brief` 方法
- 前端：wx subscribeMessage 接入 + report 页首段文案改造

### P2（30天）——持续世界状态 + 回退链

**核心改动**：
1. **`sleep_state` 持续更新** — 每次交互（问卷、聊天、报告生成、冥想选择）都更新用户状态机
2. **回退链** — LLM 挂掉时无缝降级到 rule-based 分析，用户无感知
3. **多源挂载** — 华为健康/Apple Health 数据增量合并到 world model

**改动范围**：
- 后端：状态机模块 + fallback chain 重构
- 前端：health kit 接入

---

## 立即可做：P0 实现方案（7天）

### 1. sleep_memory.py 数据结构

```python
{
  "openid": "xxx",
  "recent_reports": [],  # 最近7条报告的 key metrics
  "common_complaints": {"insomnia": 0.7, "shallow": 0.3},  # 贝叶斯更新的困扰概率
  "intervention_history": [{"type": "meditation", "id": "body_scan", "effectiveness": 0.6}],
  "last_n_facts": [],  # 最近3次对话中用户说了的关键睡眠事实
  "last_interaction_ts": 0,
  "baseline": {}  # 个人基线（14天后激活）
}
```

### 2. prompt 注入模板

```
【用户个人趋势（最近7天）】
- 入睡时间：23:00→22:45→23:15→22:30→23:00→22:50→23:00（趋势：稳定偏早）
- 总时长：7.5h→8.0h→6.5h→8.5h→7.0h→7.8h→8.0h（趋势：稳定）
- 主诉：入睡困难（3次）、多梦（2次）
- 对比前一周：深睡+5%，中断-1次
- 上次推荐干预：body_scan 冥想 → 未追踪效果
```

### 3. 改动量评估

| 文件 | 改动 | 估计行数 |
|------|------|---------|
| `sleep_memory.py`（新） | 数据模型 + 读写 + 趋势计算 | 80 |
| `deepseek_proxy.py` | `_handle_chat_report` 入口注入 + `_handle_chat` 事实提取 | 30 |
| 配置文件 | `sleep_memory_path` 等 | 5 |
| **合计** | | **115 行** |

要不要现在开始干 P0？
