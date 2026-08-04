#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "cat /root/autodl-tmp/GPT-SoVITS/weight.json 2>/dev/null",
    "ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/pretrained_models/",
    "find /root/autodl-tmp/GPT-SoVITS -name '*.pth' | head -10",
    "head -20 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/pretrained_models/ERes2NetV2/config.yml 2>/dev/null || echo NO_CONFIG",
    "grep -n 'pretrained' /root/autodl-tmp/GPT-SoVITS/config.py 2>/dev/null | head -5",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err: print(err[:100])
    print()

ssh.close()
