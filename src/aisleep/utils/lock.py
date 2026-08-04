import redis
import time
import uuid
from typing import Optional
from .redis_lock import RedisLock
from .distributed_lock import DistributedLockManager

__all__ = ['RedisLock', 'DistributedLockManager']


class DistributedLockManager:
    """基于Redis的分布式锁管理器"""
    
    def __init__(self, redis_client, default_timeout=30):
        self.redis = redis_client
        self.default_timeout = default_timeout
        self.locks = {}  # 存储管理的所有锁
        
    def create_lock(self, name: str, timeout: Optional[int] = None) -> 'RedisLock':
        """创建并返回一个新的分布式锁"""
        timeout = timeout or self.default_timeout
        lock = RedisLock(self.redis, timeout)
        self.locks[name] = lock
        return lock
        
    def get_lock(self, name: str) -> Optional['RedisLock']:
        """获取已存在的锁"""
        return self.locks.get(name)
        
    def release_all(self):
        """释放所有管理的锁"""
        for lock in self.locks.values():
            lock.release()
        self.locks.clear()
