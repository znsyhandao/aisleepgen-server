import re

FILE = r"D:\AISleepGen_Optimized\cross_user_optimizer.py"
with open(FILE, 'r', encoding='utf-8') as f:
    c = f.read()

old = """        print(f\'  {iv}: 成功率={info[\\"success_rate\\"]:.1%} \'
              f\'置信度={info[\\"confidence\\"]:.0%} \'
              f\'样本={info[\\"total_samples\\"]} \'
              f\'推荐={info[\\"recommendation\\"]}\')"""

new = """        sr = info['success_rate']
        conf = info['confidence']
        samp = info['total_samples']
        rec = info['recommendation']
        print(f'  {iv}: 成功率={sr:.1%} 置信度={conf:.0%} 样本={samp} 推荐={rec}')"""

c = c.replace(old, new)

with open(FILE, 'w', encoding='utf-8') as f:
    f.write(c)

import py_compile
py_compile.compile(FILE, doraise=True)
print("OK")
