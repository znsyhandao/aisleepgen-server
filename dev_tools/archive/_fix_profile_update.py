with open('D:\\AISleepGen_Optimized\\dp_router.py', 'r', encoding='utf-8') as f:
    src = f.read()

old = '''    def modifier(p):
            p.update(updates)
            return p
        _px._atomic_write_profile(openid, modifier)

        # 检测是否包含survey提交（含睡眠数据）
        profile_data = updates.get('latest', {})'''

new = '''    def modifier(p):
            # 合并 latest
            if 'latest' in updates:
                p['latest'] = updates['latest']
            # 追加 history（不是覆盖）
            if 'history' in updates and isinstance(updates['history'], list):
                if 'history' not in p:
                    p['history'] = []
                for entry in updates['history']:
                    p['history'].append(entry)
            # 其他字段直接更新
            for k, v in updates.items():
                if k not in ('latest', 'history'):
                    p[k] = v
            return p
        _px._atomic_write_profile(openid, modifier)

        # 检测是否包含survey提交（含睡眠数据）
        profile_data = updates.get('latest', {})'''

if old in src:
    src = src.replace(old, new)
    with open('D:\\AISleepGen_Optimized\\dp_router.py', 'w', encoding='utf-8') as f:
        f.write(src)
    print('OK')
else:
    print('OLD NOT FOUND')
    # debug
    idx = src.find('def modifier(p):')
    if idx > 0:
        print(src[idx:idx+300])
