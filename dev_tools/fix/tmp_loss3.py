#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

script = """
source /root/miniconda3/etc/profile.d/conda.sh
conda activate base
cd /root/autodl-tmp/GPT-SoVITS
python -c 'from tensorboard.backend.event_processing.event_accumulator import EventAccumulator; import os; os.chdir("/root/autodl-tmp/GPT-SoVITS"); ea = EventAccumulator("logs/caizhiming/caizhiming/version_0/events.out.tfevents.1780390592.autodl-container-atdlpbjbca-817bf974.28223.0"); ea.Reload(); [print(f"=== {tag} ===", [(s.step, round(s.value,4)) for s in ea.Scalars(tag)[:15]]) for tag in ["total_loss_epoch", "top_3_acc_epoch", "lr_epoch"] if tag in ea.Tags().get("scalars",[])]'
"""
stdin, stdout, stderr = ssh.exec_command(script, timeout=30)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:2000])
if err: print("ERR:", err[:200])

ssh.close()
