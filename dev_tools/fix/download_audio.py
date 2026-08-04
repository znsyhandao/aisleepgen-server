#!/usr/bin/env python
import paramiko, os, sys

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')
sftp = ssh.open_sftp()
sftp.get('/root/autodl-tmp/GPT-SoVITS/output_reborn/caizhi_zero_test.wav', r'D:\AISleepGen_Optimized\static\audio\caizhi_zero_test.wav')
sftp.close()
ssh.close()
sz = os.path.getsize(r'D:\AISleepGen_Optimized\static\audio\caizhi_zero_test.wav')
print(f'Downloaded: {sz} bytes ({sz/1024:.0f}KB)')
