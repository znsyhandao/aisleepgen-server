#!/usr/bin/env python
"""
逐个上传WAV到C36，每个完成后删除本地临时文件
然后用自动脚本触发C36上的训练管线
"""
import paramiko, os, sys, time, json, shutil

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X', timeout=30)
except Exception as e:
    print(f"SSH connect failed: {e}")
    sys.exit(1)

sftp = ssh.open_sftp()

src = r'D:\aisleepgen_tmp\wav_renamed'
dst_remote = '/root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav'
tmp_remote = '/root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav.tmp'

# 建目录
try: sftp.mkdir(dst_remote)
except: pass

files = sorted(f for f in os.listdir(src) if f.endswith('.wav'))
remaining = []

for f in files:
    local_path = os.path.join(src, f)
    remote_path = os.path.join(dst_remote, f)
    sz = os.path.getsize(local_path)
    
    # 检查是否已存在
    try:
        existing = sftp.stat(remote_path).st_size
        if existing == sz:
            print(f'[SKIP] {f} ({sz/1024/1024:.0f}MB) — already exists')
            continue
        elif existing < sz:
            print(f'[REMOVE] incomplete {f}')
            sftp.remove(remote_path)
    except FileNotFoundError:
        pass
    
    print(f'[UPLOAD] {f} ({sz/1024/1024:.0f}MB)...')
    start = time.time()
    success = False
    
    # 尝试方法A: put
    try:
        sftp.put(local_path, remote_path)
        # 验证
        uploaded = sftp.stat(remote_path).st_size
        if uploaded == sz:
            success = True
            elapsed = time.time() - start
            print(f'  OK ({elapsed:.0f}s, {sz/1024/1024/elapsed:.1f}MB/s)')
    except Exception as e:
        print(f'  put() failed: {str(e)[:60]}')
    
    # 尝试方法B: 分块写入
    if not success:
        try:
            with open(local_path, 'rb') as fl:
                with sftp.open(remote_path, 'wb') as fr:
                    fr.set_pipelined(True)
                    while True:
                        data = fl.read(65536)
                        if not data: break
                        fr.write(data)
            uploaded = sftp.stat(remote_path).st_size
            if uploaded == sz:
                success = True
                elapsed = time.time() - start
                print(f'  OK (chunk) ({elapsed:.0f}s, {sz/1024/1024/elapsed:.1f}MB/s)')
        except Exception as e:
            print(f'  chunk() failed: {str(e)[:60]}')
    
    if success:
        # 删除本地临时文件
        os.remove(local_path)
        print(f'  [DEL] local file cleaned')
    else:
        print(f'  FAILED! Will retry later')
        remaining.append(f)

# 清理
sftp.close()

# 记录剩余文件
if remaining:
    print(f'\n===== REMAINING FILES ({len(remaining)}) =====')
    for f in remaining:
        print(f'  {f}')
else:
    print(f'\n===== ALL 10 FILES UPLOADED! =====')
    
    # 写成功标记文件，供主调度器读取
    with open(r'D:\aisleepgen_tmp\upload_done.flag', 'w') as f:
        f.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")}\n')
    
    print('Ready to start training pipeline on C36')

ssh.close()
