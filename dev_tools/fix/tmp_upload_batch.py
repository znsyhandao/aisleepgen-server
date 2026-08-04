#!/usr/bin/env python
import paramiko, os, sys, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

sftp = ssh.open_sftp()
wav_dir = r'E:\笔记本D盘备份\发烧友快乐音乐湖\输出给柔灵'
remote_dir = '/root/autodl-tmp/GPT-SoVITS/raw_audio/rouling_input'

# 建目录
stdin, stdout, stderr = ssh.exec_command(f'mkdir -p {remote_dir}')
print("MKDIR done")

files = sorted([f for f in os.listdir(wav_dir) if f.endswith('.WAV')])
total = len(files)

for i, f in enumerate(files, 1):
    local = os.path.join(wav_dir, f)
    remote = f'{remote_dir}/{f}'
    sz = os.path.getsize(local) / (1024*1024)
    
    # 检查是否已经上传
    try:
        sftp.stat(remote)
        print(f'  [{i}/{total}] {f} ({sz:.0f}MB) — already exists, skip')
        continue
    except:
        pass
    
    start = time.time()
    print(f'  [{i}/{total}] Uploading {f} ({sz:.0f}MB)...', flush=True)
    sftp.put(local, remote)
    elapsed = time.time() - start
    print(f'    Done in {elapsed:.0f}s @ {sz/elapsed:.1f} MB/s', flush=True)

sftp.close()
ssh.close()
print('ALL UPLOADED')
