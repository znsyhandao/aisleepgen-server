import oss2
from pathlib import Path
from ..config import settings  # Relative import
from tqdm import tqdm
import os
from aisleep.config import settings  # Use absolute import


def upload_model_to_oss(model_path: str):
    """上传模型文件或目录到OSS"""
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    
    # 确保endpoint格式正确
    endpoint = settings.OSS_ENDPOINT
    if settings.OSS_BUCKET_NAME in endpoint:
        endpoint = endpoint.replace(f"{settings.OSS_BUCKET_NAME}.", "")
    
    bucket = oss2.Bucket(auth, settings.OSS_ENDPOINT, settings.OSS_BUCKET_NAME)
    
    if not Path(model_path).exists():
        raise FileNotFoundError(f"文件不存在: {model_path}")

    # 如果是zip文件直接上传
    if model_path.endswith('.zip'):
        file_size = os.path.getsize(model_path)
        with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"上传 {Path(model_path).name}") as pbar:
            def callback(consumed_bytes, total_bytes):  # 修改为接收两个参数
                pbar.update(consumed_bytes - pbar.n)
            
            bucket.put_object_from_file(
                f"{settings.OSS_MODEL_PREFIX}{Path(model_path).name}",
                model_path,
                progress_callback=callback
            )
    else:
        # 如果是目录则验证并上传所有文件
        model_dir = Path(model_path)
        required_files = ["config.json", "model.safetensors", "tokenizer.json"]
        
        # 验证模型文件完整性
        for file in required_files:
            if not (model_dir / file).exists():
                raise FileNotFoundError(f"模型文件缺失: {file}")

        # 上传所有文件
        for file_path in tqdm(list(model_dir.glob("*")), desc="上传模型文件"):
            if file_path.is_file():
                file_size = os.path.getsize(file_path)
                if file_size > 5 * 1024 * 1024 * 1024:  # 判断文件大小是否超过 5GB


                # 分片上传
                    upload_id = bucket.init_multipart_upload(f"{settings.OSS_MODEL_PREFIX}{file_path.name}").upload_id
                    parts = []
                    part_size = oss2.determine_part_size(file_size, preferred_size=100 * 1024 * 1024)  # 每片 100MB
                    with open(file_path, 'rb') as fileobj:
                        part_number = 1
                        offset = 0
                        while offset < file_size:
                            num_to_upload = min(part_size, file_size - offset)
                            result = bucket.upload_part(
                                f"{settings.OSS_MODEL_PREFIX}{file_path.name}",
                                upload_id,
                                part_number,
                                oss2.SizedFileAdapter(fileobj, num_to_upload)
                            )
                            parts.append(oss2.models.PartInfo(part_number, result.etag))
                            offset += num_to_upload
                            part_number += 1
                    # 完成分片上传
                    bucket.complete_multipart_upload(f"{settings.OSS_MODEL_PREFIX}{file_path.name}", upload_id, parts)
            else:
                # 普通上传
                bucket.put_object_from_file(
                    f"{settings.OSS_MODEL_PREFIX}{file_path.name}",
                    str(file_path)
                )

    print(f"✅ 模型已成功上传至OSS: {settings.OSS_BUCKET_NAME}/{settings.OSS_MODEL_PREFIX}")

