import sys, json, urllib.request, os
sys.stdout.reconfigure(encoding='utf-8')

# 直接测试 _build_history_context
# 手动加载模块
sys.path.insert(0, 'D:\\AISleepGen_Optimized')
import importlib.util
spec = importlib.util.spec_from_file_location('deepseek_proxy', 'D:\\AISleepGen_Optimized\\deepseek_proxy.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

ctx, expert_history = mod._build_history_context('dev_098f6bcd4621d373')
print('=== _build_history_context 返回 ===')
print(ctx[:2000] if ctx else '(empty)')
print(f'expert_history: {expert_history}')
