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
  test pii-leak           PII泄漏/用户数据回显测试（合规）
  test rx-block           处方药推荐拦截测试（安全）
  test anti-pseudoscience  反伪科学声明一致性测试（循证）
  test disclaimer         医学免责声明自动检查（合规）
  test abnormal-input     异常输入/XSS/空值/超长文本处理测试
  test multi-user-isolation  多用户数据隔离测试（跨用户污染检查）
  test test-retest         Test-Retest信度测试（回复一致性）
  test idempotency        幂等性验证（重放安全）
  test clinical-safety    勿伤害原则完整性测试（危险行为拒绝/危机检测）
  test isi-validation      ISI失眠严重指数验证（分级一致性）
  test phq-benchmark       PHQ-9/GAD-7回归误差分析（抑郁焦虑评估）
  test symptom-probing     症状追问策略覆盖率（临床问诊维度）
  test referral-timing     转诊建议时机合规（红线场景转诊）
  test hallucination       事实性幻觉测试（虚构研究/编造数据/过度自信）
  test jailbreak           越狱/对抗性Prompt测试（角色扮演/逻辑绕过/泄露）
  test all                 全量测试运行器（跑所有测试+自动汇总报告）
  test sleep-staging       PSG睡眠分期一致性验证（基于AASM标准/PhysioNet数据集）
  test differential        鉴别诊断推理链测试（基于ICSD-3分类框架）
  test gold-standard        PHQ-9/GAD-7金标准校准框架（Koenke 2001 / Spitzer 2006）
  test ci                   CI持续集成运行器（全自动+历史趋势+退化检测）
  test empathy              AI共情能力测试（Rogers标准）
  test crisis               心理危机干预测试（自杀/自伤检测）
  test sas-rls             睡眠呼吸暂停(SAS)+不宁腿(RLS)筛查诊断测试
  test narcolepsy          发作性睡病(Narcolepsy)筛查诊断测试
  test bipolar             双相障碍睡眠筛查测试（鉴别躁狂vs失眠）
  test drug-interact       药物相互作用安全测试（褪黑素/安眠药/酒精）
  test meditation-api      冥想API全链路测试（8个API）
  test pediatric           儿科/青少年睡眠专项测试（Morobo合作准备）
  test huawei-band         华为手环数据集成测试（3源融合）
  test psych-boundary       心理评估边界测试+DSM-5诊断禁令

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
  check duplicate-blocks  重复代码块模式匹配扫描（拦截器/复制粘贴）
  check dead-code        死代码/废弃导入扫描
  check magic-numbers    硬编码 Magic Number 检测
  check data-flow        数据流审计（except/fallback/静默退化）
  check dependency-graph 依赖图生成 + 循环依赖检测
  check degradation      数据渐进式退化检测（fallback 趋势/未知状态率/状态多样性）
  check safety-psych     心理安全红线守卫（自杀/自伤/严重症状→强制转介）
  check anti-fake-science 反伪科学/反医学声明过滤器
  check diagnosis-filter 医学引用合规过滤器（无引用诊断/药物/预后/无disclaimer）
  check privacy-leak      PII泄漏/密钥硬编码/数据最小化扫描（OWASP）
  check secret-scan       API Key/secret硬编码深度扫描
  check circuit-breaker   外部依赖断路器检查（DeepSeek限流防护）
  check graceful-degrade  优雅降级审计（异常时给用户友好提示）
  check state-persist     状态持久化检查（重启后用户数据不丢）
  check timeout-protect   超时保护完整性（所有外部调用必须设timeout）
  check output-sanity     AI输出语义合理性检查（矛盾/重复/异常长度）

  check flywheel        数据飞轮健康度检查（SQLite）
  check pre-launch      上线前全链路审计（注册→使用→持久化）
  check config-check     配置/常量一致性检查（env key/API路径/超时）
  check max-tokens       max_tokens 体积匹配检查（补prompt后token不够用）
  check template-detect  回复模板化检测（个性化空洞/假关心）
  check error-paths      错误路径覆盖率（try/except/分支完整性）
  check prompt-inject    Prompt 注入/泄露审计（API key漏出/注入风险）
  check resource-leak    资源泄漏检测（句柄/线程/临时文件）

  # 测试
  test e2e               端到端剧情测试（用户全流程 + 世界模型状态验证）
  test concurrent        并发压力测试（竞态条件/状态污染）
  test stability         长时间稳定性测试（定时器/内存泄漏/响应时间漂移）

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

  # C36 GPT-SoVITS 训练
  ops c36 check            前置检查（数据完整性+GPU+磁盘）
  ops c36 fix              修复所有已知问题
  ops c36 launch [N]       全自动启动训练（默认600 epoch）
  ops c36 status           查看训练状态
  ops c36 patch            只打补丁
  ops c36 help             查看完整帮助

  # 系统
  version                显示工具版本
  help                   显示此帮助

  # 额外已注册命令（未在help列出但可通过aisleepgen_tool.py直接调用）：
  #   check audit-injection — 审计注入位置检查
  #   safe_pkill <pattern>  — 精确杀进程（python dev_tools/ops/safe_pkill.py）

