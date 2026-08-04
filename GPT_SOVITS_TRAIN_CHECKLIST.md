# GPT-SoVITS caizhiming_mingxiang_v2 从重建数据到启动训练操作手册

## 预期耗时：30-40分钟

## 环境
- 服务器：`ssh -p 39916 root@36.103.198.206`
- 密码：`8OOmay9tXoHh`
- Python：`/root/miniconda3/bin/python`
- 基础路径：`/root/autodl-tmp/GPT-SoVITS`
- 实验名：`caizhiming_mingxiang_v2`
- GPU：RTX 5090

---

## 第一步：诊断当前状态（1分钟）

```bash
# 检查half_weights时间戳（如果最近更新 <30分钟说明在训练）
ls -la /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/half_weights/ | tail -3

# 检查日志最新行数
wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/train.log
tail -5 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/train.log

# 检查GPU
nvidia-smi
```

**期望状态：** half_weights 最近未更新（>1小时），日志 <50行，GPU util ≈ 0%

---

## 第二步：清除旧训练残留（2分钟）

```bash
# 杀掉旧进程
pkill -f s1_train 2>/dev/null

# 清理旧half_weights（必须清！否则会从旧checkpoint恢复）
rm -rf /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/half_weights/
rm -rf /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/ckpt/
rm -rf /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/lightning_logs/

# 重建目录
mkdir -p /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/{half_weights,ckpt,lightning_logs}

# 清老日志
> /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/train.log
```

---

## 第三步：准备真实数据（8分钟）

### 3a. 确认phoneme数据重建文件

**目录结构预期：**
```
/root/autodl-tmp/GPT-SoVITS/data/caizhiming_mingxiang_v2/
├── inp_phoneme.txt          # 管道符分隔
├── 1-cnhubert/              # CNHuBERT特征
│   └── *.wav.pt
├── 2-name2text-0.list       # 制表符分隔
├── 2-name2text_pipe.txt     # 管道符分隔
├── 3-bert/                  # BERT特征
│   └── *.pt
├── 5-phoneme/               # ★ 空目录（不需要，v2直接从2-name2text读）
└── 6-name2semantic-0.tsv    # Semantic token
```

**如果 `6-name2semantic-0.tsv` 不存在或内容假：**

```bash
cd /root/autodl-tmp/GPT-SoVITS

# 检查是否已有重建文件
ls -la data/caizhiming_mingxiang_v2/2-name2text-0.list
ls -la data/caizhiming_mingxiang_v2/inp_phoneme.txt 
ls -la data/caizhiming_mingxiang_v2/6-name2semantic-0.tsv
```

### 3b. 如果phoneme数据需要重建（计划B）

```bash
cd /root/autodl-tmp/GPT-SoVITS

# 检查原始WAV目录
ls raw_audio/冥想_wav_切片/ | wc -l

# 如果已有 inp_phoneme.txt，直接phonemize：
cat data/caizhiming_mingxiang_v2/inp_phoneme.txt | head -3

# 执行1-get-text.py（会同时生成phoneme + BERT）
export PYTHONPATH=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:$PYTHONPATH
/root/miniconda3/bin/python tools/1-get-text.py \
  --inp data/caizhiming_mingxiang_v2/inp_phoneme.txt \
  --out data/caizhiming_mingxiang_v2/
```

### 3c. 如果semantic token需要重建

```bash
cd /root/autodl-tmp/GPT-SoVITS

# 确认有s2G权重
ls logs/caizhiming_mingxiang_v2/s2G488k.pth 2>/dev/null || \
  cp pretrained_models/s2G488k.pth logs/caizhiming_mingxiang_v2/

# 执行2-get-semantic.py
export PYTHONPATH=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:$PYTHONPATH
/root/miniconda3/bin/python tools/2-get-semantic.py \
  --inp_dir data/caizhiming_mingxiang_v2/ \
  --out_dir logs/caizhiming_mingxiang_v2/
```

### 3d. 最终数据验证

```bash
# phoneme格式验证（应该是真实音素，不是0 0 0）
head -1 data/caizhiming_mingxiang_v2/2-name2text-0.list | cut -f2

# semantic 行数
wc -l logs/caizhiming_mingxiang_v2/6-name2semantic-0.tsv

# 确保两者行数匹配
wc -l data/caizhiming_mingxiang_v2/2-name2text-0.list
```

