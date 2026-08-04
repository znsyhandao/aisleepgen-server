# -*- coding: utf-8 -*-
# 熔炉v2.0自动生成 — 2026-06-16 16:47:31
# fitness: 0.572
class ForgeExpert_DN:
    """
    熔炉新专家 v2.0（系统盲区自动发现）
    关注维度: ['deep_pct', 'night_hr_avg']
    逻辑: deep_pct(超过0.82)×0.9+night_hr_avg(低于0.24)×0.2
    fitness: 0.572
    生成时间: 2026-06-16 16:47:31
    """
    
    def __init__(self):
        self.name = 'ForgeExpert_DN'
        self.specialty = '熔炉发现: deep_pct(超过0.82)×0.9+night_hr_avg(低于0.24)×0.2'
    
    def analyze(self, user_data: dict) -> dict:
        score = 0.0
        findings = []
        raw = user_data.get("deep_pct", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 50 - 0)))
        triggered = (norm > 0.8153948858990905) if False else (norm < 0.8153948858990905)
        if triggered:
            score += abs(norm - 0.8153948858990905) * 0.8944831949210071
        raw = user_data.get("night_hr_avg", 50)
        norm = max(0, min(1, (raw - 50) / max(1, 110 - 50)))
        triggered = (norm > 0.24485039007861312) if True else (norm < 0.24485039007861312)
        if triggered:
            score += abs(norm - 0.24485039007861312) * 0.1887742141256712
        return {
            'score': round(min(1, score), 3),
            'confidence': round(min(1, score * 1.5), 3),
            'findings': findings,
            'specialty': self.specialty,
        }

