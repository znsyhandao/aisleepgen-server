# AISleepGen 架构升级报告 v4.2
## 拓扑霍奇分解落地 — 从"会诊"到"场论"

---

## 一、升级了什么

### 1. WorldModelEngine 输出层 — 全局拓扑分解（切入点1）

| 改动前（v4.1） | 改动后（v4.2） |
|---|---|
| 10位专家加权汇总 → 总分 | 10位专家加权汇总 → 总分 + 拓扑三分量 |
| 总分数值（0-100） | 总分 + phi_fraction / psi_fraction / h_fraction |
| 不知道哪些问题可恢复 | 可区分"可恢复疲劳 / 节律失调 / 长期压力模式" |

**专家→拓扑映射：**
```
phi(梯度) = CBT + SleepPhysician + Chronobiologist + LifeScientist + ExerciseRehab
psi(旋度) = StressRelaxation + CardiacMonitor
h(调和)   = ClinicalPsychologist + RiskManager + NutriMetabolism
```

新增输出字段：
```python
result['insights']['topological_decomposition'] = {
    'phi_fraction': 0.346,   # 可恢复疲劳占比
    'psi_fraction': 0.356,   # 节律失调占比
    'h_fraction': 0.299,     # 长期压力模式占比
    'dominant': 'psi',       # 主导分量
    'dominant_label': '节律失调',
    'interpretation': '当前节律失调为主导（36%）...'
}
```

### 2. StressRelaxationSpecialist.analyze() — 减压专家拓扑升级（切入点2）

| 改动前（v4.1） | 改动后（v4.2） |
|---|---|
| 2个标量：physiological_score / cognitive_score | 3个分量：topo_phi / topo_psi / topo_h |
| if-else 4层 → 4种arousal_type | 归一化比值 → 3种arousal_type + 6个拓扑字段 |
| 无法区分"场景1（困）"和"场景4（节律延迟）" | 两场景phi=67% vs psi=100%，清楚区分 |

**信号→分量映射规则：**

| 输入信号 | phi(+分) | psi(+分) | h(+分) | 语义 |
|---|---|---|---|---|
| 入睡困难+高压 | +3 | 0 | 0 | 即时交感激活 |
| 入睡困难+中压 | +1 | 0 | +1 | 即时的+长期混合 |
| 入睡困难+低压 | 0 | 0 | +2 | 长期反刍习惯 |
| 疼痛 | +1.5 | +0.5 | 0 | 躯体紧张+节律干扰 |
| 疲劳感 | +0.8 | 0 | +0.4 | 可恢复+长期 |
| 夜醒≥3次 | +0.5 | +1.5 | +0.5 | 节律片段化为主 |
| 睡前屏幕 | +0.5 | +0.5 | 0 | 蓝光+认知干扰 |
| 极晚睡(>0点) | 0 | +2 | 0 | 节律相位延迟 |

**arousal_type推导新逻辑：**
```
psi_n > 0.45 and max     → 'high_physiological'   (节律紊乱)
h_n > 0.40 and > phi_n   → 'high_cognitive'        (长期压力模式)
phi_n > 0.40 and max     → 'mixed'                 (可恢复疲劳为主)
phi_n > 0.35 and h > 0.30 → 'mixed'               (混合型)
else                      → 'low_arousal'
```

---

## 二、四个场景的改进对比

| 场景 | v4.1 arousal | v4.2 arousal | v4.2 phi | v4.2 psi | v4.2 h | 实际含义 |
|---|---|---|---|---|---|---|
| 纯粹疲劳 | low_arousal | mixed | **67%** | 0% | 33% | 可恢复疲劳，呼吸法有效 |
| 严重焦虑+疼痛 | high_physiological | mixed | **53%** | **42%** | 5% | 节律+疲劳混合，需双通路干预 |
| 长期压力模式 | high_cognitive | **high_cognitive** | 0% | 0% | **100%** | 不可压缩的长期创伤，需CBT |
| 极晚睡节律 | low_arousal | **high_physiological** | 0% | **100%** | 0% | 节律相位延迟，需光照疗法 |

**关键改进：**
- 场景1 vs 场景4：v4.1都判low_arousal，v4.2一个phi=67%（可恢复）一个psi=100%（节律）
- 场景3：h=100% → 这就是框架说的"不可压缩调和分量"——需要系统级干预而非呼吸法

---

## 三、框架对照

### 框架第一层：胞腔复形
⏳ **未做。** 当前还是平铺标量特征（不是边流）。这层需要HRV时域频域数据+跨频耦合体素，目前数据源不支持。

### 框架第二层：T-VAE 三分量分解
✅ **切入点1已做。** WorldModelEngine 输出层将10位专家映射到phi/psi/h三个正交空间。

