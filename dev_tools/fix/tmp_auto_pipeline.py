#!/usr/bin/env python
"""
全自动训练管线：C36上跑完所有步骤，然后下载结果到本地，关机
"""
import paramiko, os, time, sys, re

HOST = 'connect.westd.seetacloud.com'
PORT = 14997
USER = 'root'
PASS = 'noJj8NbkPt1X'

LOCAL_DOWNLOAD_DIR = r'D:\AISleepGen_Optimized\static\audio'

def run_remote(cmd, timeout=600):
    """在C36上跑命令并返回输出"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    stdin, stdout, stderr = ssh.exec_command(f"source /root/miniconda3/etc/profile.d/conda.sh && conda activate base && cd /root/autodl-tmp/GPT-SoVITS && {cmd}", timeout=timeout)
    err = stderr.read().decode()
    out = stdout.read().decode()
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    return out, err, rc

def run_bg(cmd):
    """后台运行"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    transport = ssh.get_transport()
    channel = transport.open_session()
    channel.exec_command(f"source /root/miniconda3/etc/profile.d/conda.sh && conda activate base && cd /root/autodl-tmp/GPT-SoVITS && nohup {cmd} > /tmp/auto_train.log 2>&1 & echo PID:$!")
    out = channel.recv(1024).decode()
    ssh.close()
    return out

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ================== STEP 1: 验证上传的WAV ==================
log("STEP 1: Verifying uploaded WAVs...")
out, err, rc = run_remote("ls raw_audio/第一批_wav/*.wav | wc -l")
log(f"  WAV count: {out.strip()}")

out, err, rc = run_remote("for f in raw_audio/第一批_wav/*.wav; do ffprobe -v quiet -show_entries format=duration -of csv=p=0 \"$f\" 2>/dev/null; done | paste -sd+ | bc")
log(f"  Total duration: {out.strip()} seconds")

# ================== STEP 2: 切30秒 ==================
log("STEP 2: Slicing to 30s segments...")
out, err, rc = run_remote("""
mkdir -p raw_audio/第一批_sliced
rm -f raw_audio/第一批_sliced/*
for f in raw_audio/第一批_wav/*.wav; do
  name=$(basename "$f" .wav)
  ffmpeg -i "$f" -f segment -segment_time 30 -ar 32000 -ac 1 "raw_audio/第一批_sliced/${name}_%04d.wav" -y 2>/dev/null
done
ls raw_audio/第一批_sliced/*.wav | wc -l
""", timeout=3600)
log(f"  Sliced into {out.strip()} segments")

# ================== STEP 3: ASR标注 ==================
log("STEP 3: ASR annotation on all slices...")
out, err, rc = run_remote("""
python -c "
from funasr import AutoModel
import os
wav_dir = 'raw_audio/第一批_sliced'
model = AutoModel(model='iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch',
                  vad_model='iic/speech_fsmn_vad_zh-cn-16k-common-pytorch',
                  punc_model='iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch',
                  disable_update=True)
lines = []
files = sorted([f for f in os.listdir(wav_dir) if f.endswith('.wav')])
for i, f in enumerate(files):
    fp = os.path.join(wav_dir, f)
    name = f.replace('.wav','')
    result = model.generate(input=fp)
    text = result[0]['text'] if result else ''
    lines.append(f'{name}.wav|caizhiming|zh|{text}')
    if (i+1) % 50 == 0: print(f'  {i+1}/{len(files)}')
path = 'logs/caizhiming/第一批.list'
with open(path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'DONE {len(lines)} lines')
" 2>&1
""", timeout=3600)
log(f"  ASR result: {out[:200]}")
if 'DONE' not in out:
    log(f"  ASR ERROR: {err[:300]}")
    sys.exit(1)

# 解析行数
m = re.search(r'DONE (\d+)', out)
if m:
    total_lines = int(m.group(1))
    log(f"  Total lines: {total_lines}")
else:
    total_lines = 0

# ================== STEP 4: 合并现有数据 ==================
log("STEP 4: Merging with existing caizhi data...")
# 合并现有 caizhi_177.list + 第一批.list
out, err, rc = run_remote("""
cat logs/caizhiming/caizhi_177.list > logs/caizhiming/combined.list
echo "" >> logs/caizhiming/combined.list
cat logs/caizhiming/第一批.list >> logs/caizhiming/combined.list
wc -l logs/caizhiming/combined.list
""")
log(f"  Merged: {out.strip()}")

# ================== STEP 5: 合并WAV目录 ==================
log("STEP 5: Merging WAV directories...")
out, err, rc = run_remote("""
mkdir -p raw_audio/combined
cp raw_audio/sliced_caizhi_v2/*.wav raw_audio/combined/
cp raw_audio/第一批_sliced/*.wav raw_audio/combined/
ls raw_audio/combined/*.wav | wc -l
""")
log(f"  Combined WAVs: {out.strip()}")

