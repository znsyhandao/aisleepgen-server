#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看眠小兔的s1训练文件
cmds = [
    "ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/ | grep -i 's1\|yaml\|config'",
    "cat /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/s1_train_300epoch.yaml 2>/dev/null",
    "ls /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/",
    "cat /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/configs/s1longer.yaml 2>/dev/null",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:1000])
    if err:
        e = err[:200]
        if 'No such' not in e:
            print(f"  ERR: {e}")
    print()

ssh.close()
