#!/usr/bin/env python
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('connect.westd.seetacloud.com', port=14997, username='root', password='noJj8NbkPt1X')

# 查看lightning日志中记录了loss值
cmd = "python -c \"from tensorboard.backend.event_processing.event_accumulator import EventAccumulator; ea = EventAccumulator('/root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhiming/version_0/events.out.tfevents.1780390592.autodl-container-atdlpbjbca-817bf974.28223.0'); ea.Reload(); tags = ea.Tags(); print('tags:', tags.get('scalars',[])); scalars = ea.Scalars('loss') if 'loss' in tags.get('scalars',[]) else []; print('loss samples:', len(scalars)); [print(s.step, s.value) for s in scalars[:5]]\" 2>&1"
print(f"$ {cmd}")
stdin, stdout, stderr = ssh.exec_command(cmd, timeout=20)
out = stdout.read().decode().strip()
err = stderr.read().decode().strip()
if out: print(out[:1500])
if err: print("ERR:", err[:200])

ssh.close()
