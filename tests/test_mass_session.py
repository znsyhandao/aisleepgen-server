import unittest
from unittest.mock import patch
from aisleep.meditation import MassMeditationEngine
import redis  # 新增导入

class TestMassSessionSharding(unittest.TestCase):
    @patch('redis.Redis')
    def test_shard_rebalancing(self, mock_redis):
        """测试分片动态再平衡"""
        engine = MassMeditationEngine()
        
        # 模拟节点负载不均衡
        mock_redis.return_value.hgetall.return_value = {
            '0': '9500',  # 过载分片
            '1': '3200',
            '2': '2800'
        }
        
        # 触发再平衡
        engine.rebalance_shards()
        
        # 验证分片调整
        self.assertIn('rebalanced', engine.session_state)
        self.assertLess(engine.session_state['shards']['0'], 5000)


    def test_auto_rebalance(self, mock_redis):
        """测试自动分片再平衡"""
        # 模拟3个分片(其中1个过载)
        mock_redis.return_value.hgetall.return_value = {
            '0': '6000',  # 过载分片
            '1': '3000',
            '2': '2000'
        }
        
        engine = MassMeditationEngine()
        engine._auto_rebalance()
        
        # 验证是否触发了迁移
        self.assertGreaterEqual(
            mock_redis.return_value.hincrby.call_count,
            2  # 至少调用2次hincrby(源分片减，目标分片加)
        )

