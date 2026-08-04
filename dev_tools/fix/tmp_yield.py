#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看get_tts_wav到底yield什么
cmd = "sed -n '850,920p' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode())
ssh.close()
