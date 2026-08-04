#!/usr/bin/env python
import paramiko, time

for attempt in range(3):
    print(f"Attempt {attempt+1}...")
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', 
                    password='noJj8NbkPt1X', timeout=20, banner_timeout=20)
        print("CONNECTED!")
        stdin, stdout, stderr = ssh.exec_command("uptime; nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits", timeout=10)
        print(stdout.read().decode())
        ssh.close()
        break
    except paramiko.AuthenticationException as e:
        print(f"  Auth failed: {e}")
        break  # 密码错误不会变
    except Exception as e:
        print(f"  Failed: {e}")
        if attempt < 2:
            print("  Waiting 30s...")
            time.sleep(30)
