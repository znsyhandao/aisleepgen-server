#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    'grep -E "os.environ|cnhubert|base_path" /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py',
    'head -30 /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/2-get-hubert-wav32k.py',
]
for cmd in cmds:
    print(f"$ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:1000])
    if err: print(err[:100])
    print()

ssh.close()
