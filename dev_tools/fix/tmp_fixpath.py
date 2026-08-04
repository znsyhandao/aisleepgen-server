#!/usr/bin/env python
import paramiko, os

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 1. 找到raw_audio下所有带反斜杠的文件
stdin, stdout, stderr = ssh.exec_command("find /root/autodl-tmp/GPT-SoVITS/raw_audio/ -maxdepth 1 -name '*\\*' -type f 2>/dev/null")
print("Files with backslash:")
print(stdout.read().decode())

# 2. 直接在 find 结果里改名
stdin2, stdout2, stderr2 = ssh.exec_command("""
cd /root/autodl-tmp/GPT-SoVITS/raw_audio
for f in *\\\\001* *\\\\002* *\\\\003* *\\\\004* *\\\\005* *\\\\006* *\\\\007* *\\\\008* *\\\\009* *\\\\010*; do
  if [ -f "$f" ]; then
    newname=$(echo "$f" | sed 's/\\\\//g')
    echo "Moving: $f -> 第一批_wav/$newname"
    mv "$f" "第一批_wav/$newname"
  fi
done
ls -la 第一批_wav/ 2>/dev/null | head -15
""")
print(stdout2.read().decode())
err = stderr2.read().decode()
if err: print("ERR:", err[:200])

ssh.close()
