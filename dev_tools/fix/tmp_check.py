#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/*.log 2>/dev/null",
    "cat /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/s1_training.log 2>/dev/null",
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/lightning_logs/ 2>/dev/null",
    "find /root/autodl-tmp/GPT-SoVITS/logs/caizhiming -name 'events*' 2>/dev/null",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:2000])
    if err:
        e = err[:100]
        if "No such" not in e:
            print(f"  ERR: {e}")
    print()

ssh.close()
