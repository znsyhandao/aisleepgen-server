import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aisleep.config import check_dns_resolution
# 测试DNS解析
print("测试DNS解析功能...")
if check_dns_resolution():
    print("[OK] DNS解析测试通过")
else:
    print("[FAIL] DNS解析测试失败")
