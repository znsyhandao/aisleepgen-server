import psutil
import time
from functools import wraps
from typing import Dict

class PerformanceMonitor:
    def __init__(self):
        self.history = []
        self.max_history = 1000

    def track(self, metric_name: str):
        """性能监控装饰器工厂"""
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 资源监控
                start_cpu = psutil.cpu_percent()
                start_mem = psutil.virtual_memory().used
                start_time = time.time()
                
                try:
                    result = await func(*args, **kwargs)
                    status = 'success'
                except Exception as e:
                    status = 'failed'
                    raise e
                finally:
                    # 记录指标
                    metrics = {
                        'timestamp': time.time(),
                        'metric': metric_name,
                        'latency': time.time() - start_time,
                        'cpu_delta': psutil.cpu_percent() - start_cpu,
                        'mem_delta': (psutil.virtual_memory().used - start_mem) / 1024 / 1024,  # MB
                        'status': status
                    }
                    self._store_metrics(metrics)
                
                return result
            return wrapper
        return decorator

    def _store_metrics(self, metrics: Dict):
        """存储指标数据"""
        self.history.append(metrics)
        if len(self.history) > self.max_history:
            self.history.pop(0)
