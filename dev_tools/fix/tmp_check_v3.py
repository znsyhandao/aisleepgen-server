#!/usr/bin/env python
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "ps aux | grep python | grep -v grep | head -10",
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/ 2>/dev/null | head -10",
    "wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/2-name2text-0.txt 2>/dev/null || echo NO_FILE",
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/half_weights/ 2>/dev/null | tail -3 || echo NO_CKPT",
    "tail -20 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/s1_training.log 2>/dev/null || echo NO_LOG",
]
for c in cmds:
    print(f"$ {c}")
    stdin, stdout, stderr = ssh.exec_command(c, timeout=10)
    print(stdout.read().decode()[:500])
    print()
ssh.close()
