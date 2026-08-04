"""
self_healer.py — AISleepGen 自动修复引擎 (L5 自愈层)

核心能力：
  1. 端点崩溃检测 + CPU/内存异常
  2. 针对已知错误模式的精确修复（不盲猜）
  3. 修复后验证
  4. 修复失败则优雅降级（不再自动回滚git）

不做的：
  - 不修改源码（只注入运行时补丁）
  - 不删除文件
  - 不 git commit/revert

架构：
  monitor_loop() → detect() → diagnose() → heal() → verify() → report()
"""

import os, sys, json, time, threading, subprocess, urllib.request
from datetime import datetime, timedelta
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
HEAL_LOG = os.path.join(PROJECT_ROOT, "data", "self_evolve", "heal_history.jsonl")
os.makedirs(os.path.dirname(HEAL_LOG), exist_ok=True)

# ====================================================================
# 检测层
# ====================================================================

class HealthProbe:
    """端点健康探测"""
    
    ENDPOINTS = [
        ("health", "GET", "http://localhost:8090/health", 200),
        ("chat", "POST", "http://localhost:8090/api/sleep/world-step", None),  # 200或400均可
    ]
    
    @classmethod
    def probe(cls) -> dict:
        """探测所有端点"""
        results = {}
        for name, method, url, expect_status in cls.ENDPOINTS:
            try:
                if method == "GET":
                    resp = urllib.request.urlopen(url, timeout=5)
                    status = resp.status
                else:
                    import json as _j
                    data = _j.dumps({"openid": "healer_probe", "message": "probe"}).encode()
                    req = urllib.request.Request(url, data=data,
                        headers={"Content-Type": "application/json"})
                    resp = urllib.request.urlopen(req, timeout=5)
                    status = resp.status
                    resp.read()  # drain
                
                results[name] = {
                    "status": "UP",
                    "code": status,
                    "latency_ms": 0,  # TODO: measure
                }
            except urllib.error.HTTPError as e:
                results[name] = {
                    "status": "UP" if e.code in (200, 400, 429) else "DOWN",
                    "code": e.code,
                    "error": str(e)[:80],
                }
            except Exception as e:
                results[name] = {
                    "status": "DOWN",
                    "code": 0,
                    "error": str(e)[:80],
                }
        return results


def detect_system_memory() -> dict:
    """检测系统内存/CPU——仅限 Linux"""
    if sys.platform != "linux":
        return {"platform": sys.platform, "note": "not supported on this OS"}
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=1)
        return {
            "memory_pct": mem.percent,
            "cpu_pct": cpu,
            "memory_available_gb": mem.available / (1024**3),
        }
    except Exception as e:
        return {"error": str(e)[:60]}


# ====================================================================
# 诊断层
# ====================================================================

KNOWN_PATTERNS = {
    "wfile_proxy_collapse": {
        "symptoms": [
            "http.client.RemoteDisconnected",
            "ConnectionResetError",
            "BrokenPipeError",
        ],
    },
    "oom": {
        "symptoms": [
            "MemoryError",
            "Cannot allocate memory",
        ],
    },
    "thread_pool_exhausted": {
        "symptoms": [
            "can't start new thread",
        ],
    },
}


# ====================================================================
# 修复层
# ====================================================================

