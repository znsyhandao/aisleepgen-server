# AISleepGen 进化路线图 v1 — 从"聊天AI"到"睡眠认知伙伴"

## 现状诊断

### 已有（骨架在）
1. **世界模型闭环**：coordinator.step() 完成感知→P1→P2→P0→记忆的全链路 ✅
2. **个人化潜空间**：SubspaceSharedOptimizer (8→4维 SVD) ✅
3. **跨session记忆**：PerceptionGraph (图检索 + BFS) ✅
4. **状态预测**：Toto2 睡眠评分预测 ✅
5. **输出合理性校验**：audit_logger 输出语义校验 ✅
6. **决策审计**：3层trace + 回放 ✅

### 缺失（差距）
1. **多路径对比推演** — 没有"如果A vs 如果B"的想象引擎
2. **连续动作执行** — 没有IoT控制，呼吸引导只有text+计时
3. **个人VAE** — 没有端侧压缩，所有推理走云端
4. **物理直觉** — 没有接触压力/毫米波/任何硬件感知
5. **环境流接入** — temperature/humidity/noise 字段在WorldState里但没数据源

---

## 路线图（3步走）

### 第一步：低成本补齐"想象引擎"（1-2周）
**目标**：让世界模型能做简单的"If A vs If B"对比推演

**具体任务**：

**任务1.1：干预策略枚举器（2天）**
- 新文件 `intervention_enumerator.py`
- 功能：给定当前 WorldState，生成 3-5 种候选干预动作
- 候选列表：
  - 呼吸引导（4-7-8 / 箱式呼吸）
  - 白噪音（雨声/溪流/粉红噪音）
  - 室温调整（↓0.5°C / ↓1°C）
  - 渐进式肌肉放松引导
  - 什么都不做（基线对比）
- 输出：候选列表 + 每个候选的历史成功率（从PerceptionGraph查）

**任务1.2：轻量化推演评估器（2-3天）**
- 新文件 `intervention_predictor.py`
- 功能：对每个候选干预，用世界模型快速推演"10分钟后状态向量"
- 暂不引入深度学习，用规则+历史统计：
  - 查PerceptionGraph：类似上下文下的干预效果
  - 给每个维度的变化打分（arousal降、HRV升、stress降）
  - 选择综合得分最高的干预
- 嵌入coordinator.step()，在P2之后、返回之前

**任务1.3：干预效果记录（1天）**
- 改造 deepseek_proxy.py，用户执行干预后记录"干预→效果"对
- 存入 PerceptionGraph 的 edge weight 中
- 后续推演可以查"对这个用户，呼吸法 vs 白噪音，哪个更有效"

### 第二步：打通连续动作执行（2-4周）
**目标**：从"返回文本"到"返回可执行的渲染指令"

**任务2.1：渲染指令标准化（3天）**
- 查看 biofeedback_renderer.py 现有输出格式
- 扩展 RenderInstruction 为通用的 MultiChannelAction：
```json
{
  "audio": {"stream": "rain_vs_stream", "volume": 0.3, "fade_in_s": 120},
  "light": {"kelvin": 2700, "brightness": 0.02, "fade_out_s": 600},
  "haptic": {"mode": "gentle_wave", "intensity": 0.2, "repeat": 3},
  "text_guide": {"script": "放松你的肩膀...", "speed": "slow"}
}
```
- 兼容现有 text_guide 逻辑

**任务2.2：HTTP动作桥接器（1周）**
- 新文件 `iot_bridge.py`（可选依赖，不影响核心）
- 将 MultiChannelAction 翻译为具体后端协议：
  - Philips Hue API（灯光）
  - MQTT（智能家居）
  - 自定义串口协议（床垫）
- 桥接器错误不阻塞主流程

**任务2.3：前端渲染适配器（1周）**
- 小程序端改造：接收 MultiChannelAction，播放对应音频流 + 动画
- 微信原生API限制：音频只能单路播放，做简易混音或切换

### 第三步：个人化VAE + 离线推理（3-6周）
**目标**：端侧推理，降低延迟和成本

**任务3.1：数据采集管道（1周）**
- 改造 deepseek_proxy.py，所有对话→生理→环境数据写入结构化日志
- 格式：`data/sleep_time_series/{openid}/{date}.jsonl`
- 每行一个 `{timestamp, hr, hrv, stress, sleep_phase, intervention, effect}`
- 跑满 30 天积累真实数据

**任务3.2：轻量VAE训练（2-3周）**
- 新文件 `sleep_vae.py`
- 用公开数据（SHHS/MESA）预训练，用户本地微调
- 压缩目标：8小时睡眠数据 → 128维潜向量
- 推理设备：CPU only，单条预测 < 100ms

**任务3.3：潜空间检索（1周）**
- 在 PerceptionGraph 之外，新增潜空间向量检索
- "找到历史中与我当前潜状态最相似的3天，看那天什么干预有效"
- 这是第一阶段"想象引擎"的升级版

### 第四阶段（远期）：硬件感知
**不开始，先跑通前三阶段。**

---

## 紧急度排序

| 优先级 | 任务 | 为什么先做 |
|--------|------|-----------|
| P0 | 1.1 干预枚举器 | 产出大、代码少、复用现有数据 |
| P0 | 1.2 推演评估器 | 直接让world model变"聪明" |
| P1 | 1.3 效果记录 | 推演的基础设施，缺了数据推演不准 |
| P1 | 2.1 指令标准化 | 把渲染输出扩展为通用格式 |
| P2 | 2.2 IoT桥接器 | 硬件闭环，但不阻塞软件 |
| P2 | 3.1 时序数据管道 | VAE需要数据 |
| P3 | 3.2 VAE训练 | 重要但周期长 |

---

## 开始执行

从 **任务1.1 干预策略枚举器** 开始。
