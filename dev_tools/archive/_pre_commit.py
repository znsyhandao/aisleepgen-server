#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
_pre_commit.py — 部署前预设失败验证 v1.1

编排 pre_commit_lib（可测试的逻辑层）+ 子进程调用。

三层审核：
  1. 静态突变动力学（kinetic_scan）
  2. 运行时数据退化（mutant_watch）
  3. API 契约基线对比

用法：
  python _pre_commit.py              # 全量验证，HIGH 自动阻止
  python _pre_commit.py --allow-high # 跳过 HIGH 评审
  python _pre_commit.py --check-only # 仅对比现有基线，不跑扫描

返回值：
  0 = 通过
  1 = 有 HIGH 风险（拒绝）
  2 = 有 MEDIUM 风险（警告）
"""
import json
import os
import shutil
import subprocess
import sys
import time

import pre_commit_lib

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
KINETIC_SCAN = os.path.join(r'D:\OpenClaw_Unified_Tools\ClawHub_Compliance', 'kinetic_scan.py')
MUTANT_WATCH = os.path.join(PROJECT_DIR, 'mutant_watch.py')


def run_script(script, args, label):
    """运行外部 Python 脚本，返回解码后的 stdout"""
    print('\n{}'.format('=' * 60))
    print('  [{}] 预设失败验证'.format(label))
    print('{}'.format('=' * 60))

    cmd = [sys.executable, '-B', script] + args
    result = subprocess.run(cmd, capture_output=True, timeout=60)

    stdout = result.stdout.decode('utf-8', errors='replace')
    stderr = result.stderr.decode('utf-8', errors='replace')

    for line in stdout.split('\n'):
        stripped = line.strip()
        if not stripped or 'Exception in thread' in stripped or 'UnicodeDecodeError' in stripped:
            continue
        print(stripped)

    return stdout


def main():
    check_only = '--check-only' in sys.argv
    allow_high = '--allow-high' in sys.argv

    print('\n')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588     \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588     \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588     \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588     \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588   \u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588   \u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print('  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588    \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588\u2588\u2588   \u2588\u2588\u2588\u2588\u2588  \u2588\u2588\u2588   \u2588\u2588\u2588')
    print()

    start = time.time()

    if check_only:
        # --check-only: 跳过扫描，仅对比已保存的基线备份
        print('  [仅检查] 跳过扫描，对比 API 基线')
        contract_diff = pre_commit_lib.detect_contract_changes(
            _load_baseline_bak(), _load_baseline()
        )
        kinetic_sev = pre_commit_lib.parse_kinetic_summary({})
        kinetic_findings_raw = []
        runtime_sev = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    else:
        # 1. 备份当前 API 基线
        _backup_baseline()

        # 2. 静态扫描
        kinetic_output = run_script(KINETIC_SCAN, [PROJECT_DIR, '--json'], '静态突变动力学')
        kinetic_summary = pre_commit_lib.parse_kinetic_output(kinetic_output)
        kinetic_findings_raw = _parse_kinetic_findings(kinetic_output)
        kinetic_sev = pre_commit_lib.parse_kinetic_summary(kinetic_summary)

        # 3. 运行时扫描
        runtime_output = run_script(MUTANT_WATCH, [PROJECT_DIR], '运行时数据退化')
        runtime_sev = pre_commit_lib.parse_runtime_output(runtime_output)

        # 4. API 契约对比
        contract_diff = pre_commit_lib.detect_contract_changes(
            _load_baseline_bak(), _load_baseline()
        )

    elapsed = time.time() - start

    total_high = kinetic_sev['HIGH'] + runtime_sev['HIGH'] + \
                 contract_diff['api_route_deleted'] + contract_diff['api_return_keys_changed']
    total_medium = kinetic_sev['MEDIUM'] + runtime_sev['MEDIUM']

    # 打印汇总
    print()
    print('=' * 60)
    print('  预设失败验证 — 汇总')
    print('=' * 60)
    print('  耗时: {:.1f}s'.format(elapsed))
    print()
    print('  静态代码退化:   HIGH={}  MEDIUM={}  LOW={}'.format(
        kinetic_sev['HIGH'], kinetic_sev['MEDIUM'], kinetic_sev['LOW']))
    print('  运行时数据退化: HIGH={}  MEDIUM={}  LOW={}'.format(
        runtime_sev['HIGH'], runtime_sev['MEDIUM'], runtime_sev['LOW']))
    print('  API 契约变化:   删除={}  新增={}  字段变更={}'.format(
        contract_diff['api_route_deleted'],
        contract_diff['api_route_added'],
        contract_diff['api_return_keys_changed']))
    print()

    if contract_diff.get('deleted_routes'):
        print('  \u26a0 \u5df2\u5220\u9664 route:')
        for r in contract_diff['deleted_routes']:
            print('    - {}'.format(r))
    if contract_diff.get('changed_routes'):
        print('  \u26a0 \u5b57\u6bb5\u53d8\u66f4 route:')
        for r in contract_diff['changed_routes']:
            print('    - {}  removed={}  added={}'.format(
                r['route'], r['removed'], r['added']))
    if contract_diff.get('added_routes'):
        print('  \u2139 \u65b0\u589e route ({} \u4e2a)'.format(len(contract_diff['added_routes'])))

    # 因果追溯（博弈维度）
    try:
        git_result = subprocess.run(['git', 'diff', 'HEAD~1', '--', '*.py'],
            capture_output=True, timeout=10, cwd=PROJECT_DIR)
        git_text = git_result.stdout.decode('utf-8', errors='replace')
        blame_items = (contract_diff.get('changed_routes', []) +
            [{'route': r} for r in contract_diff.get('deleted_routes', [])])
        if blame_items:
            blame = pre_commit_lib.analyse_git_blame(git_text, blame_items)
            if blame:
                print()
                print('  \U0001f50d \u53d8\u5316\u8ffd\u6eaf\uff08git diff \u7ebf\u7d22\uff09:')
                for b in blame[:5]:
                    print('    {}  {}'.format(b.get('change_type', '?'), b.get('diff_snippet', '')))
    except Exception:
        pass

    # 脆弱性指数（TOP 5）
    if not check_only:
        try:
            fragility = pre_commit_lib.compute_fragility_scores(
                [],
                kinetic_findings_raw,
            )
            if fragility:
                print()
                print('  \U0001f4ca \u8106\u5f31\u6027\u6307\u6570\uff08TOP 5\uff09:')
                for i, (f, s, r) in enumerate(fragility[:5]):
                    star = '\u2605' * max(1, min(5, int(s / 2 + 0.5)))
                    print('    {:<30s}  {:s} ({:.1f})  {}'.format(f[:30], star, s, r))
        except Exception:
            pass

    # 决策
    blocked, msg = pre_commit_lib.should_block(total_high, total_medium, allow_high)
    print()
    if blocked:
        print('  \u274c \u9884\u8bbe\u5931\u8d25\uff1a{}'.format(msg))
        print('  \u274c \u62d2\u7edd\u63d0\u4ea4/\u90e8\u7f72')
        print()
        print('  "\u904d\u5386\u5931\u8d25\uff0c\u5c06\u5b83\u4f5c\u4e3a\u7ea6\u675f\uff0c\u52a0\u5165\u4f60\u7684\u6a21\u578b\u4e2d\u3002"')
        return 1
    elif total_high > 0:
        print('  \u26a0 {}'.format(msg))
        print('  \u26a0 \u8bc4\u5ba1\u540e\u518d\u90e8\u7f72')
        return 2
    elif total_medium > 5:
        print('  \u26a0 {}'.format(msg))
        return 2
    else:
        print('  \u2705 \u901a\u8fc7\u3002{}'.format(msg))
        print()
        print('  "\u9884\u8bbe\u5931\u8d25\u4e0d\u662f\u60b2\u89c2\u2014\u2014\u662f\u6700\u9ad8\u7ea7\u522b\u7684\u7cfb\u7edf\u601d\u7ef4\u3002"')
        print('  \u2705 \u53ef\u4ee5\u90e8\u7f72')
        return 0
def _parse_kinetic_findings(output):
    """从 kinetic_scan JSON 输出中提取 findings 列表"""
    for line in output.split('\n'):
        stripped = line.strip()
        if stripped.startswith('{'):
            try:
                data = json.loads(stripped)
                return data.get('findings', [])
            except Exception:
                pass
    return []


def _backup_baseline():
    """备份当前 API 基线文件"""
    baseline = os.path.join(PROJECT_DIR, '.api_contract_baseline.json')
    if os.path.exists(baseline):
        shutil.copy2(baseline, baseline + '.bak')


def _load_baseline():
    """加载当前 API 基线"""
    path = os.path.join(PROJECT_DIR, '.api_contract_baseline.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _load_baseline_bak():
    """加载备份的 API 基线（用于对比）"""
    path = os.path.join(PROJECT_DIR, '.api_contract_baseline.json.bak')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


if __name__ == '__main__':
    sys.exit(main())
