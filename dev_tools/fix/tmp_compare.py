#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

cmds = [
    "head -5 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/2-name2text-0.txt",
    "echo SEP",
    "head -5 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/2-name2text-0.txt",
    "echo SEP",
    "head -3 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/6-name2semantic-0.tsv",
    "echo SEP",
    "head -3 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/6-name2semantic-0.tsv",
    "echo SEP",
    "diff /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/s1_train_300epoch.yaml /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/s1_train.yaml",
    "echo SEP",
    "wc -l /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/2-name2text-0.txt /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/2-name2text-0.txt",
]
for cmd in cmds:
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    if out:
        if out == "SEP":
            print()
        else:
            print(out[:600])
    print()

ssh.close()
