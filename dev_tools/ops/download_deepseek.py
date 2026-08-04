"""
download_deepseek.py — 下载 DeepSeek-V3 模型

从 hf-mirror.com 分片下载 safetensors 模型文件，
支持断点续传 + MD5 校验。注意文件很大 (~600GB总)。
用法: python dev_tools/ops/download_deepseek.py
"""
import os
import hashlib
import subprocess
import datetime

# 基础 URL，替换为实际的文件下载路径
base_url = "https://hf-mirror.com/deepseek-ai/DeepSeek-V3-0324/resolve/main/"
# 保存文件的目录
output_dir = "E:/DeepSeek-V3-0324/"

# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 文件的预期哈希值（MD5 或 SHA256）
expected_hashes = {
    "model-00145-of-000163.safetensors": "df5bc422ecf3085964c1235f10690c2b",  # 已替换为实际的 MD5 值
    #"model-00146-of-000163.safetensors": "e99a18c428cb38d5f260853678922e03",  # 替换为实际的 MD5 值
}

# 日志函数
def log(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# 计算文件的哈希值（MD5 或 SHA256）
def calculate_hash(file_path, hash_type="md5"):
    hash_func = hashlib.md5() if hash_type == "md5" else hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()

# 验证文件完整性
def verify_file(file_path, expected_hash, hash_type="md5"):
    if not os.path.exists(file_path):
        return False
    calculated_hash = calculate_hash(file_path, hash_type)
    return calculated_hash == expected_hash

# 使用 aria2c 下载单个文件，增加最大重试次数
def download_with_aria2(i, max_retries=3):
    file_name = f"model-{i:05d}-of-000163.safetensors"
    file_url = f"{base_url}{file_name}?download=true"
    output_path = os.path.join(output_dir, file_name)

    retries = 0
    while retries < max_retries:
        if os.path.exists(output_path):
            log(f"{file_name} already exists, skipping...")
            return True

        try:
            log(f"Downloading {file_name} with aria2c (Attempt {retries + 1}/{max_retries})...")
            subprocess.run(
                [
                    "aria2c",
                    "-x", "16",
                    "-s", "16",
                    "-d", output_dir,
                    "-o", file_name,
                    file_url,
                ],
                check=True,
            )
            log(f"Downloaded {file_name} successfully!")

            if file_name in expected_hashes:
                expected_hash = expected_hashes[file_name]
                if verify_file(output_path, expected_hash):
                    log(f"{file_name} passed integrity check.")
                    return True
                else:
                    log(f"{file_name} failed integrity check. Retrying...")
                    os.remove(output_path)
            else:
                return True

        except subprocess.CalledProcessError as e:
            log(f"Failed to download {file_name} with aria2c: {e}")
            log(f"Command: {e.cmd}")
            log(f"Return code: {e.returncode}")

        retries += 1

    log(f"Failed to download {file_name} after {max_retries} attempts. Skipping...")
    return False

# 验证所有文件并重新下载损坏或缺失的文件
def verify_all_files_and_redownload():
    failed_files = []
    for file_name, expected_hash in expected_hashes.items():
        file_path = os.path.join(output_dir, file_name)
        if not os.path.exists(file_path):
            log(f"File missing: {file_name}. Redownloading...")
            if not download_with_aria2(int(file_name.split("-")[1])):
                failed_files.append(file_name)
            continue

        if not verify_file(file_path, expected_hash):
            log(f"{file_name} failed integrity check. Redownloading...")
            os.remove(file_path)
            if not download_with_aria2(int(file_name.split("-")[1])):
                failed_files.append(file_name)
        else:
            log(f"{file_name} passed integrity check.")

    if failed_files:
        log("The following files failed to download after multiple attempts:")
        for file in failed_files:
            log(f" - {file}")
    else:
        log("All files are now complete and valid!")

if __name__ == "__main__":
    verify_all_files_and_redownload()