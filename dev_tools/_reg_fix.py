import py_compile
with open('aisleepgen_tool.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# L69-70: help text
lines[69] = '  fix bare-except        修复 bare except: pass\n'
lines[70] = '  fix crash              自动修复多个应用\n'
lines.insert(71, '  fix profile-protect    修复 profile latest 保护+版本号\n')
lines.insert(72, '  fix remaining-gaps     修复4个剩余盲区(S1/H6/F2)\n')

# L139: command routing
lines.insert(139, "    ('fix', 'profile-protect'):  ('fix', 'fix_profile_protect.py'),\n")
lines.insert(140, "    ('fix', 'remaining-gaps'):   ('fix', 'fix_remaining_gaps.py'),\n")

with open('aisleepgen_tool.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

py_compile.compile('aisleepgen_tool.py', doraise=True)
print('OK')
