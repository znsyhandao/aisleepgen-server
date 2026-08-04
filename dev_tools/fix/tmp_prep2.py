#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看真实的prepare_datasets路径 - 在GPT_SoVITS目录下
cmds = [
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/',
    'head -50 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/s1_train.py',
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/s1_train.py',
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/s2_train.py',
    'head -30 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/s1_train.py',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err: print(err[:200])

ssh.close()
