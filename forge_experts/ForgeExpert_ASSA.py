# -*- coding: utf-8 -*-
# v2.2 — 2026-06-16 17:22:37
# fit=0.100
class ForgeExpert_ASSA:
    """v2.2 dims:['awake_duration', 'sleep_latency', 'screen_time', 'awake_times'] desc:awake_duration(超过0.52)x0.7+sleep_latency(超过0.56)x0.8+screen_time(超过0.71)x0.2+awake_times(低于0.48)x0.9 fit:0.100"""
    def __init__(self): self.name='ForgeExpert_ASSA'; self.specialty='awake_duration(超过0.52)x0.7+sleep_latency(超过0.56)x0.8+screen_time(超过0.71)x0.2+awake_times(低于0.48)x0.9'
    def analyze(self, user_data): score=0.0
        raw = user_data.get("awake_duration", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 120 - 0)))
        if (norm > 0.5229387180519736) if True else (norm < 0.5229387180519736):
            score += abs(norm - 0.5229387180519736) * 0.7357449842185845
        raw = user_data.get("sleep_latency", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 180 - 0)))
        if (norm > 0.5562890612505212) if True else (norm < 0.5562890612505212):
            score += abs(norm - 0.5562890612505212) * 0.8060607398265474
        raw = user_data.get("screen_time", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 8 - 0)))
        if (norm > 0.7120754726536078) if True else (norm < 0.7120754726536078):
            score += abs(norm - 0.7120754726536078) * 0.2384288241320232
        raw = user_data.get("awake_times", 0)
        norm = max(0, min(1, (raw - 0) / max(1, 10 - 0)))
        if (norm > 0.4810659539531526) if True else (norm < 0.4810659539531526):
            score += abs(norm - 0.4810659539531526) * 0.8779759794657267
        return {'score': round(min(1,score),3), 'confidence': round(min(1,score*1.5),3), 'findings': [], 'specialty': self.specialty}