class Healer:
    """持有对 deepseek_proxy.py 模块的运行时注入能力
    
    每个 heal_* 方法尝试通过模块重载或对象替换来修复
    """
    
    def __init__(self):
        self._heal_count = 0
        self._last_heal = None
    
    def heal_restart_server(self, reason: str) -> dict:
        """最后手段：重启服务器进程"""
        import signal
        print(f"  [Healer] 重启服务器: {reason}", flush=True)
        
        # kill 当前 python 进程（其父进程会重启它）
        pid = os.getpid()
        try:
            os.kill(pid, signal.SIGINT)  # 优雅退出
            time.sleep(3)
            os.kill(pid, signal.SIGKILL)  # 强制
        except Exception:
            pass
        
        return {"action": "restart_server", "reason": reason, "pid": pid}
    
    def heal_reload_module(self, module_name: str) -> dict:
        """重载指定模块（不重启服务器）"""
        try:
            import importlib
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                return {"action": "reload_module", "module": module_name, "status": "OK"}
            else:
                return {"action": "reload_module", "module": module_name, "status": "NOT_LOADED"}
        except Exception as e:
            return {"action": "reload_module", "module": module_name, "status": "FAIL", "error": str(e)[:60]}
    
    def heal_drain_heavy_requests(self) -> dict:
        """清理挂起的重请求（通过清理内存）"""
        import gc
        collected = gc.collect()
        return {"action": "drain", "collected": collected}
    
    def heal(self, diagnosis: dict) -> dict:
        """根据诊断执行修复"""
        self._heal_count += 1
        self._last_heal = datetime.now()
        
        error_type = diagnosis.get("type", "unknown")
        detail = diagnosis.get("detail", "")
        
        # 按优先级尝试修复
        if "wfile" in detail.lower() or "broken pipe" in detail.lower():
            r1 = self.heal_reload_module("deepseek_proxy")
            if r1["status"] == "OK":
                return {"type": "reload_module", "success": True, "details": r1}
            # 重载失败 → 交 watchdog 重启进程
            return self._request_watchdog_restart(f"reload失败: wfile/collapse")
        
        elif "memory" in detail.lower() or "oom" in error_type:
            r1 = self.heal_drain_heavy_requests()
            return {"type": "gc_collect", "success": True, "details": r1}
        
        elif "thread" in detail.lower():
            return self._request_watchdog_restart(f"thread exhausted")
        
        # 未知错误 → 尝试模块重载
        r1 = self.heal_reload_module("deepseek_proxy")
        if r1["status"] == "OK":
            return {"type": "reload_module_fallback", "success": True, "details": r1}
        return self._request_watchdog_restart(f"fallback重载失败")
    
    def _request_watchdog_restart(self, reason: str) -> dict:
        """请求 watchdog 重启服务器进程"""
        import subprocess, json as _j
        try:
            STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "self_evolve", "watchdog_status.json")
            if os.path.exists(STATUS_FILE):
                with open(STATUS_FILE, "r", encoding="utf-8") as f:
                    status = _j.load(f)
                wd_pid = status.get("watchdog_pid", 0)
                if wd_pid:
                    # 写入重启请求
                    status["request_restart"] = reason
                    status["request_time"] = datetime.now().isoformat()
                    with open(STATUS_FILE, "w", encoding="utf-8") as f:
                        _j.dump(status, f, ensure_ascii=False)
                    # watchdog 读取到此字段时会在下一轮循环中重启
                    return {"type": "watchdog_restart_requested",
                            "success": True,
                            "detail": f"已请求watchdog(PID {wd_pid})重启: {reason}"}
            
            # 没有 watchdog → 直接 kill 并重启
            return {"type": "no_watchdog_fallback",
                    "success": False,
                    "detail": "watchdog未运行，无法自动重启"}
        except Exception as e:
            return {"type": "request_failed", "success": False, "detail": str(e)[:60]}


# ====================================================================
# 监控循环
# ====================================================================

