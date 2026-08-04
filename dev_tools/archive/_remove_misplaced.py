# -*- coding: utf-8 -*-
# Remove the misplaced protocols and re-insert at correct position

CURRENT = r'D:\AISleepGen_Optimized\dp_router.py'

with open(CURRENT, 'rb') as f:
    data = f.read()

# Find and remove the misplaced protocol block
# It's between 'f\'wx_{hashlib...\n' and the next proper line
# Actually easier: find the insertion marker and the end of corrupted block

# Look for the pattern: the opening of handle_wx_login that has been broken
marker_start = b"openid = f'wx_{hashlib"
marker_end = b"@route('/api/user-profile')"

idx_start = data.find(marker_start)
idx_end = data.find(marker_end)

if idx_start > 0 and idx_end > idx_start:
    # Find what should be there - just the proper close of the f-string and rest of handle_wx_login
    # Replace from marker_start to marker_end with the correct version
    replacement = b"openid = f'wx_{hashlib.md5(code.encode()).hexdigest()[:16]}' if code else 'default'\n    # \u52a0\u8f7d\u6216\u521b\u5efa\u7528\u6237\n    profile = _px._load_user_profile(openid)\n    return {\n        'openid': openid,\n        'is_new': profile.get('total_sessions', 0) == 0,\n        'member': profile.get('member', {'level': 'free'}),\n    }\n\n\n"
    
    new_data = data[:idx_start] + replacement + data[idx_end:]
    
    with open(CURRENT, 'wb') as f:
        f.write(new_data)
    print(f'Repaired. Cleaned {idx_end - idx_start} bytes of misplaced code')
else:
    print(f'Cannot find markers: start={idx_start}, end={idx_end}')
