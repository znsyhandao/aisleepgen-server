import logging
logger = logging.getLogger(__name__)
import pytest

# 如果不需要redis，可以删除conftest.py中的redis相关代码
# 如果需要redis，确保安装后重试


def test_huawei_credentials(basic_credentials):
    try:
        assert all([
            basic_credentials.ak,
            basic_credentials.sk, 
            basic_credentials.project_id
        ]), "华为云凭证不完整"
        logger.info("华为云凭证验证通过")
    except Exception as e:
        logger.error(f"验证失败: {str(e)}")
        raise