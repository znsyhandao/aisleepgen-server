# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

with open('dp_router.py', 'rb') as f:
    c = f.read()

# Check if the rest of the file is intact
# After the corrupted block, the next function should be handle_wx_login
# Let's look at what's at byte 29000 (start of action trigger was 26637)
# The replacement block was 2926 bytes, so next content starts at ~29563

# Search for key function names
checks = ['handle_wx_login', 'handle_user_profile', 'handle_dashboard', 
          'handle_update_profile', 'handle_sleep_stats', 'handle_history',
          'handle_feedback', 'handle_meditation_plan', 'handle_intervention_complete',
          'from async_pipeline', 'from push_decision', 'from safeguards',
          'handle_companion_start', 'handle_narrative_story', 'from fallback_replies']

for func in checks:
    idx = c.find(func.encode())
    if idx > 0:
        print(f'OK: {func} at byte {idx}')
    else:
        print(f'MISSING: {func}')

# Check total file size
print(f'\nFile size: {len(c)} bytes')

# Check if the file has the proper ending
print(f'Last 100 bytes: {c[-100:]}')
