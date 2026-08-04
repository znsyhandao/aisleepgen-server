#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 在C36上检查是否可以通过网络访问本地
stdin, stdout, stderr = ssh.exec_command("curl -s --connect-timeout 3 http://172.16.234.137:8000/ 2>&1 | head -3")
print("CURL test:", stdout.read().decode()[:100])

ssh.close()
