#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'cat /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/reborn_mianxiaotu.list | head -5',
    'cat /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/2-name2text-0.txt | head -10',
    'ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/5-wav32k/ | head -5',
    'cat /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/s1_train_300epoch.yaml',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:2000])
    if err: print(err[:100])

ssh.close()
