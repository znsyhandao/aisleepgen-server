# 生产环境配置文件
PROD_CONFIG = {
    "raw_data_dir": "/data/prod/raw",
    "processed_dir": "/data/prod/processed",
    "max_seq_length": 512,
    "batch_size": 128,  # 增大批处理大小
    "log_dir": "/logs/aisleep",
    "backup_dir": "/backup/aisleep"
}

# 数据库配置
DATABASE = {
    "host": "prod-db.aisleep.com",
    "port": 5432,
    "user": "aisleep_prod",
    "password": "secure_password_123",
    "dbname": "aisleep_production"
}
