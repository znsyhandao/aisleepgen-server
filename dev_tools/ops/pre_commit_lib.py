#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre_commit_lib.py — 预设失败验证核心逻辑 v1.1

可测试的纯函数：解析 + 决策 + 脆弱性指数 + 因果追溯，不含 subprocess/IO 副作用。
"""
import json
import os
import re
from collections import defaultdict


def parse_kinetic_output(output):
    """从 kinetic_scan --json 的输出流中提取 summary dict"""
    for line in output.split('\n'):
        stripped = line.strip()
        if stripped.startswith('{'):
            try:
                data = json.loads(stripped if stripped.endswith('}') else
                                  '\n'.join(output.split('\n')[output.split('\n').index(line):]))
                return data.get('summary', {})
            except (json.JSONDecodeError, ValueError):
                # 可能是截断的 JSON，尝试整段
                try:
                    data = json.loads(stripped)
                    return data.get('summary', {})
                except Exception:
                    continue
    return {}


def parse_runtime_output(output):
    """从 mutant_watch 控制台输出中提取 severity 计数"""
    result = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for line in output.split('\n'):
        stripped = line.strip()
        if 'HIGH:' in stripped and 'MEDIUM:' in stripped:
            for sev in ['HIGH', 'MEDIUM', 'LOW']:
                idx = stripped.find(sev + ':')
                if idx >= 0:
                    after = stripped[idx + len(sev) + 1:].strip().split()
                    if after:
                        try:
                            result[sev] = int(after[0])
                        except (ValueError, IndexError):
                            pass
    return result


def parse_kinetic_summary(summary):
    """从 kinetic_scan summary 中提取 severity 计数"""
    by_sev = summary.get('by_severity', {})
    return {
        'HIGH': by_sev.get('HIGH', 0),
        'MEDIUM': by_sev.get('MEDIUM', 0),
        'LOW': by_sev.get('LOW', 0),
    }


def detect_contract_changes(old_baseline, new_baseline):
    """比较新旧 API 基线，返回变化摘要"""
    old_keys = set(old_baseline.keys()) if old_baseline else set()
    new_keys = set(new_baseline.keys()) if new_baseline else set()

    deleted = old_keys - new_keys
    added = new_keys - old_keys
    changed = []

    for route in old_keys & new_keys:
        old_route = old_baseline.get(route, {})
        new_route = new_baseline.get(route, {})
        old_keyset = set(old_route.get('keys', []))
        new_keyset = set(new_route.get('keys', []))
        if old_keyset != new_keyset:
            changed.append({
                'route': route,
                'removed': list(old_keyset - new_keyset),
                'added': list(new_keyset - old_keyset),
            })

    return {
        'api_route_deleted': len(deleted),
        'api_route_added': len(added),
        'api_return_keys_changed': len(changed),
        'deleted_routes': sorted(deleted),
        'added_routes': sorted(added),
        'changed_routes': changed,
    }


def should_block(total_high=0, total_medium=0, allow_high=False):
    """决策逻辑：是否应该阻止提交"""
    if total_high > 0 and not allow_high:
        return True, '{} HIGH risks, use --allow-high to override'.format(total_high)
    if total_high > 0 and allow_high:
        return False, '{} HIGH risks (allowed by --allow-high)'.format(total_high)
    if total_medium > 5:
        return False, '{} MEDIUM risks (above threshold 5), review recommended'.format(total_medium)
    return False, 'clean'


def analyse_git_blame(diff_text, route_changes):
    """从 git diff 输出追溯 route 变化的真正改动文件"""
    if not diff_text or not route_changes:
        return []

    trace_results = []
    for change in route_changes:
        route = change.get('route', '?')
        # 在 diff 中搜索 route path 或 handler 名字
        for line in diff_text.split('\n'):
            if route in line and (line.startswith('+') or line.startswith('-')):
                trace_results.append({
                    'route': route,
                    'change_type': 'added' if line.startswith('+') else 'removed',
                    'diff_snippet': line[:120].strip(),
                })
                break

    return trace_results


def compute_fragility_scores(file_paths, kinetic_findings, import_refs=None):
    """计算每个文件的脆弱性指数

    Args:
        file_paths: 项目中的所有 .py 文件路径
        kinetic_findings: kinetic_scan 返回的 findings 列表
        import_refs: {file: [imported_files]} 引用图（可选）

    Returns:
        [(file, score, reasons)]
    """
    if not file_paths:
        return []

    # 统计每个文件的高风险项
    high_per_file = defaultdict(int)
    medium_per_file = defaultdict(int)
    for f in kinetic_findings:
        fpath = f.get('file', '')
        sev = f.get('severity', '')
        if sev == 'HIGH':
            high_per_file[fpath] += 1
        elif sev == 'MEDIUM':
            medium_per_file[fpath] += 1

    # 计算被引用数（import 关系）
    ref_count = defaultdict(int)
    if import_refs:
        for src, targets in import_refs.items():
            for t in targets:
                ref_count[t] += 1

    # 计算分数
    scores = []
    for fpath in file_paths:
        h = high_per_file.get(fpath, 0)
        m = medium_per_file.get(fpath, 0)
        refs = ref_count.get(fpath, 0)
        refs_norm = min(refs / 5.0, 3.0)  # 最多 3 分

        score = h * 3 + m * 1 + refs_norm

        reasons = []
        if h > 0:
            reasons.append('{} HIGH'.format(h))
        if m > 0:
            reasons.append('{} MEDIUM'.format(m))
        if refs > 3:
            reasons.append('引用数={}'.format(refs))

        scores.append((fpath, round(score, 1), '; '.join(reasons) if reasons else '-'))

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:15]  # 只返回前 15 个最脆弱的


def detect_full_regression(kinetic_findings, runtime_findings, contract_diff, kinetic_summary):
    """聚合全部退化数据，产生完整退化报告

    Returns:
        {
            'kinetic_sev': {'HIGH': N, 'MEDIUM': N, 'LOW': N},
            'runtime_sev': {'HIGH': N, 'MEDIUM': N, 'LOW': N},
            'contract': {...},
            'total_high': N,
            'total_medium': N,
        }
    """
    kinetic_sev = parse_kinetic_summary(kinetic_summary)

    runtime_sev = {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
    for f in runtime_findings:
        sev = f.get('severity', '')
        if sev in runtime_sev:
            runtime_sev[sev] += 1

    total_high = kinetic_sev['HIGH'] + runtime_sev['HIGH'] + \
                 contract_diff['api_route_deleted'] + contract_diff['api_return_keys_changed']
    total_medium = kinetic_sev['MEDIUM'] + runtime_sev['MEDIUM']

    return {
        'kinetic_sev': kinetic_sev,
        'runtime_sev': runtime_sev,
        'contract': contract_diff,
        'total_high': total_high,
        'total_medium': total_medium,
    }
