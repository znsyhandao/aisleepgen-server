class EnvironmentOptimizer:
    def calculate_ideal_conditions(self, user_profile: Dict) -> Dict:
        """计算个性化理想睡眠环境"""
        return {
            'temperature': self._adjust_for_bmi(user_profile),
            'humidity': self._calculate_humidity_range(user_profile['location']),
            'light_intensity': self._determine_optimal_lighting(user_profile['chronotype'])
        }
