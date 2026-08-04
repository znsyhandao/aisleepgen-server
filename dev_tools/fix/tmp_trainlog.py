#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'head -30 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/train_300epoch.log',
    'grep -i \"get-text\\|1-get\\|prepare\\|env\" /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/train_300epoch.log | head -20',
    'tail -30 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/train_300epoch.log',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:2000])
    if err: print(err[:200])

ssh.close()
