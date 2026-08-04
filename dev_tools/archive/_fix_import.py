"""Fix label_best.py"""
with open(r'D:\AISleepGen_Optimized\label_best.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: add re import
old1 = 'import os, cv2, numpy as np, pickle, shutil, sys, gc, torch, torch.nn as nn'
new1 = 'import os, cv2, numpy as np, pickle, shutil, sys, gc, re, torch, torch.nn as nn'
content = content.replace(old1, new1)

# Fix 2: fix man detection regex
old2 = "has_man_marker = '_man_' in fl_no_woman or fl_no_woman.startswith('man_')"
new2 = "has_man_marker = bool(re.search(r'_man[_.]', fl_no_woman))"
content = content.replace(old2, new2)

with open(r'D:\AISleepGen_Optimized\label_best.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed. Changes:', old1 != new1, old2 != new2)
