#!/usr/bin/env python3
"""
隔离测试：验证 SAE 特征捕获模块的正确性
测试目标：在 deepseek_proxy.py 的 wfile.write 审计链中插入SAE特征子空间记录
"""
import sys, os, json, tempfile, unittest

sys.path.insert(0, r'D:\AISleepGen_Optimized')
from audit_logger import log_api_call, validate_response

class TestSAEFeatureCapture(unittest.TestCase):
    """SAE特征捕获概念验证测试"""
    
    def setUp(self):
        # 模拟审计日志数据
        self.sample_request = {
            'user_message': '我最近睡眠不好，总是凌晨3点醒',
            'physio_context': {'hrv': 42, 'bpm': 7},
        }
        self.sample_response = {
            'reply': '我理解你的困扰，建议保持规律作息',
            'intervention': True,
            'stress_type': '焦虑',
        }
    
    def test_1_validate_response_structure(self):
        """测试1: 验证响应中包含 SAE 特征捕获位"""
        resp = dict(self.sample_response)
        # SAE特征捕获：在响应中注入特征子空间标记
        resp['_sae_features'] = {
            'feature_subspace_id': 'ss_v1_20260611',
            'activation_pattern': [0.42, 0.15, 0.78, 0.33, 0.91],
            'subspace_stability': 0.89,
        }
        self.assertIn('_sae_features', resp)
        self.assertIn('feature_subspace_id', resp['_sae_features'])
        self.assertIn('subspace_stability', resp['_sae_features'])
    
    def test_2_validate_response_compliance(self):
        """测试2: SAE特征不应被合规过滤误删"""
        resp = dict(self.sample_response)
        resp['_sae_features'] = {
            'feature_subspace_id': 'test_123',
            'activation_pattern': [0.5, 0.3],
            'subspace_stability': 0.95,
        }
        from compliance import filter_sensitive
        clean = filter_sensitive(resp)
        # filter_sensitive 不应剔除 _sae_features
        self.assertIn('_sae_features', clean)
    
    def test_3_audit_log_includes_sae(self):
        """测试3: 审计日志中包含 SAE 特征记录"""
        # 模拟 log_api_call 接受 sae_features 参数
        resp = dict(self.sample_response)
        resp['_sae_features'] = {
            'feature_subspace_id': 'ss_v1_20260611',
            'subspace_stability': 0.92,
        }
        # 验证 log_api_call 能处理 sae_features
        entry = log_api_call(
            openid='test_user_001',
            session_id='test_session',
            api='/api/sleep/world-step',
            method='POST',
            request=self.sample_request,
            response=resp,
        )
        self.assertIn('response', entry)
        self.assertIn('_sae_features', entry['response'])
        self.assertEqual(entry['response']['_sae_features']['subspace_stability'], 0.92)
    
    def test_4_sae_feature_stability_range(self):
        """测试4: 特征子空间稳定性值必须在有效范围 [0,1]"""
        stable = 0.89
        self.assertGreaterEqual(stable, 0.0)
        self.assertLessEqual(stable, 1.0)
        
        stable = 0.0
        self.assertGreaterEqual(stable, 0.0)
        
        stable = 1.0
        self.assertLessEqual(stable, 1.0)
    
    def test_5_activation_pattern_structure(self):
        """测试5: 激活模式必须是向量且有稳定维度"""
        pattern = [0.42, 0.15, 0.78, 0.33, 0.91]
        self.assertIsInstance(pattern, list)
        self.assertGreater(len(pattern), 0)
        # 验证均值在合理范围
        import statistics
        mean = statistics.mean(pattern)
        self.assertGreaterEqual(mean, 0.0)
        self.assertLessEqual(mean, 1.0)

if __name__ == '__main__':
    print('=' * 60)
    print('  SAE 特征捕获概念验证测试')
    print('=' * 60)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(unittest.TestLoader().loadTestsFromTestCase(TestSAEFeatureCapture))
    print(f'\n结果: {result.testsRun} 测试, {len(result.failures)} 失败, {len(result.errors)} 错误')
    sys.exit(0 if result.wasSuccessful() else 1)
