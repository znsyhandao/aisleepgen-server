# AISleepGen 并发100 服务器扩容方案

## 当前架构瓶颈

**生产环境**: D70 (82.156.208.245)
- CPU: 2核
- 内存: 4GB
- 架构: Python ThreadingHTTPServer (单进程多线程)
- **并发上限: ~10-15** (实测)

**核心瓶颈**: Python GIL + ThreadingHTTPServer 线程切换开销
- 单连接约 500ms-2s 处理时间（含 DeepSeek API 远程调用）
- 100并发下线程数激增到 100+，线程上下文切换吃掉 CPU

---

## 方案 A: 中等投入（推荐）— 4核8G + 异步化

**服务器**: 华为云/阿里云 4核8G 轻量应用服务器
**月成本**: ~250-350元

### 改造要点:

1. **ThreadingHTTPServer → Uvicorn + FastAPI**
   - 异步事件循环，单 worker 可处理数千并发连接
   - 改造量小：只需要把请求处理函数改为 async def

2. **workers = 4**（= CPU 核数）
   - 每个 worker 独立进程，突破 GIL
   - 配合 Nginx 做负载均衡

3. **内存配置**
   - 每个 worker ~1GB（含 DeepSeek 响应缓存）
   - 系统预留 2GB → 4核8G 足够

### 架构图:
```
Nginx (反向代理+静态资源)
  └── Uvicorn worker x4 (端口 8001-8004)
       └── 异步 DeepSeek API 调用
       └── Redis 缓存热点数据
       └── PostgreSQL (现有)
```

### 预期性能:
- 100并发: 平均响应 < 2s
- 200并发: 开始有排队

---

## 方案 B: 高配（稳妥）— 8核16G

**月成本**: ~500-700元

- workers = 8
- 内存充裕，可加载更多缓存
- 并发 200-300 无压力

---

## 方案 C: 低成本（将就用）— 优化现有 D70

不改服务器，只改代码：
1. 加 connection pool 复用
2. 加 Redis 缓存热点 API（pricing, user-profile 等）
3. 请求限流 + 排队机制

**月成本**: 0元（继续用 D70）
**并发上限**: ~30（优化后）

---

## 推荐

**初期先方案 C**（零成本优化代码），待用户量上来后直接上方案 A（4核8G）。

### 实施步骤（方案 C — 今晚可做）:

1. **加 Redis 缓存**: pip install redis → 缓存 sleep-stats, user-profile 等高频读接口
2. **连接池**: requests.Session() 复用 HTTP 连接（DeepSeek API）
3. **简单限流**: 每用户 10次/秒 → 返回 429

### 实施步骤（方案 A — 需要迁移时）:

1. 安装 Uvicorn + FastAPI
2. 重构 deepseek_proxy.py 的路由系统
3. 测试 → 切换 DNS → 旧服务器停服
