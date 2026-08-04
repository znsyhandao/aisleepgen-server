#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aisleepgen_tool.py - 统一开发工具入口

用法:
  python aisleepgen_tool.py <类别> <命令> [参数]

命令:

  # 审核 - audit/security/topology/inner-eye
  audit triple           三层审核（数学+动力学+运行时）
  audit topology         拓扑动力学框架对比
  audit response-quality  AI回复质量审计（LLM-as-Judge）
  audit inner-eye        架构内视分析

  # 测试 - 全部API/冒烟/串行/A-B/异步
  test api               全面 API 测试（25条路由）
  test smoke             支付/推荐冒烟测试
  test quick             快速测试（chat + profile）
  test serial            全量串行测试（无并发干扰）
  test ab                A/B 测试框架（统计显著性）
  test async             异步管道测试（快速回复+后台AI）
  test verify-curl       curl 验证（已废弃）
  test verify-pay        支付 API 远程验证（外网）
  test verify-recommend  推荐 API 远程验证（外网）
  test file-check        用户配置文件检查
  test after-restart     重启后快速验证
  test health-func       华为健康 API 连通性测试
  test default           默认用户流程测试
  test dev-user          开发用户数据验证

  # 检查 - 编译/路由/契约/健康/安全
  check health           全面静态检查
  check deploy           部署前环境检查
  check auth             微信登录链路检测
  check auth-api         API 安全检测（运行时库）
  check contract         前后端接口契约检查
  check audio            音频库扫描+声学评分
  check self-heal        自愈系统检查（运行时守护）
  check diagnose         全量诊断测试
  check damage           损害评估扫描
  check duplicates       重复数据检测
  check history          用户历史记录检索
  check messages         聊天消息检索
  check stories          晚安故事检索
  check routes           API 路由表扫描
  check compile          快速编译检查
  check kinetic          突变动力学静态扫描（来自ClawHub工具链）
  check security-claims  安全声明与代码一致性审计（来自ClawHub工具链）
  check data-flow        数据流一致性扫描
  check omission         数据遗漏检测（监控AI是否忽略用户数据）
  check blind-spots      盲区覆盖率检查

  # 监控
  monitor runtime        运行时突变检测

  # 运维 - 备份/部署/转换/清理
  ops pre-op [file]      编辑前安全备份+编译检查
  ops pre-commit         提交前验证（7项检查）
  ops install-hooks      安装 git pre-commit hook
  ops batch-m4a          批量转换 m4a 录音（ffmpeg）
  ops download-model     下载 DeepSeek 模型（分片）
  ops run-crash          崩溃捕获运行（已过时）
  ops clean-files        清理项目根杂散文件
  ops release-clean      发布前清理缓存/临时文件（来自ClawHub工具链）

  # 数据采集管线
  pipeline evening        晚间提醒模式
  pipeline morning        早晨处理模式（分析音频→提取特征→更新模型）

  # 模型训练
  train full              全量24天LOOCV训练
  train cross-night       跨夜变化模型训练
  train top10             Top-10特征GBR训练

  # 数据质量审计
  audit data-quality      数据完整性+质量报告（人脸检测率/特征NaN/音频覆盖）
  audit noise-metrics     连拍噪声指标分析（PCA burst）
  audit feature-drift     特征随时间漂移检测

  # 修复 — 一次性工具
  fix bare-except        修复 bare except: pass
  fix bare-except        修复 bare except: pass
  fix crash              自动修复多个应用
  fix profile-protect    修复 profile latest 保护+版本号
  fix remaining-gaps     修复4个剩余盲区(S1/H6/F2)
  ops pre-op-js          前端JS/JSON预检（括号/双逗号/语法）
  # GPT-SoVITS 语音克隆
  gtss check              环境三关检查（CUDA/磁盘/依赖）
  gtss setup              一键安装所有缺失依赖
  gtss guide              打印训练/推理命令参考
  gtss clean [dir]        清理旧权重和临时文件 [--keep N]
  gtss transfer           实例迁移指南
  gtss ref <audio>        预处理参考音频 [--start ms] [--duration ms]

  # 系统
  version                显示工具版本
  help                   显示此帮助

