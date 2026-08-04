import pytest
import redis
from unittest.mock import patch, MagicMock
from src.aisleep.meditation import MeditationGuide
from fakeredis import FakeRedis
import uuid

@pytest.fixture(autouse=True)
def mock_redis():
    """增强版Redis mock，支持多进程锁测试"""
    lock_stores = {}  # 按进程ID隔离锁状态
    
    def get_lock_store():
        import os
        pid = os.getpid()
        if pid not in lock_stores:
            lock_stores[pid] = {}
        return lock_stores[pid]
    
    with patch('redis.Redis') as mock_redis:
        mock_client = MagicMock()
        
        # 模拟set操作
        def mock_set(key, value, nx=False, ex=None):
            store = get_lock_store()
            if nx and key in store:
                return False
            store[key] = value
            return True
            
        # 模拟get操作
        def mock_get(key):
            return get_lock_store().get(key)
            
        # 模拟delete操作
        def mock_delete(key):
            store = get_lock_store()
            if key in store:
                del store[key]
                return 1
            return 0
            
        # 模拟eval操作
        def mock_eval(script, numkeys, *args):
            store = get_lock_store()
            if "del" in script:
                key, token = args[0], args[1]
                if store.get(key) == token:
                    del store[key]
                    return 1
            elif "expire" in script:
                key, token = args[0], args[1]
                if store.get(key) == token:
                    return 1
            return 0

        mock_client.set.side_effect = mock_set
        mock_client.get.side_effect = mock_get
        mock_client.delete.side_effect = mock_delete
        mock_client.eval.side_effect = mock_eval
        
        mock_redis.return_value = mock_client
        yield mock_client

        
        



@pytest.fixture
def meditation_guide(mock_redis):
    """Enhanced fixture with better test isolation"""
    # Create unique session ID for each test
    session_id = str(uuid.uuid4())[:8]
    
    guide = MeditationGuide(
        redis_client=mock_redis,
        model_path=f"test_model_{session_id}"
    )
    # Configure lock with test-specific settings
    guide.distributed_lock = RedisLock(
        redis_client=mock_redis,
        lock_timeout=1,  # Short timeout for tests
        lock_prefix=f"test_{session_id}_"  # Unique prefix per test
    )
    
    try:
        yield guide
    finally:
        # Clean up locks and resources
        if hasattr(guide, 'distributed_lock'):
            guide.distributed_lock.release(
                guide.distributed_lock._lock_name or 
                guide.distributed_lock._default_lock_name
            )
        # Additional cleanup if needed
        mock_redis.flushall()




@pytest.fixture
def redis_client():
    """为测试提供专用的Redis客户端"""
    client = redis.Redis(db=15)
    yield client
    client.flushdb()

# ... 其他fixture定义 ...


@pytest.fixture
def mock_hardware():
    """统一的硬件模拟"""
    mock = MagicMock()
    # 添加必要的模拟数据
    mock.bci_data = [0.1, 0.2, 0.3]
    mock.wearable_data = {
        'heart_rate': 72,
        'hrv': 0.5,
        'breath_rate': 12
    }
    return mock


@pytest.fixture(autouse=True)
def mock_redis():
    with patch('redis.Redis') as mock_redis:
        mock_client = MagicMock()
        # 添加常用方法mock
        mock_client.set.return_value = True
        mock_client.get.return_value = None
        mock_client.delete.return_value = 1
        mock_redis.return_value = mock_client
        yield mock_client


def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", help="run integration tests")

def pytest_runtest_setup(item):
    if "integration" in item.keywords and not item.config.getvalue("integration"):
        pytest.skip("需要添加 --integration 选项来运行集成测试")
import pytest
from pytest_asyncio import fixture

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "audio: audio related tests"
    )
    config.addinivalue_line(
        "markers",
        "stress: stress testing"
    )
    config.addinivalue_line(
        "markers",
        "timeout: mark test to have timeout"
    )
    config.addinivalue_line(
        "markers", 
        "benchmark: benchmark performance tests"
    )
    config.addinivalue_line(
        "markers",
        "quality: quality measurement tests"
    )
    # Keep existing configuration
    config.option.asyncio_default_fixture_loop_scope = "function"




# Original configuration remains
def pytest_addoption(parser):
    parser.addoption("--integration", action="store_true", help="run integration tests")

def pytest_runtest_setup(item):
    if "integration" in item.keywords and not item.config.getvalue("integration"):
        pytest.skip("需要添加 --integration 选项来运行集成测试")
def pytest_collection_modifyitems(items):
    for item in items:
        if "TestConcurrent" in item.nodeid:
            item.add_marker(pytest.mark.skip(reason="并发测试需要单独运行"))


@pytest.fixture(scope="session")
def shared_mocks():
    with patch('redis.Redis') as mock_redis, \
         patch('src.aisleep.meditation.MeditationGuide._load_model_safely') as mock_load:
        mock_redis.return_value = MagicMock()
        mock_load.return_value = MagicMock()
        yield {'redis': mock_redis, 'load_model': mock_load}

def pytest_collection_modifyitems(config, items):
    # 跳过标记为slow的测试
    skip_slow = pytest.mark.skip(reason="跳过耗时测试")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
