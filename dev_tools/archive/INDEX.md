# archive/ — 一次性/历史脚本

这些脚本是为特定任务一次性编写的，不值得沉淀到 dev_tools 中。
如需要，直接 `python %s` 运行。历史保留不删。

## 分类

### 一次性修复 (27个)

- `_check_all_users.py` — (无文档)
- `_check_compile.py` — (无文档)
- `_check_default.py` — (无文档)
- `_check_default2.py` — (无文档)
- `_check_dev_user.py` — (无文档)
- `_check_real_users.py` — (无文档)
- `_check_users.py` — (无文档)
- `_fix_api_base.py` — (无文档)
- `_fix_app_log.py` — (无文档)
- `_fix_bare_except.py` — Fix all 'bare except:' to 'except Exception:' 
Retains existing except Exception
- `_fix_cache.py` — (无文档)
- `_fix_chat_final.py` — chat.js 一次性最终修复
- `_fix_chat_timeline.py` — 修复chat.js：api.request后面的逗号和.then错位
- `_fix_crash.py` — def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.pa
- `_fix_cross_print.py` — print(f\'  {iv}: 成功率={info[\\"success_rate\\"]:.1%} \'
              f\'置信度={inf
- `_fix_dup.py` — "
tail_marker = '{history_context}\n\n{wm_context}{evidence_context}{scene_conte
- `_fix_dup2.py` — 【有历史数据时的特殊情况 - 覆盖规则1和规则2】
{history_context} 中包含了用户的睡眠数据。直接使用这些数据进行讨论和分析。禁止问"你几点睡
- `_fix_dupe.py` — (无文档)
- `_fix_history_ctx.py` — latest_sleep = profile.get('latest', {})
    sleep_data = latest_sleep.get('slee
- `_fix_inj.py` — _inj_sd = _inj_latest.get('sleep_data', {}) or _inj_latest
- `_fix_latest_override.py` — # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    _old_sleep_data = profile.get('latest', {}).ge
- `_fix_profile_update.py` — (无文档)
- `_fix_prompt.py` — 开头的第一行（"你是眠小兔，一名睡眠健康顾问"）之后
# 添加基线强制注入
old =
- `_fix_return.py` — return {
        'reply': reply,
        'action': _action_trigger,
        'med
- `_fix_shake4.py` — (无文档)
- `_fix_survery_openid.py` — (无文档)
- `_fix_unknown.py` — sleep_data = latest.get('sleep_data', {}) or latest
            if sleep_data:
 

### 一次性数据处理 (17个)

- `_add_5_protocols.py` — # === 行为认知类（5种新增） ===
        'cognitive_unloading': {
            'name': '认知卸荷
- `_add_clinical_report.py` — Add clinical validation report to AISleepGen
1. Backend: /api/clinical-report en
- `_dl_edf_background.py` — Background EDF download - single file, patient, with recovery
- `_dl_edf_sequential.py` — Download EDF using Mendeley data.caltech.edu mirror
- `_download_2_edf.py` — Download 2 EDF files using requests with streaming
- `_download_mendeley.py` — Download Mendeley insomnia dataset
- `_download_mendeley_edf.py` — _mendeley_edf_download.py — 批量下载 Mendeley 失眠数据集 EDF 文件

突变动力学审核：
  1. 只下载 24 个标注
- `_inject_atmosphere.py` — Inject ambient atmosphere into meditation-plan response.
- `_insert_protocols.py` — # === 行为认知类（5种新增） ===
        'cognitive_unloading': {
            'name': "认知卸荷
- `_mendeley_download_master.py` — _mendeley_edf_download.py — 批量下载 Mendeley 失眠数据集 EDF

突变动力学审核:
1. 断点续传: 已存在的文件自动跳
- `_parse_mendeley_xlsx.py` — Parse Mendeley XLSX to check demographics and PSQI
- `_parse_mendeley_xlsx2.py` — Parse Mendeley XLSX for PSQI/diagnosis columns
- `_remove_misplaced.py` — (无文档)
- `_scan_all_audio.py` — 完整的音频库扫描 + 声学专家级评分排名
- `_score_replacement.py` — 基于声学特征+分类器输出映射睡眠指数和减压指数
    使用决策树分类（不依赖SVM类型输出，而是结合声学指标）
- `_train_final.py` — 彻底重训分类器：真实背景样本 + 22维特征
- `_validate_mendeley.py` — 验证 Mendeley 失眠数据集 — EDF 分析 vs Excel 金标准
先跑已有的3个EDF + 全部22个受试者的Excel评分数据对比

### 一次性调试/验证 (8个)

- `_debug_414.py` — (无文档)
- `_debug_580.py` — (无文档)
- `_debug_592.py` — (无文档)
- `_debug_613.py` — (无文档)
- `_debug_616.py` — (无文档)
- `_find_latest_update.py` — (无文档)
- `_test_4_fails.py` — (无文档)
- `_test_correct_paths.py` — (无文档)

### 一次性推送/部署 (9个)

- `_do_push.py` — (无文档)
- `_gh_push_install_sh.py` — (无文档)
- `_gh_verify.py` — (无文档)
- `_gh_verify2.py` — (无文档)
- `_gh_verify3.py` — (无文档)
- `_github_push.py` — Push files to GitHub via API
- `_push_debug.py` — (无文档)
- `_push_profile.py` — (无文档)
- `_push_tier_recommender.py` — Push tier_recommender.py to GitHub repo

### 一次性运维 (3个)

- `_deploy_server.py` — Deploy: Push latest local files to GitHub repo, then server auto-pulls.
- `_final_verify.py` — (无文档)
- `_run_with_crash_catch.py` — 带崩溃捕获的守护启动

### 需人工判断 (48个)

- `_assess_damage.py` — (无文档)
- `_check_mendeley.py` — (无文档)
- `_comprehensive_test.py` — 全面 API 测试 — 覆盖昨晚测试报错 + 所有主要路由
- `_find_dup.py` — (无文档)
- `_find_history.py` — (无文档)
- `_find_msgs.py` — (无文档)
- `_find_routes.py` — (无文档)
- `_find_story.py` — Find sleep story prompt in JS files
- `_full_diagnose.py` — AISleepGen 全面诊断测试 - 检视所有可能导致崩溃的问题
- `_full_serial_test.py` — 单进程串行测试 - 无并发连接
- `_pre_commit.py` — _pre_commit.py — 部署前预设失败验证 v1.1

编排 pre_commit_lib（可测试的逻辑层）+ 子进程调用。

三层审核：
  1. 
- `_quick_test.py` — (无文档)
- `_quick_test2.py` — (无文档)
- `_self_heal_v2.py` — SelfHeal v2 — 真正的自愈系统
检测+修复+报警，不光是“我还活着”

集成方式: 在 deepseek_proxy.py 中 import 并启动
- `_smoke_test.py` — Smoke test for all payment + recommendation APIs
- `_test_after_restart.py` — (无文档)
- `_test_api.py` — (无文档)
- `_test_ask.py` — (无文档)
- `_test_boot.py` — (无文档)
- `_test_chain.py` — (无文档)
- `_test_chat.py` — (无文档)
- `_test_compile.py` — (无文档)
- `_test_default.py` — (无文档)
- `_test_dev_user.py` — (无文档)
- `_test_edf_dl.py` — Download Normal_01 + Insomnia_10 for topology verification
- `_test_edf_dl2.py` — Download 1 EDF using raw urllib (which worked for XLSX)
- `_test_exact.py` — (无文档)
- `_test_file_check.py` — (无文档)
- `_test_file_vs_api.py` — (无文档)
- `_test_full_default.py` — (无文档)
- `_test_gbk.py` — (无文档)
- `_test_get_detail.py` — (无文档)
- `_test_health_func.py` — Test with actual function from huawei_health_kit
- `_test_history_ctx.py` — (无文档)
- `_test_huawei_api.py` — Test Huawei Health Kit API
- `_test_huawei_endp.py` — Test endpoints one at a time
- `_test_huawei_endpoints.py` — Try multiple Huawei Health API endpoint patterns
- `_test_mendeley_dl.py` — Quick connectivity test
- `_test_quick.py` — 快速测试引擎v2 - 前90秒，验证分类器
- `_test_read.py` — (无文档)
- `_test_truncate.py` — (无文档)
- `_test_write.py` — (无文档)
- `_topology_audit.py` — 对比分析：拓扑动力学框架 vs AISleepGen 现有架构

框架四层：
1. 胞腔复形（跨频耦合体素 → 边流 → 2-单形）
2. T-VAE（φ梯度/
- `_triple_audit.py` — 三层审核报告生成器
层1: 数学审核 — phi/psi/h 三分量合理性 + 专家权重 + 边界条件
层2: 动力学审核 — API基线退化 + 数据漂移 +
- `_verify_curl.py` — (无文档)
- `_verify_pay.py` — (无文档)
- `_verify_pay2.py` — (无文档)
- `_verify_recommend.py` — (无文档)
