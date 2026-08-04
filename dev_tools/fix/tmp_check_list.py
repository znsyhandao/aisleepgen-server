#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看所有行
stdin, stdout, stderr = ssh.exec_command("wc -l /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10_full.list && grep -c '|caizhiming|zh|' /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10_full.list")
print("line count:", stdout.read().decode())

# 看每行文件名
stdin2, stdout2, stderr2 = ssh.exec_command("awk -F'|' '{print $1}' /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10_full.list")
print("files:", stdout2.read().decode())

# 看每行文本长度
stdin3, stdout3, stderr3 = ssh.exec_command("awk -F'|' '{print length($4), $1}' /root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10_full.list")
print("text lengths:", stdout3.read().decode())

ssh.close()
