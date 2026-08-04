#!/usr/bin/env python
import paramiko
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "find /root/autodl-tmp/GPT-SoVITS/raw_audio -name '*.wav' -type f | head -20",
    "ls -la /root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav/",
    "ls -la /root/autodl-tmp/GPT-SoVITS/raw_audio/ | grep -i 'batch\\|wav\\|001'",
]
for c in cmds:
    print(f"$ {c}")
    stdin, stdout, stderr = ssh.exec_command(c, timeout=10)
    print(stdout.read().decode()[:1000])
    print()
ssh.close()
