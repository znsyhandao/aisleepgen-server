import socket
import urllib.request
from urllib.error import URLError

def test_connection():
    try:
        # TCP连接测试
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3)
        s.connect(("8.8.8.8", 53))
        print("TCP连接成功")
        s.close()  # 显式关闭连接
        
        # HTTP请求测试（增加重试和超时处理）
        for _ in range(3):  # 重试3次
            try:
                req = urllib.request.Request(
                    "http://www.ubuntu.com",
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=5) as f:
                    if f.status in (200, 301, 302):
                        print(f"HTTP状态码: {f.status}")
                        return True
            except URLError as e:
                print(f"尝试失败: {e}")
                continue
        return False
    except Exception as e:
        print(f"连接失败: {e}")
        return False

test_connection()

