#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
asyncio_server.py — 纯异步 HTTP 服务器
路由委托给 dp_router.dispatch()。业务逻辑零冗余。

启动: python asyncio_server.py [--benchmark]
"""
import os, sys, json, asyncio, time
from datetime import datetime
from urllib.parse import urlparse
import concurrent.futures

sys.path = [p for p in sys.path if 'openclaw' not in p.lower()]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ['AISLEEPGEN_SKIP_MAIN'] = '1'
BASE = os.path.dirname(os.path.abspath(__file__))
EVIDENCE_UPDATE_INTERVAL = 86400 * 7  # 7天更新一次PubMed

from dp_router import dispatch, ROUTES

EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=100)

class AIGate:
    def __init__(self, n=200):
        self._sem = asyncio.Semaphore(n)
        self.active = 0; self.waiting = 0
    @property
    def stats(self):
        return {'active': self.active, 'waiting': self.waiting}
    async def run(self, fn, *a, **kw):
        self.waiting += 1
        async with self._sem:
            self.waiting -= 1; self.active += 1
            try: return await fn(*a, **kw)
            finally: self.active -= 1

gate = AIGate(200)

async def route(method, path, data):
    """路由分发——AI调用走并发槽，其余直走线程池"""
    loop = asyncio.get_event_loop()
    if method == 'POST' and urlparse(path).path == '/api/chat':
        async def ai():
            return await loop.run_in_executor(EXECUTOR, dispatch, method, path, data)
        return await gate.run(ai)
    return await loop.run_in_executor(EXECUTOR, dispatch, method, path, data)


class Proto(asyncio.Protocol):
    def connection_made(self, t):
        self.t = t; self.b = b''

    def data_received(self, d):
        self.b += d
        try:
            if b'\r\n\r\n' not in self.b: return
            i = self.b.index(b'\r\n\r\n') + 4
            h = self.b[:i].decode('utf-8', errors='replace')
            body = self.b[i:]; self.b = b''
            lines = h.split('\r\n')
            parts = lines[0].split(' ')
            if len(parts) < 2: return
            method, path = parts[0], parts[1]
            cl = 0
            for l in lines[1:]:
                if ':' in l:
                    k, v = l.split(':', 1)
                    if k.strip().lower() == 'content-length':
                        cl = int(v.strip())
            body_str = body[:cl].decode('utf-8', errors='replace') if cl > 0 else ''
            asyncio.create_task(self.go(method, path, body_str))
        except:
            self.w(400, b'Bad Request')

    async def go(self, method, path, body_str):
        try:
            data = json.loads(body_str) if body_str else {}
            result = await route(method, path, data)
            self.w(200, json.dumps(result, ensure_ascii=False).encode())
        except Exception as e:
            self.w(500, json.dumps({'error': str(e)}, ensure_ascii=False).encode())

    def w(self, status, body_bytes):
        r = (f'HTTP/1.1 {status} {"OK" if status < 400 else "Error"}\r\n'
             f'Content-Type: application/json; charset=utf-8\r\n'
             f'Content-Length: {len(body_bytes)}\r\n'
             f'Access-Control-Allow-Origin: *\r\n'
             f'Connection: keep-alive\r\n\r\n').encode() + body_bytes
        self.t.write(r)
        self.t.close()


async def benchmark():
    print('[Benchmark] 启动压力测试...')
    loop = asyncio.get_event_loop()
    srv = await loop.create_server(lambda: Proto(), '127.0.0.1', 8091)

    async def hit(i):
        try:
            r, w = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', 8091), 5)
            d = json.dumps({'message': f'测试{i}', 'openid': f'u{i%100}'}, ensure_ascii=False).encode()
            req = (f'POST /api/chat HTTP/1.1\r\nContent-Type: application/json\r\n'
                   f'Content-Length: {len(d)}\r\nConnection: close\r\n\r\n').encode() + d
            w.write(req); await w.drain()
            await asyncio.wait_for(r.read(-1), 30)
            w.close()
            return 1
        except: return 0

    for label, n in [('10并发',10), ('50并发',50), ('200并发',200), ('500并发',500)]:
        t0 = time.monotonic()
        rs = await asyncio.gather(*[hit(i) for i in range(n)])
        t = time.monotonic() - t0
        ok = sum(rs)
        print(f'  [{label}] {n}req/{t:.1f}s -> 成功{ok} 失败{n-ok} ({n/t:.0f} req/s)')

    srv.close()
    print('[Benchmark] 完成')


EVIDENCE_UPDATE_INTERVAL = 86400 * 7  # 7天更新一次

async def evidence_auto_updater():
    """启动后异步定时拉取PubMed睡眠医学文献"""
    while True:
        try:
            print('[EVIDENCE] 开始循证数据库更新...')
            proc = await asyncio.create_subprocess_exec(
                sys.executable, os.path.join(BASE, 'scripts', 'evidence_updater.py'), '--auto',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            if proc.returncode == 0:
                print(f'[EVIDENCE] 更新完成')
            else:
                err = stderr.decode('utf-8', errors='replace')[:200]
                print(f'[EVIDENCE] 更新异常: {err}')
        except asyncio.TimeoutError:
            print('[EVIDENCE] 更新超时')
        except Exception as e:
            print(f'[EVIDENCE] 更新失败: {e}')
        await asyncio.sleep(EVIDENCE_UPDATE_INTERVAL)


if __name__ == '__main__':
    print(f'[asyncio] AISleepGen 纯异步服务器')
    print(f'[asyncio] {len(ROUTES)} 条路由 | 线程池 100 | AI并发 200')
    print(f'[asyncio] http://localhost:8090')
    
    # 启动闭环智能体（后台线程，每30分钟对所有活跃用户执行一次闭环）
    try:
        from loop_agent import LoopAgent
        loop_agent = LoopAgent(interval_minutes=30)
        loop_agent.start()
        print(f'[asyncio] 闭环智能体已启动 (30min间隔)')
    except Exception as e:
        print(f'[asyncio] 闭环智能体启动失败: {e}')
    
    if '--benchmark' in sys.argv:
        asyncio.run(benchmark())
    else:
        async def main():
            # 启动循证更新后台任务
            asyncio.create_task(evidence_auto_updater())
            s = await asyncio.get_event_loop().create_server(
                lambda: Proto(), '0.0.0.0', 8090)
            async with s: await s.serve_forever()
        asyncio.run(main())
