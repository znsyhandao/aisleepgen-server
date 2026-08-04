import pytest
from src.aisleep.utils import RedisLock

class TestRedisLock:
    def test_lock_acquire_release(self, mock_redis):
        lock = RedisLock(mock_redis)
        assert lock.acquire("test_lock") == True
        assert lock.release("test_lock") == True

    def test_context_manager(self, mock_redis):
        with RedisLock(mock_redis) as lock:
            assert lock._acquired == True
