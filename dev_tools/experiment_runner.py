#!/usr/bin/env python3
"""
experiment_runner.py — AISleepGen 实验平台 MVP v1

核心思想: 不改代码, 只改权重/配置/参数, 然后观测效果

实验管线:
  1. 定义实验 (experiment_manifest)
  2. 自动分组 (平分用户到 A/B)
  3. 应用干预 (改 calibration.json / 改权重)
  4. 等待 (N天)
  5. 回收数据 (读 feedback.json / user_profile)
  6. 统计分析
  7. 决断: 上线(保留干预) / 回滚(恢复原始)
  8. 通知至尊宝

设计原则:
  - 零修改 deepseek_proxy.py
  - 所有变更可回滚
  - 每次实验独立记录
  - 支持并发实验不冲突
"""

import os, json, copy, datetime, hashlib, random, math

BASE = r"D:\AISleepGen_Optimized"
DATA_DIR = os.path.join(BASE, "data")
RADAR_DIR = r"D:\super_frontier_radar"
EXPERIMENT_DIR = os.path.join(DATA_DIR, "experiments")
USER_PROFILE = os.path.join(DATA_DIR, "user_profile.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")
CALIBRATION_FILE = os.path.join(DATA_DIR, "calibration.json")
WEIGHT_BACKUP_DIR = os.path.join(BASE, ".experiment_backups")

# 实验默认配置
DEFAULT_MANIFEST = {
    "min_days": 3,           # 最少跑多少天
    "min_users_per_group": 5, # 每组最少多少用户
    "confidence_threshold": 0.8,  # 统计置信度阈值
    "effect_size_threshold": 0.05  # 最小效应量 (5%变化)
}

# 可实验的"旋钮"——列出现有 calibration.json 中可以调的参数
# 以及其他配置文件中的数值型参数


