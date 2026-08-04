#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看ERes2NetV2的定义
cmd = "grep -n 'class ERes2NetV2\\|def load\\|def __init__\\|nn.Module' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/ERes2NetV2.py 2>/dev/null | head -10"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print("ERes2NetV2:", stdout.read().decode())

# 看2-get-sv.py的import部分和第62行附近
cmd2 = "sed -n '45,70p' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/prepare_datasets/2-get-sv.py"
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2, timeout=10)
print("2-get-sv.py line 45-70:")
print(stdout2.read().decode())

ssh.close()
