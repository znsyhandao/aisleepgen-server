#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看看最短的两个蔡志明音频的长度
cmd = '''
cd /root/autodl-tmp/GPT-SoVITS/raw_audio/input/
for f in "从1数到五-蔡引导.wav" "蔡引导的冥想.wav"; do
  dur=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$f" 2>/dev/null)
  echo "$f: ${dur}s"
done
'''
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=15)
print(stdout.read().decode())

# 也看看眠小兔的.list文件是怎么生成的——是sliced目录的切片
cmd2 = 'ls /root/autodl-tmp/GPT-SoVITS/raw_audio/sliced/ | wc -l'
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2, timeout=5)
print(f'sliced count: {stdout2.read().decode().strip()}')

ssh.close()
