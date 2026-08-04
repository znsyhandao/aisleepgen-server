#!/usr/bin/env python3
"""
experiment_dashboard.py — 实验平台 HTML Dashboard 生成器 (2026-07-06)

输出: data/experiments/_dashboard.html (浏览器直接打开)
内容: 实验列表 + knob状态 + 时间线 + 统计摘要
"""

import os, json, datetime

AISLEEP = r"D:\AISleepGen_Optimized"
EXPERIMENT_DIR = os.path.join(AISLEEP, "data", "experiments")
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
OUTPUT = os.path.join(EXPERIMENT_DIR, "_dashboard.html")


def generate():
    """生成 Dashboard HTML"""
    cal = json.load(open(CAL_PATH, "r", encoding="utf-8"))
    now = datetime.datetime.now()

    # 加载所有实验
    experiments = []
    for fname in os.listdir(EXPERIMENT_DIR):
        if not fname.endswith(".json") or fname.startswith("_"):
            continue
        fpath = os.path.join(EXPERIMENT_DIR, fname)
        try:
            data = json.load(open(fpath, "r", encoding="utf-8"))
            experiments.append(data)
        except:
            pass

    # 计时信息
    running = [e for e in experiments if e.get("status") == "running" and e.get("applied")]
    completed = [e for e in experiments if e.get("status") == "completed"]
    pending = [e for e in experiments if e.get("status") in ("running", "confirmed") and not e.get("applied")]

    def _time_remaining(e):
        if not e.get("started_at"):
            return "?"
        started = datetime.datetime.fromisoformat(e["started_at"])
        elapsed = (now - started).total_seconds() / 86400
        min_days = e.get("min_duration_days", 7)
        remaining = max(0, min_days - elapsed)
        return f"{remaining:.1f}天"

    # Knobs 状态
    knobs = {
        "pain_flag": cal.get("_regression_coefs", {}).get("pain_flag", "?"),
        "awake": cal.get("_regression_coefs", {}).get("awake", "?"),
        "latency": cal.get("_regression_coefs", {}).get("latency", "?"),
        "wm_score": cal.get("_regression_coefs", {}).get("wm_score", "?"),
        "duration": cal.get("_regression_coefs", {}).get("duration", "?"),
        "stress": cal.get("_regression_coefs", {}).get("stress", "?"),
    }

    # 构建 HTML
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>实验平台 Dashboard</title>
<style>
body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 960px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
.card {{ background: white; border-radius: 12px; padding: 16px; margin: 12px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
h1 {{ font-size: 22px; margin: 0 0 4px 0; }}
h2 {{ font-size: 16px; margin: 16px 0 8px 0; color: #555; }}
.stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
.stat {{ flex: 1; min-width: 80px; text-align: center; background: #f0f4ff; border-radius: 8px; padding: 12px; }}
.stat-value {{ font-size: 24px; font-weight: 700; }}
.stat-label {{ font-size: 12px; color: #666; }}
.experiment {{ padding: 8px 0; border-bottom: 1px solid #eee; }}
.experiment:last-child {{ border-bottom: none; }}
.status-running {{ color: #22c55e; font-weight: 600; }}
.status-completed {{ color: #6366f1; font-weight: 600; }}
.status-pending {{ color: #f59e0b; font-weight: 600; }}
.knob {{ display: inline-block; background: #f0f4ff; border-radius: 20px; padding: 4px 12px; margin: 4px; font-size: 13px; }}
.footer {{ font-size: 11px; color: #999; text-align: center; margin-top: 20px; }}
.progress-bar {{ background: #e5e7eb; border-radius: 6px; height: 8px; margin: 4px 0; }}
.progress-fill {{ background: #22c55e; border-radius: 6px; height: 100%; }}
</style></head>
<body>

<h1>🔬 实验平台</h1>
<p style="color:#666;font-size:13px;">{now.strftime('%Y-%m-%d %H:%M')} · 心跳自动投喂运行中</p>

<div class="stats">
  <div class="stat">
    <div class="stat-value">{len(running)}</div>
    <div class="stat-label">运行中</div>
  </div>
  <div class="stat">
    <div class="stat-value">{len(completed)}</div>
    <div class="stat-label">已完成</div>
  </div>
  <div class="stat">
    <div class="stat-value">{len(pending)}</div>
    <div class="stat-label">待应用</div>
  </div>
  <div class="stat">
    <div class="stat-value">{cal.get('samples', '?')}</div>
    <div class="stat-label">反馈样本</div>
  </div>
  <div class="stat">
    <div class="stat-value">{cal.get('_regression_score', '?')}</div>
    <div class="stat-label">R²</div>
  </div>
  <div class="stat">
    <div class="stat-value">{cal.get('avg_user_rating', '?')}</div>
    <div class="stat-label">均分</div>
  </div>
</div>

<div class="card">
<h2>📋 运行中 ({len(running)})</h2>
"""

    for e in running:
        name = e.get("name", e.get("title", "?"))
        eid = e.get("experiment_id", "?")[:10]
        days = _time_remaining(e)
        knob = e.get("knob_key", e.get("knob_path", "?")[:20])
        html += f"""<div class="experiment">
  <span class="status-running">● 运行中</span>
  <strong>{name}</strong><br>
  <span style="font-size:13px;color:#666;">{knob} · {eid} · 剩余{days}</span>
</div>"""

    html += f"""
</div>

<div class="card">
<h2>🔧 当前 Knobs</h2>
"""
    for k, v in knobs.items():
        html += f"""<span class="knob">{k}: {v}</span>"""
    html += f"""
</div>

<div class="card">
<h2>🧠 系统状态</h2>
<table style="width:100%;font-size:13px;">
<tr><td>学习模式</td><td>{cal.get('_learn_mode', '?')}</td><td>最后学习</td><td>{cal.get('learned_on', '?')}</td></tr>
<tr><td>用户数</td><td>{cal.get('_user_count', '?')}</td><td>疼痛惩罚</td><td>{cal.get('pain_penalty_base', '?')}</td></tr>
<tr><td>预测因子</td><td>{', '.join(cal.get('_regression_coefs', {}).keys())}</td><td>实验平台</td><td>60% (11/25)</td></tr>
</table>
</div>

<div class="card">
<h2>📈 心跳管线状态</h2>
<table style="width:100%;font-size:13px;">
<tr><td>阶段</td><td>组件</td><td>频率</td></tr>
<tr><td>1</td><td>自我雷达 (9项检查)</td><td>每次心跳</td></tr>
<tr><td>2a</td><td>退化检查 → 自动回滚</td><td>每次心跳</td></tr>
<tr><td>2b</td><td>实验投喂 → 自动创建</td><td>每次心跳</td></tr>
<tr><td>2c</td><td>OPSD v2 蒸馏</td><td>每次心跳</td></tr>
<tr><td>3</td><td>决策产出 + 桥 + 埋点</td><td>每次心跳</td></tr>
</table>
</div>

<div class="footer">
  AISleepGen 实验平台 · 2026-07-06 v1 · 自动生成<br>
  至尊宝确认后 patch 落地 · 不自动写代码
</div>

</body></html>"""

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard: {OUTPUT}")
    return len(running), len(completed)


if __name__ == "__main__":
    generate()
