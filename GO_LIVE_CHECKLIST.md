# 🚀 AISleepGen 上线 Checklist

## 备案通过后、提交审核前

### 1. 微信支付配置（必配）
- [ ] 在微信公众平台开通微信支付
- [ ] 获取商户号（MCHID）
- [ ] 设置 APIv2 密钥（API_KEY）
- [ ] 填入 `AISleepGen_Optimized/.env`：
  - `AISLEEPGEN_WECHAT_MCHID=你的商户号`
  - `AISLEEPGEN_WECHAT_API_KEY=你的APIv2密钥`
- [ ] 将 `.env` 上传到华为云：

```bash
scp D:\AISleepGen_Optimized\.env root@123.60.222.129:/opt/aisleepgen/.env
systemctl restart aisleepgen.service
```

### 2. 微信小程序 AppSecret
- [ ] 在微信公众平台获取 AppSecret
- [ ] 填入 `.env` 的 `AISLEEPGEN_WECHAT_SECRET`
- [ ] 重新部署 `.env` + 重启

### 3. 小程序提交审核
- [ ] 打开微信开发者工具 → 项目配置确认 appid: `wx35a66ca7a7ed3009`
- [ ] 点击「上传」按钮提交代码
- [ ] 在微信公众平台提交审核
- [ ] 类目选择「健康管理」或「工具」
- [ ] 审核说明注明：
  > "本应用提供AI驱动的睡眠分析与建议，所有结论仅供参考，不构成医疗诊断。"

### 4. 域名配置（微信小程序必配）
- [ ] 登录微信公众平台 → 开发 → 开发设置
- [ ] 添加服务器域名白名单：`123.60.222.129`（IP 或绑定域名）
- [ ] request 合法域名 + socket 合法域名

---

## ✅ 已经完成的

| 项目 | 状态 |
|------|------|
| 后端 8 个核心端点 | ✅ 冒烟通过 |
| 防火墙（ufw，仅 22+8090） | ✅ 已开启 |
| systemd 服务（开机自启+崩溃重启） | ✅ 已部署 |
| .env 环境变量模板 | ✅ 已部署 |
| 隐私授权弹窗 | ✅ 已添加 |
| 隐私协议含联系方式 | ✅ 已更新 |
| 敏感文件权限 600 | ✅ 已修复 |
| urlCheck 上线模式 | ✅ 已设置 |
| 实验全部暂停（备案期间） | ✅ |
| predelete 打包归档 | ✅ 59.5MB |
| 服务器健康 | ✅ running |
| 代码瘦身（429→86 核心文件） | ✅ |

## ⚠️ 上线后第一天要看的

```bash
# 看服务状态
ssh root@123.60.222.129 'systemctl status aisleepgen.service'

# 看日志
ssh root@123.60.222.129 'journalctl -u aisleepgen.service --since "5 minutes ago" --no-pager'

# 检查实时连接
ssh root@123.60.222.129 'ss -tn | grep 8090 | wc -l'

# 检查支付回调
ssh root@123.60.222.129 'tail -50 /opt/aisleepgen/proxy_nohup.log | grep -i pay'
```
