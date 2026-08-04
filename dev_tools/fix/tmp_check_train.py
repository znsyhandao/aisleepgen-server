#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/half_weights/ | tail -10",
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/ckpt/ | tail -3",
    "wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/s1_training.log",
    "grep 'total_loss_epoch\|Trainer.fit stopped' /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/s1_training.log | tail -5",
    "free -h",
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:800])
    if err:
        e = err[:100]
        if "No such" not in e:
            print(f"  ERR: {e}")
    print()

ssh.close()
