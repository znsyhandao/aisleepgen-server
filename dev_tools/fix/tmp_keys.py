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
import sys, os, json
sys.path.insert(0, '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS')
os.chdir('/root/autodl-tmp/GPT-SoVITS')

# 加载inference_webui但不跑
from GPT_SoVITS.inference_webui import change_gpt_weights, change_sovits_weights

# 加载模型
change_gpt_weights(gpt_path='logs/caizhiming/half_weights/caizhiming-e600.ckpt')
change_sovits_weights(sovits_path='GPT_SoVITS/pretrained_models/gsv-v2final-pretrained/s2G2333k.pth')

# 看model_version
from GPT_SoVITS.inference_webui import model_version
print('model_version:', model_version)

# 看dict_language是什么
from GPT_SoVITS.inference_webui import dict_language
print('dict_language keys:', list(dict_language.keys()))
print('dict_language values:', list(dict_language.values()))
"
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=60)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:2000])
if err: print("ERR:", err[:300])
ssh.close()
