import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:\\AISleepGen_Optimized\\miniprogram\\app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# 在 _initLogin 中加一个强制日志，显示最终的 openid
old = "that.globalData.openid = cached;\n      console.log"
new = "that.globalData.openid = cached;\n      console.log('[Login] 最终openid: ' + that.globalData.openid);\n      console.log"

content = content.replace(old, new, 1)

old = "that.globalData.openid = data.openid;\n              wx.setStorageSync"
new = "that.globalData.openid = data.openid;\n              console.log('[Login] 最终openid(新): ' + that.globalData.openid);\n              wx.setStorageSync"

content = content.replace(old, new, 1)

with open('D:\\AISleepGen_Optimized\\miniprogram\\app.js', 'w', encoding='utf-8') as f:
    f.write(content)

print('OK')