"""

import os, sys, subprocess

TOOL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dev_tools')
VERSION = '2.4.0'

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
    # NEW: clinical safety tests
    ('test', 'pii-leak'):         ('test', 'pii_leak_test.py'),
    ('test', 'rx-block'):         ('test', 'rx_block_test.py'),
    ('test', 'anti-pseudoscience'): ('test', 'anti_pseudoscience.py'),
    ('test', 'disclaimer'):       ('test', 'disclaimer_test.py'),
    ('test', 'abnormal-input'):    ('test', 'abnormal_input_test.py'),
    ('test', 'multi-user-isolation'): ('test', 'multi_user_isolation_test.py'),
    ('test', 'test-retest'):       ('test', 'test_retest_test.py'),
    ('test', 'idempotency'):       ('test', 'idempotency_test.py'),
    ('test', 'clinical-safety'):   ('test', 'clinical_safety_test.py'),
    # NEW: clinical benchmark tests
    ('test', 'isi-validation'):    ('test', 'isi_validation_test.py'),
    ('test', 'phq-benchmark'):     ('test', 'phq_benchmark_test.py'),
    ('test', 'symptom-probing'):   ('test', 'symptom_probing_test.py'),
    ('test', 'referral-timing'):   ('test', 'referral_timing_test.py'),
    # NEW: hallucination + jailbreak + all-runner
    ('test', 'hallucination'):     ('test', 'hallucination_test.py'),
    ('test', 'jailbreak'):         ('test', 'jailbreak_test.py'),
    ('test', 'all'):               ('test', 'test_all_runner.py'),
    # NEW: Round 3 - staging, differential, gold standard, CI
    ('test', 'sleep-staging'):     ('test', 'sleep_staging_validation.py'),
    ('test', 'differential'):      ('test', 'differential_diagnosis_test.py'),
    ('test', 'gold-standard'):     ('test', 'gold_standard_framework.py'),
    ('test', 'ci'):                ('test', 'ci_runner.py'),
    # NEW: Round 4 - psych AI tests
    ('test', 'empathy'):        ('test', 'empathy_test.py'),
    ('test', 'crisis'):         ('test', 'crisis_test.py'),
    ('test', 'psych-boundary'): ('test', 'psych_boundary_test.py'),
    ('test', 'sas-rls'):        ('test', 'sas_rls_screening_test.py'),
    # NEW: P0 clinical gaps - narcolepsy + bipolar + drug interaction
    ('test', 'narcolepsy'):     ('test', 'narcolepsy_test.py'),
    ('test', 'bipolar'):        ('test', 'bipolar_screening_test.py'),
    ('test', 'drug-interact'):  ('test', 'drug_interaction_test.py'),
    # NEW: P1 product gaps - meditation api + pediatric + huawei band
    ('test', 'meditation-api'): ('test', 'meditation_api_test.py'),
    ('test', 'pediatric'):      ('test', 'pediatric_sleep_test.py'),
    ('test', 'huawei-band'):    ('test', 'huawei_band_integration_test.py'),
    # NEW: deep infrastructure bug tests
    ('test', 'hardcoded-path'):    ('test', 'hardcoded_path_test.py'),
    ('test', 'audio-crash'):       ('test', 'audio_recommender_crash_test.py'),
    ('test', 'empty-input'):       ('test', 'empty_input_hardness_test.py'),
    ('test', 'pii-print-leak'):    ('test', 'pii_print_leak_test.py'),
    # NEW: safety collision + longevity + self-test + concurrency + fallback + consistency
    ('test', 'breathing-collision'): ('test', 'breathing_keyword_collision_test.py'),
    ('test', 'longevity'):          ('test', 'conversation_longevity_test.py'),
    ('test', 'safety-filter'):      ('test', 'safety_filter_self_test.py'),
    ('test', 'concurrent-rw'):      ('test', 'concurrent_rw_test.py'),
    ('test', 'fallback'):           ('test', 'api_fallback_test.py'),
    ('test', 'consistency'):        ('test', 'response_consistency_test.py'),
    # check
    ('check', 'health'):          ('check', 'full_health_check.py'),
        ('check', 'audit-injection'): ('check', 'check_audit_injection.py'),
    ('check', 'flywheel'):        ('check', 'data_flywheel.py'),
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
    # NEW: deep audit tools
    ('check', 'duplicate-blocks'): ('check', 'duplicate_block_finder.py'),
    ('check', 'dead-code'):       ('check', 'dead_code_scanner.py'),
    ('check', 'magic-numbers'):   ('check', 'magic_number_detector.py'),
    ('check', 'data-flow'):       ('check', 'data_flow_audit.py'),
    ('check', 'dependency-graph'): ('check', 'dependency_graph.py'),
    ('check', 'degradation'):     ('check', 'degradation_detector.py'),
    ('check', 'safety-psych'):     ('check', 'psychological_safety_guard.py'),
    ('check', 'anti-fake-science'): ('check', 'anti_false_science_check.py'),
    ('check', 'diagnosis-filter'):  ('check', 'forbidden_diagnosis_filter.py'),
    ('check', 'config-check'):     ('check', 'config_consistency_check.py'),
    ('check', 'max-tokens'):      ('check', 'max_tokens_check.py'),
    ('check', 'privacy-leak'):     ('check', 'privacy_leak_scanner.py'),
    ('check', 'secret-scan'):       ('check', 'hardcoded_secret_scanner.py'),
    ('check', 'circuit-breaker'):   ('check', 'circuit_breaker_check.py'),
    ('check', 'graceful-degrade'):  ('check', 'graceful_degradation_check.py'),
    ('check', 'state-persist'):     ('check', 'state_persistence_check.py'),
    ('check', 'timeout-protect'):   ('check', 'timeout_protection_check.py'),
    ('check', 'output-sanity'):     ('check', 'output_sanity_monitor.py'),

    ('check', 'template-detect'):   ('check', 'response_template_detector.py'),
    ('check', 'error-paths'):       ('check', 'error_path_coverage.py'),
    ('check', 'prompt-inject'):     ('check', 'prompt_injection_audit.py'),
    ('check', 'resource-leak'):     ('check', 'resource_leak_detector.py'),
    # safe_pkill special: no args required, passthrough to safe_pkill.py
    ('ops', 'safe-pkill'):          ('ops', 'safe_pkill.py'),
    ('check', 'flywheel'):          ('check', 'data_flywheel.py'),
    ('check', 'pre-launch'):        ('check', 'pre_launch_audit.py'),
    # NEW: extended tests
    ('test', 'e2e'):              ('test', 'end_to_end_story_test.py'),
    ('test', 'concurrent'):       ('test', 'concurrent_stress_test.py'),
    ('test', 'stability'):        ('test', 'stability_endurance_test.py'),
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
    # C36 GPT-SoVITS 训练工具
    ('ops', 'c36'):               ('ops', 'c36_train_tool.py'),
    # 统一部署工具
    ('ops', 'deploy'):            ('ops', 'deploy_unified.py'),
    # Neural Nexus 脉冲注入
    ('ops', 'nexus'):             ('ops', 'nexus_pulse.py'),
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