# ================== STEP 6: 预处理管道 ==================
log("STEP 6: Running preprocessing pipeline...")
out, err, rc = run_remote("""
rm -rf logs/caizhiming_v3
export PYTHONPATH="/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:$PYTHONPATH"
export inp_text=/root/autodl-tmp/GPT-SoVITS/logs/caizhiming/combined.list
export inp_wav_dir=/root/autodl-tmp/GPT-SoVITS/raw_audio/combined
export exp_name=caizhiming_v3
export i_part=0
export all_parts=1
export opt_dir=/root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3
export bert_pretrained_dir=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large
export cnhubert_base_dir=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/pretrained_models/chinese-hubert-base
export is_half=True
export version=v2

export pretrained_s2G=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/pretrained_models/s2G488k.pth
export s2config_path=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/s2.json

mkdir -p $opt_dir
python GPT_SoVITS/prepare_datasets/1-get-text.py && echo "1_OK"
python GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py && echo "2_OK"
python GPT_SoVITS/prepare_datasets/3-get-semantic.py && echo "3_OK"
ls $opt_dir/ && echo "PREPROC_DONE"
""", timeout=7200)
log(f"  Preprocess: {out[:500]}")

if 'PREPROC_DONE' not in out:
    log(f"  PREPROC FAILED: {err[:500]}")
    sys.exit(1)

# 看数据量
out2, _, _ = run_remote("wc -l logs/caizhiming_v3/2-name2text-0.txt")
log(f"  Phoneme entries: {out2.strip()}")

# ================== STEP 7: 训练 ==================
log("STEP 7: Starting s1 training (600 epochs)...")
out, err, rc = run_remote("""
sed 's/reborn_mianxiaotu/caizhiming_v3/g' logs/reborn_mianxiaotu/s1_train_300epoch.yaml > logs/caizhiming_v3/s1_train.yaml
mkdir -p logs/caizhiming_v3/half_weights logs/caizhiming_v3/ckpt
CUDA_VISIBLE_DEVICES=0 python GPT_SoVITS/s1_train.py --config_file logs/caizhiming_v3/s1_train.yaml 2>&1 | tail -10
echo "TRAIN_DONE"
""", timeout=3600*6)
log(f"  Training output: {out[:300]}")

if 'TRAIN_DONE' not in out:
    log(f"  Training might still be running, checking...")
    out2, _, _ = run_remote("ls logs/caizhiming_v3/half_weights/ | tail -3")
    log(f"  Checkpoints: {out2[:200]}")

# ================== STEP 8: Infer测试 ==================
log("STEP 8: Running inference...")
out, err, rc = run_remote("""
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS

python -c "
import sys, os
sys.path.insert(0, 'GPT_SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf, numpy as np

best = 'logs/caizhiming_v3/half_weights'
ckpt = [f for f in os.listdir(best) if f.endswith('.ckpt')]
if ckpt:
    gpt = os.path.join(best, sorted(ckpt)[-1])
    change_gpt_weights(gpt_path=gpt)
    change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')
    
    gen = get_tts_wav(
        ref_wav_path='raw_audio/caizhi_ref.wav',
        prompt_text='大家好,欢迎来到眠小兔的冥想世界,我是蔡志明。',
        prompt_language='Chinese',
        text='欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想。大自然界万物生生不息，世间万事万物都存在着紧密的联系。',
        text_language='Chinese',
        top_k=5, top_p=0.8, temperature=0.8)
    samples = []
    for chunk in gen:
        sr, audio = chunk
        samples.append(audio)
    all_audio = np.concatenate(samples)
    sf.write('output_reborn/caizhi_v3_final.wav', all_audio, sr)
    sz = os.path.getsize('output_reborn/caizhi_v3_final.wav')
    print(f'INFER_OK {sz} {len(all_audio)/sr:.1f}s')
else:
    print('INFER_FAIL no_ckpt')
"
""", timeout=600)

log(f"  Infer result: {out[:200]}")

# ================== STEP 9: 下载到本地 ==================
log("STEP 9: Downloading files to local...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
sftp = ssh.open_sftp()

files_to_download = [
    ('output_reborn/caizhi_v3_final.wav', 'caizhi_v3_final.wav'),
]

# 找最好的checkpoint
out, _, _ = run_remote("ls -t logs/caizhiming_v3/half_weights/ | head -1")
best_ckpt = out.strip()
if best_ckpt:
    files_to_download.append((f'logs/caizhiming_v3/half_weights/{best_ckpt}', f'caizhiming_v3_{best_ckpt}'))

for remote_rel, local_name in files_to_download:
    remote_abs = f'/root/autodl-tmp/GPT-SoVITS/{remote_rel}'
    local_abs = os.path.join(LOCAL_DOWNLOAD_DIR, local_name)
    try:
        sftp.stat(remote_abs)
        sftp.get(remote_abs, local_abs)
        sz = os.path.getsize(local_abs)
        log(f"  Downloaded {local_name} ({sz/1024:.0f}KB)")
    except FileNotFoundError:
        log(f"  SKIP: {remote_rel} not found")

sftp.close()

log("ALL DONE! All files downloaded.")
log("Now shutting down C36...")

# ================== STEP 10: 关机 ==================
log("STEP 10: Powering off C36...")
run_remote("poweroff", timeout=10)
log("C36 shutdown command sent. Goodnight!")

print("\n" + "="*50)
print("✅ FULL PIPELINE COMPLETE!")
print("✅ Inference audio: D:\\AISleepGen_Optimized\\static\\audio\\caizhi_v3_final.wav")
print("✅ Model downloaded locally")
print("✅ C36 powered off")
print("="*50)
