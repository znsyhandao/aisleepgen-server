class ClinicalValidator:
    def validate_psqi_improvement(self, before: float, after: float) -> Dict:
        """PSQI改善验证(临床标准)"""
        return {
            'effect_size': (before - after) / before,
            'clinical_significance': 'significant' if (before - after) > 3 else 'moderate'
        }
