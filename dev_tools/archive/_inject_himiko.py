# -*- coding: utf-8 -*-
"""在 deepseek_proxy.py 中插入姬心脏"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

fp = r'D:\AISleepGen_Optimized\deepseek_proxy.py'
with open(fp, 'r', encoding='utf-8') as f:
    content = f.read()

# 找到插入点：ButlerScheduler.check 调用前的注释
insertion_marker = '# 强制执'
idx = content.find(insertion_marker)
if idx < 0:
    print('找不到插入点')
    sys.exit(1)

# 回溯到前面的空行后
prev_newline = content.rfind('\n', 0, idx)
prev_prev = content.rfind('\n', 0, prev_newline - 1) if prev_newline > 0 else 0

insertion_point = prev_prev + 1  # 从上一个空行开始

# 确认这一部分是 print 语句后面
before_snippet = content[insertion_point:insertion_point + 30]
print(f'插入点确认: {repr(before_snippet)}')

# 要插入的代码块（保持缩进一致）
himiko_block = '''        # 姬心脏：先跑主动分析
        try:
            from himiko_heart import HimikoHeart, generate_active_conversation
            himiko = HimikoHeart()
            himiko_result = himiko.run()
            if himiko_result.get('total_events', 0) > 0:
                print(f'[Himiko] {himiko_result["total_events"]} events for {himiko_result["user_analyzed"]} users')
                conv = generate_active_conversation(openid, [], profile)
                if conv:
                    himiko_result['active_conversation'] = conv
                    print(f'[Himiko] active_conversation: [{conv["type"]}] {conv["message"]}')
        except Exception as e:
            print(f'[Himiko] error: {e}')
            himiko_result = {}

'''

new_content = content[:insertion_point] + himiko_block + content[insertion_point:]

with open(fp, 'w', encoding='utf-8') as f:
    f.write(new_content)

print(f'插入完成: 共 {len(new_content)} 字符 (+{len(himiko_block)})')

# 验证编译
import py_compile
try:
    py_compile.compile(fp, doraise=True)
    print('编译通过')
except py_compile.PyCompileError as e:
    print(f'编译失败: {e}')
