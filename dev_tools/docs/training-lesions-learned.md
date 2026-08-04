# GPT-SoVITS 蔡志明音色训练 · 经验教训（v1.0 · 2026-06-03）

> 沉淀自 reborn_mianxiaotu 数据集训练 GPT-SoVITS v2 Text2SemanticDecoder(s1)  
> 从零开始，单卡 Blackwell GPU，347/348 条数据  
> 历时 3 小时，8 次启动失败，最终跑起来  
> **每一次失败都揭示了框架/数据/环境的一个隐性假设**

---

## 一、事故全景

### 1.1 时间线

```
08:00  开始 BERT 特征生成 → 成功 348 条
09:00  第一次启动 DDP → Worker 被 SIGTERM 杀
09:15  第二次 num_workers=0 → prefetch_factor 不兼容
09:25  第三次修 prefetch → persistent_workers 冲突
09:40  第四次 DDPStrategy → 2进程deadlock
09:55  第五次 strategy=auto → init_process_group 未初始化
10:10  第六次 WORLD_SIZE=1 环境变量 → 跑起来了但只到model init无loss
10:20  第七次 standalone 绕过DDP → DistributedBucketSampler 不认
10:32  第八次 断电断连
10:50  第九次 → 至尊宝手动启动，成功
```

### 1.2 成本统计

```
GPU 时间浪费: ~45分钟（≈ 18元） ← 这本不该花的
根源: 每次只修眼前报错，没有回溯"这个错误在什么场景下会发生"
```

---

## 二、八大错误 · 根因分析

### 🔴 错误 #1: Bert 特征维度不匹配

**症状：**
`python gen_bert.py` 生成 348 个 `reborn_XXXX.wav.pt`，训练时 `dataset.py __getitem__` 报张量形状 assert fail。

**根因：**
- `clean_text(text, "all", "v2")` 得出的 phoneme_ids 长度 ≠ `bert_tokenizer(text)` 的 token 长度
- BERT 的 BPE 分词和音素化是两套不同粒度的方案
- 这在 GPT-SoVITS v2 官方 repo 的 issue 里就有讨论（事前没查）

**修复：** 删 3-bert 目录，让 dataset 走 `if flag == 1:` fallback 分支

### 🔴 错误 #2: BERT fallback 用了全零张量

**症状：** 训练启动成功，model init 通过、dataloader 加载 OK、forward 成功 → **backward 卡死，不报错，GPU 利用率不降**

**根因（至尊宝诊断）：**
- `torch.zeros([1024, phoneme_len])` 经过 `bert_proj(Linear(1024→512))` 全零输出
- 加到 Transformer 的 `x` 上 → **LayerNorm 遇到全零输入 → 标准差=0 → NaN**
- NaN 梯度在 DDP `all_reduce` 通信中死锁
- **零比 None 更危险：** None 会报 TypeError（可修可查），zeros 会产生 NaN ∈ 静默崩溃

**修复：** `torch.randn(1024, phoneme_len) * 0.01`

### 🔴 错误 #3: DDP + num_workers > 0 → DataLoader worker 被杀

**症状：** `DataLoader worker (pid XXX) is killed by signal: Terminated`

**根因：**
- GPU 云环境没有足够系统资源（或 ulimit）/ fork 后的文件句柄冲突
- DDP 子进程和 DataLoader worker 子进程形成嵌套 fork，被杀
- 这是 `num_workers` 和 DDP 的经典兼容问题

**修复：** `num_workers: 0`

### 🔴 错误 #4: num_workers=0 → prefetch_factor / persistent_workers 报错

**症状：** `prefetch_factor option could only be specified in multiprocessing`

**根因：**
- GPT-SoVITS 代码写死 `prefetch_factor=16, persistent_workers=True`
- PyTorch 2.x：这两个参数在 `num_workers=0` 时不可用
- 是 GPT-SoVITS 的上游硬编码，不是训用户的错

**修复：** 在 `data_module.py` 中条件化：
```python
prefetch_factor=None if self.num_workers == 0 else 16
persistent_workers=False if self.num_workers == 0 else True
```

### 🔴 错误 #5: DDPStrategy 在单卡上死锁

**症状：** PyTorch Lightning 的 `DDPStrategy` 启动后 spawn 2 个进程，在 `DistributedBucketSampler` 初始化时互相等待

**根因：**
- `strategy='ddp'` 在单 GPU 上会 spawn 一个子进程（rank 1）
- `DistributedBucketSampler` 需要两个 rank 都 init 完才能继续
- 如果 spawn 出的子进程初始化失败（比如环境变量缺失），父进程永远等不到

**修复：** 用 `devices=1` 替代 `devices=-1`

