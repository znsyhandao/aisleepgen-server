#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'ls /root/autodl-tmp/GPT-SoVITS/prepare_datasets/',
    'head -30 /root/autodl-tmp/GPT-SoVITS/prepare_datasets/1-ffmpeg.py 2>/dev/null || echo "NO 1-ffmpeg.py"',
    'head -30 /root/autodl-tmp/GPT-SoVITS/prepare_datasets/2-ssl.py 2>/dev/null || echo "NO 2-ssl.py"',
    'ls /root/autodl-tmp/GPT-SoVITS/prepare_datasets/ | head -10',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err: print(f'ERR: {err[:200]}')

ssh.close()
