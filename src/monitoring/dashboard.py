from prometheus_client import start_http_server, Counter

REQUESTS = Counter('api_requests', 'Total API requests')
STRESS_LEVEL = Counter('stress_predicted', 'Stress predictions')

def start_monitoring(port=8001):
    """启动监控指标服务"""
    start_http_server(port)
