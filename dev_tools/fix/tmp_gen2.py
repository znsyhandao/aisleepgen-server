#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

script = """
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS
python -c "
import sys, os
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'

from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf
import numpy as np

change_gpt_weights(gpt_path='logs/caizhiming/half_weights/caizhiming-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')

text = '欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想。'
gen = get_tts_wav(ref_wav_path='raw_audio/sliced_caizhi/gongsheng_0000.wav', prompt_text=text, prompt_language='all_zh', text=text, text_language='all_zh', top_k=5, top_p=0.8, temperature=0.8)
audio_list = [c for c in gen]
if audio_list:
    audio = np.concatenate(audio_list, axis=0)
    sf.write('output_reborn/caizhi_600epoch.wav', audio, 32000)
    sz = os.path.getsize('output_reborn/caizhi_600epoch.wav')
    print(f'OK: {sz} bytes, {audio.shape[0]/32000:.1f}s')
else:
    print('Failed: empty')
"
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=120)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:2000])
if err: print("ERR:", err[:500])
ssh.close()
