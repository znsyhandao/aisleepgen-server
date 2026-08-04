#!/usr/bin/env python
"""上传剩余的5个WAV到C36，完成后触发自动训练"""
import paramiko, os, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')
sftp = ssh.open_sftp()

src = r'D:\aisleepgen_tmp\wav_renamed'
dst_remote = '/root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav'

# 检查已有的
stdin, stdout, stderr = ssh.exec_command('ls /root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav/')
existing = set(stdout.read().decode().strip().split('\n'))
print(f"Existing: {existing}")

files_to_upload = []
for f in sorted(os.listdir(src)):
    if f.endswith('.wav') and f not in existing:
        files_to_upload.append(f)

print(f"\nNeed upload: {len(files_to_upload)} files")
for f in files_to_upload:
    print(f"  {f}")

for f in files_to_upload:
    local_path = os.path.join(src, f)
    remote_path = os.path.join(dst_remote, f)
    sz = os.path.getsize(local_path)
    
    print(f'\nUploading {f} ({sz/1024/1024:.0f}MB)')
    start = time.time()
    
    # 分块上传
    with open(local_path, 'rb') as fl:
        with sftp.open(remote_path, 'wb') as fr:
            fr.set_pipelined(True)
            total = 0
            while True:
                data = fl.read(131072)  # 128KB chunks
                if not data: break
                fr.write(data)
                total += len(data)
                if total % (1024*1024*10) == 0:
                    elapsed = time.time() - start
                    print(f'  {total/1024/1024:.0f}MB @ {total/1024/1024/elapsed:.1f}MB/s', flush=True)
    
    elapsed = time.time() - start
    speed = sz/1024/1024/elapsed
    print(f'  DONE ({elapsed:.0f}s, {speed:.1f}MB/s)')

print(f'\n===== ALL {len(files_to_upload)} FILES UPLOADED! =====')
sftp.close()
ssh.close()
