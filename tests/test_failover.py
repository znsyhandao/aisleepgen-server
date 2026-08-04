import unittest
import pytest
from unittest.mock import patch



class TestNodeFailure:
    @patch('src.aisleep.meditation.ClusterManager')
    def test_node_failover(self, mock_cluster):
        """测试节点故障转移"""
        # 模拟3节点集群
        mock_cluster.return_value.get_nodes.return_value = ['node1', 'node2', 'node3']
        
        # 触发节点故障
        engine = MassMeditationEngine()
        engine.handle_node_failure('node2')
        
        # 验证会话迁移
        assert 'node2' not in engine.active_nodes
        assert len(engine.session_redistribution) == 2
