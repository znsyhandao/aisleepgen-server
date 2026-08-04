#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

stdin, stdout, stderr = ssh.exec_command('grep -A 5 "dict_language_v1\|dict_language_v2" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py | head -20')
print(stdout.read().decode())
ssh.close()
