# -*- coding: utf-8 -*-
"""
core_dev/algo_quality_gate.py — 注册算法质量闸门
===========================================================
对 core_dev/injected_algorithms/ 每个算法执行三关判定：
  1. py_compile 编译
  2. 有 __main__ 自测 → subprocess 实际运行 (timeout 40s)
  3. 无自测 → UNVERIFIED

输出:
  - core_dev/algo_quality_report.json  (质量报告)
  - 注册表 algos[] 每项加 status 字段  (pass/warn/crash/untested)

用法:
  python core_dev/algo_quality_gate.py            # 全量
  python core_dev/algo_quality_gate.py --legacy   # 只测本地遗留(不在 manifest 的)
"""
import json
import os
import subprocess
import sys
import time

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INJ_DIR = os.path.join(_BASE, "core_dev", "injected_algorithms")
_REGISTRY = os.path.join(_BASE, "core_dev", "algo_registry.json")
_REPORT = os.path.join(_BASE, "core_dev", "algo_quality_report.json")
_MANIFEST = os.path.join(_BASE, "core_dev", "injected_manifest.json")
_TIMEOUT = 40


def is_legacy(fname, synced_files):
    return fname not in synced_files


def gate_one(fp, fname):
    """单文件三关判定 → (status, detail)"""
    # 第一关: 编译
    try:
        import py_compile
        py_compile.compile(fp, doraise=True)
    except Exception as e:
        return "fail", "compile: %s" % str(e)[:80]
    # 第二关: 自测存在性
    try:
        src = open(fp, encoding="utf-8").read()
    except Exception as e:
        return "fail", "read: %s" % str(e)[:80]
    if '__main__' not in src:
        return "untested", "no __main__ selftest"
    # 第三关: 实际运行
    try:
        proc = subprocess.run(
            [sys.executable, fp],
            capture_output=True, text=True, timeout=_TIMEOUT,
            cwd=os.path.dirname(fp),
        )
        if proc.returncode == 0:
            return "pass", "selftest ok"
        err = (proc.stderr or "").strip().splitlines()
        return "crash", (err[-1] if err else "exit %d" % proc.returncode)[:120]
    except subprocess.TimeoutExpired:
        return "crash", "timeout >%ds" % _TIMEOUT
    except Exception as e:
        return "fail", "run: %s" % str(e)[:80]


def main():
    only_legacy = "--legacy" in sys.argv
    reg = json.load(open(_REGISTRY, encoding="utf-8"))
    synced = set()
    if os.path.exists(_MANIFEST):
        mf = json.load(open(_MANIFEST, encoding="utf-8"))
        synced = {s["file"] for s in mf.get("synced", [])}

    results = []
    for e in reg.get("algos", []):
        fname = e["file"]
        if only_legacy and not is_legacy(fname, synced):
            continue
        fp = os.path.join(_INJ_DIR, fname)
        if not os.path.exists(fp):
            status, detail = "fail", "file missing"
        else:
            status, detail = gate_one(fp, fname)
        results.append({"algo": e["algo"], "file": fname, "status": status,
                        "detail": detail, "legacy": is_legacy(fname, synced)})
        print("  [%s] %s (%s)" % (status.upper(), fname, detail[:60]))

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "pass": sum(1 for r in results if r["status"] == "pass"),
        "crash": sum(1 for r in results if r["status"] == "crash"),
        "untested": sum(1 for r in results if r["status"] == "untested"),
        "fail": sum(1 for r in results if r["status"] == "fail"),
        "results": results,
    }
    tmp = _REPORT + ".tmp"
    json.dump(report, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, _REPORT)
    print("===== 质量报告: total=%d pass=%d crash=%d untested=%d fail=%d → %s =====" % (
        report["total"], report["pass"], report["crash"], report["untested"], report["fail"], _REPORT))

    # 更新注册表 status
    status_map = {r["algo"]: r["status"] for r in results}
    for e in reg.get("algos", []):
        if e["algo"] in status_map:
            e["status"] = status_map[e["algo"]]
    reg["quality_gate"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp2 = _REGISTRY + ".tmp"
    json.dump(reg, open(tmp2, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp2, _REGISTRY)
    print("注册表已更新 status 字段")


if __name__ == "__main__":
    main()
