#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看yield语句
stdin, stdout, stderr = ssh.exec_command('grep -n "yield" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py')
print("yield lines:", stdout.read().decode())

ssh.close()
