"""整理工具目录——补齐遗漏的工具+归档一次性脚本"""
import os, shutil

BASE = r'D:\AISleepGen_Optimized'
TOOLS = os.path.join(BASE, 'dev_tools')

# 需要补齐的实用工具（非_前缀 + 重要_前缀）
MISSING = [
    # 源文件名 -> (目标子目录, 新文件名)
    ('batch_convert_m4a.py', ('ops', 'batch_convert_m4a.py'), '批量转换m4a'),
    ('download_deepseek.py', ('ops', 'download_deepseek.py'), '下载DeepSeek模型'),
    ('api_security.py', ('check', 'api_security.py'), 'API安全检测'),
    ('architecture_inner_eye.py', ('audit', 'architecture_inner_eye.py'), '架构内视分析'),
    ('async_pipeline.py', ('test', 'async_pipeline.py'), '异步管线测试'),
    ('ab_framework.py', ('test', 'ab_framework.py'), 'A/B测试框架'),
    ('_scan_all_audio.py', ('check', 'scan_all_audio.py'), '扫描音频文件'),
    ('_self_heal_v2.py', ('check', 'self_heal.py'), '自愈检查v2'),
    ('_full_diagnose.py', ('check', 'full_diagnose.py'), '全量诊断'),
    ('_full_serial_test.py', ('test', 'full_serial_test.py'), '全量串行测试'),
    ('_verify_curl.py', ('test', 'verify_curl.py'), 'curl验证'),
    ('_verify_pay.py', ('test', 'verify_pay.py'), '支付验证'),
    ('_verify_recommend.py', ('test', 'verify_recommend.py'), '推荐验证'),
    ('_run_with_crash_catch.py', ('ops', 'run_with_crash_catch.py'), '崩溃捕获运行'),
    ('_test_file_check.py', ('test', 'file_check.py'), '文件一致性检查'),
    ('_test_after_restart.py', ('test', 'after_restart.py'), '重启后测试'),
    ('_test_health_func.py', ('test', 'health_func.py'), '健康功能测试'),
    ('_fix_crash.py', ('fix', 'fix_crash.py'), '(已存在)崩溃修复'),
]

print('=== 补齐遗漏的工具 ===')
copied = 0
for src_name, (subdir, dst_name), desc in MISSING:
    src = os.path.join(BASE, src_name)
    dst = os.path.join(TOOLS, subdir, dst_name)
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        print(f'  + {subdir}/{dst_name}  ({desc})')
        copied += 1
    elif os.path.exists(dst):
        print(f'  = {subdir}/{dst_name}  (已存在)')

print(f'\n新增: {copied} 个')

# 归档 _* 脚本
archive = os.path.join(TOOLS, 'archive')
os.makedirs(archive, exist_ok=True)

archived = 0
for f in os.listdir(BASE):
    if f.startswith('_') and f.endswith('.py'):
        src = os.path.join(BASE, f)
        dst = os.path.join(archive, f)
        if not os.path.exists(dst):
            # 排除已拷贝到子目录的（不重复归档）
            already_in_sub = False
            for root, dirs, files in os.walk(TOOLS):
                if f in files and root != archive:
                    already_in_sub = True
                    break
            if not already_in_sub:
                shutil.copy2(src, dst)
                archived += 1

print(f'归档: {archived} 个一次性脚本到 archive/')

# 统计
total = 0
for root, dirs, files in os.walk(TOOLS):
    total += len([f for f in files if f.endswith('.py')])
print(f'\ndev_tools 最终脚本总数: {total}')
