# -*- coding: utf-8 -*-
"""
对比分析：拓扑动力学框架 vs AISleepGen 现有架构

框架四层：
1. 胞腔复形（跨频耦合体素 → 边流 → 2-单形）
2. T-VAE（φ梯度/h调和/ψ旋度三分量）
3. 逆向场调控（消解病理性调和分量）
4. 理论保证（拓扑不变量 + 安全铁律）

现有AISleepGen（sleep_world_model.py）：
- 10位专家软规则会诊
- 特征工程（PHQ-9/GAD-7模拟 + 循证匹配）
- 两轮交叉会诊（round1 + round2）
- 输出层加权汇总 + 疼痛修正
"""
import json, subprocess, sys, os, shutil, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.header import Header
from email import encoders

BASE = r'D:\AISleepGen_Optimized'
BACKUP_BASE = r'D:\AISleepGen_Optimized\.topology_backup'
os.makedirs(BACKUP_BASE, exist_ok=True)

# ===== 第一步：备份当前核心文件 =====
files_to_backup = [
    'sleep_world_model.py',
    'dp_router.py',
    'working_memory.py',
    'deepseek_proxy.py',
]
for fn in files_to_backup:
    src = os.path.join(BASE, fn)
    if os.path.exists(src):
        # 按日期+文件名备份
        dst = os.path.join(BACKUP_BASE, f'{fn}.20260515.bak')
        shutil.copy2(src, dst)
        sz = os.path.getsize(src)
        print(f'备份: {fn} ({sz/1024:.0f}KB) → {dst}')
    else:
        print(f'跳过: {fn} (不存在)')

# ===== 第二步：对比分析 =====
print('\n' + '='*60)
print('框架层1: 胞腔复形（高阶拓扑数据结构）')
print('='*60)
print('现状: 10位专家使用 data Dict[str, Any] 作为输入')
print('     特征是平铺的标量（sleep_latency=30, stress_level=7）')
print('     无跨频耦合、无边流、无2-单形')
print('差距: 特征空间是欧氏向量，不是流形上的边流')
print('')

print('='*60)
print('框架层2: T-VAE 三分量分解(φ/ψ/h)')
print('='*60)
print('现状: 专家独立评分 → 加权汇总(weighted_score)')
print('     输出是标量 total_score (0-100)')
print('     无势能/旋度/调和的分解')
print('差距: 模型不知道哪些问题是"可恢复的疲劳" vs "不可压缩的创伤"')
print('')

print('='*60)
print('框架层3: 逆向场调控')
print('='*60)
print('现状: 减压专家(StressRelaxationSpecialist) 用if-else规则匹配方案')
print('     唤醒分型: high_physiological/high_cognitive/mixed/low_arousal')
print('     推荐: 4_7_8_breathing / body_scan / PMR')
print('差距: 没有闭环刺激、没有调和分量对消、没有拓扑重塑')
print('')

print('='*60)
print('框架层4: 理论保证')
print('='*60)
print('现状: pain_penalty修正+置信区间(ci_lower/ci_upper)')
print('     expeert_agreement: high/medium/low (方差判定)')
print('差距: 调和分量拓扑不变量为0，波动无上界')
print('')

# ===== 第三步：最小可行切入点 =====
print('='*60)
print('最小可行切入点分析')
print('='*60)
print()

print('切入点1 [最容易]: 为WorldModelEngine增加拓扑正交正则')
print('  改动: output层加权汇总后，增加score_phi/score_psi/score_h三分量输出')
print('  代价: 3-5行代码，不破坏现有会诊流程')
print('  价值: 区分可修复问题 vs 不可压缩问题，提升推荐精度')
print()

print('切入点2 [中等]: StressRelaxationSpecialist升级为调和感知型')
print('  改动: arousal_type判据改为三分量评分（phi_slope/psi_circulation/h_invariant）')
print('  代价: 该专家代码大改，不影响其他专家的analyze方法')
print('  价值: 区分"今天很累" vs "长期压力创伤"，给出更精准的减压方案')
print()

print('切入点3 [最难]: 添加闭环刺激控制器')
print('  改动: 新增一个stimulation_scheduler.py，读取调和分量后生成刺激参数')
print('  代价: 全新模块，需硬件支持（音频刺激设备）')
print('  价值: 实现框架三层（从观测到干预）')
print()

print('建议路线: 切入点1(今天) → 切入点2(明天) → 切入点3(下周)')
print()
print('改动保证:')
print('  1. 所有备份在 .topology_backup/')
print('  2. 每个切入点可单独回滚（覆盖回.bak文件即可）')
print('  3. 改动范围不超过3个文件')
print('  4. 不改数据库/路由/API层')
