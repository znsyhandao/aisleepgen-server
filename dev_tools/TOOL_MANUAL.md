<?xml version="1.0"?>
<tool_update>
<tool name="ops/deploy_unified.py">
<description>统一部署工具，4个目标一键部署</description>
<syntax>aisleepgen_tool.py ops deploy &lt;target&gt; [--diff] [--file ...]</syntax>
<targets>
  <target name="huawei">华为云 · AISleepGen (123.60.222.129:8090)</target>
  <target name="tengxun">腾讯云 · 华尔街脑 (82.156.208.245:8928)</target>
  <target name="furnace">腾讯云 · 数字生命熔炉 (82.156.208.245:8921)</target>
  <target name="frontier">本地 · 前沿速递 (8930/8931)</target>
</targets>
<features>
  <feature>预检：编译检查 + 文件存在 + 端口状态</feature>
  <feature>备份：自动 .surgical_backups/{file}_{timestamp}.bak</feature>
  <feature>远程备份：SFTP上传前远程备份</feature>
  <feature>编译验证：上传后远程 py_compile 验证</feature>
  <feature>回退：远程编译失败自动回退</feature>
  <feature>--diff：仅预览不部署</feature>
</features>
</tool_update>
