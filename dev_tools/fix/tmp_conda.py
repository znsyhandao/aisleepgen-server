#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 在conda环境里跑
cmd = 'bash -c "source /root/miniconda3/etc/profile.d/conda.sh && conda activate base && python GPT_SoVITS/s1_train.py --config_file logs/caizhiming/s1_train.yaml --print_config 2>&1 | head -5"'
print(f"Running: {cmd}")
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:2000])
if err: print("ERR:", err[:200])

ssh.close()
