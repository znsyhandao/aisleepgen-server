#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

stdin, stdout, stderr = ssh.exec_command("cat /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10_full.list")
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:3000])
if err: print("ERR:", err[:200])
ssh.close()
