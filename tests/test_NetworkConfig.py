import unittest
from unittest.mock import patch, MagicMock
import socket
from aisleep.config import Settings, check_dns_resolution

class TestNetworkConfig(unittest.TestCase):
    
    def setUp(self):
        self.config = Settings()
    
    def test_initial_dns_servers(self):
        """测试默认DNS服务器配置"""
        print("\n测试默认DNS服务器配置...", end="")
        self.assertEqual(
            self.config.DNS_SERVERS,
            ["114.114.114.114", "8.8.8.8"]
        )
        print("[OK] 通过")
    
    def test_initial_dns_timeout(self):
        """测试默认DNS超时设置"""
        print("\n测试默认DNS超时设置...", end="")
        self.assertEqual(self.config.DNS_TIMEOUT, 5)
        print("[OK] 通过")
    
    @patch('socket.gethostbyname')
    def test_dns_resolution_success(self, mock_gethostbyname):
        """测试DNS解析成功"""
        print("\n测试DNS解析成功...", end="")
        mock_gethostbyname.return_value = "192.168.1.1"
        result = check_dns_resolution()
        self.assertTrue(result)
        print("[OK] 通过")
    
    @patch('socket.gethostbyname')
    def test_dns_resolution_fallback(self, mock_gethostbyname):
        """测试DNS解析失败回退"""
        print("\n测试DNS解析失败回退...", end="")
        mock_gethostbyname.side_effect = socket.gaierror
        with patch('socket.socket') as mock_socket:
            mock_socket.return_value.connect.return_value = None
            result = check_dns_resolution()
            self.assertTrue(result)
        print("[OK] 通过")
    
    @patch('socket.gethostbyname')
    def test_dns_resolution_failure(self, mock_gethostbyname):
        """测试DNS解析完全失败"""
        print("\n测试DNS解析完全失败...", end="")
        mock_gethostbyname.side_effect = socket.gaierror
        with patch('socket.socket') as mock_socket:
            mock_socket.return_value.connect.side_effect = Exception
            result = check_dns_resolution()
            self.assertFalse(result)
        print("[OK] 通过")

if __name__ == '__main__':
    print("\n=== 开始运行DNS配置测试 ===")
    unittest.main(verbosity=0)
    print("\n=== 测试完成 ===")
