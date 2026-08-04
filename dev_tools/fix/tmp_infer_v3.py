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
import sys, os, torch, numpy as np
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf
change_gpt_weights(gpt_path='logs/caizhiming/half_weights/caizhiming-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')
gen = get_tts_wav(ref_wav_path='raw_audio/caizhi_ref.wav', prompt_text='欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想', prompt_language='Chinese', text='今天我们来修习共生冥想。大自然界万物生生不息。', text_language='Chinese', top_k=5, top_p=0.8, temperature=0.8)
# try to collect
try:
    first = next(gen)
    print(f'first chunk type={type(first)}', end=' ')
    if isinstance(first, torch.Tensor):
        print(f'shape={first.shape}')
    elif isinstance(first, np.ndarray):
        print(f'shape={first.shape}')
    else:
        print(f'len={len(first)}')
    # write just the first chunk
    if isinstance(first, torch.Tensor):
        sf.write('output_reborn/caizhi_600epoch.wav', first.cpu().numpy(), 32000)
    elif isinstance(first, np.ndarray):
        sf.write('output_reborn/caizhi_600epoch.wav', first, 32000)
    else:
        sf.write('output_reborn/caizhi_600epoch.wav', np.array(first), 32000)
    print(f'OK')
except StopIteration:
    print('Failed: empty generator')
"
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=120)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:3000])
if err: print("ERR:", err[:500])
ssh.close()