### 框架第二层：单专家调和感知
✅ **切入点2已做。** StressRelaxationSpecialist 的评分逻辑从二元升级为三分量。

### 框架第三层：逆向场调控
⏳ **未做。** 需要硬件（音频闭环刺激设备）+ 新模块 `stimulation_scheduler.py`。

### 框架第四层：理论保证
⏳ **未做。** 调和分量拓扑不变性证明需要持久同调计算，AISleepGen现有管线不支持。

---

## 四、风险与回滚

- 所有改动**不改路由/API/数据库**，只在 `sleep_world_model.py` 内部
- 回滚：`copy .topology_backup\sleep_world_model.py.20260515.bak sleep_world_model.py`
- 切入1+2一起回滚（在同一个文件中）
- 风险等级：**低**，改动均为新增字段+逻辑替换，未删除任何现有字典键

---

## 五、下一步（等至尊宝决策）

| 优先级 | 内容 | 前置条件 |
|---|---|---|
| P0 | 切入点2验证（生产数据跑一下，看真实用户场景的topo分布） | 重启后端+有用户的晚间/晨间数据 |
| P1 | 切入点1的 `primary_focus`（`_build_actionable_takeaway`）利用 `topological_decomposition` 结果优化推荐词 | 今天talk到的框架"建议以X为优先级..." |
| P2 | 切入点2的交叉会诊二次修正（peer_findings影响arousal_type时，同步更新topo分量） | 暂无 |
| P3 | 切入点3：闭环刺激控制器 `stimulation_scheduler.py` | 需确认硬件路线（耳机？骨传导？经颅？） |
| P4 | 框架第一层：胞腔复形（HRV+EEG边流） | 需HRV设备接入确认 |

---

*报告生成于 2026-05-15 14:09 · AISleepGen v4.2*


---

## v4.2 最终升级总结 (14:15)

### 架构成熟度矩阵（更新）

| 框架层 | 旧状态 | 新状态 | 说明 |
|---|---|---|---|
| 层1：胞腔复形 | ❌ 未做 | ❌ 未做 | 需要HRV+EEG跨频数据源 |
| 层2：T-VAE（全局） | ❌ | ✅ **动态映射** | 10位专家全部注入topo_bias，动态加权 |
| 层2：T-VAE（专家） | ❌ | ✅ **调和感知** | StressRelaxation三分量评分 |
| 层3：逆向场调控 | ❌ 未做 | ❌ 未做 | 需硬件（音频闭环刺激） |
| 层4：理论保证 | ❌ 未做 | ❌ 未做 | 需持久同调计算 |

### 10位专家拓扑身份

| 专家 | phi | psi | h | 拓扑身份 |
|---|---|---|---|---|
| 临床心理 | 0.15 | 0.15 | **0.70** | h主导（长期心理） |
| CBT-I | **0.70** | 0.15 | 0.15 | phi主导（可恢复行为） |
| 睡眠医生 | **0.45** | 0.35 | 0.20 | phi+psi（生理筛查） |
| 时间生物 | 0.15 | **0.70** | 0.15 | psi主导（节律） |
| 生命科学 | **0.40** | **0.40** | 0.20 | phi+psi（综合） |
| 风险管理 | 0.15 | 0.15 | **0.70** | h主导（长期风险） |
| 减压专家 | 0.35 | **0.45** | 0.20 | psi+phi（节律+生理） |
| 运动康复 | **0.75** | 0.10 | 0.15 | phi主导（疲劳） |
| 心血管 | 0.35 | **0.50** | 0.15 | psi+phi（节律） |
| 营养代谢 | **0.40** | 0.15 | **0.45** | h+phi（长期+即时） |

### v4.2 新增字段

- WorldModelEngine输出: `topological_decomposition`, `action_instruction`
- `_build_actionable_takeaway`: 拓扑感知推荐词（优先SR局部拓扑）
- StressRelaxation: `topo_phi_gradient`, `topo_psi_circulation`, `topo_h_harmonic`, `topo_*_fraction`
- 所有专家: `topo_bias` (动态拓扑身份声明)

### 今日改动总结

| 改动 | 范围 | 类型 |
|---|---|---|
| 切入1：全局拓扑分解 | ~40行 | 输出层扩展 |
| 切入2：SR调和感知 | ~80行 | 评分逻辑重构 |
| 改进A：动态映射 | ~20行 | 静态→动态 |
| 改进D：10位专家topo_bias | ~20行 | 注入拓扑身份 |
| 改进E：拓扑感知推荐 | ~30行 | primary_focus升级 |

*报告更新于 2026-05-15 14:15*
