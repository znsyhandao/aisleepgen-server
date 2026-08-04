import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\miniprogram\\pages\\survey\\survey.js', 'r', encoding='utf-8') as f:
    content = f.read()

old = "var openid = wx.getStorageSync('openid') || 'default'"
new = "var openid = wx.getStorageSync('aisleepgen_openid') || wx.getStorageSync('openid') || 'default'"

if old in content:
    content = content.replace(old, new, 1)
    with open('D:\\AISleepGen_Optimized\\miniprogram\\pages\\survey\\survey.js', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed survey.js openid key')
else:
    print('Not found in survey.js')
