#!/usr/bin/env python3
"""AISleepGen 合规体检报告 v2"""
import os, json, sys

BASE = r'D:\AISleepGen_Optimized'

checks = []

# ====== P0 生死线 ======
p0 = []

# P0-1 AI生成标识
r = "❌"
with open(os.path.join(BASE, 'world_model_coordinator.py'), 'r', encoding='utf-8') as f:
    if 'AI生成' in f.read():
        r = "✅"
p0.append((r, "AI生成标识", "回复末尾标注(AI生成，仅供参考)，P0-今晚已加"))

# P0-2 隐私弹出
p0_path = os.path.join(BASE, 'miniprogram', 'app.js')
r = "❌"
if os.path.exists(p0_path):
    with open(p0_path, 'r', encoding='utf-8') as f:
        c = f.read()
        if 'privacy' in c.lower() or '隐私' in c:
            r = "✅"
p0.append((r, "隐私弹窗", "app.js启动时弹出隐私协议，用户同意后才初始化"))

# P0-3 隐私协议全文
r = "✅" if os.path.exists(os.path.join(BASE, 'PRIVACY_POLICY.md')) else "❌"
p0.append((r, "隐私协议文件", "PRIVACY_POLICY.md 存在"))

# P0-4 数据收集明示 + 删除/导出 API
r = "✅" if os.path.exists(os.path.join(BASE, 'compliance.py')) else "❌"
p0.append((r, "合规 API", "consent/delete-my-data/export-my-data 端点已实现"))

# P0-5 小程序隐私接口 (wx 新规)
r = "❓"
wx_path = os.path.join(BASE, 'miniprogram', 'app.json')
if os.path.exists(wx_path):
    with open(wx_path, 'r', encoding='utf-8') as f:
        if 'privacy' in f.read().lower() or '__usePrivacy' in f.read():
            r = "✅"
        else:
            r = "❌"
p0.append((r, "微信隐私接口", "app.json 配 __usePrivacy 和 Privacy 接口"))

# ====== P1 上线门槛 ======
p1 = []

# P1-1 算法备案文档
r = "❌" if not os.path.exists(os.path.join(BASE, 'compliance', 'algorithm_filing.md')) else "✅"
p1.append((r, "算法备案文档", "需要提交算法机理说明、安全评估报告"))

# P1-2 安全评估
r = "❌" if not os.path.exists(os.path.join(BASE, 'compliance', 'security_assessment.md')) else "✅"
p1.append((r, "安全评估报告", "自评估/第三方评估"))

# P1-3 ICP备案
p1.append(("❌", "ICP备案", "需要域名+服务器，需至尊宝操作"))

# P1-4 域名白名单
p1.append(("❌", "微信域名白名单", "需至尊宝在微信公众平台配置"))

# ====== P2 防御性 ======
p2 = []
p2.append(("✅", "非医疗诊断", "AISleepGen 不做诊断/处方，仅做减压建议+冥想推荐"))
p2.append(("❓", "深度合成", "不涉及语音/视频生成，目前不需要备案"))
p2.append(("❓", "数据出境", "不涉及，数据在国内"))

# ====== 输出 ======
print("=== AISleepGen 合规体检 ===")
print()
print("--- P0 生死线 (上线必须) ---")
for status, name, desc in p0:
    print(f"  {status} {name}")
    print(f"      {desc}")

print()
print("--- P1 上线后一个月内 ---")
for status, name, desc in p1:
    print(f"  {status} {name}")
    print(f"      {desc}")

print()
print("--- P2 防御性 ---")
for status, name, desc in p2:
    print(f"  {status} {name}")
    print(f"      {desc}")

p0_ok = sum(1 for s,_,_ in p0 if "✅" in s)
p0_total = len(p0)
print(f"\nP0 完成度: {p0_ok}/{p0_total}")
