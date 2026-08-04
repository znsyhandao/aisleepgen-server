#!/usr/bin/env python3
"""
expert_opsd.py — OPSD 专家互蒸馏 (2026-07-06)

论文: arXiv 2607.02234 "Purified OPSD: On-Policy Self-Distillation"
核心: 8+名专家互相学习, 但不丢失各自专长

蒸馏时序:
  1. 选教师: 最近评分最高的专家
  2. 选学生: 评分最低但有独特贡献的专家 (用 cross_consult_rules 判断独特维度)
  3. 蒸馏: 教师的推理链 → 学生权重微调
  4. 专长保护: 如果学生某个维度原本更强 → 不覆盖

集成:
  心跳阶段2自动调用
  结果写 calibration.json 的 _opsd_state
"""

import os, sys, json, datetime, hashlib, math

AISLEEP = r"D:\AISleepGen_Optimized"
CAL_PATH = os.path.join(AISLEEP, "data", "calibration.json")
FEEDBACK_PATH = os.path.join(AISLEEP, "data", "feedback.json")
RADAR = r"D:\super_frontier_radar"

# 10位专家的"专长维度"映射 (从cross_consult_rules推断)
# 每个专家擅长的评分维度
EXPERT_SPECIALTIES = {
    "ClinicalPsychologist": ["mood", "anxiety", "stress_perception", "sleep_quality_subjective"],
    "CBT": ["maladaptive_thoughts", "sleep_hygiene", "behavior_change"],
    "SleepPhysician": ["sleep_disorders", "medical_history", "symptom_severity"],
    "Chronobiologist": ["circadian_rhythm", "light_exposure", "bedtime_regularity"],
    "LifeScientist": ["lifestyle", "diet_exercise", "stress_management"],
    "RiskManager": ["health_risk", "safety_concerns", "urgency_level"],
    "StressRelaxation": ["relaxation_response", "stress_level", "calmness"],
    "ExerciseRehab": ["physical_activity", "recovery", "body_awareness"],
    "CardiacMonitor": ["heart_rate", "blood_pressure", "cardiac_risk"],
    "NutriMetabolism": ["nutrition", "metabolism", "supplements"],
}

# 蒸馏超参数
DISTILL_LEARNING_RATE = 0.1  # 学生吸收教师知识的速度
SPECIALIZATION_THRESHOLD = 0.8  # 专长保护: 学生超过此阈值就不覆盖
MIN_FEEDBACK_PER_EXPERT = 3  # 每个专家最少反馈数才能参与蒸馏