### 🔴 错误 #6: SINGLE GPU 也缺 DDP group 初始化

**症状：** `ValueError: Default process group has not been initialized`  
(`_get_default_group` → `distributed_c10d.py:1379`)

**根因：**
- `DistributedBucketSampler` 硬编码调用了 `torch.distributed` API
- 即使只有 1 GPU，`WORLD_SIZE=1 RANK=0` 也必须设
- 这不是"分布式训练"的问题，是代码写了分布式调用

**修复：**
```bash
export MASTER_ADDR=127.0.0.1
export MASTER_PORT=29500
export WORLD_SIZE=1
export RANK=0
```

### 🔴 错误 #7: 训练启动后不等 first backward

**症状：** 改了 5 轮代码，看到 GPU 0% / 日志停在 48 行 → Ctrl+C → 重新修改 → 重试 → 但每次都是同一个位置停

**根因：**
- PyTorch Lightning 在第一个 batch 的 forward 要做 CUDA graph capture、kernel autotuning
- **Blackwell GPU 上这点尤其慢**（新架构的 cuDNN 自动调优）
- 实际上 GPU 利用率在 35-44% 波动，说明在算，只是没打印日志

**修复：** 看 `nvidia-smi` 的 utilization 判断是否在干活，不是日志行数

### 🔴 错误 #8: 遇到错误不改根因，只改当前报错

**症状：** 8 次失败，每次只修一个表层错误，没有一次停下来画张完整的"数据流 → 框架依赖 → 错误条件"图谱

**根因：**
- 紧张（有 GPU 计费压力）+ 急于看到训练跑起来
- 没有按"错误幂等"原则：修完 A 后 B 会报什么？先想清楚再动手

---

## 三、六条铁律（下次执行前回顾）

```
1. 🚫 BERT 特征不要生成实体文件 — 删 3-bert/，用 torch.randn * 0.01 fallback
2. 🌐 单卡也要 DDP init — WORLD_SIZE=1 RANK=0 MASTER_ADDR=127.0.0.1
3. 🛑 num_workers 永远 0 — 同时修 prefetch_factor=None + persistent_workers=False
4. ⏳ 第一次 backward 跑 3-5 分钟正常 — 看 GPU utilization，不是日志行数
5. ✏️ 永远不 python -c 写多行 — 写文件传上去跑
6. 📋 数据检查顺序 — list → wav32k → name2text → semantic → 3-bert(空)
```

---

## 四、下次训练 Checklist（执行前必过）

```bash
# ===== 90秒检查 =====

# 1. 数据完整性
cd /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu
wc -l < reborn_mianxiaotu.list           # 应有 347+
ls 5-wav32k/ | wc -l                     # 应等于 list
wc -l < 2-name2text-0.txt                # 应等于 list
wc -l < 6-name2semantic-0.tsv            # 应等于 list
ls 3-bert/ 2>/dev/null | wc -l           # 应为 0！

# 2. 环境变量
export MASTER_ADDR=127.0.0.1 MASTER_PORT=29500 WORLD_SIZE=1 RANK=0

# 3. 补丁
# - dataset.py: bert_feature = torch.randn(1024, len(phoneme_ids)) * 0.01
# - data_module.py: prefetch_factor + persistent_workers 条件化
# - config: num_workers: 0

# 4. 启动
screen -dmS train600 bash -c 'nohup CUDA_VISIBLE_DEVICES=0 \
  /root/miniconda3/bin/python GPT_SoVITS/s1_train.py \
  --config_file logs/reborn_mianxiaotu/s1_train_300epoch.yaml \
  > logs/train_$(date +%Y%m%d_%H%M).log 2>&1'

# 5. 等待验证（至少 3 分钟）
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader --loop=10
# 利用率 30-50%，持续波动 → 正常训练中
```

---

## 五、工具

`D:\AISleepGen_Optimized\dev_tools\ops\c36_train_tool.py`

```bash
python dev_tools/ops/c36_train_tool.py check    # 前置检查
python dev_tools/ops/c36_train_tool.py fix      # 修复
python dev_tools/ops/c36_train_tool.py launch   # 启动
python dev_tools/ops/c36_train_tool.py status   # 查看状态
```

工具做了三件事：①检查数据②打补丁③启动监控——**六条铁律都在代码里，不需要记住**。

---

## 六、致谢

至尊宝诊断了"全零张量导致 backward 卡死"这一最隐蔽的 bug，以及"forward 过了 backward 卡死 → 不是 DataLoader 的事"这个根本判断。在发现我总是踢同一块石头后，要求做真正的工具沉淀。

---

*版本: v1.0 | 创建: 2026-06-03 | 修改时更新版本号*
