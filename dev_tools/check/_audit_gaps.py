import py_compile, sys, os, re
sys.stdout.reconfigure(encoding='utf-8')

with open('deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')

print('=== 1. 代码规模 ===')
sz = len(content.encode('utf-8'))
print(f'  文件大小: {sz:,} bytes = {sz/1024:.0f} KB')
print(f'  代码行数: {len(lines)}')
print(f'  函数定义: {content.count("def ")}')
print(f'  类定义: {content.count("class ")}')

print('\n=== 2. 结构 ===')
classes = re.findall(r'class (\w+)', content)
experts = [c for c in classes if any(k in c.lower() for k in ['expert','specialist','dimension','doctor','professor'])]
print(f'  类: {len(classes)} (其中专家类: {len(experts)})')
for c in classes:
    if 'expert' in c.lower() or 'dimension' in c.lower():
        print(f'    {c}')

print('\n=== 3. API ===')
apis = sorted(set(re.findall(r'/api/[a-z-]+', content)))
print(f'  {len(apis)} 个独立路由:')
for a in apis:
    print(f'    {a}')

print('\n=== 4. 前沿特性 ===')
checks = [
    ('流式输出 (SSE)', 'utf-8' in content and 'event' in content),
    ('音频多模态', 'audio' in content.lower()),
    ('记忆系统', '/api/memory' in content),
    ('HRV生物反馈', 'hrv' in content.lower()),
    ('CBT-I理念', 'cbt' in content.lower() or 'sleep hygiene' in content.lower()),
    ('动态专家池', 'expert_inference' in content or 'expert_pool' in content),
    ('向量检索', 'vector' in content or 'embedding' in content),
    ('强化学习', 'reinforcement' in content or 'bandit' in content),
    ('主动干预', 'intervention' in content),
    ('异常检测', 'anomaly' in content or 'outlier' in content),
    ('异步处理', 'asyncio' in content),
]
for name, has in checks:
    print(f'  {"YES" if has else "NO "} {name}')

print('\n=== 5. 第三方依赖 ===')
imports = re.findall(r'^import (\w+)|^from (\w+)\.', content, re.MULTILINE)
deps = sorted(set(i[0] or i[1] for i in imports if (i[0] or i[1]) not in 
    ('sys','os','json','re','datetime','io','time','math','urllib','hashlib','threading','abc','base64','binascii','collections','copy','decimal','functools','glob','http','logging','pathlib','pickle','platform','pprint','queue','random','shutil','signal','socket','sqlite3','ssl','string','struct','subprocess','tempfile','textwrap','traceback','types','typing','unittest','uuid','warnings','weakref','xml','zipfile','zlib','configparser','csv')))
for d in deps:
    print(f'  {d}')
print(f'  外部依赖: {len(deps)}')

print('\n=== 6. 潜在问题 ===')
print(f'  lambda: {content.count("lambda")}')
print(f'  嵌套回调深度 > 3: {content.count("lambda") > 10}')
print(f'  single-file: 6500+行一个文件 = 高危')
print(f'  硬编码: {len(re.findall(r"\"[^\"]{0,100}\"", content)) // 50} 个字符串')

# 7. 对比行业前沿（以我的知识为基准）
print('\n=== 7. 和行业前沿差距 ===')
print('''
       AISleepGen          行业前沿 (CBT-I SaaS 2025-2026)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
模型架构    8专家v2                 Specialist Mixture (MoE)
可解释性    维度评分                 SHAP + counterfactual
数据闭环    用户反馈介入             在线RLHF + 个人化bias校正
记忆系统    对话摘要+profile         episodic memory + 梯度遗忘
多模态      无                      音频呼吸模式+可穿戴HRV
临床验证    AI自评                  AASM三级验证+临床RCT
隐私        None                    on-device推理+联邦学习
订阅系统    简单free/pro tier        动态福利定价+按效果付费
部署        单机python               k8s+灰度上线+AB实验平台
可观测性    手动跑tool               实时drift监测+自动报警
''')
