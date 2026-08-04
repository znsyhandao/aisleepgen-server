#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 改weight.json并infer
script = """
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS

# 改weight.json
cat > weight.json << 'EOF'
{"GPT": {"v2": "logs/caizhiming_v2/half_weights/caizhiming_v2-e600.ckpt"}, "SoVITS": {}}
EOF

python -c "
import sys, os
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')
os.environ['cnhubert_base_path'] = 'GPT_SoVITS/pretrained_models/chinese-hubert-base'
os.environ['bert_path'] = 'GPT_SoVITS/pretrained_models/chinese-roberta-wwm-ext-large'
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights, get_tts_wav
import soundfile as sf, numpy as np

change_gpt_weights(gpt_path='logs/caizhiming_v2/half_weights/caizhiming_v2-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')

gen = get_tts_wav(ref_wav_path='raw_audio/caizhi_wav/从1数到五-蔡引导.wav', prompt_text=open('output_reborn/ref_caizhi.txt').read() if os.path.exists('output_reborn/ref_caizhi.txt') else '接下来我会从一数到五', prompt_language='Chinese', text='欢迎来到眠小兔大自然疗愈系列，今天我们来修习共生冥想。大自然界万物生生不息。', text_language='Chinese', top_k=5, top_p=0.8, temperature=0.8)
samples = []
for chunk in gen:
    sr, audio = chunk
    samples.append(audio)
if samples:
    all_audio = np.concatenate(samples)
    sf.write('output_reborn/caizhi_v2_600epoch.wav', all_audio, sr)
    sz = os.path.getsize('output_reborn/caizhi_v2_600epoch.wav')
    print(f'OK: {sz} bytes, {len(all_audio)/sr:.1f}s')
else:
    print('Failed: empty')
"
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=120)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:2000])
if err: print("ERR:", err[:300])
ssh.close()
