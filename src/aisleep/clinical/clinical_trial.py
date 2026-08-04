class ClinicalTrial:
    """临床试验管理类"""
    def __init__(self):
        self.trials = {}
    
    def add_trial(self, name, protocol):
        self.trials[name] = protocol
