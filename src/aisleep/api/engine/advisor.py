class SleepAdvisor:
    def __init__(self, user_profile):
        self.profile = user_profile
        
    def get_advice(self, analysis_result):
        """基于分析结果生成建议"""
        advice = []
        
        if analysis_result['rem_percent'] < 0.2:
            advice.append("增加REM睡眠：建议睡前避免酒精摄入")
            
        if analysis_result['waso'] > 30:
            advice.append(f"减少夜间觉醒：尝试{self._get_relaxation_method()}")

        return advice
    
    def _get_relaxation_method(self):
        return "478呼吸法" if self.profile['stress_level'] > 5 else "渐进式肌肉放松"
