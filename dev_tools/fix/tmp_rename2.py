#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 重命名去掉前缀
stdin, stdout, stderr = ssh.exec_command("""
cd /root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav
for f in 第一批_wav*.wav; do
  newname=$(echo "$f" | sed 's/第一批_wav//')
  echo "mv '$f' '$newname'"
  mv "$f" "$newname"
done
ls -la *.wav | head -12
""", timeout=30)
print(stdout.read().decode())
err = stderr.read().decode()[:200]
if err: print("ERR:", err)

# 确认WAV总大小
stdin2, stdout2, stderr2 = ssh.exec_command("""
cd /root/autodl-tmp/GPT-SoVITS/raw_audio/第一批_wav
ls *.wav | wc -l
du -sh .
""")
print(stdout2.read().decode())
ssh.close()
