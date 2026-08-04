#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看训练日志，找到ZeroDivisionError前后
stdin, stdout, stderr = ssh.exec_command("grep -B5 -A5 'ZeroDivisionError\|division by zero' /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/s1_training.log")
print(stdout.read().decode()[:1000])

# 看看config里有没有batch_size问题
stdin2, stdout2, stderr2 = ssh.exec_command("head -20 /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v2/s1_train.yaml")
print(stdout2.read().decode())

ssh.close()
