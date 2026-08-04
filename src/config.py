import os
from pydantic import BaseSettings

class Settings(BaseSettings):
    # 支付配置
    WECHAT_API_KEY: str = os.getenv("WECHAT_API_KEY")
    ALIPAY_APP_ID: str = os.getenv("ALIPAY_APP_ID")
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "payment.log"

settings = Settings()
