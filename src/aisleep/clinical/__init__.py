__version__ = "1.0.0"  # Or your actual version number
import os
import sys
print(sys.path)  # 检查路径是否包含项目根目录
from .clinical_trial import ClinicalTrial

__all__ = ['ClinicalTrial']


# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
