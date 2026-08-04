from locust import HttpUser, task, between, events
import random
import numpy as np
import json

@events.request.add_listener
def log_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    if exception:
        print(f"❌ 请求失败 | 类型: {request_type} | 错误: {exception}")
    else:
        print(f"✅ 请求成功 | 耗时: {response_time}ms | 长度: {response_length}字节")

class SleepStageUser(HttpUser):
    wait_time = between(0.5, 2.5)
    
    @task(3)
    def test_valid_request(self):
        """合法请求测试（3000个0.1）"""
        valid_data = [0.1] * 2999 + [0.1]
        self._send_request(valid_data, "合法数据")
    
    @task(1)
    def test_invalid_request(self):
        """非法请求测试（包含超限值666.0）"""
        invalid_data = [0.1] * 2999 + [666.0]
        self._send_request(invalid_data, "非法数据")

    def _send_request(self, data, case_type):
     with self.client.post(
        "/predict",
        json=data,
        headers={"Content-Type": "application/json"},
        name=f"Predict-{case_type}",
        catch_response=True
    ) as response:
        #▼▼▼ 增强响应验证逻辑 ▼▼▼
        try:
            response_data = response.json()
        except JSONDecodeError:
            response.failure("响应不是有效JSON")
            return
            
        if response.status_code == 422:
            if "EEG信号异常" in str(response_data.get("detail", "")):
                response.success()
            else:
                response.failure("非预期的422错误")
        elif 200 <= response.status_code < 300:
            required_keys = {"prediction", "prediction_label", "probabilities"}
            if not required_keys.issubset(response_data.keys()):
                missing = required_keys - response_data.keys()
                response.failure(f"缺少关键字段: {missing}")

if __name__ == "__main__":
    import os
    os.system("locust -f locustfile.py")
