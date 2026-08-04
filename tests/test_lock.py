import pytest
import redis
from aisleep.utils.lock import RedisLock, DistributedLockManager

@pytest.fixture
def redis_client():
    return redis.StrictRedis()

def test_lock_acquire_release():
    lock = RedisLock(redis_client())
    assert lock.acquire('test_lock')
    assert lock.release('test_lock')

def test_lock_timeout():
    lock = RedisLock(redis_client(), lock_timeout=1)
    assert lock.acquire('test_lock')
    time.sleep(2)  # 等待锁超时
    assert not lock.is_locked('test_lock')

def test_lock_manager():
    manager = DistributedLockManager(redis_client())
    lock = manager.create_lock('session_lock')
    assert lock.acquire()
    assert manager.get_lock('session_lock') is not None
