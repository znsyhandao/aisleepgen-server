#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看get_tts_wav参数
stdin, stdout, stderr = ssh.exec_command('grep -n "def get_tts_wav" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py')
print("Line:", stdout.read().decode())

stdin2, stdout2, stderr2 = ssh.exec_command('sed -n "790,810p" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py')
print(stdout2.read().decode())

ssh.close()
