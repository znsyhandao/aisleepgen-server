# -*- coding: utf-8 -*-
"""
core_dev/algo_runner.py — Nexus 落地算法注册表 + 隔离执行器
===========================================================
让 core_dev/injected_algorithms/ 下的算法可被主流程按需调用。

安全模型（重要）：
  算法是 LLM 自动生成的变异产物（engine 产出），可能有危险代码
  （无限循环 / 内存炸弹 / 恶意 import）。
  → 一律通过 subprocess 子进程隔离执行 + 超时保护，绝不直接 import 进主进程。

组件：
  build_registry()  : 扫描 injected_algorithms/*.py → AST 解析签名 → 写 algo_registry.json
  list_algos()      : 读注册表
  run_algo(name, kwargs) : 查注册表 → subprocess 调 algo_exec.py → 返回结果

用法：
  python -c "import sys; sys.path.insert(0,'.'); from core_dev.algo_runner import build_registry; build_registry()"
"""
import ast
import hashlib
import json
import os
import subprocess
import sys
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\AISleepGen_Optimized
_INJ_DIR = os.path.join(_BASE, "core_dev", "injected_algorithms")
_REGISTRY = os.path.join(_BASE, "core_dev", "algo_registry.json")
_EXEC = os.path.join(_BASE, "core_dev", "algo_exec.py")
_TIMEOUT = 30  # 子进程超时秒

# 参数名启发式: 这些关键词的参数会被转为 np.ndarray
_ARRAY_HINTS = (
    "signal", "data", "array", "matrix", "mat", "seq", "sequence", "obs",
    "observation", "series", "measurements", "window", "wave", "spectrum",
    "trajectory", "state", "features", "embed", "profile", "depth", "ecg",
    "eda", "input", "values", "samples", "sample", "time", "times", "x",
)


def _parse_sig(tree, fname):
    """从 AST 提取函数签名: {name, args: [{name, default, has_default}], doc 首行}"""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fname:
            args = []
            pos = node.args.posonlyargs + node.args.args
            defaults = node.args.defaults or []
            n_default = len(defaults)
            for idx, a in enumerate(pos):
                has_def = idx >= len(pos) - n_default
                default = None
                if has_def:
                    d = defaults[idx - (len(pos) - n_default)]
                    try:
                        default = ast.literal_eval(d)
                    except Exception:
                        default = None
                args.append({"name": a.arg, "has_default": has_def, "default": default})
            doc = ast.get_docstring(node) or ""
            return {"name": fname, "args": args, "doc_first": doc.strip().splitlines()[0] if doc.strip() else ""}
    return None


