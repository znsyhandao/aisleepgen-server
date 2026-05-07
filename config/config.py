from pydantic import BaseSettings, Field, validator

class Settings(BaseSettings):
    OSS_ACCESS_KEY_ID: str
    OSS_ACCESS_KEY_SECRET: str
    OSS_ENDPOINT: str
    OSS_BUCKET_NAME: str = Field(..., alias="OSS_BUCKET_NAME")
    OSS_MODEL_PREFIX: str = "models/"
    secret_key: str
    
    @validator('OSS_ENDPOINT')
    def validate_endpoint(cls, v, values):
        """验证并标准化OSS_ENDPOINT格式"""
        bucket_name = values.get('OSS_BUCKET_NAME', '')
        if bucket_name:
            v = v.replace(f"{bucket_name}.", "")
        if not v.startswith(('http://', 'https://')):
            v = f'https://{v}'
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = 'ignore'
        env_nested_delimiter = '__'
