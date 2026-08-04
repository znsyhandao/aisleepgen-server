import redis
import time
import uuid
from typing import Optional
import os


class RedisLock:
    def __init__(self, redis_client, lock_timeout=30):

        
        # 多进程测试支持
        worker_id = os.environ.get('PYTEST_XDIST_WORKER', 'master')
        self.lock_prefix = f"aisleep_{worker_id}_"
        
        self.redis_client = redis_client
        self.lock_timeout = lock_timeout
        self._lock_name = None
        self._lock_token = str(uuid.uuid4())
        self._acquired = False
        self._default_lock_name = f"{self.lock_prefix}default_lock"  # 使用前缀
        
    # ... 其他方法保持不变 ...


    def acquire(self, lock_name: str, timeout: Optional[int] = None) -> bool:
        """优化后的获取锁方法"""
        if self._acquired and self._lock_name == lock_name:
            return True
            
        if timeout is None:
            acquired = bool(self.redis_client.set(
                lock_name, self._lock_token,  # 使用唯一token
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
                time.sleep(0.05)  # 减少sleep时间
        
        if acquired:
            self._lock_name = lock_name
            self._acquired = True
        return acquired

    def release(self, lock_name: str) -> bool:
        """优化后的释放锁方法"""
        if not self._acquired or self._lock_name != lock_name:
            return False
            
        # 使用Lua脚本确保只有锁的持有者能释放
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
        if not self.acquire(self._default_lock_name):
            raise RuntimeError(f"无法获取锁: {self._default_lock_name}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理协议"""
        self.release(self._default_lock_name)

    def renew(self, additional_time: int) -> bool:
        """延长锁持有时间"""
        if not self._acquired or not self._lock_name:
            return False
            
        # 使用Lua脚本确保只有锁的持有者能续期
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        return bool(self.redis_client.eval(
            lua_script, 1, self._lock_name, self._lock_token, additional_time
        ))
