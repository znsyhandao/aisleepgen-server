f=open(r'D:\AISleepGen_Optimized\deepseek_proxy.py','r',encoding='utf-8');c=f.read()
i=c.find("/api/health")
print(f'at={i}')
for j in range(max(0,i-100), min(len(c),i+500)):
    print(f'[{j}] {repr(c[j])}', end='')
