#!/usr/bin/env python3
with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the OUTSIDE-class huawei handlers (after 'return len(articles)')
old_marker = 'return len(articles)\n\n    # \xe2\x94\x80\xe2\x94\x80 \xe5\x8d\x8e\xe4\xb8\xba\xe6\x89\x8b\xe7\x8e\xaf API \xe2\x94\x80\xe2\x94\x80'
new_marker = 'return len(articles)\n\ndef run_pubmed_cron():'

start = content.find(old_marker)
end = content.find(new_marker)

if start > 0 and end > 0:
    before = content[:start]
    after = content[end:]
    new_content = before + after
    with open(r'D:\AISleepGen_Optimized\deepseek_proxy.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print('Removed outside-class huawei handlers')
    print(f'New file: {len(new_content.splitlines())} lines')
else:
    print(f'start={start} end={end}')
    if start < 0:
        i = content.find('华为手环 API')
        print(f'  marker hex: {content[i:i+20].encode("utf-8").hex() if i>=0 else "not found"}')
