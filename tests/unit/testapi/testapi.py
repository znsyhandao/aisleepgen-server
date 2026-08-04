import requests

response = requests.post(
    "http://localhost:8000/predict",
    json={
        "audio": [0.1] * 3000,
        "text": "test"
    }
)
print("状态码:", response.status_code)
print("响应内容:", response.json())
