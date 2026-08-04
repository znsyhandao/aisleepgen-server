import requests
import numpy as np
import sys
import json
import traceback
import time
import base64
import pytest
from fastapi.testclient import TestClient
from aisleep.api.main import app
import logging

# 配置详细日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

client = TestClient(app)

@pytest.mark.audio
def test_predict_endpoint():
    test_data = {
        "audio": [0.5] * 3000,
        "text": "example text"
    }
    
    response = client.post("/api/v1/predict", json=test_data)
    assert response.status_code == 200
    assert "prediction" in response.json()

@pytest.mark.audio
def test_empty_input():
    """测试空输入的情况"""
    response = client.post("/api/v1/predict", json={"audio": [], "text": ""})
    assert response.status_code == 400  # 假设服务端会返回400错误

@pytest.mark.audio
def test_invalid_input():
    """测试无效输入的情况"""
    response = client.post("/api/v1/predict", json={"invalid": "data"})
    assert response.status_code == 422  # FastAPI默认会返回422验证错误

def test_main_endpoint():
    """测试主端点是否可用"""
    response = client.get("/")
    assert response.status_code == 200

def main():
    url = "http://localhost:8000/predict"
    
    # 修正数据格式与测试用例一致
    data = {
        "audio": [0.5] * 3000,
        "text": "example text"
    }

    try:
        response = requests.post(url, json=data)
        print("\n=== 响应结果 ===")
        print(json.dumps(response.json(), indent=2))
        print(f"DEBUG: Response headers: {dict(response.headers)}")
        print(f"DEBUG: Response text: {response.text}")
    except Exception as e:
        logger.error(f"测试失败: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    main()
