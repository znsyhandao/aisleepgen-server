#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看change_sovits_weights的签名
stdin, stdout, stderr = ssh.exec_command('grep -n "def change_sovits_weights\|def get_tts_wav\|def change_gpt_weights" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py | head -10')
print(stdout.read().decode())
ssh.close()
