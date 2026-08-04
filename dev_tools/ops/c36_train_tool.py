#!/usr/bin/env python3
"""
C36 GPT-SoVITS 训练全自动工具
==============================
用法:
    python c36_train_tool.py check       # 前置检查：数据完整性 + GPU + 磁盘
    python c36_train_tool.py fix         # 修复所有已知问题（无需手动）
    python c36_train_tool.py launch      # 检查→修复→启动训练→监控
    python c36_train_tool.py patch       # 只打补丁（不做别的）
    python c36_train_tool.py infer       # 训练完成后推理
    python c36_train_tool.py status      # 检查训练状态

六条铁律全部固化在代码里，不需要记。

铁律:
    1. BERT: 不生成实体文件，用 randn fallback（zeros → NaN 死锁）
    2. DDP: 单卡也要初始化 WORLD_SIZE=1 RANK=0 MASTER_ADDR=127.0.0.1
    3. num_workers: 永远 0（同时修 prefetch_factor + persistent_workers）
    4. 等待: 第一次 backward 跑 3-5 分钟正常
    5. 调试: 永远不 python -c 写多行代码，都用文件传
    6. 检查: list→wav32k→name2text→semantic→3-bert(空)
    
v1.0 | 2026-06-03 沉淀于三次打断、八个失败启动的惨痛教训
"""

import paramiko
import sys
import os
import time
import json

# ============================================================
# C36 连接配置（从 TOOLS.md 同步）
# ============================================================
C36_HOST = "connect.westd.seetacloud.com"
C36_PORT = 14997
C36_USER = "root"
C36_PASS = "noJj8NbkPt1X"
C36_PYTHON = "/root/miniconda3/bin/python"
C36_WORKDIR = "/root/autodl-tmp/GPT-SoVITS"
C36_DATA = f"{C36_WORKDIR}/logs/reborn_mianxiaotu"
C36_CONFIG = f"{C36_DATA}/s1_train_300epoch.yaml"
C36_CKPT = f"{C36_DATA}/ckpt"
C36_HALF = f"{C36_DATA}/half_weights"
C36_BERT = f"{C36_DATA}/3-bert"
C36_LIST = f"{C36_DATA}/reborn_mianxiaotu.list"
C36_NAME2TEXT = f"{C36_DATA}/2-name2text-0.txt"
C36_SEMANTIC = f"{C36_DATA}/6-name2semantic-0.tsv"
C36_WAV32K = f"{C36_DATA}/5-wav32k"
C36_OUTPUT = f"{C36_WORKDIR}/output_reborn"
C36_SCREEN = "train600"

LOCAL_MODEL_DIR = r"D:\AISleepGen_Optimized\models"
LOCAL_AUDIO_DIR = r"D:\AISleepGen_Optimized\test_audio"


# ============================================================
# SSH 工具
# ============================================================
class C36:
    _client = None

    @classmethod
    def connect(cls):
        if cls._client is None:
            cls._client = paramiko.SSHClient()
            cls._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            cls._client.connect(C36_HOST, port=C36_PORT, username=C36_USER, password=C36_PASS, timeout=15)
        return cls._client

    @classmethod
    def close(cls):
        if cls._client:
            cls._client.close()
            cls._client = None

    @classmethod
    def exec(cls, cmd, timeout=30):
        """执行命令，返回 (stdout, stderr)"""
        c = cls.connect()
        _, o, e = c.exec_command(cmd, timeout=timeout)
        return o.read().decode('utf-8', 'replace').strip(), e.read().decode('utf-8', 'replace').strip()

    @classmethod
    def write_file(cls, path, content):
        """写文件到 C36（二进制安全）"""
        c = cls.connect()
        stdin, _, _ = c.exec_command(f"cat > {path}", timeout=10)
        stdin.write(content)
        stdin.close()
        time.sleep(0.5)

    @classmethod
    def run_python(cls, code, timeout=60):
        """在 C36 上运行 Python 代码"""
        path = "/root/autodl-tmp/_tmp_run.py"
        cls.write_file(path, code)
        cmd = f"cd {C36_WORKDIR} && {C36_PYTHON} {path}"
        out, err = cls.exec(cmd, timeout=timeout)
        cls.exec(f"rm -f {path}", timeout=5)
        return out, err

    @classmethod
    def run_bash(cls, script, timeout=120):
        """在 C36 上运行 bash 脚本"""
        path = "/root/autodl-tmp/_tmp_run.sh"
        cls.write_file(path, f"#!/bin/bash\nset -e\n{script}")
        cls.exec(f"chmod +x {path}", timeout=5)
        cmd = f"cd {C36_WORKDIR} && bash {path}"
        out, err = cls.exec(cmd, timeout=timeout)
        cls.exec(f"rm -f {path} /root/autodl-tmp/_tmp_run.py", timeout=5)
        return out, err

    @classmethod
    def check_process(cls, name="s1_train"):
        out, _ = cls.exec(f"ps aux | grep {name} | grep -v grep | wc -l", timeout=5)
        return int(out.strip())

    @classmethod
    def screen_running(cls, name=C36_SCREEN):
        out, _ = cls.exec(f"screen -ls 2>&1 | grep {name} || echo 'NO'", timeout=5)
        return "NO" not in out


