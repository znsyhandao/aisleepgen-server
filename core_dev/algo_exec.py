# -*- coding: utf-8 -*-
"""
core_dev/algo_exec.py — 算法子进程执行器（隔离沙箱）
===========================================================
由 algo_runner.run_algo 通过 subprocess 调用。
输入: argv[1] = JSON {file, func, args, sig_names}
输出: stdout JSON {ok, result} 或 {ok, error}

安全边界:
  - 独立进程, 超时由父进程控制 (30s)
  - 数组类参数按参数名启发式转 np.array
  - 结果序列化: ndarray→list, 标量→原生, 其他→str
"""
import json
import sys
import traceback


def _to_array_hint(name, hints):
    for h in hints:
        if h in name:
            return True
    return False


ARRAY_HINTS = (
    "signal", "data", "array", "matrix", "mat", "seq", "sequence", "obs",
    "observation", "series", "measurements", "window", "wave", "spectrum",
    "trajectory", "state", "features", "embed", "profile", "depth", "ecg",
    "eda", "input", "values", "samples", "sample", "time", "times", "x",
)


def _serialize(obj):
    """把结果转为 JSON 可序列化结构"""
    import numpy as np
    if obj is None:
        return None
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (int, float, bool, str)):
        return obj
    return str(obj)


def main():
    try:
        payload = json.loads(sys.argv[1])
    except Exception:
        print(json.dumps({"ok": False, "error": "bad payload"}))
        return
    fpath = payload["file"]
    func = payload["func"]
    args = payload.get("args", {})
    sig_names = payload.get("sig_names", [])

    import numpy as np
    # 转换: 数组类参数名 → np.array; 其余原样
    call_args = {}
    for name, val in args.items():
        if isinstance(val, list) and _to_array_hint(name, ARRAY_HINTS):
            try:
                call_args[name] = np.array(val)
            except Exception:
                call_args[name] = val
        else:
            call_args[name] = val

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_algo_mod", fpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = getattr(mod, func)
        result = fn(**call_args)
        print(json.dumps({"ok": True, "result": _serialize(result)}, ensure_ascii=False))
    except Exception as e:
        tb = traceback.format_exc().splitlines()
        print(json.dumps({"ok": False, "error": (tb[-1] if tb else str(e))[:300]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
