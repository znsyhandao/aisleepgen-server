# -*- coding: utf-8 -*-
"""
landing_sync.py — Nexus 落地算法 → 本地 injected_algorithms/ 注入链路
===========================================================
从腾讯云 nexus 拉取"落地成功"的算法到本地 core_dev/injected_algorithms/

落地成功定义（双绿闸门）：
  1. algo 在 eco_data.json landings 中（engine 已标记落地）
  2. algo 不在 fuzz_report.json failures 中（fuzz 全绿）
  3. algo 不在 unverified_list 中（有 __main__ 自测且运行通过）

安全设计：
  - 远程只读（不删不改远程文件）
  - 本地只新增不覆盖（同名冲突 → 跳过 + 记录）
  - manifest 幂等（injected_manifest.json 记录已同步清单，防重复）
  - 双闸门：py_compile 校验通过才写入；失败 → 移入 .injected_rejected/ 留痕

用法：
  python tools/landing_sync.py            # 执行同步
  python tools/landing_sync.py --dry-run  # 只看候选不下载
  python tools/landing_sync.py --limit 5  # 限制本次同步数量
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

try:
    import paramiko
except ImportError:
    print('[FATAL] 需要 paramiko: pip install paramiko')
    sys.exit(2)

# ============ 配置 ============
HOST = "82.156.208.245"
PORT = 22
USER = "ubuntu"
PASS = "AISleepGen20260427cqs103@!"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # D:\AISleepGen_Optimized
INJECT_DIR = os.path.join(BASE_DIR, "core_dev", "injected_algorithms")
REJECT_DIR = os.path.join(BASE_DIR, "core_dev", ".injected_rejected")
MANIFEST = os.path.join(BASE_DIR, "core_dev", "injected_manifest.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "landing_sync.log")

REMOTE_ECO = "/home/ubuntu/nexus/data/eco_data.json"
REMOTE_FUZZ = "/home/ubuntu/nexus/data/fuzz_report.json"
REMOTE_EXP = "/home/ubuntu/nexus/core_dev/experiments"

os.makedirs(INJECT_DIR, exist_ok=True)
os.makedirs(REJECT_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


def log(msg):
    line = "[%s] %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_manifest():
    if os.path.exists(MANIFEST):
        try:
            return json.load(open(MANIFEST, encoding="utf-8"))
        except Exception:
            return {"synced": []}
    return {"synced": []}


def save_manifest(mf):
    tmp = MANIFEST + ".tmp"
    json.dump(mf, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    os.replace(tmp, MANIFEST)


def ssh_connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, port=PORT, username=USER, password=PASS, timeout=30)
    return c


def ssh_read_json(ssh, path):
    cmd = "/usr/bin/python3 -c \"import json;print(json.dumps(json.load(open('%s'))))\" " % path
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
    err = stderr.read().decode("utf-8", errors="replace")
    if err.strip():
        return None
    out = stdout.read().decode("utf-8", errors="replace").strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只看候选不下载")
    ap.add_argument("--limit", type=int, default=0, help="限制本次同步数量 (0=不限)")
    args = ap.parse_args()

    log("===== landing_sync 启动 (dry_run=%s) =====" % args.dry_run)
    ssh = ssh_connect()

    eco = ssh_read_json(ssh, REMOTE_ECO)
    fuzz = ssh_read_json(ssh, REMOTE_FUZZ)
    if eco is None or fuzz is None:
        log("[FATAL] 远程数据读取失败 eco=%s fuzz=%s" % (eco is not None, fuzz is not None))
        ssh.close()
        sys.exit(1)

    landings = eco.get("landings", [])
    failures = {f.get("algo") for f in fuzz.get("failures", []) if isinstance(f, dict)}
    unverified = set(fuzz.get("unverified_list", []))
    # crash 闸门: fuzz 报告里的 crash 算法是自测炸掉的, 不得同步
    # (Attention_Residue_v2 案例: 不在 failures 但在 crash 名单 -> 漏网)
    crashed = set()
    for f in fuzz.get("failures", []):
        if isinstance(f, dict):
            _st = str(f.get("status", "")).upper()
            if _st in ("CRASH", "TIMEOUT") or str(f.get("detail", "")).upper().startswith("CRASH"):
                crashed.add(f.get("algo"))
    crash_list = fuzz.get("crash", [])
    if isinstance(crash_list, list):
        crashed |= {c.get("algo") if isinstance(c, dict) else str(c) for c in crash_list}
    fuzz_generated = fuzz.get("generated", "?")

    log("landings=%d failures=%d unverified=%d crash=%d fuzz_generated=%s" % (
        len(landings), len(failures), len(unverified), len(crashed), fuzz_generated))

    mf = load_manifest()
    synced_names = {s["algo"] for s in mf.get("synced", [])}

    candidates = []
    stale_skipped = 0
    crashed_skipped = 0
    for l in landings:
        algo = l.get("algo", "")
        fpath = l.get("file", "")
        if not algo or not fpath:
            continue
        # 双绿闸门
        if algo in failures:
            continue
        if algo in unverified:
            continue
        if algo in crashed:
            crashed_skipped = crashed_skipped + 1
            continue
        # fuzz 新鲜度闸门: landing 时间晚于 fuzz 报告 -> 该算法未被本次 fuzz 覆盖
        # (否则会带进 fuzz 未验证的算法, 如 v66 案例)
        l_time = l.get("time", "")
        if l_time and fuzz_generated and l_time > fuzz_generated:
            stale_skipped += 1
            continue
        # 幂等
        if algo in synced_names:
            continue
        candidates.append({"algo": algo, "file": fpath, "time": l.get("time", "")})

    # 去重（同 algo 只取最新 landing）
    seen = {}
    for c in candidates:
        seen[c["algo"]] = c
    candidates = list(seen.values())
    candidates.sort(key=lambda c: c["time"])

    log("候选（双绿+未同步）: %d 个 (fuzz 新鲜度拦截 %d 个, crash 拦截 %d 个)" % (len(candidates), stale_skipped, crashed_skipped))
    if args.limit > 0:
        candidates = candidates[-args.limit:]
        log("limit=%d → 本次 %d 个" % (args.limit, len(candidates)))

    if args.dry_run:
        for c in candidates[-15:]:
            log("  [候选] %s | %s" % (c["algo"], c["time"]))
        log("===== dry-run 结束: 候选 %d 个 =====" % len(candidates))
        ssh.close()
        return

    sftp = ssh.open_sftp()
    ok_n = fail_n = skip_n = 0
    for c in candidates:
        algo = c["algo"]
        fname = os.path.basename(c["file"])
        # 本地同名冲突 → 跳过
        local_path = os.path.join(INJECT_DIR, fname)
        if os.path.exists(local_path):
            log("  [SKIP] 本地已存在: %s" % fname)
            skip_n += 1
            continue
        try:
            remote_path = REMOTE_EXP + "/" + fname  # POSIX 路径，勿用 os.path.join (Windows 会出反斜杠)
            sftp.stat(remote_path)
        except IOError:
            log("  [SKIP] 远程文件不存在: %s" % fname)
            skip_n += 1
            continue
        # 下载到临时文件
        tmp_path = local_path + ".tmp"
        try:
            sftp.get(remote_path, tmp_path)
        except Exception as e:
            log("  [ERR] 下载失败 %s: %s" % (fname, str(e)[:120]))
            fail_n += 1
            continue
        # 双闸门 1: py_compile
        try:
            import py_compile
            py_compile.compile(tmp_path, doraise=True)
        except Exception as e:
            reject_path = os.path.join(REJECT_DIR, fname)
            os.replace(tmp_path, reject_path)
            log("  [REJECT] 编译失败 %s: %s" % (fname, str(e)[:120]))
            fail_n += 1
            continue
        # 双闸门 2: 内容 sanity（非空 + 含 def）
        try:
            content = open(tmp_path, encoding="utf-8").read()
            if len(content.strip()) < 50 or not re.search(r"^def ", content, re.M):
                raise ValueError("内容异常（过短或无函数定义）")
        except Exception as e:
            reject_path = os.path.join(REJECT_DIR, fname)
            os.replace(tmp_path, reject_path)
            log("  [REJECT] 内容校验失败 %s: %s" % (fname, str(e)[:120]))
            fail_n += 1
            continue
        # 通过 → 写入
        os.replace(tmp_path, local_path)
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        mf["synced"].append({
            "algo": algo, "file": fname, "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "landing_time": c["time"], "fuzz_generated": fuzz_generated, "sha256": sha,
        })
        ok_n += 1
        log("  [OK] %s 已注入 (sha=%s)" % (fname, sha))

    save_manifest(mf)
    sftp.close()
    ssh.close()
    log("===== 完成: OK=%d REJECT=%d SKIP=%d 累计已同步=%d =====" % (
        ok_n, fail_n, skip_n, len(mf["synced"])))


if __name__ == "__main__":
    main()
