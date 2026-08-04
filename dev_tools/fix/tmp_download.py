#!/usr/bin/env python
import paramiko, os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

sftp = ssh.open_sftp()
remote = '/root/autodl-tmp/GPT-SoVITS/output_reborn/caizhi_600epoch.wav'
local = 'D:/AISleepGen_Optimized/static/audio/caizhi_600epoch_test.wav'

# 检查远程文件
stat = sftp.stat(remote)
print(f'Remote: {remote} ({stat.st_size} bytes)')

# 下载
sftp.get(remote, local)
sz = os.path.getsize(local)
print(f'Downloaded: {local} ({sz} bytes)')

sftp.close()
ssh.close()
