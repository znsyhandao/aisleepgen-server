#!/usr/bin/env python3
"""
expert_opsd_v2.py — OPSD v2: 深度专家互蒸馏 (2026-07-06)

区别于 v1 (调regression_coefs):
  v2 直接调每位专家内部的 personal_bias 参数
  
personal_bias 结构 (每位专家共享):
  recovery, vulnerability, focus_capacity, avg_err
  其中 recovery=vulnerability=fc: [0, 2] 范围
  avg_err=[0.1, 0.3]: 越低 = 评分越准

蒸馏原理:
  教师: avg_err 最低的专家 (评分最准)
  学生: avg_err 最高的专家 (评分波动大)
  蒸馏: 学生向教师的 personal_bias 靠近, 但保护学生的独特专长

论文: arXiv 2607.02234 Purified OPSD
"""

import os, sys, json, datetime, random

AISLEEP = r"D:\AISleepGen_Optimized"
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
PROFILE_PATH = os.path.join(AISLEEP, "data", "user_profile.json")
RADAR = r"D:\super_frontier_radar"

# 10位专家的专长维度 (每人的personal_weights中哪些维度占比高)
EXPERT_KEY_DIMS = {
    "ClinicalPsychologist": {"mood_score": 0.3, "anxiety_level": 0.3, "stress_perception": 0.2, "sleep_quality_score": 0.2},
    "CBT": {"cbt_adherence": 0.3, "sleep_hygiene": 0.3, "thought_pattern": 0.2, "behavior_change": 0.2},
    "SleepPhysician": {"sleep_latency": 0.3, "awake_times": 0.25, "total_duration": 0.25, "symptom_severity": 0.2},
    "Chronobiologist": {"bedtime_regularity": 0.3, "light_exposure": 0.25, "circadian_alignment": 0.25, "wake_consistency": 0.2},
    "LifeScientist": {"diet_quality": 0.25, "exercise_freq": 0.25, "stress_management": 0.25, "social_health": 0.25},
    "RiskManager": {"risk_score": 0.3, "safety_flags": 0.3, "urgency": 0.2, "complication_risk": 0.2},
    "StressRelaxation": {"relaxation_quality": 0.3, "stress_baseline": 0.3, "calmness_score": 0.2, "recovery_rate": 0.2},
    "ExerciseRehab": {"exercise_freq": 0.25, "recovery_quality": 0.25, "body_awareness": 0.25, "movement_diversity": 0.25},
    "CardiacMonitor": {"heart_rate_variability": 0.3, "blood_pressure_trend": 0.3, "cardiac_risk_score": 0.2, "exercise_tolerance": 0.2},
    "NutriMetabolism": {"diet_quality": 0.25, "metabolic_health": 0.25, "supplement_adherence": 0.25, "energy_level": 0.25},
}

# 蒸馏率: 学生向教师靠近的速度
DISTILL_RATE = 0.15


