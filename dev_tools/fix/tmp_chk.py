#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "ls -la /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/half_weights/",
    "ls -la /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/ckpt/",
    "free -h",
    "df -h /root/autodl-tmp",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err:
        e = err[:100]
        if "No such" not in e and "command" not in e:
            print(f"  ERR: {e}")
    print()

ssh.close()
