#!/usr/bin/env python3
"""消息解析器单元测试"""
import sys; sys.path.insert(0, r'D:\AISleepGen_Optimized')
from message_parser import parse_sleep_message

tests = [
    ("入睡困难", "我昨晚翻来覆去睡不着，大概快2点才睡着，6点多就醒了，中间还醒了一次"),
    ("焦虑失眠", "最近工作压力大，躺下脑子就不停了，一直在想明天的事，心跳也快"),
    ("安全红线", "我最近失眠很严重，吃了安眠药也没用，想试试加大剂量"),
    ("正常睡眠", "睡得还行，10点半睡到6点"),
    ("严重失眠", "一夜没怎么睡，大概躺了两三个小时才睡着，中间醒了好几次"),
    ("噩梦惊醒", "昨晚做了噩梦惊醒，再也睡不着了"),
]

for name, msg in tests:
    r = parse_sleep_message(msg)
    print(f"[{name}] {r}")
