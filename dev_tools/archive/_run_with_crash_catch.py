"""带崩溃捕获的守护启动"""
import subprocess, sys, os, time
sys.stdout.reconfigure(encoding='utf-8')

py = sys.executable
script = 'D:\\AISleepGen_Optimized\\deepseek_proxy.py'

p = subprocess.Popen(
    [py, '-B', script],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd='D:\\AISleepGen_Optimized'
)

time.sleep(3)

# 检查是否存活
if p.poll() is not None:
    # 已崩溃，输出所有日志
    out, err = p.communicate()
    print('=== STDOUT ===')
    print(out.decode('utf-8', errors='replace')[-3000:])
    print('=== STDERR ===')
    print(err.decode('utf-8', errors='replace')[-3000:])
    print(f'Exit code: {p.returncode}')
else:
    print(f'Server running (pid {p.pid})')
    # 跑测试
    import urllib.request, json
    body = json.dumps({'message': '帮我做个呼吸练习吧', 'history': [], 'openid': 'dev_e209266b333b1329'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request('http://localhost:8090/api/chat', data=body, headers={'Content-Type':'application/json'}), timeout=120) as r:
            print('Chat OK')
    except Exception as e:
        print(f'Chat fail: {e}')
    
    # 检查进程状态
    time.sleep(2)
    if p.poll() is not None:
        out, err = p.communicate()
        print('=== CRASHED ===')
        print('STDERR:', err.decode('utf-8', errors='replace')[-2000:])
    else:
        print('Still alive after test')
        p.terminate()
