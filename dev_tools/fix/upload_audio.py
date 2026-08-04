#!/usr/bin/env python
# upload_audio.py — 上传蔡志明AAC到C36
import paramiko, os, sys

host = 'connect.westd.seetacloud.com'
port = 14997
user = 'root'
password = 'noJj8NbkPt1X'

print('Connecting...')
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(host, port=port, username=user, password=password, timeout=30, banner_timeout=30)
print('Connected!')

sftp = ssh.open_sftp()
remote_dir = '/root/autodl-tmp/GPT-SoVITS/raw_audio/caizhi/'
try:
    sftp.stat(remote_dir)
except FileNotFoundError:
    sftp.mkdir(remote_dir)
    print('Created remote dir')

local_dir = r'D:\AISleepGen_Optimized\static\raw_audio_caizhi'
for f in sorted(os.listdir(local_dir)):
    if not f.endswith('.aac'):
        continue
    lp = os.path.join(local_dir, f)
    sz = os.path.getsize(lp)
    mb = sz / (1024*1024)
    rp = os.path.join(remote_dir, f)
    print(f'Uploading {f} ({mb:.1f}MB)...')
    sys.stdout.flush()
    try:
        sftp.put(lp, rp, callback=lambda t,tt: None)
        rsz = sftp.stat(rp).st_size
        print(f'  OK: {rsz} bytes matched' if rsz == sz else f'  MISMATCH: local={sz} remote={rsz}')
    except Exception as e:
        print(f'  FAIL: {type(e).__name__}: {e}')
    sys.stdout.flush()

sftp.close()
ssh.close()
print('All done!')
