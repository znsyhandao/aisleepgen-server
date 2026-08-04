#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 检查切片时长
script = """
cd /root/autodl-tmp/GPT-SoVITS
for f in raw_audio/sliced_caizhi_v2/从1数到五-蔡引导_0000.wav raw_audio/sliced_caizhi_v2/从1数到五-蔡引导_0001.wav raw_audio/sliced_caizhi_v2/从1数到五-蔡引导_0002.wav raw_audio/sliced_caizhi_v2/从1数到五-蔡引导_0003.wav raw_audio/sliced_caizhi_v2/从1数到五-蔡引导_0004.wav raw_audio/caizhi_ref.wav raw_audio/caizhi_wav/从1数到五-蔡引导.wav; do
  dur=$(ffprobe -v quiet -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null)
  echo "$dur $f"
done
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=10)
print(stdout.read().decode()[:1000])

# 找caizhi_ref.wav的文本
script2 = "cat /root/autodl-tmp/GPT-SoVITS/output_reborn/ref_caizhi.txt 2>/dev/null || echo NO_FILE"
stdin2, stdout2, stderr2 = ssh.exec_command(script2, timeout=10)
print("ref text:", stdout2.read().decode().strip())

ssh.close()
