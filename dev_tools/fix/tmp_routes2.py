#!/usr/bin/env python3
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

stdin, stdout, stderr = ssh.exec_command('cat -n /root/autodl-tmp/GPT-SoVITS/api.py | sed -n "1328,1370p"')
print(stdout.read().decode().strip())

ssh.close()
