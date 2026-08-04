# 在文件顶部添加导入
from aisleep.utils.lock import DistributedLockManager
import redis
from src.aisleep.meditation import MeditationGuide
from src.aisleep.enterprise import MassMeditationEngine
from aisleep.utils.monitor import PerformanceMonitor
from aisleep.hardware.manager import HardwareManager
from aisleep.config import load_config, validate_config
from aisleep.health.checker import SystemHealthChecker
from aisleep.exceptions import InvalidConfigError
from aisleep.discovery import ServiceRegistry
import logging
import logging.config
import signal
import sys
import asyncio
import os
from pathlib import Path
import multiprocessing
from setuptools import setup, find_packages
import uvicorn
from fastapi import FastAPI
from api.webhooks import router as payment_router
from api.health import router as health_router
from config import settings
from src.aisleep.interventions.music_therapy import MusicTherapy


# FastAPI应用初始化
app = FastAPI()
app.include_router(payment_router, prefix="/api/v1")
app.include_router(health_router)

# 路径和配置初始化
src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
os.chdir(Path(__file__).parent)

# 日志配置
logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'standard': {'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'}
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'standard'},
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'app.log',
            'maxBytes': 10485760,
            'backupCount': 5,
            'formatter': 'standard'
        }
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': logging.INFO
    }
})
logger = logging.getLogger(__name__)

def create_redis_client():
    """创建并配置Redis客户端"""
    return redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        max_connections=int(os.getenv('REDIS_MAX_CONNECTIONS', 100)),
        socket_connect_timeout=int(os.getenv('REDIS_TIMEOUT', 5)),
        health_check_interval=int(os.getenv('REDIS_HEALTH_CHECK', 30)),
        decode_responses=True
    )

async def init_services(redis_client):
    """增强版服务初始化"""
    try:
        config = {
            **load_config(),
            **os.environ.get('AISLEEP_CONFIG', {}),
        }
        validate_config(config)
        
        # 初始化核心服务（添加超时保护）
        services = await asyncio.wait_for(
            _init_core_services(config, redis_client),
            timeout=30.0
        )
        return (*services, registry)
        
    except asyncio.TimeoutError:
        logger.error("服务初始化超时")
        raise
    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

async def _init_core_services(config, redis_client):
    """核心服务初始化逻辑"""
    manager = HardwareManager(config=config)
    guide = MeditationGuide(redis_client=redis_client)
    engine = MassMeditationEngine(redis_client=redis_client)
    health_checker = SystemHealthChecker(manager)
    
    # 服务注册
    registry = ServiceRegistry()
    registry.register('hardware_manager', manager)
    registry.register('medition_guide', guide)
    registry.register('mass_engine', engine)
    registry.register('health_checker', health_checker)
    
    await registry.initialize()
    return manager, guide, engine, health_checker


async def run_services(manager, health_checker):
    """运行所有后台服务"""
    monitor = PerformanceMonitor()
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(monitor.run_metrics_loop())
            tg.create_task(health_checker.run_checks())
            tg.create_task(manager.start_real_time_processing())
    except* Exception as e:
        logger.error(f"服务运行错误: {e}")
        raise

async def main():

    # 初始化 MusicTherapy 实例
    music_therapy = MusicTherapy(device_manager=None)
    
    # 加载音乐库
    music_therapy.load_music_library('path/to/music_library.json')
    
    # 其他逻辑
    print("Music library loaded successfully!")
    """增强版主程序入口"""
    redis_client = None
    try:
        # 添加信号处理
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, handle_shutdown)
            
        redis_client = await create_redis_client()
        services = await init_services(redis_client)
        
        # 健康检查配置
        health_checker = SystemHealthChecker(
            services[0],
            check_interval=10,
            critical_services=['redis', 'audio', 'biofeedback']
        )
        
        # 服务注册
        services[-1].register('lock_manager', DistributedLockManager(redis_client))
        
        # 运行服务（添加超时保护）
        await asyncio.wait_for(
            run_services(*services[:3], health_checker),
            timeout=300.0
        )
    except asyncio.TimeoutError:
        logger.error("主程序运行超时")
    except Exception as e:
        logger.error(f"主程序异常: {e}")
    finally:
        if redis_client:
            await redis_client.close()


def handle_shutdown(signum, frame):
    """信号处理函数"""
    logger.info(f"收到信号 {signum}, 正在关闭...")
    raise KeyboardInterrupt

if __name__ == "__main__":
    # FastAPI服务启动
    uvicorn.run(app, host="0.0.0.0", port=8000)
    
    # 主程序启动
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)
    multiprocessing.set_start_method('spawn')
    
    try:
        if os.environ.get('MULTI_PROCESS'):
            with multiprocessing.Pool() as pool:
                pool.apply_async(asyncio.run, (main(),))
        else:
            asyncio.run(main())
    except Exception as e:
        logger.critical(f"致命错误: {e}")
        sys.exit(1)
