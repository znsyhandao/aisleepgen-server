#!/usr/bin/env python3
"""SSH to B39 machine and check disk"""
import subprocess, os, sys

password = "JIztKP80Ez7p"
cmd = [
    "ssh",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "PasswordAuthentication=yes",
    "-o", "PreferredAuthentications=password",
    "-p", "38474",
    "root@connect.westd.seetacloud.com"
]

proc = subprocess.Popen(
    cmd,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# 发送密码 + 命令
import time
time.sleep(2)
proc.stdin.write(password + "\n")
proc.stdin.flush()
time.sleep(1)
proc.stdin.write("df -h\n")
proc.stdin.write("echo '---DIRS---'\n")
proc.stdin.write("du -sh /root/* 2>/dev/null | sort -rh | head -20\n")
proc.stdin.write("echo '---LARGE_FILES---'\n")
proc.stdin.write("find /root -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | sort -k5 -rh | head -20\n")
proc.stdin.write("exit\n")
proc.stdin.flush()

try:
    out, err = proc.communicate(timeout=30)
    print("=== STDOUT ===")
    print(out)
    print("=== STDERR ===")
    print(err[:1000])
except subprocess.TimeoutExpired:
    proc.kill()
    out, err = proc.communicate()
    print("=== TIMEOUT STDOUT ===")
    print(out)
    print("=== TIMEOUT STDERR ===")
    print(err[:1000])
