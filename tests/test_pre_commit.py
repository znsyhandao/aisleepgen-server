# -*- coding: utf-8 -*-
"""测试 pre_commit_lib.py 核心逻辑层"""
import json
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pre_commit_lib


class TestParseKineticOutput(unittest.TestCase):
    """测试 kinetic_scan JSON 输出解析"""

    def setUp(self):
        self.sample_json = json.dumps({
            'tool': 'kinetic_scan.py v1.2',
            'summary': {
                'total': 13,
                'by_severity': {'HIGH': 3, 'MEDIUM': 3, 'LOW': 7},
                'by_type': {'except_pass': 3, 'shared_write': 2},
                'suppressed_count': 7,
            }
        })

    def test_parse_full_output(self):
        """能从带前缀文本的完整输出中提取 JSON"""
        output = (
            '============================================================\n'
            '  扫描完成: 63 项\n'
            '============================================================\n'
            + self.sample_json
        )
        summary = pre_commit_lib.parse_kinetic_output(output)
        self.assertEqual(summary['total'], 13)
        self.assertEqual(summary['by_severity']['HIGH'], 3)

    def test_parse_no_json(self):
        """输出中无 JSON 时返回空"""
        self.assertEqual(pre_commit_lib.parse_kinetic_output('no json here'), {})

    def test_parse_malformed_json(self):
        """输出中包含非法 JSON 时优雅跳过"""
        output = 'some text\n{invalid}\n' + self.sample_json
        summary = pre_commit_lib.parse_kinetic_output(output)
        self.assertEqual(summary['total'], 13)

    def test_parse_empty_output(self):
        """空输出返回空"""
        self.assertEqual(pre_commit_lib.parse_kinetic_output(''), {})


class TestParseRuntimeOutput(unittest.TestCase):
    """测试 mutant_watch 输出解析"""

    def test_parse_severity_line(self):
        """能从标准 severity 行提取"""
        output = '  HIGH: 3  MEDIUM: 2  LOW: 58'
        result = pre_commit_lib.parse_runtime_output(output)
        self.assertEqual(result, {'HIGH': 3, 'MEDIUM': 2, 'LOW': 58})

    def test_parse_multi_line(self):
        """能多行中提取正确行"""
        output = (
            'some noise\n'
            '  完成: 52 项\n'
            '  HIGH: 1  MEDIUM: 0  LOW: 5\n'
        )
        result = pre_commit_lib.parse_runtime_output(output)
        self.assertEqual(result, {'HIGH': 1, 'MEDIUM': 0, 'LOW': 5})

    def test_parse_no_match(self):
        """无匹配时返回全零"""
        self.assertEqual(
            pre_commit_lib.parse_runtime_output('nothing here'),
            {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        )

    def test_parse_strange_separator(self):
        """处理各种空白分隔风格"""
        output = 'HIGH:0 MEDIUM:1 LOW:2'
        result = pre_commit_lib.parse_runtime_output(output)
        self.assertEqual(result, {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2})


class TestParseKineticSummary(unittest.TestCase):
    """测试 kinetic summary 解析"""

    def test_empty_summary(self):
        self.assertEqual(
            pre_commit_lib.parse_kinetic_summary({}),
            {'HIGH': 0, 'MEDIUM': 0, 'LOW': 0}
        )

    def test_partial_severity(self):
        self.assertEqual(
            pre_commit_lib.parse_kinetic_summary({
                'by_severity': {'HIGH': 5}
            }),
            {'HIGH': 5, 'MEDIUM': 0, 'LOW': 0}
        )


class TestContractChanges(unittest.TestCase):
    """测试 API 契约对比逻辑"""

    def setUp(self):
        self.old = {
            '/api/chat': {'route': '/api/chat', 'keys': ['reply', 'action', 'timestamp']},
            '/api/wx-login': {'route': '/api/wx-login', 'keys': ['openid']},
        }
        self.new = {
            '/api/chat': {'route': '/api/chat', 'keys': ['reply', 'action', 'timestamp', 'debug']},
            '/api/wx-login': {'route': '/api/wx-login', 'keys': ['openid']},
            '/api/new': {'route': '/api/new', 'keys': ['status']},
        }

    def test_no_changes(self):
        """无变化时返回全零"""
        result = pre_commit_lib.detect_contract_changes(self.old, self.old)
        self.assertEqual(result['api_route_deleted'], 0)
        self.assertEqual(result['api_return_keys_changed'], 0)

    def test_detects_added_keys(self):
        """检测字段新增"""
        result = pre_commit_lib.detect_contract_changes(self.old, self.new)
        self.assertEqual(result['api_return_keys_changed'], 1)
        self.assertEqual(result['changed_routes'][0]['route'], '/api/chat')
        self.assertEqual(result['changed_routes'][0]['added'], ['debug'])

    def test_detects_deleted_route(self):
        """检测 route 删除"""
        deleted_old = {'/api/chat': {'keys': ['reply']}}
        result = pre_commit_lib.detect_contract_changes(deleted_old, {})
        self.assertEqual(result['api_route_deleted'], 1)
        self.assertEqual(result['deleted_routes'], ['/api/chat'])

    def test_detects_new_route(self):
        """检测 route 新增"""
        result = pre_commit_lib.detect_contract_changes({}, self.new)
        self.assertEqual(result['api_route_added'], 3)

    def test_both_empty(self):
        """两个空 baseline 返回全零"""
        result = pre_commit_lib.detect_contract_changes({}, {})
        self.assertEqual(result['api_route_deleted'], 0)
        self.assertEqual(result['api_return_keys_changed'], 0)


class TestShouldBlock(unittest.TestCase):
    """测试决策逻辑"""

    def test_clean_passes(self):
        blocked, msg = pre_commit_lib.should_block(0, 0)
        self.assertFalse(blocked)
        self.assertEqual(msg, 'clean')

    def test_high_blocks(self):
        blocked, msg = pre_commit_lib.should_block(1, 0)
        self.assertTrue(blocked)
        self.assertIn('HIGH', msg)

    def test_high_allowed(self):
        blocked, msg = pre_commit_lib.should_block(1, 0, allow_high=True)
        self.assertFalse(blocked)
        self.assertIn('allowed', msg)

    def test_medium_above_threshold_warns(self):
        blocked, msg = pre_commit_lib.should_block(0, 6)
        self.assertFalse(blocked)
        self.assertIn('threshold', msg)

    def test_medium_below_threshold_passes(self):
        blocked, msg = pre_commit_lib.should_block(0, 3)
        self.assertFalse(blocked)
        self.assertEqual(msg, 'clean')


if __name__ == '__main__':
    unittest.main()