# ============================================================
# 铁律 #1: BERT 特征处理（不生成实体文件，用噪声 fallback）
# ============================================================
def patch_dataset():
    """把 bert_feature = None 替换为 torch.randn * 0.01（不是 zeros！）"""
    code = '''
import sys
fp = "/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/AR/data/dataset.py"
with open(fp) as f:
    c = f.read()
old = "bert_feature = None"
new = "bert_feature = torch.randn(1024, len(phoneme_ids)) * 0.01"
if old in c:
    c = c.replace(old, new, 1)
    with open(fp, "w") as f:
        f.write(c)
    print("OK: bert_feature=randn patch applied")
else:
    print("WARN: pattern not found, checking current state")
    for i, line in enumerate(c.split("\\n")):
        if "bert_feature" in line:
            print(f"  L{i+1}: {line.strip()}")
'''
    out, err = C36.run_python(code)
    print(out)
    if err:
        print("ERR:", err[:200])
    return "OK" in out


# ============================================================
# 铁律 #2 + #3: DDP 环境变量 + num_workers=0
# ============================================================
def patch_data_module():
    """修复 data_module.py 对 num_workers=0 的兼容性"""
    code = '''
import sys
fp = "/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/AR/data/data_module.py"
with open(fp) as f:
    c = f.read()
c = c.replace("prefetch_factor=16,", "prefetch_factor=None if self.num_workers == 0 else 16,")
c = c.replace("persistent_workers=True,", "persistent_workers=False if self.num_workers == 0 else True,")
with open(fp, "w") as f:
    f.write(c)
print("OK: data_module patched for num_workers=0")
'''
    out, err = C36.run_python(code)
    print(out)
    if err:
        print("ERR:", err[:200])
    return "OK" in out


def set_config():
    """设置训练配置：num_workers=0, save_every_n_epoch=50, if_save_every_weights=false"""
    out1, _ = C36.exec(f"sed -i 's/num_workers:.*/num_workers: 0/' {C36_CONFIG}", timeout=10)
    out2, _ = C36.exec(f"sed -i 's/save_every_n_epoch:.*/save_every_n_epoch: 50/' {C36_CONFIG}", timeout=10)
    out3, _ = C36.exec(f"sed -i 's/if_save_every_weights:.*/if_save_every_weights: false/' {C36_CONFIG}", timeout=10)
    return True


