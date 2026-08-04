#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'cat /root/autodl-tmp/GPT-SoVITS/raw_audio/sliced/0.list 2>/dev/null',
    'ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/',
    'ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/half_weights/ | tail -10',
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/',
    'cat /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/s1longer.yaml 2>/dev/null',
    'cat /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/s2.json 2>/dev/null | head -30',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:1000])
    if err: print(err[:100])

ssh.close()
