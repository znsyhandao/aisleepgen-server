# dev_tools/ — 开发工具目录

## 使用方式
所有脚本可原地运行：python dev_tools/<category>/<script>.py

## 分类

### audit/ — 审核与审计
- triple_audit.py — 三层审核（数学+动力学+运行时）
- topology_audit.py — 拓扑动力学框架对比
- security_audit.py — 安全声明 vs 代码行为一致性审计

### test/ — 测试
- comprehensive_test.py — 全面 API 测试（设 \ 换端口）
- smoke_test.py — 支付/推荐快速冒烟
- quick_test.py — 快速测试
- api_contract_check.py — API 契约检查

### check/ — 检查
- full_health_check.py — 全面静态检查
- deploy_check.py — 部署前检查
- auth_check.py — 认证检查

### monitor/ — 监控（建议 cron 定期跑）
- mutant_watch.py — 运行时突变探测器

### fix/ — 修复工具（临时用，不常驻）
- fix_crash.py, fix_bare_except.py

### ops/ — 运维
- pre_op.py — 编辑前安全气垫
- pre_commit.py — 提交前检查
- install_hooks.py — git hooks 安装

### archive/ — 一次性/历史脚本，不再维护
- 项目根下 _* 脚本的归档
