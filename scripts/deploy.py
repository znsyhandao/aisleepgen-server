import shutil
from datetime import datetime

def setup_prod_environment(config):
    """设置生产环境目录结构"""
    required_dirs = [
        config['raw_data_dir'],
        config['processed_dir'],
        config['log_dir'],
        config['backup_dir']
    ]
    
    for dir_path in required_dirs:
        os.makedirs(dir_path, exist_ok=True)
        print(f"已创建目录: {dir_path}")

def backup_existing_data(config):
    """备份现有数据"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{config['backup_dir']}/backup_{timestamp}"
    shutil.copytree(config['processed_dir'], backup_path)
    print(f"数据已备份至: {backup_path}")
