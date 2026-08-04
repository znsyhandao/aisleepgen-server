#!/usr/bin/env python3
"""SSH to B39 with password"""
import pexpect, sys

child = pexpect.spawn(
    'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
    '-o LogLevel=ERROR -p 38474 root@connect.westd.seetacloud.com '
    '"df -h /root/autodl-tmp/ && echo === && ls /root/autodl-tmp/GPT-SoVITS/logs/reborn_mianxiaotu/5-wav32k/ | wc -l"',
    timeout=20
)
child.expect('password:')
child.sendline('JIztKP80Ez7p')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8', errors='replace'))