def run_one_cycle() -> dict:
    """一次完整的检测→诊断→修复→验证周期"""
    cycle = {
        "timestamp": datetime.now().isoformat(),
        "probe": {},
        "diagnosis": {},
        "heal": None,
        "verify": {},
    }
    
    # 检测
    probe = HealthProbe.probe()
    cycle["probe"] = probe
    
    # 检查DOWN端点
    down_endpoints = [k for k, v in probe.items() if v["status"] == "DOWN"]
    if not down_endpoints:
        cycle["diagnosis"] = {"type": "healthy", "detail": "all endpoints UP"}
        cycle["verify"] = {"status": "PASS"}
        return cycle
    
    # 诊断
    errors = []
    for ep in down_endpoints:
        err = probe[ep].get("error", "")
        if err:
            errors.append(err)
    
    diagnosis = {"type": "endpoint_down", "detail": "; ".join(errors), "endpoints": down_endpoints}
    cycle["diagnosis"] = diagnosis
    
    # 修复
    healer = Healer()
    heal_result = healer.heal(diagnosis)
    cycle["heal"] = heal_result
    
    # 验证
    time.sleep(1)
    verify = HealthProbe.probe()
    still_down = [k for k, v in verify.items() if v["status"] == "DOWN"]
    cycle["verify"] = {
        "status": "FAIL" if still_down else "PASS",
        "still_down": still_down,
        "probe_after": verify,
    }
    
    # 记录
    os.makedirs(os.path.dirname(HEAL_LOG), exist_ok=True)
    with open(HEAL_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(cycle, ensure_ascii=False, default=str) + "\n")
    
    return cycle


def monitor_loop(interval: int = 30):
    """持续监控循环（后台线程）"""
    while True:
        try:
            cycle = run_one_cycle()
            if cycle["diagnosis"].get("type") != "healthy":
                print(f"  🔧 自愈: {cycle['diagnosis']['type']} → {cycle['heal']}")
        except Exception as e:
            print(f"  ⚠️ 自愈循环异常: {e}")
        time.sleep(interval)


# ====================================================================
# CLI
# ====================================================================

def print_status():
    """查看自愈历史"""
    records = []
    if os.path.exists(HEAL_LOG):
        with open(HEAL_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
    
    print("=" * 55)
    print("  AISleepGen 自愈历史")
    print("=" * 55)
    print()
    
    if not records:
        print("  ❓ 尚无自愈记录")
        return
    
    for i, r in enumerate(records[-10:]):
        ts = r.get("timestamp", "?")[:19]
        diag = r.get("diagnosis", {})
        heal = r.get("heal")
        verify = r.get("verify", {})
        status = "✅" if verify.get("status") == "PASS" else "❌"
        diag_type = diag.get("type", "?")
        heal_type = heal.get("type", "none") if heal else "none"
        print(f"  {status} #{i+1:2d} {ts} | {diag_type:<20} → {heal_type:<25} | {verify.get('status','?')}")
    
    print()
    print(f"  总记录: {len(records)} 次")
    still_down = [r for r in records if r.get("verify", {}).get("status") == "FAIL"]
    if still_down:
        print(f"  🔴 未恢复: {len(still_down)} 次")
    
    # 当前健康状态
    probe = HealthProbe.probe()
    print()
    print("  当前端点状态:")
    for name, status in probe.items():
        icon = "✅" if status["status"] == "UP" else "❌"
        print(f"    {icon} {name:<10} {status['status']} (code={status.get('code','?')})")


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            print_status()
        elif cmd == "start":
            print("  🔧 自愈监控已启动 (间隔 30 秒)")
            monitor_loop()
        elif cmd == "cycle":
            result = run_one_cycle()
            diag = result.get("diagnosis", {})
            heal = result.get("heal")
            verify = result.get("verify", {})
            print(f"  诊断: {diag.get('type')} — {diag.get('detail', '')[:80]}")
            if heal:
                print(f"  修复: {heal.get('type')} | {'✅' if heal.get('success') else '❌'}")
            print(f"  验证: {verify.get('status')}")
        else:
            print("用法:")
            print("  python self_healer.py           run_one_cycle")
            print("  python self_healer.py start    后台监控")
            print("  python self_healer.py status   查看自愈历史")
            print("  python self_healer.py cycle    单次检测→修复")
    else:
        result = run_one_cycle()
        print(f"  诊断: {result['diagnosis'].get('type')}")
        print(f"  验证: {result['verify'].get('status')}")


if __name__ == "__main__":
    main()
