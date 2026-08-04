#!/usr/bin/env python
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used --format=csv,noheader,nounits",
    "ls -lt /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/half_weights/ | head -5",
    "cat /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/s1_train.yaml | head -25",
    # 找training log
    "find /root/autodl-tmp/GPT-SoVITS/ -name 's1_training*' -mmin -30 2>/dev/null",
    "ls /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/eval/ | head -5",
]
for c in cmds:
    print(f"$ {c}")
    stdin, stdout, stderr = ssh.exec_command(c, timeout=10)
    print(stdout.read().decode()[:300])
    print()
ssh.close()