class OPSDv2:
    def __init__(self):
        self.now = datetime.datetime.now()
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)
        print(f"  [OPSDv2] {msg}")

    def _load_cal(self):
        return json.load(open(CAL_PATH, "r", encoding="utf-8"))

    def _save_cal(self, cal):
        json.dump(cal, open(CAL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def _load_profiles(self):
        return json.load(open(PROFILE_PATH, "r", encoding="utf-8"))

    def _save_profiles(self, profiles):
        json.dump(profiles, open(PROFILE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def evaluate_experts(self, profiles):
        """
        评估每位专家的 personal_bias.avg_err
        avg_err 越低 → 评分越准 → 可能做教师
        """
        # 从第一个有 learning_context 的 profile 出发
        expert_stats = {}

        for uid, pdata in profiles.items():
            if not isinstance(pdata, dict):
                continue
            lc = pdata.get("_learning_context", {})
            weights = lc.get("personal_weights", {})
            conf = lc.get("learning_confidence", "low")
            bias = lc.get("personal_bias", (0, 0, 0, 0.3))

            avg_err = bias[3] if isinstance(bias, (list, tuple)) and len(bias) >= 4 else 0.3
            conf_score = {"high": 1.0, "medium": 0.6, "low": 0.3}.get(conf, 0.3)

            expert_stats[uid] = {
                "avg_err": avg_err,
                "confidence": conf_score,
                "weights": weights,
                "bias": bias,
            }

        return expert_stats

    def select_teacher_and_student(self, expert_stats):
        """从用户 profiles 中选教师和学生"""
        if not expert_stats:
            return None, None, "无profile数据"

        # 按 avg_err 排序 (低的准)
        sorted_users = sorted(expert_stats.items(), key=lambda x: x[1]["avg_err"])

        # 教师: avg_err 最低的用户
        teacher_uid, teacher_stats = sorted_users[0]
        # 学生: avg_err 最高的用户 (但有足够confidence)
        candidates = [(uid, s) for uid, s in reversed(sorted_users) if s["confidence"] >= 0.3]
        if len(candidates) < 2:
            return None, None, "用户太少, 无法配对"

        # 跳过教师自己
        student_uid, student_stats = candidates[0] if candidates[0][0] != teacher_uid else candidates[1]

        return teacher_uid, student_uid, None

    def distill_personal_bias(self, teacher_uid, student_uid, profiles):
        """蒸馏 personal_bias: 学生 → 靠近教师的方向"""
        t_p = profiles.get(teacher_uid, {})
        s_p = profiles.get(student_uid, {})

        # 保护: 如果没有learning_context, 先创建默认
        t_lc = t_p.get("_learning_context", {})
        s_lc = s_p.get("_learning_context", {})
        if not s_lc:
            s_lc = {
                "personal_bias": (0.5, 0.5, 0.5, 0.3),
                "personal_weights": {},
                "learning_confidence": "low",
            }
            profiles[student_uid]["_learning_context"] = s_lc

        t_bias = t_lc.get("personal_bias", (0, 0, 0, 0.3))
        s_bias = s_lc.get("personal_bias", (0, 0, 0, 0.3))
        t_weights = t_lc.get("personal_weights", {})
        s_weights = s_lc.get("personal_weights", {})

        # bias 是 (recovery, vulnerability, fc, avg_err) 4元组
        if not isinstance(t_bias, (list, tuple)) or not isinstance(s_bias, (list, tuple)):
            return {"note": "bias格式异常"}

        t_bias_list = list(t_bias) if isinstance(t_bias, tuple) else t_bias
        s_bias_list = list(s_bias) if isinstance(s_bias, tuple) else s_bias

        # 蒸馏 bias 前3个参数 (忽略 avg_err, 那是confidence决定的)
        new_bias = []
        for i in range(min(3, len(t_bias_list), len(s_bias_list))):
            delta = (t_bias_list[i] - s_bias_list[i]) * DISTILL_RATE
            new_val = round(s_bias_list[i] + delta, 4)
            new_bias.append(new_val)

        # 保护 avg_err (第4个)
        if len(t_bias_list) >= 4 and len(s_bias_list) >= 4:
            new_bias.append(s_bias_list[3])  # 不改变学生的avg_err
        elif len(s_bias_list) >= 4:
            new_bias.append(s_bias_list[3])

        # 同时蒸馏 weights (专家专属参数)
        new_weights = {}
        for dim, default_val in EXPERT_KEY_DIMS.get("ClinicalPsychologist", {}).items():
            t_val = t_weights.get(dim, default_val)
            s_val = s_weights.get(dim, default_val)
            # 如果学生在这个维度权重高 → 保护 (学生的独特专长)
            if s_val > t_val * 1.2:  # 学生高出 20%+
                new_weights[dim] = s_val  # 保护
            else:
                delta = (t_val - s_val) * DISTILL_RATE
                new_weights[dim] = round(s_val + delta, 3)

        # 应用
        new_bias_tuple = tuple(new_bias) if isinstance(t_bias, tuple) else new_bias
        profiles[student_uid]["_learning_context"]["personal_bias"] = new_bias_tuple
        profiles[student_uid]["_learning_context"]["personal_weights"] = new_weights
        profiles[student_uid]["_learning_context"]["last_distill"] = self.now.isoformat()
        if profiles[student_uid]["_learning_context"].get("learning_confidence") == "low":
            profiles[student_uid]["_learning_context"]["learning_confidence"] = "medium"

        self._save_profiles(profiles)

        old_bias_str = f"({s_bias_list[0]:.2f},{s_bias_list[1]:.2f},{s_bias_list[2]:.2f})"
        new_bias_str = f"({new_bias[0]:.2f},{new_bias[1]:.2f},{new_bias[2]:.2f})"
        changed_dims = [d for d, v in new_weights.items() if s_weights.get(d, 0) != v]

        return {
            "teacher": teacher_uid[:10],
            "student": student_uid[:10],
            "bias_change": f"{old_bias_str} → {new_bias_str}",
            "weights_changed": len(changed_dims),
            "protected_dims": [d for d, v in s_weights.items() 
                             if v == new_weights.get(d) and v == s_weights.get(d)],
        }

    def run(self):
        """完整蒸馏周期"""
        self.log("OPSD v2 深度蒸馏...")

        profiles = self._load_profiles()
        stats = self.evaluate_experts(profiles)

        if not stats:
            self.log("无可用profile数据")
            return {"status": "skipped"}

        self.log(f"profiles: {len(profiles)}, 有learning_context: {len(stats)}")

        teacher, student, reason = self.select_teacher_and_student(stats)
        if reason:
            self.log(f"跳过: {reason}")
            return {"status": "skipped", "reason": reason}

        self.log(f"教师: {teacher}, 学生: {student}")
        result = self.distill_personal_bias(teacher, student, profiles)

        # 记录校准
        cal = self._load_cal()
        cal["_opsd_v2"] = {
            "last_distill": self.now.isoformat(),
            "teacher": teacher,
            "student": student,
            "count": cal.get("_opsd_v2", {}).get("count", 0) + 1,
        }
        self._save_cal(cal)

        try:
            sys.path.insert(0, RADAR)
            from _pending_alerts import PendingAlerts
            pa = PendingAlerts()
            pa.add(
                f"opsd_v2_{self.now.strftime('%Y%m%d')}",
                f"[OPSD v2] {teacher}→{student} | bias调整: {result.get('bias_change','')} | weights变动: {result.get('weights_changed',0)}",
                "INFO"
            )
        except:
            pass

        self.log(f"完成: bias {result.get('bias_change','')}")
        return {"status": "ok", "result": result}


def main():
    d = OPSDv2()
    r = d.run()
    if r["status"] == "ok":
        res = r["result"]
        print(f"  教师: {res.get('teacher')} → 学生: {res.get('student')}")
        print(f"  bias: {res.get('bias_change')}")
        print(f"  weights变动: {res.get('weights_changed')} 项")
        print(f"  专长保护: {len(res.get('protected_dims',[]))} 项")
    else:
        print(f"  状态: {r.get('status')}: {r.get('reason','?')}")


if __name__ == "__main__":
    main()
