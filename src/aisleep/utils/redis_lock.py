import redis
import uuid
import time
import os
from typing import Optional

class RedisLock:
    def __init__(self, redis_client, lock_timeout=30):
        self.redis_client = redis_client
        self.lock_timeout = lock_timeout
        self._lock_name = None
        self._lock_token = str(uuid.uuid4())
        self._acquired = False
    
    def acquire(self, lock_name: str, timeout: Optional[int] = None) -> bool:
        """获取分布式锁"""
        if self._acquired and self._lock_name == lock_name:
            return True
            
        if timeout is None:
            acquired = bool(self.redis_client.set(
                lock_name, self._lock_token,
                nx=True,
                ex=self.lock_timeout
            ))
        else:
            pipe = self.redis_client.pipeline()
            end_time = time.time() + timeout
            while time.time() < end_time:
                pipe.set(lock_name, self._lock_token, nx=True, ex=self.lock_timeout)
                if pipe.execute()[0]:
                    acquired = True
                    break
                time.sleep(0.1)
        
        if acquired:
            self._lock_name = lock_name
            self._acquired = True
        return acquired

    def release(self, lock_name: str) -> bool:
        """释放分布式锁"""
        if not self._acquired or self._lock_name != lock_name:
            return False
            
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        released = bool(self.redis_client.eval(
            lua_script, 1, lock_name, self._lock_token
        ))
        
        if released:
            self._acquired = False
            self._lock_name = None
        return released

    def __enter__(self):
        """支持上下文管理协议"""
        if not self.acquire("default_lock"):
            raise RuntimeError("无法获取默认锁")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理协议"""
        self.release("default_lock")

