#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看2-get-sv.py的sv_path
cmd = "grep -n 'sv_path' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/2-get-sv.py"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode())

cmd2 = "head -70 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/2-get-sv.py"
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2, timeout=10)
print('---')
print(stdout2.read().decode())

ssh.close()