**成功标志：** phoneme 列是 `j ie1 x ia4 l ai5...` 这样的真实中文拼音音素，不是数字。

---

## 第四步：配置训练（3分钟）

### 4a. 创建正确的yaml

```yaml
# /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/s1_train_300epoch.yaml
output_dir: /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2

train_semantic_path: /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/6-name2semantic-0.tsv
train_phoneme_path: /root/autodl-tmp/GPT-SoVITS/data/caizhiming_mingxiang_v2/2-name2text-0.list

train:
  epochs: 300
  batch_size: 4
  accumulate_grad_batches: 1
  num_workers: 2
  learning_rate: 1e-4
  save_every_n_epoch: 10
  if_train_s1_encoder: true
  if_train_s1_pho: true

model:
  type: Text2SemanticDecoder
  config:
    dropout: 0.1
    norm_type: layer_norm

data:
  max_ps_ratio: 25
  min_ps_ratio: 3
  max_sample: 1000
```

### 4b. 写入yaml

```bash
cat > /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/s1_train_300epoch.yaml << 'EOF'
[粘贴上面的yaml内容]
EOF
```

---

## 第五步：创建文本软链接（1分钟）

```bash
cd /root/autodl-tmp/GPT-SoVITS
ln -sf GPT_SoVITS/text ./text
```

**不做的后果：** `ModuleNotFoundError: No module named 'text'`

---

## 第六步：启动训练（1分钟）

```bash
cd /root/autodl-tmp/GPT-SoVITS

screen -dmS train bash -c "
  export PYTHONPATH=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:\$PYTHONPATH && \
  /root/miniconda3/bin/python GPT_SoVITS/s1_train.py \
    --config_file logs/caizhiming_mingxiang_v2/s1_train_300epoch.yaml \
    > logs/caizhiming_mingxiang_v2/train.log 2>&1
"

echo "启动命令已发送"
```

---

## 第七步：验证训练启动（5分钟等待）

```bash
# 等10秒
sleep 10

# 检查进程
ps aux | grep s1_train | grep -v grep

# 检查日志是否有新内容
wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/train.log
tail -20 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/train.log

# 检查GPU是否开始占用
nvidia-smi

# 等30秒后检查half_weights是否开始生成
sleep 30
ls -la /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_mingxiang_v2/half_weights/ | tail -3
```

**成功标志：**
- half_weights 目录开始出现 `.ckpt` 文件
- 日志行数持续增加（>50, >100, >200...）
- GPU memory 在 4000-8000 MiB 之间
- half_weights 文件大小会略有不一致（参数在实际更新）

**失败信号：**
- 日志停在 `Total FLOPs: 0` — 数据问题（phoneme/semantic 不匹配）
- half_weights 大小完全一致 — 伪训练，参数没变化

---

## 故障排除速查

| 症状 | 原因 | 修复 |
|------|------|------|
| `Total FLOPs: 0` | 数据格式错或路径不对 | 检查train_semantic_path和train_phoneme_path路径，确认行数匹配 |
| `No module named 'text'` | 缺少软链接 | `ln -sf GPT_SoVITS/text ./text`（在BASE目录） |
| `No module named 'utils'` | PYTHONPATH没设置 | 用screen脚本确保export了PYTHONPATH |
| half_weights 大小全一致 | 假数据或旧checkpoint恢复 | 清half_weights/ckpt/lightning_logs重新启动 |
| GPU util=0% 但mem占用>4GB | 训练可能卡在DataLoader | 检查nltk数据包：`python -c "import nltk; nltk.download('averaged_perceptron_tagger_eng')"` |
| `KeyError: 'total_memory'` | pyTorch版本问题 | 搜代码把total_mem改成total_memory |
| 日志行数增加但loss不降 | 数据质量差 | 检查phoneme是否是真音素 |

---

## 本地启动工具（Windows一键启动）

```bash
python D:\super_frontier_radar\c36_train_tool.py launch [epochs]
```

当前 `c36_train_tool.py` 支持命令：`check`、`launch`、`status`
使用前需根据实际数据状态确认步骤2-5已手动完成。
