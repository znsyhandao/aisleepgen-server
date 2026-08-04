#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 看每个wav文件的时长
stdin, stdout, stderr = ssh.exec_command('ffprobe -i /root/autodl-tmp/GPT-SoVITS/raw_audio/caizhi_wav/从1数到五-蔡引导.wav -show_entries format=duration -v quiet -of csv=p=0 2>/dev/null')
print("从1数到五 duration:", stdout.read().decode().strip())

stdin2, stdout2, stderr2 = ssh.exec_command('for f in /root/autodl-tmp/GPT-SoVITS/raw_audio/caizhi_wav/*.wav; do name=$(basename "$f" .wav); dur=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null); echo "$dur $name"; done')
print(stdout2.read().decode())

ssh.close()
