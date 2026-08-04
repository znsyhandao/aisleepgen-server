import mne
import numpy as np
from pathlib import Path

def edf_to_numpy(edf_path, output_dir, resample=100):
    """将EDF文件转换为标准格式的numpy数组"""
    raw = mne.io.read_raw_edf(edf_path, preload=True)
    
    # 预处理流程
    raw.filter(0.5, 30., fir_design='firwin')  # 带通滤波
    raw.resample(resample)  # 降采样
    
    # 保存为numpy格式
    output_path = Path(output_dir) / (Path(edf_path).stem + ".npy")
    np.save(output_path, raw.get_data())
    
    return output_path