from obs import ObsClient
from ..config import settings

# 创建全局OBS客户端实例
obs_client = ObsClient(
    access_key_id=settings.OBS_ACCESS_KEY,
    secret_access_key=settings.OBS_SECRET_KEY,
    server=settings.OBS_ENDPOINT
)
