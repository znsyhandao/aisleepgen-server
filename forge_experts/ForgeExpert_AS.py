# -*- coding: utf-8 -*-
# 熔炉v2.1 真实专家版 — 2026-06-16 17:17:10
# fit=0.594
class ForgeExpert_AS:
    """熔炉v2.1 真实专家盲区发现  维度:['awake_times', 'sleep_latency'] desc:awake_times(低于0.21)×0.6+sleep_latency(低于0.11)×0.3 fit:0.594"""
    def __init__(self):
        self.name = 'ForgeExpert_AS'; self.specialty = '熔炉发现: awake_times(低于0.21)×0.6+sleep_latency(低于0.11)×0.3'
    def analyze(self, user_data: dict) -> dict:
        score = 0.0; findings = []
        raw = user_data.get("awake_times", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 10 - 0)))
        if (norm > 0.21103972287231282) if True else (norm < 0.21103972287231282):
            score += abs(norm - 0.21103972287231282) * 0.6320390354736378
        raw = user_data.get("sleep_latency", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 180 - 0)))
        if (norm > 0.1129793410340676) if True else (norm < 0.1129793410340676):
            score += abs(norm - 0.1129793410340676) * 0.31347396148624435
        return {'score': round(min(1,score),3), 'confidence': round(min(1,score*1.5),3), 'findings': findings, 'specialty': self.specialty}

