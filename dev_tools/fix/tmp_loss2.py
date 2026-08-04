#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 直接在服务器上建一个临时脚本跑
script = """
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS
python -c 'from tensorboard.backend.event_processing.event_accumulator import EventAccumulator; import os; os.chdir("/root/autodl-tmp/GPT-SoVITS"); ea = EventAccumulator("logs/caizhiming/caizhiming/version_0/events.out.tfevents.1780390592.autodl-container-atdlpbjbca-817bf974.28223.0"); ea.Reload(); tags = ea.Tags(); print("tags:", tags.get("scalars",[])); scalars = ea.Scalars("loss") if "loss" in tags.get("scalars",[]) else []; print("loss:", len(scalars)); [print(s.step, round(s.value,4)) for s in scalars[:10]]'
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=30)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out)
if err: print("ERR:", err[:300])

ssh.close()
