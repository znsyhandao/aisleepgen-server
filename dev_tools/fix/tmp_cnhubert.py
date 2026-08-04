#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看cnhubert.py需要什么环境变量
cmd = "head -40 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/feature_extractor/cnhubert.py"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode())

ssh.close()
