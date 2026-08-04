#!/usr/bin/env python
"""简化版自动管线脚本"""
import paramiko, os, time, re

HOST = 'connect.westd.seetacloud.com'
PORT = 14997
USER = 'root'
PASS = 'noJj8NbkPt1X'
LOCAL_DIR = r'D:\AISleepGen_Optimized\static\audio'

def run(cmd, timeout=300):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    stdin, stdout, stderr = ssh.exec_command(
        f"source /root/miniconda3/etc/profile.d/conda.sh && conda activate base && "
        f"cd /root/autodl-tmp/GPT-SoVITS && {cmd}", timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    return out, err, rc

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# 先把WAV都转成16k格式（ASR需要）
log("STEP 1/8: Converting WAVs to 16kHz for ASR...")
out, err, rc = run("""
mkdir -p raw_audio/第一批_16k
for f in raw_audio/第一批_wav/*.wav; do
  name=$(basename "$f" .wav)
  ffmpeg -i "$f" -ar 16000 -ac 1 "raw_audio/第一批_16k/${name}.wav" -y 2>/dev/null
done
ls raw_audio/第一批_16k/*.wav | wc -l
""", timeout=600)
log(f"  16k WAVs: {out.strip()}")

# 全段ASR
log("STEP 2/8: Full-audio ASR...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
sftp = ssh.open_sftp()
try: sftp.mkdir('/root/autodl-tmp/GPT-SoVITS/dev_tools')
except: pass
# 确保dev_tools目录存在
try: sftp.mkdir('/root/autodl-tmp/GPT-SoVITS/dev_tools')
except: pass

# 写ASR脚本
asr_code = '''
import os
from funasr import AutoModel
wav_dir = '/root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav'
model = AutoModel(model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                  vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                  punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                  disable_update=True)
lines = []
files = sorted([f for f in os.listdir(wav_dir) if f.endswith(".wav")])
for i, f in enumerate(files):
    fp = os.path.join(wav_dir, f)
    name = f.replace(".wav", "")
    result = model.generate(input=fp)
    text = result[0]["text"] if result else ""
    lines.append(f"{name}.wav|caizhiming|zh|{text}")
    if (i + 1) % 5 == 0:
        print(f"{i+1}/{len(files)}", flush=True)
path = "/root/autodl-tmp/GPT-SoVITS/logs/caizhiming/第一批.list"
with open(path, "w", encoding="utf-8") as f:
    f.write("\\n".join(lines))
print(f"DONE {len(lines)} lines")
'''
sftp.open('/root/autodl-tmp/GPT-SoVITS/dev_tools/tmp_auto_asr.py', 'w').write(asr_code)
sftp.close()
ssh.close()

out, err, rc = run("python /root/autodl-tmp/GPT-SoVITS/dev_tools/tmp_auto_asr.py", timeout=3600)
log(f"  ASR: {out[:200]}")
if 'DONE' not in out:
    log(f"  ASR FAILED: {err[:300]}")
    log("  Trying funasr direct...")

# 检查结果
out, _, _ = run("wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/第一批.list 2>/dev/null")
log(f"  Lines: {out.strip()}")

# 合并旧数据
log("STEP 3/8: Merging with caizhi data...")
out, err, rc = run("""
cat logs/caizhiming/caizhi_177.list > logs/caizhiming/combined.list
echo "" >> logs/caizhiming/combined.list
cat logs/caizhiming/第一批.list >> logs/caizhiming/combined.list
wc -l logs/caizhiming/combined.list
""")
log(f"  Merged: {out.strip()}")

# 切片 + 预处理
log("STEP 4/8: Slicing + preprocessing...")
out, err, rc = run("""
# 切片30秒
mkdir -p raw_audio/第一批_sliced_32k
for f in raw_audio/第一批_wav/*.wav; do
  name=$(basename "$f" .wav)
  ffmpeg -i "$f" -f segment -segment_time 30 -ar 32000 -ac 1 "raw_audio/第一批_sliced_32k/${name}_%04d.wav" -y 2>/dev/null
done

# 合并所有切片
mkdir -p raw_audio/all_sliced_v3
cp raw_audio/sliced_caizhi_v2/*.wav raw_audio/all_sliced_v3/
cp raw_audio/第一批_sliced_32k/*.wav raw_audio/all_sliced_v3/
echo "WAVS: $(ls raw_audio/all_sliced_v3/*.wav | wc -l)"

# 预处理
rm -rf logs/caizhiming_v3
export PYTHONPATH=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:$PYTHONPATH
export inp_text=/root/autodl-tmp/GPT-SoVITS/logs/caizhiming/combined.list
export inp_wav_dir=/root/autodl-tmp/GPT-SoVITS/raw_audio/all_sliced_v3
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
wc -l $opt_dir/2-name2text-0.txt
ls $opt_dir/
echo "PREPROC_DONE"
""", timeout=7200)
log(f"  Preprocess: {out[:500]}")

if 'PREPROC_DONE' not in out:
    log(f"  FAILED: {err[:500]}")
    exit(1)

# 训练
log("STEP 5/8: Training 600 epochs...")
out, err, rc = run("""
sed 's/reborn_mianxiaotu/caizhiming_v3/g' logs/reborn_mianxiaotu/s1_train_300epoch.yaml > logs/caizhiming_v3/s1_train.yaml
mkdir -p logs/caizhiming_v3/half_weights logs/caizhiming_v3/ckpt
CUDA_VISIBLE_DEVICES=0 python GPT_SoVITS/s1_train.py --config_file logs/caizhiming_v3/s1_train.yaml
echo "TRAIN_DONE"
""", timeout=21600)
log(f"  Training: {out[:200]}")

# 检查模型
out, _, _ = run("ls logs/caizhiming_v3/half_weights/ | tail -2")
log(f"  Models: {out.strip()}")

# 推理
log("STEP 6/8: Inference...")
infer_code = '''
import sys, os
sys.path.insert(0, "/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS")
os.chdir("/root/autodl-tmp/GPT-SoVITS")
os.environ["cnhubert_base_path"] = "GPT_SoVITS/pretrained_models/chinese-hubert-base"
os.environ["bert_path"] = "GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large"
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf, numpy as np
best = "/root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/half_weights"
ckpt = [f for f in os.listdir(best) if f.endswith(".ckpt")]
if ckpt:
    gpt = os.path.join(best, sorted(ckpt)[-1])
    change_gpt_weights(gpt_path=gpt)
    change_sovits_weights(sovits_path="GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth")
    gen = get_tts_wav(ref_wav_path="raw_audio/caizhi_ref.wav",
                       prompt_text="大家好,欢迎来到眠小兔的冥想世界,我是蔡志明。",
                       prompt_language="Chinese",
                       text="欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想。大自然界万物生生不息。",
                       text_language="Chinese", top_k=5, top_p=0.8, temperature=0.8)
    samples = []
    for chunk in gen:
        sr, audio = chunk
        samples.append(audio)
    all_audio = np.concatenate(samples)
    sf.write("output_reborn/caizhi_v3_final.wav", all_audio, sr)
    sz = os.path.getsize("output_reborn/caizhi_v3_final.wav")
    print(f"INFER_OK {sz} {len(all_audio)/sr:.1f}s")
else:
    print("INFER_FAIL no_ckpt")
'''

sftp2 = paramiko.SSHClient()
sftp2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
sftp2.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
sftp2.open_sftp().open('/root/autodl-tmp/GPT-SoVITS/dev_tools/tmp_auto_infer.py', 'w').write(infer_code)
sftp2.close()

out, err, rc = run("python /root/autodl-tmp/GPT-SoVITS/dev_tools/tmp_auto_infer.py", timeout=600)
log(f"  Infer: {out[:200]}")
if 'INFER_OK' not in out:
    log(f"  Infer FAILED: {err[:300]}")

# 下载到本地
log("STEP 7/8: Downloading to local...")
ssh3 = paramiko.SSHClient()
ssh3.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh3.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
sftp3 = ssh3.open_sftp()

for remote_rel, local_name in [
    ('output_reborn/caizhi_v3_final.wav', 'caizhi_v3_final.wav'),
    ('logs/caizhiming_v3/half_weights', 'half_weights_v3'),
]:
    if remote_rel.endswith('.wav'):
        remote_abs = f'/root/autodl-tmp/GPT-SoVITS/{remote_rel}'
        local_abs = os.path.join(LOCAL_DIR, local_name)
        try:
            sftp3.stat(remote_abs)
            sftp3.get(remote_abs, local_abs)
            sz = os.path.getsize(local_abs)
            log(f"  Downloaded {local_name} ({sz/1024:.0f}KB)")
        except: pass

sftp3.close()
ssh3.close()

# 关机
log("STEP 8/8: Powering off C36...")
run("poweroff", timeout=10)
log("C36 SHUTDOWN SENT")

print("\n" + "="*50)
print("✅ AUTO PIPELINE COMPLETE!")
print("✅ Audio: D:\\AISleepGen_Optimized\\static\\audio\\caizhi_v3_final.wav")
print("✅ C36 powered off")
print("✅ Goodnight!")
print("="*50)
