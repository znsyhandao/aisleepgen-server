#!/usr/bin/env python
import paramiko, os, time

# 试着重连
for i in range(3):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X', timeout=15)
        
        # 检查训练状态
        cmds = [
            "ls -lt /root/autodl-tmp/GPT-SoVITS/logs/caizhiming_v3/half_weights/ | head -3",
            "uptime",
        ]
        for c in cmds:
            stdin, stdout, stderr = ssh.exec_command(c, timeout=10)
            print(f"$ {c}\n{stdout.read().decode()[:200]}")
        
        ssh.close()
        break
    except Exception as e:
        print(f"Attempt {i+1}: {e}")
        time.sleep(5)
