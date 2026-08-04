# -*- coding: utf-8 -*-
"""修复chat.js：api.request后面的逗号和.then错位"""
with open('miniprogram/pages/chat/chat.js', 'r', encoding='utf-8') as f:
    c = f.read()

old = "api.request('/api/timeline', { openid: openid, limit: 20 }),\n        .then(res => {"
new = "api.request('/api/timeline', { openid: openid, limit: 20 }).then(res => {"

if old in c:
    c = c.replace(old, new)
    with open('miniprogram/pages/chat/chat.js', 'w', encoding='utf-8') as f:
        f.write(c)
    print('Fixed')
else:
    print('Not found')
