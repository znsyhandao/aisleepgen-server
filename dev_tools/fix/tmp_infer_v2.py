#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 直接在服务器上写文件避免转义地狱
script2 = """
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS
python -c "
import sys, os, numpy as np
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf
change_gpt_weights(gpt_path='logs/caizhiming/half_weights/caizhiming-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')
gen = get_tts_wav(ref_wav_path='raw_audio/caizhi_ref.wav', prompt_text='欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想', prompt_language='Chinese', text='今天我们来修习共生冥想。大自然界万物生生不息。', text_language='Chinese', top_k=5, top_p=0.8, temperature=0.8)
audio_list = []
for chunk in gen:
    a = np.asarray(chunk)
    audio_list.append(a)
    print(f'chunk: {a.shape} dtype={a.dtype}', end=' ')
if audio_list:
    shapes = [a.shape for a in audio_list]
    print(f'shapes: {shapes[:3]}')
    if len(audio_list) == 1:
        sf.write('output_reborn/caizhi_600epoch.wav', audio_list[0], 32000)
    else:
        flat = np.concatenate([a.reshape(-1) for a in audio_list])
        sf.write('output_reborn/caizhi_600epoch.wav', flat, 32000)
    sz = os.path.getsize('output_reborn/caizhi_600epoch.wav')
    print(f'OK: {sz} bytes')
else:
    print('Failed: empty')
"
"""
stdin, stdout, stderr = ssh.exec_command(script2, timeout=120)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:3000])
if err: print("ERR:", err[:500])
ssh.close()
