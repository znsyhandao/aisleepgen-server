# -*- coding: utf-8 -*-
"""
algo_injection_test.py — Nexus 注入链路守门测试 (2026-08-04 建立)
============================================================
验证进化链路末端: 落地算法 -> 注册表 -> 生产 API 可调

背景: 2026-08-04 发现 algo_registry.json 过期 bug (注册表停在昨天,
      307 个新算法生产调不到) -> list_algos 加 freshness 自动重建
      本测试守护该链路, 防止再断。

用法: python -X utf8 dev_tools/test/algo_injection_test.py
退出码: 0 = 全过, 1 = 有 FAIL
"""
import io, sys, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BASE)

PASS = 0; FAIL = 0
def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  [PASS] %s' % name)
    else:
        FAIL += 1
        print('  [FAIL] %s %s' % (name, detail))

def main():
    print('=== Nexus 注入链路守门 ===')

    # 1. 注册表 freshness (核心: 不再过期)
    from core_dev.algo_runner import list_algos, _registry_fresh
    reg = list_algos()
    check('注册表自动刷新 count>=100', reg.get('count', 0) >= 100, 'count=%s' % reg.get('count'))
    check('注册表新鲜', _registry_fresh() is True)
    check('generated 非空', bool(reg.get('generated')))

    # 2. 注册表结构
    algos = reg.get('algos', [])
    check('algos 非空', len(algos) > 0)
    if algos:
        s = algos[0]
        check('条目字段完整', all(k in s for k in ['algo', 'file', 'func', 'signature', 'sha256']), str(list(s.keys()))[:80])

    # 3. 真实执行 (全默认参数算法)
    default_algos = [a for a in algos if all(x.get('has_default', False) for x in a.get('signature', {}).get('args', []))]
    check('存在可无参执行算法', len(default_algos) >= 1)
    if default_algos:
        from core_dev.algo_runner import run_algo
        r = run_algo(default_algos[0]['algo'], {}, timeout=30)
        check('run_algo 真实执行成功', r.get('ok') is True, str(r.get('error'))[:100])

    # 4. 生产 API 端点存在
    dp = open(os.path.join(BASE, 'deepseek_proxy.py'), encoding='utf-8', errors='ignore').read()
    check('algo-list 端点', '_handle_algo_list' in dp and 'algo-list' in dp)
    check('algo-run 端点', '_handle_algo_run' in dp and 'algo-run' in dp)
    check('路由已注册', 'ProxyHandler._handle_algo_list' in dp and 'ProxyHandler._handle_algo_run' in dp)

    print('\n===== 注入链路守门: %d passed, %d failed =====' % (PASS, FAIL))
    return 0 if FAIL == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
