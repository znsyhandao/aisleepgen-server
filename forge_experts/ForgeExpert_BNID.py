# -*- coding: utf-8 -*-
# 熔炉进化自动生成 — 2026-06-16 15:48:34
# 适应度: 0.62

class ForgeExpert_BNID:
    """
    熔炉-新专家（v0.8自动发现）
    关注的维度: ['bedtime_variance', 'night_hr', 'interruptions', 'deep_pct']
    逻辑: bedtime_variance(超过0.52×0.4)
    """
    
    def __init__(self):
        self.name = 'ForgeExpert_BNID'
        self.specialty = '熔炉进化发现: bedtime_variance(超过0.52×0.4)'
    
    def analyze(self, user_data: dict) -> dict:
        """分析用户数据，返回异常见解"""
        score = 0
        findings = []
        
        # 规则集（来自熔炉进化）
        rules = {"bedtime_variance": {"threshold": 0.5177090104160506, "direction": "above", "weight": 0.3651387521031111}}
        
        for dim_info, rule in __import__('json').loads(list(rules.keys())[0]):
            raw_val = user_data.get(dim, 0.5)
            ranges = {
                'efficiency': (0, 100), 'latency': (0, 180), 'duration': (0, 12),
                'deep_pct': (0, 50), 'interruptions': (0, 10),
            }
            lo, hi = ranges.get(dim, (0, 100))
            norm = max(0, min(1, (raw_val - lo) / max(1, hi - lo)))
            
            triggered = (norm > rule['threshold']) if rule['direction'] == 'above' else (norm < rule['threshold'])
            if triggered:
                findings.append({
                    'dimension': dim,
                    'value': round(raw_val, 1),
                    'normalized': round(norm, 2),
                    'severity': round(abs(norm - rule['threshold']) * rule['weight'], 2),
                })
                score += abs(norm - rule['threshold']) * rule['weight']
        
        return {
            'score': round(min(1, score), 3),
            'confidence': round(min(1, score * 2), 3),
            'findings': findings,
            'specialty': self.specialty,
        }
