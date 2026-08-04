#!/usr/bin/env python3
"""GPT-SoVITS 一键推理 + 下载到本地"""
import subprocess, json, os, sys, time, base64
from pathlib import Path

D70_SSH = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null", "-p", "46185", "root@connect.westd.seetacloud.com"]
D70_PWD = "noJj8NbkPt1X"

# 检查已有的 checkpoint
print("=== 检查 checkpoint ===")
ls = subprocess.run(
    D70_SSH + ["ls", "-lh", "/root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/half_weights/"],
    capture_output=True, text=True, input=D70_PWD + "\n", timeout=15
)
print(ls.stdout.strip())

print("\n=== 检查参考音频 ===")
ls2 = subprocess.run(
    D70_SSH + ["ls", "/root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/5-wav32k/", "|", "head", "-5"],
    capture_output=True, text=True, input=D70_PWD + "\n", timeout=15
)
print(ls2.stdout.strip())
