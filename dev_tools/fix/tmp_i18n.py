#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 直接看字典内容
cmd = "sed -n '150,180p' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py"
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
print(stdout.read().decode())

# 看i18n是什么
cmd2 = "grep -n 'def i18n' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py | head -3"
stdin2, stdout2, stderr2 = ssh.exec_command(cmd2, timeout=10)
print("\ni18n def:", stdout2.read().decode())

# 看dict_language_v2在get_tts_wav里怎么用的
cmd3 = "sed -n '790,840p' /root/autodl-tmp/GPT-SoVITS/GPT_SoVITS/inference_webui.py"
stdin3, stdout3, stderr3 = ssh.exec_command(cmd3, timeout=10)
print("\nget_tts_wav header:", stdout3.read().decode()[:2000])
ssh.close()
