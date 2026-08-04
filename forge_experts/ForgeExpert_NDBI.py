# -*- coding: utf-8 -*-
# 熔炉v2.0自动生成 — 2026-06-16 16:42:13
# fitness: 0.534
class ForgeExpert_NDBI:
    """
    熔炉新专家 v2.0（系统盲区自动发现）
    关注维度: ['night_hr', 'deep_pct', 'bedtime_variance', 'interruptions']
    逻辑: night_hr(低于0.27)×0.7+deep_pct(超过0.56)×0.6+bedtime_variance(低于0.39)×0.5+interruptions(低于0.18)×0.4
    fitness: 0.534
    生成时间: 2026-06-16 16:42:13
    """
    
    def __init__(self):
        self.name = 'ForgeExpert_NDBI'
        self.specialty = '熔炉发现: night_hr(低于0.27)×0.7+deep_pct(超过0.56)×0.6+bedtime_variance(低于0.39)×0.5+interruptions(低于0.18)×0.4'
    
    def analyze(self, user_data: dict) -> dict:
        score = 0.0
        findings = []
        raw = user_data.get("night_hr", 40)
        norm = max(0, min(1, (raw - 40) / max(1, 120 - 40)))
        triggered = (norm > 0.2669189907741538) if True else (norm < 0.2669189907741538)
        if triggered:
            score += abs(norm - 0.2669189907741538) * 0.6934346287957536
        raw = user_data.get("deep_pct", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 50 - 0)))
        triggered = (norm > 0.560827794756951) if False else (norm < 0.560827794756951)
        if triggered:
            score += abs(norm - 0.560827794756951) * 0.589220503549941
        raw = user_data.get("bedtime_variance", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 120 - 0)))
        triggered = (norm > 0.3882770942424563) if True else (norm < 0.3882770942424563)
        if triggered:
            score += abs(norm - 0.3882770942424563) * 0.4625281650277934
        raw = user_data.get("interruptions", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 10 - 0)))
        triggered = (norm > 0.17835737352717682) if True else (norm < 0.17835737352717682)
        if triggered:
            score += abs(norm - 0.17835737352717682) * 0.42933280528277645
        return {
            'score': round(min(1, score), 3),
            'confidence': round(min(1, score * 1.5), 3),
            'findings': findings,
            'specialty': self.specialty,
        }

