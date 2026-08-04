#!/usr/bin/env python3
"""调试：消息解析后世界模型专家评分"""
import sys; sys.path.insert(0, r'D:\AISleepGen_Optimized')
from sleep_world_model import WorldModelEngine

we = WorldModelEngine()

analysis = we.comprehensive_analysis({
    'feeling': '翻来覆去睡不着，2点才睡着，6点多就醒了',
    'sleep_latency': 180,
    'stress_level': 5,
    'awake_times': 1,
})

print(f"total_score: {analysis.get('total_score')}")
print(f"primary_focus: {analysis.get('insights',{}).get('primary_focus','?')[:120]}")

dims = analysis.get('analysis', {}).get('dimensions', {})
sr = dims.get('StressRelaxation', {})
print(f"\nSR arousal_type: {sr.get('arousal_type', '?')}")
print(f"SR score: {sr.get('score')}")
for f in sr.get('findings', [])[:5]:
    print(f"  find: {f[:100]}")
