from .obs_client import obs_client  # 使用集中管理的客户端
from pathlib import Path
from ..config import settings
from tqdm import tqdm
import os

def upload_model_to_obs(model_path: str):
    """上传模型文件或目录到华为云OBS"""
    if not Path(model_path).exists():
        raise FileNotFoundError(f"文件不存在: {model_path}")

    # 使用全局obs_client替代局部创建
    if model_path.endswith('.zip'):
        file_size = os.path.getsize(model_path)
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"上传 {Path(model_path).name}") as pbar:
            resp = obs_client.putFile(
                settings.OBS_BUCKET_NAME,
                f"{settings.OBS_MODEL_PREFIX}{Path(model_path).name}",
                file_path=model_path
            )
            if resp.status >= 300:
                raise RuntimeError(f"上传失败: {resp.errorCode}")
    
    print(f"✅ 上传成功至OBS: {settings.OBS_BUCKET_NAME}/{settings.OBS_MODEL_PREFIX}")