"""

import os, sys, subprocess

TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dev_tools')
VERSION = '1.0.0'

COMMANDS = {
    # audit
    ('audit', 'triple'):          ('audit', 'triple_audit.py'),
    ('audit', 'topology'):        ('audit', 'topology_audit.py'),
    ('audit', 'security'):        ('audit', 'security_audit.py'),
    ('audit', 'response-quality'): ('audit', 'audit_response_quality.py'),
    ('audit', 'inner-eye'):       ('audit', 'architecture_inner_eye.py'),
    # test
    ('test', 'api'):              ('test', 'comprehensive_test.py'),
    ('test', 'smoke'):            ('test', 'smoke_test.py'),
    ('test', 'quick'):            ('test', 'quick_test.py'),
    ('test', 'serial'):           ('test', 'full_serial_test.py'),
    ('test', 'ab'):               ('test', 'ab_framework.py'),
    ('test', 'async'):            ('test', 'async_pipeline.py'),
    ('test', 'verify-curl'):      ('test', 'verify_curl.py'),
    ('test', 'verify-pay'):       ('test', 'verify_pay.py'),
    ('test', 'verify-recommend'): ('test', 'verify_recommend.py'),
    ('test', 'file-check'):       ('test', 'file_check.py'),
    ('test', 'after-restart'):    ('test', 'after_restart.py'),
    ('test', 'health-func'):      ('test', 'health_func.py'),
    ('test', 'default'):          ('test', 'test_default.py'),
    ('test', 'dev-user'):         ('test', 'test_dev_user.py'),
    # check
    ('check', 'health'):          ('check', 'full_health_check.py'),
    ('check', 'deploy'):          ('check', 'deploy_check.py'),
    ('check', 'auth'):            ('check', 'auth_check.py'),
    ('check', 'auth-api'):        ('check', 'api_security.py'),
    ('check', 'contract'):        ('check', 'api_contract_check.py'),
    ('check', 'audio'):           ('check', 'scan_all_audio.py'),
    ('check', 'self-heal'):       ('check', 'self_heal.py'),
    ('check', 'diagnose'):        ('check', 'full_diagnose.py'),
    ('check', 'damage'):          ('check', 'assess_damage.py'),
    ('check', 'duplicates'):      ('check', 'find_duplicates.py'),
    ('check', 'history'):         ('check', 'find_history.py'),
    ('check', 'messages'):        ('check', 'find_messages.py'),
    ('check', 'stories'):         ('check', 'find_stories.py'),
    ('check', 'routes'):          ('check', 'find_routes.py'),
    ('check', 'compile'):         ('check', 'test_compile.py'),
    ('check', 'kinetic'):         ('check', 'kinetic_scan.py'),
    ('check', 'security-claims'): ('audit', 'claim_verifier.py'),
    ('check', 'data-flow'):       ('check', 'check_data_flow.py'),
    # audio (GPT-SoVITS 语音克隆)
    ('gtss', 'check'):            ('audio', '_gptsovits_pipeline.py'),
    ('gtss', 'setup'):            ('audio', '_gptsovits_pipeline.py'),
    ('gtss', 'guide'):            ('audio', '_gptsovits_pipeline.py'),
    ('gtss', 'clean'):            ('audio', '_gptsovits_pipeline.py'),
    ('gtss', 'transfer'):         ('audio', '_gptsovits_pipeline.py'),
    ('gtss', 'ref'):              ('audio', '_gptsovits_pipeline.py'),
    ('check', 'omission'):        ('check', 'check_omission.py'),
    ('check', 'blind-spots'):     ('check', 'check_blind_spot_coverage.py'),
    # monitor
    ('monitor', 'runtime'):       ('monitor', 'mutant_watch.py'),
    # ops
    ('ops', 'pre-op'):            ('ops', 'pre_op.py'),
    ('ops', 'pre-commit'):        ('ops', 'pre_commit.py'),
    ('ops', 'install-hooks'):     ('ops', 'install_hooks.py'),
    ('ops', 'batch-m4a'):         ('ops', 'batch_convert_m4a.py'),
    ('ops', 'download-model'):    ('ops', 'download_deepseek.py'),
    ('ops', 'run-crash'):         ('ops', 'run_with_crash_catch.py'),
    ('ops', 'clean-files'):       ('ops', 'clean_misplaced_files.py'),
    ('ops', 'release-clean'):     ('ops', 'release_cleaner.py'),
    # 数据采集管线
    ('pipeline', 'evening'):       ('ops', 'pipeline.py'),
    ('pipeline', 'morning'):       ('ops', 'pipeline.py'),
    # 模型训练
    ('train', 'full'):           ('ops', 'train_full.py'),
    ('train', 'cross-night'):    ('ops', 'cross_night_pipeline.py'),
    ('train', 'top10'):          ('ops', 'train_top10.py'),
    # 数据质量审计
    ('audit', 'data-quality'):   ('audit', 'data_quality_audit.py'),
    ('audit', 'noise-metrics'):  ('audit', 'noise_metrics_audit.py'),
    ('audit', 'feature-drift'):  ('audit', 'feature_drift_audit.py'),
    # fix
    ('fix', 'profile-protect'):  ('fix', 'fix_profile_protect.py'),
    ('fix', 'remaining-gaps'):   ('fix', 'fix_remaining_gaps.py'),
    ('fix', 'bare-except'):       ('fix', 'fix_bare_except.py'),
    ('fix', 'crash'):             ('fix', 'fix_crash.py'),
}


def print_usage():
    print(__doc__.strip())
    sys.exit(0)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ('help', '-h', '--help'):
        print_usage()

    if args[0] == 'version':
        print(f'aisleepgen_tool v{VERSION}')
        sys.exit(0)

    if len(args) < 2:
        print(f'Error: need 2+ arguments. Got: {" ".join(args)}')
        print_usage()

    key = (args[0], args[1])
    if key not in COMMANDS:
        print(f'Error: unknown command "{args[0]} {args[1]}"')
        print_usage()

    subdir, script = COMMANDS[key]
    script_path = os.path.join(TOOL_DIR, subdir, script)

    if not os.path.exists(script_path):
        print(f'Error: script not found at {script_path}')
        sys.exit(1)

    sub_args = [sys.executable, '-B', script_path] + args[2:]

    # Special handling for some commands
    if key == ('monitor', 'runtime'):
        sub_args.append(os.path.dirname(os.path.abspath(__file__)))

    if key == ('check', 'kinetic'):
        # kinetic_scan 需要项目目录参数
        sub_args.append(os.path.dirname(os.path.abspath(__file__)))

    if key == ('check', 'security-claims'):
        # claim_verifier 需要项目目录参数（SECURITY_STATEMENT.md 所在位置）
        sub_args.append(os.path.dirname(os.path.abspath(__file__)))

    if key == ('ops', 'pre-op'):
        sub_args.append(args[2] if len(args) > 2 else 'deepseek_proxy.py')

    env = os.environ.copy()
    if key == ('test', 'api') and 'API' not in env:
        port = env.get('AISLEEPGEN_PORT', '8090')
        env['API'] = f'http://127.0.0.1:{port}'

    print(f'[aisleepgen_tool] Running {subdir}/{script}...')
    sys.stdout.flush()

    result = subprocess.run(sub_args, env=env)
    sys.exit(result.returncode)


if __name__ == '__main__':
    main()
