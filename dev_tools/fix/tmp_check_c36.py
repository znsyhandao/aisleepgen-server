#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看第一期_wav目录
cmd = 'ls -la /root/autodl-tmp/GPT-SoVITS/raw_audio/第一期_wav/ 2>/dev/null; echo "---"; ls /root/autodl-tmp/GPT-SoVITS/raw_audio/'
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode()[:2000])

ssh.close()