def build_registry():
    """扫描 injected_algorithms/*.py → 注册表 JSON"""
    entries = []
    if not os.path.isdir(_INJ_DIR):
        print("[registry] 目录不存在: %s" % _INJ_DIR)
        return 0
    for fname in sorted(os.listdir(_INJ_DIR)):
        if not fname.endswith(".py"):
            continue
        fp = os.path.join(_INJ_DIR, fname)
        try:
            src = open(fp, encoding="utf-8").read()
            tree = ast.parse(src)
        except Exception as e:
            print("[registry] 解析失败 %s: %s" % (fname, str(e)[:80]))
            continue
        # 主函数: mut_ 前缀优先, 否则第一个 def
        fns = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        main_fn = None
        for n in fns:
            if n.startswith("mut_"):
                main_fn = n
                break
        if main_fn is None and fns:
            # 排除 __init__ / 私有
            cands = [n for n in fns if not n.startswith("_")]
            main_fn = cands[0] if cands else fns[0]
        if main_fn is None:
            continue
        sig = _parse_sig(tree, main_fn)
        if sig is None:
            continue
        sha = hashlib.sha256(src.encode("utf-8")).hexdigest()[:16]
        entries.append({
            "algo": fname[:-3],
            "file": fname,
            "path": fp,
            "func": main_fn,
            "signature": sig,
            "sha256": sha,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
    reg = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(entries), "algos": entries}
    tmp = _REGISTRY + ".tmp"
    json.dump(reg, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, _REGISTRY)
    print("[registry] 注册 %d 个算法 → %s" % (len(entries), _REGISTRY))
    return len(entries)


_REGISTRY_LOCK = False


def _registry_fresh():
    """注册表是否新鲜: 目录最新算法文件 mtime <= 注册表 mtime"""
    try:
        if not os.path.exists(_REGISTRY):
            return False
        reg_mtime = os.path.getmtime(_REGISTRY)
        latest = 0.0
        if os.path.isdir(_INJ_DIR):
            for fname in os.listdir(_INJ_DIR):
                if fname.endswith('.py'):
                    fp = os.path.join(_INJ_DIR, fname)
                    try:
                        latest = max(latest, os.path.getmtime(fp))
                    except Exception:
                        pass
        return latest <= reg_mtime
    except Exception:
        return True


def list_algos():
    """读注册表 (目录新于注册表 -> 自动重建, 保证生产总能调到最新落地算法)"""
    global _REGISTRY_LOCK
    if not _registry_fresh() and not _REGISTRY_LOCK:
        _REGISTRY_LOCK = True
        try:
            build_registry()
        finally:
            _REGISTRY_LOCK = False
    if not os.path.exists(_REGISTRY):
        return {"count": 0, "algos": []}
    try:
        return json.load(open(_REGISTRY, encoding="utf-8"))
    except Exception:
        return {"count": 0, "algos": []}


def _convert_args(sig, kwargs):
    """参数转换: kwargs + 默认值补齐; 数组类参数名 → 标记由子进程转 np.array"""
    out = {}
    for a in sig["args"]:
        name = a["name"]
        if name in kwargs:
            out[name] = kwargs[name]
        elif a["has_default"] and a["default"] is not None:
            out[name] = a["default"]
        # 无默认值且未提供 → 交给子进程报错（缺参）
    return out


def run_algo(algo, kwargs, timeout=_TIMEOUT):
    """查注册表 → subprocess 隔离执行 → 返回 {ok, result|error}"""
    reg = list_algos()
    entry = None
    for e in reg.get("algos", []):
        if e["algo"] == algo:
            entry = e
            break
    if entry is None:
        return {"ok": False, "error": "algorithm not in registry: %s" % algo}
    # 质量门禁: crash/untested 算法调用时明确提示 (不阻止, 但调用方须知风险)
    status = entry.get("status", "")
    warning = ""
    if status == "crash":
        warning = "WARNING: algorithm self-test CRASHED in quality gate - result unreliable"
    elif status == "untested":
        warning = "WARNING: algorithm has NO self-test (untested) - result unreliable"
    sig = entry["signature"]
    args = _convert_args(sig, kwargs or {})
    payload = {
        "file": entry["path"],
        "func": entry["func"],
        "args": args,
        "sig_names": [a["name"] for a in sig["args"]],
    }
    if not os.path.exists(_EXEC):
        return {"ok": False, "error": "algo_exec.py missing"}
    try:
        proc = subprocess.run(
            [sys.executable, _EXEC, json.dumps(payload, ensure_ascii=False)],
            capture_output=True, text=True, timeout=timeout,
            cwd=_BASE,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout after %ds (算法执行超时)" % timeout}
    except Exception as e:
        return {"ok": False, "error": "subprocess error: %s" % str(e)[:150]}
    out = (proc.stdout or "").strip()
    if proc.returncode != 0:
        err = (proc.stderr or "").strip().splitlines()
        return {"ok": False, "error": (err[-1] if err else "exit %d" % proc.returncode)[:300]}
    try:
        res = json.loads(out)
        if warning and isinstance(res, dict):
            res["warning"] = warning
        return res
    except Exception:
        return {"ok": True, "result": out[:2000], "warning": warning}


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "build"
    if mode == "build":
        build_registry()
    elif mode == "list":
        reg = list_algos()
        print("注册算法 %d 个:" % reg["count"])
        for e in reg.get("algos", [])[:10]:
            print("  -", e["algo"], "→", e["func"])
    elif mode == "run":
        algo = sys.argv[2]
        kwargs = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        r = run_algo(algo, kwargs)
        print(json.dumps(r, ensure_ascii=False)[:1500])