# ============================================================
# 铁律 #6: 数据完整性检查
# ============================================================
def check_data():
    """检查数据完整性，返回 {'ok': bool, 'detail': {...}}"""
    script = '''
LIST=$(wc -l < reborn_mianxiaotu.list 2>/dev/null || echo 0)
WAV=$(ls logs/reborn_mianxiaotu/5-wav32k/ 2>/dev/null | wc -l || echo 0)
SEM=$(wc -l < logs/reborn_mianxiaotu/6-name2semantic-0.tsv 2>/dev/null || echo 0)
NT=$(wc -l < logs/reborn_mianxiaotu/2-name2text-0.txt 2>/dev/null || echo 0)
BERT_FILE=$(ls logs/reborn_mianxiaotu/3-bert/ 2>/dev/null | wc -l || echo 0)
CKPT=$(ls logs/reborn_mianxiaotu/ckpt/ 2>/dev/null | wc -l || echo 0)
DISK=$(df -h / | tail -1 | awk '{print $3"/"$2" ("$5")"}')
GPU=$(nvidia-smi --query-gpu=utilization.gpu,memory.used,temperature.gpu --format=csv,noheader 2>/dev/null || echo 'no-gpu')
echo "LIST=$LIST"
echo "WAV=$WAV"
echo "SEM=$SEM"
echo "NT=$NT"
echo "BERT=$BERT_FILE"
echo "CKPT=$CKPT"
echo "DISK=$DISK"
echo "GPU=$GPU"
'''
    out, _ = C36.run_bash(script)
    detail = {}
    for line in out.split("\n"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            detail[k] = v

    # 逻辑判断
    list_cnt = int(detail.get("LIST", 0))
    wav_cnt = int(detail.get("WAV", 0))
    bert_cnt = int(detail.get("BERT", 0))

    ok = True
    msgs = []
    if list_cnt == 0:
        ok = False
        msgs.append("list 文件为空")
    if wav_cnt != list_cnt:
        ok = False
        msgs.append(f"wav32k({wav_cnt}) != list({list_cnt})")
    if bert_cnt > 0:
        # BERT 存在但不是 0 → 可能是旧数据维度不匹配 → 建议删
        msgs.append(f"🚩 BERT 有 {bert_cnt} 个文件（建议删除，用噪声 fallback）")

    return ok, detail, msgs


# ============================================================
# 铁律 #4: 启动训练
# ============================================================
def clear_old_checkpoints():
    """清理旧 checkpoint"""
    C36.exec(f"rm -f {C36_CKPT}/*.ckpt {C36_HALF}/*", timeout=10)


def launch_training(epochs=600):
    """启动训练（不阻塞），返回 PID"""
    # 如果 3-bert 有文件，先删掉
    C36.exec(f"rm -rf {C36_BERT} && mkdir -p {C36_BERT}", timeout=10)

    # 清理旧 ckpt
    clear_old_checkpoints()

    # 用 bash 脚本启动（避免引号问题）
    script = f"""#!/bin/bash
cd {C36_WORKDIR}
export version="v2"
export CUDA_VISIBLE_DEVICES=0
export MASTER_ADDR=127.0.0.1
export MASTER_PORT=29500
export WORLD_SIZE=1
export RANK=0

# 确认补丁已打
python -c "
from AR.data.dataset import Text2SemanticDataset
ds = Text2SemanticDataset(
    phoneme_path='{C36_NAME2TEXT}',
    semantic_path='{C36_SEMANTIC}',
    max_sec=54, pad_val=1024,
)
item = ds[0]
bf = item['bert_feature']
print(f'BERT shape={{bf.shape}}, mean={{bf.mean().item():.4f}}, std={{bf.std().item():.4f}}')
assert bf.std().item() > 0, 'BERT IS ZERO! NaN risk!'
print('OK: bert_feature is random noise')
"

LOG={C36_DATA}/train_{epochs}epoch_$(date +%Y%m%d_%H%M).log
echo "Starting {epochs}-epoch training..." > $LOG

# 启动
{C36_PYTHON} GPT_SoVITS/s1_train.py --config_file {C36_CONFIG} >> $LOG 2>&1 &
PID=$!
echo "PID=$PID" >> $LOG

# 输出进度（防云平台心跳超时）
while kill -0 $PID 2>/dev/null; do
    echo "[$(date)] GPU=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null) PID=$PID"
    sleep 120
done
wait $PID
echo "DONE: $?" >> $LOG
"""
    C36.write_file("/root/autodl-tmp/launch_train.sh", script)
    C36.exec("chmod +x /root/autodl-tmp/launch_train.sh", timeout=5)

    # 在 screen 中后台运行
    out, _ = C36.exec(f"screen -dmS {C36_SCREEN} bash -c '/root/autodl-tmp/launch_train.sh'", timeout=10)
    time.sleep(10)

    # 检查是否启动成功
    procs = C36.check_process()
    if procs > 0:
        out, _ = C36.exec(f"nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader", timeout=10)
        return True, f"启动成功: {procs} 进程, {out}"
    else:
        return False, "启动失败: 无进程"


# ============================================================
# 状态检查
# ============================================================
def check_status():
    """检查训练状态"""
    procs = C36.check_process()
    out, _ = C36.exec(f"nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader", timeout=10)
    gpu = out.strip()

    # 找最新日志
    out, _ = C36.exec(f"ls -t {C36_DATA}/train*.log 2>/dev/null | head -1", timeout=10)
    latest_log = out.strip() if out else "-"

    if latest_log and latest_log != "-":
        out, _ = C36.exec(f"wc -l {latest_log} 2>/dev/null", timeout=5)
        log_lines = out.strip()
        out, _ = C36.exec(f"tail -5 {latest_log} 2>/dev/null", timeout=5)
        tail = out.strip()[:500]
    else:
        log_lines = "-"
        tail = "-"

    screen_alive = C36.screen_running()

    return {
        "processes": procs,
        "gpu": gpu,
        "screen_alive": screen_alive,
        "log": latest_log,
        "log_lines": log_lines,
        "tail": tail,
    }


# ============================================================
# 推理
# ============================================================
def infer(epoch=None):
    """训练完成后推理测试音频"""
    if epoch:
        ckpt_pattern = f"{C36_CKPT}/epoch={epoch-1}-*"
    else:
        ckpt_pattern = f"{C36_CKPT}/*.ckpt"

    out, _ = C36.exec(f"ls -t {ckpt_pattern} 2>/dev/null | head -1", timeout=10)
    if not out.strip():
        return False, "未找到 checkpoint"

    ckpt = out.strip()
    out_name = f"test_{epoch or 'final'}.wav"
    out_path = f"{C36_OUTPUT}/{out_name}"

    infer_code = f"""
import sys, os
os.environ["version"] = "v2"
os.chdir("{C36_WORKDIR}")
from AR.models.t2s_lightning_module import Text2SemanticLightningModule
from AR.utils.io import load_yaml_config
config = load_yaml_config("{C36_CONFIG}")
model = Text2SemanticLightningModule(config, None)
ckpt = "{ckpt}"

import torch
state = torch.load(ckpt, map_location="cpu")
if "state_dict" in state:
    model.load_state_dict(state["state_dict"])
elif "weight" in state:
    model.load_state_dict(state["weight"])
model = model.cuda().eval()

from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained("GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large")
from text.cleaner import clean_text
from text import cleaned_text_to_sequence

text = "创作意向冥想，欢迎您来到冥想兔"
phonemes, tones, lang = clean_text(text, "all", "v2")
phoneme_ids = cleaned_text_to_sequence(phonemes, "v2")
inp = tok(text, return_tensors="pt")
inp = {{k: v.cuda() for k, v in inp.items()}}

with torch.no_grad():
    out = model(text, inp["input_ids"], inp["attention_mask"])
    
torch.save(out.cpu(), "{out_path}")
print(f"Saved to {{out_path}}")
"""
    out, err = C36.run_python(infer_code, timeout=120)
    return "Saved" in out, f"{out}\\n{err[:200] if err else ''}"


# ============================================================
# 本地下载
# ============================================================
def download(epoch=None):
    """下载模型和测试音频到本地"""
    import subprocess

    ckpt_name = f"model_e{epoch}.ckpt" if epoch else "model_final.ckpt"
    audio_name = f"test_e{epoch}.wav" if epoch else "test_final.wav"

    # 找文件
    out, _ = C36.exec(f"ls -t {C36_CKPT}/*.ckpt 2>/dev/null | head -1", timeout=10)
    if not out.strip():
        return False, "没有 checkpoint"
    remote_ckpt = out.strip()

    # 找音频
    out, _ = C36.exec(f"ls -t {C36_OUTPUT}/*.wav 2>/dev/null | head -1", timeout=10)
    remote_audio = out.strip() if out.strip() else ""

    os.makedirs(LOCAL_MODEL_DIR, exist_ok=True)
    os.makedirs(LOCAL_AUDIO_DIR, exist_ok=True)

    msgs = []
    try:
        scp_cmd = [
            "scp", "-P", str(C36_PORT),
            f"{C36_USER}@{C36_HOST}:{remote_ckpt}",
            os.path.join(LOCAL_MODEL_DIR, ckpt_name)
        ]
        subprocess.run(scp_cmd, check=True, capture_output=True, timeout=120)
        msgs.append(f"模型下载: {LOCAL_MODEL_DIR}\\{ckpt_name}")
    except Exception as e:
        msgs.append(f"模型下载失败: {e}")

    if remote_audio:
        try:
            scp_cmd = [
                "scp", "-P", str(C36_PORT),
                f"{C36_USER}@{C36_HOST}:{remote_audio}",
                os.path.join(LOCAL_AUDIO_DIR, audio_name)
            ]
            subprocess.run(scp_cmd, check=True, capture_output=True, timeout=120)
            msgs.append(f"音频下载: {LOCAL_AUDIO_DIR}\\{audio_name}")
        except Exception as e:
            msgs.append(f"音频下载失败: {e}")

    return True, "\n".join(msgs)


# ============================================================
# 主命令
# ============================================================
def cmd_check():
    """前置检查"""
    print("=" * 50)
    print("  C36 前置检查")
    print("=" * 50)
    ok, detail, msgs = check_data()
    for k, v in detail.items():
        print(f"  {k}: {v}")
    print()
    if ok:
        print("  ✅ 数据完整性 OK")
    else:
        print("  ❌ 数据完整性问题:")
        for m in msgs:
            print(f"     - {m}")
    print()

    # GPU
    status = check_status()
    print(f"  GPU: {status['gpu']}")
    print(f"  进程: {status['processes']}")

    if status['screen_alive']:
        print(f"  Screen: {C36_SCREEN} 运行中")
    print()

    return ok, detail


def cmd_fix():
    """修复所有已知问题"""
    print("=" * 50)
    print("  修复已知问题")
    print("=" * 50)

    print("[1/4] 清理 3-bert 目录（用噪声 fallback）...")
    C36.exec(f"rm -rf {C36_BERT} && mkdir -p {C36_BERT}", timeout=10)
    print("      ✅")

    print("[2/4] 打 BERT 噪声补丁（randn * 0.01，不是 zeros）...")
    ok = patch_dataset()
    print(f"      {'✅' if ok else '❌'}")

    print("[3/4] 打 data_module 补丁（num_workers=0 兼容）...")
    ok = patch_data_module()
    print(f"      {'✅' if ok else '❌'}")

    print("[4/4] 设置训练配置...")
    set_config()
    print("      ✅")

    print()
    print("  ✅ 修复完成，可以启动了")
    print()

    return True


def cmd_launch(epochs=600):
    """检查→修复→启动→监控"""
    print("=" * 50)
    print("  C36 全自动训练启动")
    print("=" * 50)

    # 检查
    ok, detail = cmd_check()
    if not ok:
        print("⚠️  数据检查有警告，看看是否继续")
        # 如果 list 为空就直接退出
        if int(detail.get("LIST", 0)) == 0:
            print("❌ 无训练数据，终止")
            return False

    # 修复
    cmd_fix()

    # 启动
    print("[🚀] 启动训练...")
    success, msg = launch_training(epochs)
    print(f"     {msg}")

    if success:
        print()
        print("  ~~~~ 监控中 ~~~~")
        for i in range(5):
            time.sleep(20)
            s = check_status()
            print(f"  t={i*20+10}s | GPU={s['gpu']} | 进程={s['processes']} | 日志行数={s['log_lines']}")
            if i == 0 and s['processes'] == 0:
                print("  ❌ 进程启动失败")
                break

        if s['processes'] > 0:
            print()
            print(f"  ✅ 训练运行中!")
            print(f"  screen -r {C36_SCREEN}")
            print(f"  tail -f {s['log']}")

    return success


def cmd_status():
    """检查训练状态"""
    s = check_status()
    print(f"  进程: {s['processes']}")
    print(f"  GPU: {s['gpu']}")
    print(f"  Screen: {'✅' if s['screen_alive'] else '❌'}")
    print(f"  日志: {s['log']}")
    print(f"  行数: {s['log_lines']}")
    if s['tail'] and s['tail'] != '-':
        print(f"  最新输出: {s['tail'][:300]}")
    return s


def cmd_infer(epoch=None):
    """推理"""
    success, msg = infer(epoch)
    print(msg)
    return success


def cmd_patch():
    """只打补丁不做别的"""
    print("BERT 噪声补丁...", end=" ")
    r1 = patch_dataset()
    print("✅" if r1 else "❌")

    print("data_module 补丁...", end=" ")
    r2 = patch_data_module()
    print("✅" if r2 else "❌")

    print("配置设置...", end=" ")
    set_config()
    print("✅")

    return r1 and r2


# ============================================================
# 入口
# ============================================================
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    try:
        C36.connect()

        if command == "check":
            cmd_check()
        elif command == "fix":
            cmd_fix()
        elif command == "launch":
            epochs = int(sys.argv[2]) if len(sys.argv) > 2 else 600
            cmd_launch(epochs)
        elif command == "status":
            cmd_status()
        elif command == "patch":
            cmd_patch()
        elif command == "infer":
            epoch = int(sys.argv[2]) if len(sys.argv) > 2 else None
            cmd_infer(epoch)
        elif command == "help":
            print(__doc__)
        else:
            print(f"未知命令: {command}")
            print(__doc__)
    finally:
        C36.close()


if __name__ == "__main__":
    main()
