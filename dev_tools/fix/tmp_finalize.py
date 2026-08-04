#!/usr/bin/env python
"""重新infer + 下载 + 关机"""
import paramiko, os

HOST = 'connect.westd.seetacloud.com'
PORT = 14997
USER = 'root'
PASS = 'noJj8NbkPt1X'
LOCAL_DIR = r'D:\AISleepGen_Optimized\static\audio'

def run(cmd, timeout=60):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    ssh.exec_command(f"source /root/miniconda3/etc/profile.d/conda.sh && conda activate base && "
                     f"cd /root/autodl-tmp/GPT-SoVITS && {cmd}", timeout=timeout)
    ssh.close()

def run_get(cmd, timeout=60):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    stdin, stdout, stderr = ssh.exec_command(f"source /root/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate base && cd /root/autodl-tmp/GPT-SoVITS && {cmd}", timeout=timeout)
    out = stdout.read().decode()
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    return out, rc

# 第一步：下载模型到本地
print("STEP 1: Downloading model...")
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
sftp = ssh.open_sftp()

remote_model = '/root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/half_weights/caizhiming_v3-e600.ckpt'
local_model = os.path.join(LOCAL_DIR, 'caizhiming_v3-e600.ckpt')
sftp.get(remote_model, local_model)
print(f"  Model: {os.path.getsize(local_model)/1024/1024:.0f}MB")

# 第二步：Infer（需要先设PYTHONPATH）
print("STEP 2: Running inference on C36...")
infer_script = """
export PYTHONPATH=/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:$PYTHONPATH
python -c "
import sys, os
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf, numpy as np
change_gpt_weights(gpt_path='logs/caizhiming_v3/half_weights/caizhiming_v3-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')
gen = get_tts_wav(
    ref_wav_path='raw_audio/caizhi_ref.wav',
    prompt_text='大家好,欢迎来到眠小兔的冥想世界,我是蔡志明。',
    prompt_language='Chinese',
    text='欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想。大自然界万物生生不息。',
    text_language='Chinese', top_k=5, top_p=0.8, temperature=0.8)
samples = []
for chunk in gen:
    sr, audio = chunk
    samples.append(audio)
all_audio = np.concatenate(samples)
sf.write('output_reborn/caizhi_v3_final.wav', all_audio, sr)
sz = os.path.getsize('output_reborn/caizhi_v3_final.wav')
print(f'INFER_OK {sz} bytes {len(all_audio)/sr:.1f}s')
"
"""
out, rc = run_get(infer_script, timeout=300)
print(f"  Infer: {out[:200]}")

# 第三步：下载infer音频
print("STEP 3: Downloading inference audio...")
try:
    remote_infer = '/root/autodl-tmp/GPT-SoVITS/output_reborn/caizhi_v3_final.wav'
    local_infer = os.path.join(LOCAL_DIR, 'caizhi_v3_final.wav')
    sftp.stat(remote_infer)
    sftp.get(remote_infer, local_infer)
    print(f"  Audio: {os.path.getsize(local_infer)/1024:.0f}KB")
except FileNotFoundError:
    print("  No infer output found")

sftp.close()
ssh.close()

print("\n✅ ALL DONE!")
print(f"✅ Model: {local_model}")
print(f"✅ Audio: {local_infer}")

# 第四步：发关机命令
print("STEP 4: Shutting down C36...")
run_get("poweroff", timeout=5)
print("✅ C36 shutdown sent")
