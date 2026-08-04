# -*- coding: utf-8 -*-
"""
拍照引导工具 — 标准化采集条件
用法: python photo_guide.py [evening|morning]
"""
import os, sys
from datetime import datetime

PROJECT = r'D:\AISleepGen_Optimized'
SKIN_DB = os.path.join(PROJECT, 'sleep-skin image database')

GUIDE_EVENING = """
╔══════════════════════════════════════════════╗
║        🌙 睡前准备 — 标准化采集              ║
╠══════════════════════════════════════════════╣
║                                              ║
║  📱 自拍 (22:00-23:00)                       ║
║  ─────────────────────────                   ║
║  ✅ 正面面对光源 (台灯/顶灯)                 ║
║  ✅ 距离30-40cm (手臂伸直)                  ║
║  ✅ 表情放松、不要笑                        ║
║  ✅ 拍摄3张 (不同小角度)                    ║
║  ✅ 位置：固定座位 (今晚和明早同一位)       ║
║  ❌ 不要逆光、不要侧光                     ║
║  ❌ 不要刚洗完脸有水珠                     ║
║                                              ║
║  🎤 开始录音 (放在床头)                     ║
║  ─────────────────────────                   ║
║  1. 打开录音app                              ║
║  2. 放在床头柜 (非枕头上)                    ║
║  3. 确认麦克风未被遮挡                       ║
║  4. 开始录制 → 关灯 → 睡觉                 ║
║                                              ║
║         🌙 晚安！明早见。                     ║
╚══════════════════════════════════════════════╝
"""

GUIDE_MORNING = """
╔══════════════════════════════════════════════╗
║        ☀️ 睡后采集 — 标准化流程              ║
╠══════════════════════════════════════════════╣
║                                              ║
║  📱 自拍 (7:00-8:00)                         ║
║  ─────────────────────────                   ║
║  ✅ 相同位置、相同光线                      ║
║  ✅ 起床5分钟内拍 (避免表情恢复)            ║
║  ✅ 拍3张                                    ║
║  ❌ 不要先洗脸                              ║
║  ❌ 不要先做表情/说话多                     ║
║                                              ║
║  🎤 停止录音                                  ║
║  ─────────────────────────                   ║
║  1. 确认昨晚录音已保存                       ║
║  2. 停止录制                                  ║
║  3. 文件名格式: YYYYMMDD_HHMMSS.m4a          ║
║                                              ║
║  📂 文件存放                                  ║
║  ─────────────────────────                   ║
║  照片 → D:\\AISleepGen_Optimized\\sleep-skin image database\\{today}/
║  录音 → D:\\AISleepGen_Optimized\\sleep_record\\
║                                              ║
║         ☕ 早安！数据已在收集。               ║
╚══════════════════════════════════════════════╝
"""

def print_guide(mode):
    today = datetime.now().strftime('%Y%m%d')
    
    if mode == 'evening':
        guide = GUIDE_EVENING
    elif mode == 'morning':
        guide = GUIDE_MORNING.format(today=today)
    else:
        print(f"用法: python photo_guide.py [evening|morning]")
        return
    
    # Clear screen
    os.system('cls' if os.name == 'nt' else 'clear')
    print(guide)

def check_directories():
    """检查采集目录是否存在"""
    ok = True
    for d in [SKIN_DB, os.path.join(PROJECT, 'sleep_record')]:
        if not os.path.isdir(d):
            print(f"[WARN] 目录不存在: {d}")
            ok = False
    if ok:
        print("[OK] 采集目录正常")

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'evening'
    print_guide(mode)
