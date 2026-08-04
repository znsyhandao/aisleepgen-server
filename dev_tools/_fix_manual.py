"""Fix TOOL_MANUAL.md command names — replace full path with short command"""
import re

CMD_MAP = {
    'audit/architecture_inner_eye.py': 'audit inner-eye',
    'audit/security_audit.py': 'audit security',
    'audit/topology_audit.py': 'audit topology',
    'audit/triple_audit.py': 'audit triple',
    'check/api_contract_check.py': 'check contract',
    'check/api_security.py': 'check auth-api',
    'check/assess_damage.py': 'check damage',
    'check/auth_check.py': 'check auth',
    'check/deploy_check.py': 'check deploy',
    'check/find_duplicates.py': 'check duplicates',
    'check/find_history.py': 'check history',
    'check/find_messages.py': 'check messages',
    'check/find_routes.py': 'check routes',
    'check/find_stories.py': 'check stories',
    'check/full_diagnose.py': 'check diagnose',
    'check/full_health_check.py': 'check health',
    'check/scan_all_audio.py': 'check audio',
    'check/self_heal.py': 'check self-heal',
    'check/test_compile.py': 'check compile',
    'fix/fix_bare_except.py': 'fix bare-except',
    'fix/fix_crash.py': 'fix crash',
    'monitor/mutant_watch.py': 'monitor runtime',
    'ops/batch_convert_m4a.py': 'ops batch-m4a',
    'ops/clean_misplaced_files.py': 'ops clean-files',
    'ops/download_deepseek.py': 'ops download-model',
    'ops/install_hooks.py': 'ops install-hooks',
    'ops/pre_commit.py': 'ops pre-commit',
    'ops/pre_op.py': 'ops pre-op',
    'ops/run_with_crash_catch.py': 'ops run-crash',
    'test/ab_framework.py': 'test ab',
    'test/after_restart.py': 'test after-restart',
    'test/async_pipeline.py': 'test async',
    'test/comprehensive_test.py': 'test api',
    'test/file_check.py': 'test file-check',
    'test/full_serial_test.py': 'test serial',
    'test/health_func.py': 'test health-func',
    'test/quick_test.py': 'test quick',
    'test/smoke_test.py': 'test smoke',
    'test/test_default.py': 'test default',
    'test/test_dev_user.py': 'test dev-user',
    'test/verify_curl.py': 'test verify-curl',
    'test/verify_pay.py': 'test verify-pay',
    'test/verify_recommend.py': 'test verify-recommend',
}

with open('D:\\AISleepGen_Optimized\\dev_tools\\TOOL_MANUAL.md', 'r', encoding='utf-8') as f:
    content = f.read()

def fix_line(m):
    fname = m.group(1)
    short_cmd = CMD_MAP.get(fname)
    if short_cmd:
        return 'python aisleepgen_tool.py ' + short_cmd
    return m.group(0)

content = re.sub(r'python aisleepgen_tool\.py (\w+/[^`]+)', fix_line, content)

# Also fix "命令" line - replace full format
content = re.sub(
    r'- \*\*命令\*\*: `([^`]+)`',
    lambda m: '- **命令**: `' + m.group(1) + '`',
    content
)

with open('D:\\AISleepGen_Optimized\\dev_tools\\TOOL_MANUAL.md', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
cmd_lines = [l for l in content.split('\n') if '命令' in l and 'aisleepgen_tool' in l]
print(f'Fixed {len(cmd_lines)} command lines:')
for l in cmd_lines[:10]:
    print(f'  {l.strip()}')
print('...' if len(cmd_lines) > 10 else '')
print('Done.')
