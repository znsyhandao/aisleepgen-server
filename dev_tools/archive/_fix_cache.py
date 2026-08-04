import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "qs_openid = qs_params.get('openid', '')\n            openid = qs_openid if qs_openid else self._get_openid({})\n            profile = _load_user_profile(openid)\n            member = profile.get('member', {})"

new = "qs_openid = qs_params.get('openid', '')\n            openid = qs_openid if qs_openid else self._get_openid({})\n            # GET/user-profile绕过缓存直读文件\n            try:\n                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_profile.json'), 'r', encoding='utf-8') as _f:\n                    _all = json.load(_f)\n                profile = _all.get(openid, {})\n            except:\n                profile = {}\n            if not profile:\n                profile = _load_user_profile(openid)\n            member = profile.get('member', {})"

count = content.count(old)
print(f'匹配数: {count}')
if count >= 1:
    content = content.replace(old, new, 1)
    with open('D:\\AISleepGen_Optimized\\deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('已替换')
else:
    print('匹配失败')
