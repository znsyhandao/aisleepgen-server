#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'find /root/autodl-tmp/GPT-SoVITS -name text -type d 2>/dev/null',
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/text/ 2>/dev/null',
    'python -c "import sys;print(1)" 2>&1',
    'ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/text/cleaner.py 2>/dev/null || echo NO_CLEANER',
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:500])
    if err: print(err[:200])
    print()

ssh.close()
