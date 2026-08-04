import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 检查api.py的确切版本和路由
cmd = "grep -rn 'app.' /root/autodl-tmp/GPT-SoVITS/api.py | grep -E 'get|post|route|add_api' | head -20"
stdin, stdout, stderr = ssh.exec_command(cmd)
print(stdout.read().decode())
print('STDERR:', stderr.read().decode()[:200] if stderr.readable() else '')

ssh.close()
