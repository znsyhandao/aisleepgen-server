import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class SystemHealthChecker:
    def __init__(self, hardware_manager):
        self.hardware_manager = hardware_manager
        self._running = False
        self._task = None
        self.health_status = {
            'hardware': 'unknown',
            'last_check': None,
            'errors': []
        }

    async def start(self):
        """异步启动健康检查服务"""
        if self._running:
            logger.warning("Health checker already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Health checker started")

    async def stop(self):
        """优雅停止健康检查服务"""
        if not self._running:
            return

        self._running = False
        if self._task:
            await self._task
        logger.info("Health checker stopped")

    async def _run_loop(self):
        """健康检查主循环"""
        while self._running:
            try:
                await self._perform_checks()
                await asyncio.sleep(60)  # 每分钟检查一次
            except Exception as e:
                logger.error(f"Health check failed: {str(e)}")
                self.health_status['errors'].append(str(e))
                await asyncio.sleep(10)  # 出错后等待10秒

    async def _perform_checks(self):
        """执行具体的健康检查"""
        checks = {
            'hardware': self._check_hardware,
            'connections': self._check_connections
        }

        results = {}
        for name, check in checks.items():
            try:
                results[name] = await check()
            except Exception as e:
                results[name] = {'status': 'error', 'message': str(e)}
                logger.error(f"{name} check failed: {str(e)}")

        self.health_status.update({
            **results,
            'last_check': asyncio.get_event_loop().time()
        })

    async def _check_hardware(self) -> Dict[str, Any]:
        """检查硬件状态"""
        status = await self.hardware_manager.get_status()
        return {
            'status': 'ok' if status['ready'] else 'error',
            'details': status
        }

    async def _check_connections(self) -> Dict[str, Any]:
        """检查设备连接状态"""
        devices = self.hardware_manager.list_connected_devices()
        return {
            'status': 'ok' if devices else 'warning',
            'count': len(devices),
            'devices': devices
        }

    def is_healthy(self) -> bool:
        """获取整体健康状态"""
        return all(
            check.get('status') == 'ok'
            for check in self.health_status.values()
            if isinstance(check, dict)
        )
