import pytest
from settings import settings

def test_obs_connection():
    """华为云OBS连接测试"""
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkobs.obs.client import ObsClient
    from huaweicloudsdkcore.exceptions import exceptions

    try:
        credentials = BasicCredentials(
            ak=settings.obs_access_key,
            sk=settings.obs_secret_key
        )
        obs_client = ObsClient(
            endpoint=settings.obs_endpoint,
            credentials=credentials
        )
        buckets = obs_client.listBuckets().body.buckets
        assert settings.obs_bucket in [b.name for b in buckets]
    except exceptions.ClientRequestException as e:
        pytest.fail(f"OBS连接失败: {e.error_msg}")

# 新增SWR连接测试
def test_swr_connection():
    """华为云SWR连接测试"""
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkswr.v2 import SwrClient
    
    credentials = BasicCredentials(
        ak=settings.obs_access_key,
        sk=settings.obs_secret_key
    )
    swr_client = SwrClient(
        endpoint=f"swr-api.{settings.obs_endpoint.split('.')[1]}.myhuaweicloud.com",
        credentials=credentials
    )
    assert swr_client.list_namespaces() is not None