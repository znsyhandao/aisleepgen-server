from huggingface_hub import hf_hub_download

import os
import sys
import shutil
import time
import requests
from requests.exceptions import RequestException



# Force using mirror endpoint
# ... existing imports ...

# Only use hf-mirror.com since it's the only working endpoint
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

def check_connection():
    try:
        # Only check hf-mirror.com since other sites may be blocked
        response = requests.get('https://hf-mirror.com', timeout=10)
        return response.status_code == 200
    except Exception:
        return False

def download_with_retry(repo_id, filename, local_dir, max_retries=3):
    for attempt in range(max_retries):
        try:
            print(f"Download attempt {attempt + 1} for {filename}")
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                local_dir=local_dir,
                force_download=True
            )
            print(f"Successfully downloaded {filename}")
            return True
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)  # Longer wait between retries
                print(f"Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
    return False

# ... rest of the existing download_model function ...


def download_model():
    print("Starting model download...")
    try:
        if not check_connection():
            raise Exception("No internet connection detected")
            
        # Clean up existing directory
        model_dir = 'E:/models/DeepSeek-V3-0324'
        if os.path.exists(model_dir):
            shutil.rmtree(model_dir)
            
        # Test connection with a small file
        print("Testing connection with config.json...")
        if not download_with_retry('deepseek-ai/DeepSeek-V3-0324', 'config.json', model_dir):
            raise Exception("Failed to download config.json after retries")
        print("Connection test successful!")
        
        # Download model files sequentially
        print("Starting model download...")
        for i in range(1, 164):
            filename = f"model-{str(i).zfill(5)}-of-00163.safetensors"
            print(f"Downloading {filename}...")
            if not download_with_retry('deepseek-ai/DeepSeek-V3-0324', filename, model_dir):
                print(f"Failed to download {filename} after retries")
                continue
                
        print("Download completed!")
    except Exception as e:
        print(f"Download failed: {str(e)}")
        print("Troubleshooting steps:")
        print("1. Try different mirrors:")
        print("   set HF_ENDPOINT=https://hf-mirror.com")
        print("2. Enable hf_transfer:")
        print("   set HF_HUB_ENABLE_HF_TRANSFER=1")
        print("3. Check firewall/proxy settings")
        sys.exit(1)

if __name__ == "__main__":
    download_model()