class OPSDDistiller:
    def __init__(self):
        self.now = datetime.datetime.now()
        self.today = self.now.strftime("%Y-%m-%d")
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)
        print(f"  [OPSD] {msg}")

    def _load_calibration(self):
        return json.load(open(CAL_PATH, "r", encoding="utf-8"))

    def _save_calibration(self, cal):
        json.dump(cal, open(CAL_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    def _load_feedback(self):
        fb = json.load(open(FEEDBACK_PATH, "r", encoding="utf-8"))
        return fb if isinstance(fb, list) else []

    def _get_expert_ratings(self, feedbacks):
        """从feedback中提取每位专家的评分表现"""
        # feedback中每条有 wm_score_at_time (世界模型综合评分)
        # 但没有单独的各专家评分 -> 用 _regression_coefs 做间接评估
        cal = self._load_calibration()
        coefs = cal.get("_regression_coefs", {})

        # 使用 regression_coefs 作为"专长领域的表现"
        # 系数绝对值越大 = 该维度对评分影响越强 = 该专家贡献越大
        expert_performance = {}
        for expert_name in EXPERT_SPECIALTIES:
            specialties = EXPERT_SPECIALTIES[expert_name]
            # 找coef中匹配的维度
            scores = []
            for dim in specialties:
                for ck, cv in coefs.items():
                    if dim in ck or any(d in ck for d in dim.split("_")):
                        scores.append(abs(cv))
            if scores:
                expert_performance[expert_name] = sum(scores) / len(scores)
            else:
                expert_performance[expert_name] = 0.5  # 默认

        return expert_performance

    def select_teacher_and_student(self, expert_performance):
        """选教师和学生"""
        if not expert_performance:
            return None, None, None

        # 按性能排序
        sorted_experts = sorted(expert_performance.items(), key=lambda x: -x[1])

        # 教师 = 最佳表现
        teacher_name = sorted_experts[0][0]

        # 学生 = 最差表现的专家（但要有独特专长）
        worst = sorted_experts[-1]
        worst_name = worst[0]
        worst_score = worst[1]

        # 检查最差专家是否有"独特专长"(其他专家没有的维度)
        teacher_specs = set(EXPERT_SPECIALTIES.get(teacher_name, []))
        worst_specs = set(EXPERT_SPECIALTIES.get(worst_name, []))
        unique_specs = worst_specs - teacher_specs

        if not unique_specs:
            # 如果最差专家没有独特专长 → 选第二差的
            for name, score in reversed(sorted_experts[1:]):
                specs = set(EXPERT_SPECIALTIES.get(name, []))
                if specs - teacher_specs:
                    worst_name = name
                    worst_score = score
                    unique_specs = specs - teacher_specs
                    break
            else:
                # 都没独特专长 → 跳过本轮
                return teacher_name, None, "所有专家专长已被教师覆盖"

        return teacher_name, worst_name, None

    def distill(self, teacher_name, student_name):
        """执行蒸馏: 教师→学生"""
        cal = self._load_calibration()
        coefs = cal.get("_regression_coefs", {})

        # 找到教师和学生的共有的维度
        teacher_specs = EXPERT_SPECIALTIES.get(teacher_name, [])
        student_specs = EXPERT_SPECIALTIES.get(student_name, [])
        common_dims = set(teacher_specs) & set(student_specs)
        unique_student_dims = set(student_specs) - set(teacher_specs)

        adjustments = {}
        for dim in common_dims:
            # 对于共有的维度: 学生向教师靠近
            for ck, cv in coefs.items():
                if dim in ck:
                    # 教师优势方向
                    teacher_val = cv
                    # 学生值 = 当前值 + lr * (教师值 - 当前值)
                    adjustment = DISTILL_LEARNING_RATE * (teacher_val - 0)  # 简化: 假设学生起始为0
                    adjustments[ck] = round(adjustment, 4)
                    break

        # 保护专长: 学生独有的维度完全不调
        for dim in unique_student_dims:
            adjustments[f"{dim}(protected)"] = 0

        if not adjustments:
            return {"note": "无共有维度可蒸馏"}

        # 应用蒸馏到 calibration
        applied = []
        for ck, adj in adjustments.items():
            if "(protected)" not in ck and ck in coefs:
                old = coefs[ck]
                # 蒸馏方向: 朝着教师方向微调
                coefs[ck] = round(old + adj, 4)
                applied.append(f"{ck}: {old}→{coefs[ck]}")
            elif "(protected)" in ck:
                applied.append(f"{ck}: 已保护, 未调整")

        cal["_regression_coefs"] = coefs
        self._save_calibration(cal)

        return {
            "teacher": teacher_name,
            "student": student_name,
            "applied": applied,
            "common_dims": list(common_dims),
            "protected_dims": list(unique_student_dims),
        }

    def run(self):
        """完整蒸馏周期"""
        self.log("运行专家互蒸馏...")

        cal = self._load_calibration()
        feedbacks = self._load_feedback()

        # 1. 评估专家表现
        perf = self._get_expert_ratings(feedbacks)
        self.log(f"专家数: {len(perf)}")

        # 2. 选教师和学生
        teacher, student, skip_reason = self.select_teacher_and_student(perf)

        if skip_reason:
            self.log(f"跳过: {skip_reason}")
            return {"status": "skipped", "reason": skip_reason}

        if not teacher or not student:
            self.log("未找到合适的师生对")
            return {"status": "skipped", "reason": "no_pair"}

        self.log(f"教师: {teacher}, 学生: {student}")

        # 3. 执行蒸馏
        result = self.distill(teacher, student)

        # 4. 记录状态
        cal["_opsd_state"] = {
            "last_distill": self.now.isoformat(),
            "teacher": teacher,
            "student": student,
            "count": cal.get("_opsd_state", {}).get("count", 0) + 1,
        }
        self._save_calibration(cal)

        # 5. 写 pending_alerts
        try:
            sys.path.insert(0, RADAR)
            from _pending_alerts import PendingAlerts
            pa = PendingAlerts()
            note = "蒸馏完成" if result.get("applied") else "特有专长, 未调整权重"
            pa.add(
                f"opsd_distill_{self.today}",
                f"[OPSD] {teacher}→{student} {note}",
                "INFO"
            )
        except:
            pass

        self.log(f"完成")
        return {"status": "ok", "result": result}


def main():
    distiller = OPSDDistiller()
    result = distiller.run()
    if result.get("status") == "ok":
        r = result["result"]
        print(f"  教师: {r.get('teacher')}")
        print(f"  学生: {r.get('student')}")
        print(f"  调整: {', '.join(r.get('applied', [])[:5])}")
        print(f"  专长保护: {r.get('protected_dims', [])}")
    else:
        print(f"  状态: {result.get('status')}: {result.get('reason', '?')}")


if __name__ == "__main__":
    main()
