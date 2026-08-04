import sys, os, subprocess, time
sys.stdout.reconfigure(encoding='utf-8')

# 确保从正确的目录启动
os.chdir(r'D:\AISleepGen_Optimized')
print(f'启动 deepseek_proxy.py 从 {os.getcwd()}')

proc = subprocess.Popen(
    [sys.executable, '-B', 'deepseek_proxy.py'],
    stdout=open(r'D:\AISleepGen_Optimized\logs\server_stdout.log', 'w', encoding='utf-8'),
    stderr=open(r'D:\AISleepGen_Optimized\logs\server_stderr.log', 'w', encoding='utf-8'),
    creationflags=subprocess.CREATE_NO_WINDOW
)
print(f'PID: {proc.pid}')
time.sleep(3)

# 检查进程存活
if proc.poll() is None:
    print('存活中')
else:
    print(f'已退出 code={proc.returncode}')
    print('=== stderr ===')
    for line in open(r'D:\AISleepGen_Optimized\logs\server_stderr.log', 'r', encoding='utf-8').readlines()[-5:]:
        print(f'  {line.rstrip()}')
