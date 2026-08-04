"""
信号处理工具库
包含需要复杂数学运算的信号处理方法
"""
import numpy as np
from scipy import signal

def calc_sample_entropy(data: np.ndarray) -> float:
    """计算样本熵(可被多个类复用)"""
    # ... 实现内容不变 ...

def calc_hurst_exponent(data: np.ndarray) -> float:
    """计算Hurst指数"""
    # ... 实现内容不变 ...

def synchronize_signals(*signals, method='dtw') -> List[np.ndarray]:
    """多信号时间对齐"""
    # ... 实现动态时间规整等算法 ...
