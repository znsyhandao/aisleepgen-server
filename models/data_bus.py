# data_bus.py
from typing import Dict, List, Callable, Any
import threading
import queue

class DataBus:
    """数据总线，基于发布-订阅模式"""
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = {}
        self.queue = queue.Queue(maxsize=1000)
        self.lock = threading.RLock()
        self.running = False
        self.thread = None
        
    def subscribe(self, topic: str, callback: Callable):
        """订阅主题"""
        with self.lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(callback)
            
    def unsubscribe(self, topic: str, callback: Callable):
        """取消订阅"""
        with self.lock:
            if topic in self.subscribers:
                try:
                    self.subscribers[topic].remove(callback)
                except ValueError:
                    pass
                    
    def publish(self, topic: str, data: Any):
        """发布数据"""
        self.queue.put((topic, data))
        
    def start(self):
        """启动数据总线"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._process_queue, daemon=True)
            self.thread.start()
            
    def stop(self):
        """停止数据总线"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
            
    def _process_queue(self):
        """处理队列中的数据"""
        while self.running:
            try:
                topic, data = self.queue.get(timeout=0.1)
                self._notify_subscribers(topic, data)
                self.queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"处理数据时出错: {e}")
                
    def _notify_subscribers(self, topic: str, data: Any):
        """通知订阅者"""
        with self.lock:
            if topic in self.subscribers:
                for callback in self.subscribers[topic]:
                    try:
                        callback(data)
                    except Exception as e:
                        print(f"回调执行失败: {e}")
