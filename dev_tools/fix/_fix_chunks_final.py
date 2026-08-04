import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('api.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 resolve(fullText) 前加 clearTimeout
content = content.replace(
    'if (fullText) resolve(fullText);',
    'if (fullText) { if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; } resolve(fullText); }'
)
# 在 reject 前加 clearTimeout  
content = content.replace(
    "else reject(new Error('\u65e0\u56de\u590d'));",
    "else { if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; } reject(new Error('\u65e0\u56de\u590d')); }"
)
# 在 reject(parsed.error) 前加 clearTimeout
content = content.replace(
    'reject(new Error(parsed.error));',
    'if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; } reject(new Error(parsed.error));'
)

with open('api.js', 'w', encoding='utf-8') as f:
    f.write(content)
print('OK')