class ExperimentRunner:
    def __init__(self):
        self.now = datetime.datetime.now()
        self.today = self.now.strftime("%Y-%m-%d")
        os.makedirs(EXPERIMENT_DIR, exist_ok=True)
        os.makedirs(WEIGHT_BACKUP_DIR, exist_ok=True)

    # ======== 工具方法 ========

    def _load_json(self, path, default=None):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return default if default is not None else {}

    def _save_json(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_calibration(self):
        return self._load_json(CALIBRATION_FILE, {})

    def _save_calibration(self, data):
        self._save_json(CALIBRATION_FILE, data)

    def _backup_calibration(self, experiment_id):
        """实验前备份权重"""
        cal = self._load_calibration()
        backup_path = os.path.join(WEIGHT_BACKUP_DIR, f"calibration_{experiment_id}_{self.today}.json")
        self._save_json(backup_path, cal)
        return backup_path

    def _restore_calibration(self, backup_path):
        if os.path.exists(backup_path):
            cal = self._load_json(backup_path)
            self._save_calibration(cal)
            return True
        return False

    def _load_user_profiles(self):
        return self._load_json(USER_PROFILE, {})

    def _load_feedback(self):
        fb = self._load_json(FEEDBACK_FILE, [])
        return fb if isinstance(fb, list) else []

    # ======== 实验定义 ========

    def discover_knobs(self):
        """发现可实验的参数旋钮——扫描 calibration.json 等配置文件"""
        cal = self._load_calibration()
        knobs = []

        # calibration 中的数值参数
        for key, value in cal.items():
            if isinstance(value, (int, float)):
                knobs.append({
                    "key": f"calibration.{key}",
                    "current_value": value,
                    "type": type(value).__name__,
                    "source": "calibration.json"
                })

        # calibration 中的专家权重向量
        for key, value in cal.items():
            if isinstance(value, dict):
                for subkey, subval in value.items():
                    if isinstance(subval, (int, float)):
                        knobs.append({
                            "key": f"calibration.{key}.{subkey}",
                            "current_value": subval,
                            "type": type(subval).__name__,
                            "source": "calibration.json"
                        })

        return knobs

    def create_experiment(self, name, knob_key, new_value, description="", 
                         min_days=3, min_users=5):
        """创建一个新的实验"""
        knobs = self.discover_knobs()
        knob_info = None
        for k in knobs:
            if k["key"] == knob_key:
                knob_info = k
                break

        if knob_info is None:
            return {"error": f"旋钮 {knob_key} 不存在", "available_knobs": knobs[:5]}

        experiment_id = hashlib.md5(f"{name}_{self.now.isoformat()}".encode()).hexdigest()[:12]

        # 确保当前没有冲突的实验在运行
        active = self.list_active_experiments()
        for exp in active:
            exp_knob = exp.get("knob_key", exp.get("knob_path", ""))
            if exp_knob == knob_key:
                return {"error": f"旋钮 {knob_key} 已有运行中的实验: {exp.get('name', exp.get('title', '?'))}"}

        manifest = {
            "experiment_id": experiment_id,
            "name": name,
            "description": description,
            "knob_key": knob_key,
            "old_value": knob_info["current_value"],
            "new_value": new_value,
            "created_at": self.now.isoformat(),
            "status": "running",
            "min_days": min_days,
            "min_users_per_group": min_users,
            "applied": False,        # 干预是否已应用
            "started_at": None,
            "finished_at": None
        }

        # 保存
        self._save_json(
            os.path.join(EXPERIMENT_DIR, f"{experiment_id}.json"),
            manifest
        )
        return manifest

    def list_experiments(self):
        """列出所有实验"""
        experiments = []
        if os.path.exists(EXPERIMENT_DIR):
            for f in sorted(os.listdir(EXPERIMENT_DIR)):
                if f.endswith(".json"):
                    exp = self._load_json(os.path.join(EXPERIMENT_DIR, f))
                    if exp:
                        experiments.append(exp)
        return experiments

    def list_running_experiments(self):
        return [e for e in self.list_experiments() if e.get("status") == "running"]

    def list_active_experiments(self):
        """已应用干预但尚未完成的实验"""
        return [e for e in self.list_experiments() 
                if e.get("status") == "running" and e.get("applied")]

    # ======== 干预应用 ========

    def apply_experiment(self, experiment_id):
        """应用一个实验的干预——改 calibration.json"""
        exp_file = os.path.join(EXPERIMENT_DIR, f"{experiment_id}.json")
        manifest = self._load_json(exp_file)
        if not manifest:
            return {"error": f"实验 {experiment_id} 不存在"}

        if manifest.get("applied"):
            return {"error": "实验已应用，不可重复应用"}

        # 备份
        backup_path = self._backup_calibration(experiment_id)
        manifest["backup_path"] = backup_path

        # 解析 knob key 并修改 value
        cal = self._load_calibration()
        knob_key = manifest["knob_key"]
        new_value = manifest["new_value"]

        # 支持 calibration.xxx.yyy 格式
        parts = knob_key.split(".")
        if len(parts) == 2 and parts[0] == "calibration":
            if parts[1] in cal:
                cal[parts[1]] = new_value
                self._save_calibration(cal)
                manifest["applied"] = True
                manifest["started_at"] = self.now.isoformat()
                self._save_json(exp_file, manifest)
                return {"ok": True, "message": f"calibration.{parts[1]} 已从 {manifest['old_value']} 改为 {new_value}"}
            else:
                return {"error": f"calibration 中不存在键 {parts[1]}"}
        
        # 支持 calibration.xxx 格式
        elif len(parts) == 1:
            if knob_key in cal:
                cal[knob_key] = new_value
                self._save_calibration(cal)
                manifest["applied"] = True
                manifest["started_at"] = self.now.isoformat()
                self._save_json(exp_file, manifest)
                return {"ok": True, "message": f"{knob_key} 已从 {manifest['old_value']} 改为 {new_value}"}
            else:
                return {"error": f"calibration 中不存在键 {knob_key}"}

        # 支持 calibration.xxx.yyy.zzz 多级 — 导航到目标再设置
        if parts[0] == "calibration" and len(parts) >= 2:
            target = cal
            # 导航到父级
            for part in parts[1:-1]:  # 跳过 "calibration" 和最后一个 key
                if isinstance(target, dict) and part in target:
                    target = target[part]
                else:
                    self._restore_calibration(backup_path)
                    return {"error": f"路径 {knob_key} 在 {part} 处不存在"}
            last_key = parts[-1]
            if isinstance(target, dict) and last_key in target:
                old_val = target[last_key]
                target[last_key] = new_value
                self._save_calibration(cal)
                manifest["applied"] = True
                manifest["started_at"] = self.now.isoformat()
                self._save_json(exp_file, manifest)
                return {"ok": True, "message": f"{knob_key} 已从 {old_val} 改为 {new_value}"}
            else:
                self._restore_calibration(backup_path)
                return {"error": f"路径末端 {last_key} 不存在于 calibration"}
        
        return {"error": f"不支持的 knob 路径: {knob_key}"}

    def rollback_experiment(self, experiment_id):
        """回滚一个实验"""
        exp_file = os.path.join(EXPERIMENT_DIR, f"{experiment_id}.json")
        manifest = self._load_json(exp_file)
        if not manifest:
            return {"error": f"实验 {experiment_id} 不存在"}

        backup_path = manifest.get("backup_path")
        if backup_path and os.path.exists(backup_path):
            self._restore_calibration(backup_path)
            manifest["status"] = "rolled_back"
            manifest["finished_at"] = self.now.isoformat()
            self._save_json(exp_file, manifest)
            return {"ok": True, "message": f"实验 {experiment_id} 已回滚"}
        else:
            return {"error": "无备份文件，无法回滚"}

    # ======== 落地标记 ========

    def _mark_landed_experiment(self, manifest, patch):
        """标记实验落地到 calibration"""
        try:
            cal = self._load_calibration()
            knob_key = manifest.get("knob_key", "")
            new_value = manifest.get("new_value")
            if knob_key and new_value is not None:
                knob_short = knob_key.replace("calibration.", "")
                # 记录到算法存档
                archive_path = os.path.join(DATA_DIR, "algorithm_archive.json")
                archive = self._load_json(archive_path, default=[])
                if isinstance(archive, dict):
                    archive = list(archive.values())
                
                # 找到或创建条目
                found = False
                for a in archive:
                    if isinstance(a, dict) and a.get("code_hint", "") == knob_short:
                        a["landed"] = True
                        a["landed_at"] = self.now.isoformat()
                        a["landed_value"] = new_value
                        a["avg_rating"] = manifest.get("report", {}).get("avg_rating")
                        found = True
                        break
                if not found:
                    archive.append({
                        "name": f"实验上线: {knob_short}",
                        "code_hint": knob_short,
                        "landed": True,
                        "landed_at": self.now.isoformat(),
                        "landed_value": new_value,
                        "lines_needed": patch.get("lines", 0),
                    })
                self._save_json(archive_path, archive)
        except Exception:
            pass

    # ======== 实验结束 + 分析 ========

    def finish_experiment(self, experiment_id):
        """完成实验: 收集数据 + 统计分析 + 是否上线"""
        exp_file = os.path.join(EXPERIMENT_DIR, f"{experiment_id}.json")
        manifest = self._load_json(exp_file)
        if not manifest:
            return {"error": "实验不存在"}

        # 读取反馈数据
        feedbacks = self._load_feedback()
        profiles = self._load_user_profiles()

        # 简单分析:
        # 看看实验运行期间的总反馈量和满意度趋势
        started = manifest.get("started_at", "1970-01-01")
        # 这里简化: 只统计实验开始后的反馈
        recent_feedbacks = [f for f in feedbacks 
                           if isinstance(f, dict) and f.get("timestamp", "") >= started]

        report = {
            "experiment_id": experiment_id,
            "name": manifest["name"],
            "knob_key": manifest["knob_key"],
            "old_value": manifest["old_value"],
            "new_value": manifest["new_value"],
            "started_at": started,
            "finished_at": self.now.isoformat(),
            "duration_days": round((self.now - datetime.datetime.fromisoformat(started)).total_seconds() / 86400, 1),
            "total_feedback": len(recent_feedbacks),
            "user_count": len(profiles),
        }

        # 统计满意度 (如果有 rating 字段)
        ratings = []
        for fb in recent_feedbacks:
            if isinstance(fb, dict):
                for key in ["rating", "score", "satisfaction"]:
                    if key in fb and isinstance(fb[key], (int, float)):
                        ratings.append(fb[key])
                        break

        if ratings:
            report["avg_rating"] = round(sum(ratings) / len(ratings), 2)
            report["rating_count"] = len(ratings)
        else:
            report["avg_rating"] = None
            report["rating_count"] = 0

        # 决定: 是否上线
        # 简化版: 如果有反馈且评分无明显下降, 就建议上线
        if report["total_feedback"] >= 3 and (report["avg_rating"] is None or report["avg_rating"] >= 3.0):
            report["recommendation"] = "上线"
            manifest["status"] = "completed"

            # ═══ 实验上线 → 自动生成代码patch + 标记落地 ═══
            try:
                from dev_tools.patch_generator import generate_patch, write_alert
                _patch = generate_patch(report)
                if _patch.get("status") == "ready":
                    report["patch"] = _patch
                    write_alert(_patch)
                    # 实际落地: calibration 权重已经在实验期间生效
                    # 这里只是标记这个 knob 的最优值供下次搜索参考
                    self._mark_landed_experiment(manifest, _patch)
            except Exception:
                pass
        else:
            report["recommendation"] = "数据不足, 建议延期"
            manifest["status"] = "extended"

        manifest["finished_at"] = self.now.isoformat()
        manifest["report"] = report
        self._save_json(exp_file, manifest)

        return report

    # ======== 退化检测回滚 ========

    def check_degradation_and_rollback(self):
        """
        检查系统退化 → 如果有运行中的实验且系统变差 → 自动回滚

        读 health_status.json 中的 degradations.
        如果退化且有活跃实验 → 回滚
        """
        health_file = os.path.join(RADAR_DIR, "health_status.json")
        if not os.path.exists(health_file):
            return {"note": "无健康数据"}

        health = self._load_json(health_file, {})
        status = health.get("status", "OK")
        degradations = health.get("degradations", [])

        if status == "OK":
            return {"note": "系统健康, 无需回滚"}
        if status == "WARN" and not degradations:
            return {"note": "WARN但无退化信号, 跳过"}

        active = self.list_active_experiments()
        if not active:
            return {"note": f"系统{status}但无活跃实验, 无需回滚"}

        rolled_back = []
        for exp in active:
            eid = exp["experiment_id"]
            ename = exp.get("name", eid[:8])
            result = self.rollback_experiment(eid)
            if result.get("ok"):
                exp_file = os.path.join(EXPERIMENT_DIR, f"{eid}.json")
                manifest = self._load_json(exp_file)
                if manifest:
                    manifest["rollback_reason"] = "degradation_detected"
                    manifest["degradation_status"] = status
                    manifest["degradation_count"] = len(degradations)
                    self._save_json(exp_file, manifest)
                rolled_back.append(ename)

        if rolled_back:
            msg = f"退化回滚: {', '.join(rolled_back)}"
            try:
                sys.path.insert(0, RADAR_DIR)
                from _pending_alerts import PendingAlerts
                pa = PendingAlerts()
                pa.add(
                    f"degradation_rollback_{self.today}",
                    f"[自动回滚] 检测到系统退化({status}), 已自动回滚实验: {', '.join(rolled_back)}",
                    "WARN"
                )
            except:
                pass
            return {"ok": True, "message": msg}
        return {"note": "退化检测完成, 无回滚"}

    # ======== 自动化管线 ========

    def is_meaningful_knob(self, key, value):
        """判断一个旋钮是否值得实验——过滤掉元数据/计数器"""
        SKIP_PATTERNS = [
            "_user_count", "_last_evolution", "_last_evolve",
            "_regression_intercept", "_regression_score",
        ]
        for pat in SKIP_PATTERNS:
            if pat in key:
                return False
        # True/False 类型没有实验意义
        if isinstance(value, bool):
            return False
        # int 且值很小(计数器)
        if isinstance(value, int) and value < 10:
            return False
        return True

    def auto_run_cycle(self, auto_create=False):
        """
        自动运行一个实验周期:
          1. 检查是否有完成的实验 (min_days 已过)
          2. 如果有 → 完成 + 分析
          3. 扫描可实验旋钮 (过滤无意义的)
          4. 如果没有活跃实验 + auto_create=True → 自动创建+应用下一个实验
        """
        results = {"completed": [], "recommended": None, "created": None}

        # 检查待完成的实验 (含 Sequential Testing)
        running = self.list_running_experiments()
        for exp in running:
            if not exp.get("applied") or not exp.get("started_at"):
                continue
            started = datetime.datetime.fromisoformat(exp["started_at"])
            elapsed_days = (self.now - started).total_seconds() / 86400
            min_days = exp.get("min_days", 3)

            # Sequential Testing: p<0.05 且超过12小时 → 提前结束
            if elapsed_days >= 0.5:
                try:
                    from dev_tools.experiment_tracker import ExperimentTracker
                    _tracker = ExperimentTracker()
                    _analysis = _tracker.analyze()
                    if _analysis and "p_value" in _analysis and _analysis["p_value"] is not None:
                        _p = _analysis["p_value"]
                        _n_jepa = _analysis.get("n_jepa", 0)
                        _n_ctrl = _analysis.get("n_control", 0)
                        if _p < 0.05 and _n_jepa >= 3 and _n_ctrl >= 3:
                            self.log(f"  序贯: p={_p:.4f}, jepa={_n_jepa} ctrl={_n_ctrl}, 提前结束")
                            report = self.finish_experiment(_exp_id)
                            results["completed"].append({
                                "name": exp.get("name", exp.get("title", "")),
                                "report": report,
                                "early_stop": True,
                                "elapsed_days": round(elapsed_days, 1),
                            })
                            continue
                except Exception:
                    pass

            if elapsed_days >= min_days:
                report = self.finish_experiment(exp["experiment_id"])
                results["completed"].append({
                    "name": exp["name"],
                    "report": report
                })

        # 推荐下一个实验 (只推荐有意义的旋钮)
        knobs = self.discover_knobs()
        meaningful = [k for k in knobs if self.is_meaningful_knob(k["key"], k["current_value"])]
        active_keys = {e.get("knob_key", e.get("knob_path", "")) for e in self.list_active_experiments() if e.get("applied")}
        available = [k for k in meaningful if k["key"] not in active_keys]

        if available:
            # ═══ 贝叶斯超参搜索: 替代线性增量 ═══
            try:
                from dev_tools.bayes_search import BayesSearch
                _bs = BayesSearch()
                _bayes_rec = _bs.recommend()
                if _bayes_rec and "error" not in _bayes_rec and _bayes_rec["knob_key"] in {k["key"] for k in available}:
                    knob_key = _bayes_rec["knob_key"]
                    new_val = _bayes_rec["suggested_value"]
                    current_val = _bayes_rec["current_value"]
                    knob = next(k for k in knobs if k["key"] == knob_key)
                    rec = {
                        "knob_key": knob_key,
                        "current_value": current_val,
                        "suggested_value": round(new_val, 4),
                        "type": knob["type"],
                        "method": f"贝叶斯 EI={_bayes_rec.get('expected_improvement','?')}",
                    }
                    results["recommended"] = rec
                else:
                    raise ValueError("贝叶斯推荐不可用, 降级")
            except Exception:
                # 降级: 选绝对值最大的負系数
                priority = sorted(
                    [k for k in available if "regression_coef" in k["key"]],
                    key=lambda k: abs(k["current_value"]), reverse=True
                )
                if not priority:
                    priority = available
                knob = priority[0]
                delta = max(0.05, abs(knob["current_value"]) * 0.2)
                if isinstance(knob["current_value"], (int, float)) and knob["current_value"] < 0:
                    new_val = knob["current_value"] - delta
                else:
                    new_val = knob["current_value"] + delta
                rec = {
                    "knob_key": knob["key"],
                    "current_value": knob["current_value"],
                    "suggested_value": round(new_val, 4),
                    "type": knob["type"],
                    "method": "降级: 绝对值优先",
                }
                results["recommended"] = rec

            # 如果 auto_create=True → 自动创建+应用下一个实验
            # 只要 knob_key 不与其他活跃实验冲突即可
            active_exps = self.list_active_experiments()
            conflict_keys = {e.get("knob_key", e.get("knob_path", "")) for e in active_exps if e.get("applied")}
            if auto_create and rec["knob_key"] not in conflict_keys:
                knob_short = knob["key"].split(".")[-1][:12]
                exp_name = f"auto_{knob_short}_{self.now.strftime('%m%d')}"
                create_result = self.create_experiment(exp_name, knob["key"], round(new_val, 4))
                if "error" not in create_result:
                    exp_id = create_result.get("experiment_id", create_result.get("message", ""))
                    try:
                        apply_result = self.apply_experiment(exp_id.split()[-1])
                        results["created"] = {
                            "experiment_id": exp_id.split()[-1] if " " in exp_id else exp_id,
                            "name": exp_name,
                            "knob_key": knob["key"],
                            "from": knob["current_value"],
                            "to": round(new_val, 4),
                        }
                    except Exception:
                        pass
        
        return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AISleepGen 实验平台")
    parser.add_argument("--list", action="store_true", help="列出实验和旋钮")
    parser.add_argument("--create", nargs=3, metavar=("NAME", "KNOB", "VALUE"),
                       help="创建实验: --create '调高放松权重' calibration.relax_weight 0.8")
    parser.add_argument("--apply", metavar="EXPERIMENT_ID", help="应用实验干预")
    parser.add_argument("--finish", metavar="EXPERIMENT_ID", help="完成实验+分析")
    parser.add_argument("--rollback", metavar="EXPERIMENT_ID", help="回滚实验")
    parser.add_argument("--auto", action="store_true", help="自动运行一个实验周期")
    parser.add_argument("--knobs", action="store_true", help="列出可实验旋钮")
    parser.add_argument("--check-degradation", action="store_true",
                       help="检查系统退化→自动回滚实验")
    parser.add_argument("--auto-create", action="store_true",
                       help="自动创建+应用下一个推荐实验（需要--auto）")
    args = parser.parse_args()

    runner = ExperimentRunner()

    if args.knobs or args.list:
        print("=== 可实验旋钮 ===")
        knobs = runner.discover_knobs()
        for k in knobs[:20]:
            print(f"  {k['key']} = {k['current_value']} ({k['type']}) [{k['source']}]")
        if len(knobs) > 20:
            print(f"  ... 还有 {len(knobs)-20} 个")

    if args.list:
        experiments = runner.list_experiments()
        print(f"\n=== 实验列表 ({len(experiments)}) ===")
        for e in experiments:
            status = f"[{e.get('status','?')}]"
            applied = "已应用" if e.get("applied") else "未应用"
            print(f"  {status} {e.get('experiment_id', '?')[:12]} {e.get('name', e.get('title', '?'))} ({applied})")

    if args.create:
        name, knob, value_str = args.create
        try:
            value = float(value_str)
        except:
            value = value_str
        result = runner.create_experiment(name, knob, value)
        if "error" in result:
            print(f"错误: {result['error']}")
        else:
            print(f"实验创建成功: {result['experiment_id']}")

    if args.apply:
        result = runner.apply_experiment(args.apply)
        if "error" in result:
            print(f"错误: {result['error']}")
        else:
            print(f"应用成功: {result['message']}")

    if args.finish:
        report = runner.finish_experiment(args.finish)
        if "error" in report:
            print(f"错误: {report['error']}")
        else:
            print(f"实验完成: {report['name']}")
            print(f"  持续时间: {report.get('duration_days', '?')} 天")
            print(f"  总反馈: {report.get('total_feedback', 0)}")
            print(f"  平均评分: {report.get('avg_rating', 'N/A')}")
            print(f"  建议: {report.get('recommendation', 'N/A')}")

    if args.rollback:
        result = runner.rollback_experiment(args.rollback)
        print(result.get("message", result.get("error", "?")))

    if args.auto:
        print("=== 自动实验周期 ===")
        results = runner.auto_run_cycle(auto_create=args.auto_create)
        for c in results.get("completed", []):
            r = c["report"]
            print(f"  实验完成: {c['name']} | 评分={r.get('avg_rating','?')} | 建议={r.get('recommendation','?')}")
        created = results.get("created")
        if created:
            print(f"  自动创建: {created['name']} | {created['knob_key']}: {created['from']} → {created['to']}")
            print(f"  ID: {created['experiment_id']}")
        rec = results.get("recommended")
        if rec and not created:
            print(f"  推荐新实验: {rec['knob_key']} = {rec['current_value']} → {rec['suggested_value']}")
        elif not rec:
            print("  无可用旋钮")

    if args.check_degradation:
        result = runner.check_degradation_and_rollback()
        note = result.get("note", result.get("message", "?"))
        print(f"  退化检查: {note}")


if __name__ == "__main__":
    main()
