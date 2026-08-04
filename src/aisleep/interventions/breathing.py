class BreathingExercise(StressInterventionBase):
    TECHNIQUES = {
        '4-7-8': {'inhale':4, 'hold':7, 'exhale':8},
        'box': {'inhale':4, 'hold':4, 'exhale':4},
        'coherent': {'inhale':6, 'hold':0, 'exhale':6}
    }
    
    async def apply(self, biometrics):
        hrv = biometrics['hrv']
        technique = self._select_technique(hrv)
        
        return {
            'type': 'breathing',
            'technique': technique,
            'cycles': self._calculate_cycles(hrv),
            'guided': True
        }
    
    def _select_technique(self, hrv):
        if hrv < 30: return '4-7-8'
        elif hrv < 50: return 'box'
        return 'coherent'
