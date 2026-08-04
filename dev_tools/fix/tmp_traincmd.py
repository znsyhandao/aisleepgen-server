#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看眠小兔整个训练流程怎么跑的
cmds = [
    # 看s1训练的参数
    'grep -n "exp_name\|opt_dir\|inp_wav\|inp_text\|bert" /root/autodl-tmp/GPT-SoVITS/prepare_datasets/1-get-text.py | head -20',
    'head -50 /root/autodl-tmp/GPT-SoVITS/prepare_datasets/2-get-hubert-wav32k.py 2>/dev/null || echo "NO 2"',
    'head -50 /root/autodl-tmp/GPT-SoVITS/prepare_datasets/3-get-semantic.py 2>/dev/null || echo "NO 3"',
    # 看眠小兔的实际训练命令
    'ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/ | head -20',
    # 训练日志开头
    'head -5 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/train_reborn.log 2>/dev/null || head -5 /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/train_300epoch.log',
    # 看有没有setup脚本
    'ls /root/autodl-tmp/GPT-SoVITS/setup_gptsovits.sh',
    'head -40 /root/autodl-tmp/GPT-SoVITS/setup_gptsovits.sh 2>/dev/null',
]
for cmd in cmds:
    print(f'\n$ {cmd}')
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    if out: print(out[:1500])
    if err: print(err[:100])

ssh.close()
