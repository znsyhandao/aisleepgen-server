#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看import在哪
cmds = [
    "grep -rn 'class ERes2NetV2' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/ 2>/dev/null | head -5",
    "grep -rn 'class ERes2NetV2' /root/autodl-tmp/GPT-SoVITS/ 2>/dev/null | head -5",
    "python -c \"from ERes2NetV2 import ERes2NetV2; e = ERes2NetV2(24,4,4); print(type(e)); print(dir(e)[:10])\" 2>&1",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err: print(err[:200])
    print()

ssh.close()
