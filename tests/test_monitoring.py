import unittest
from unittest.mock import patch, MagicMock
from aisleep.monitoring import PerformanceMonitor, ShardMonitor, AlertManager

class TestPerformanceMonitor(unittest.TestCase):
    @patch('redis.Redis')
    def setUp(self, mock_redis):
        self.mock_redis = mock_redis.return_value
        self.monitor = PerformanceMonitor()
        
    def test_track_metrics(self):
        # Setup mock returns
        self.mock_redis.info.return_value = {'instantaneous_ops_per_sec': 1000}
        self.mock_redis.execute_command.return_value = {'avg_cluster_latency': '0.05'}
        self.mock_redis.hgetall.return_value = {'shard1': '500', 'shard2': '520'}
        
        metrics = self.monitor.track_critical_metrics()
        self.assertEqual(metrics['throughput'], 1000)
        self.assertAlmostEqual(metrics['latency'], 50)  # 0.05s = 50ms
