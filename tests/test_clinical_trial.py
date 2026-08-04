import unittest  # Add this
from aisleep.clinical import ClinicalTrial



class ClinicalTrialTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sample_data = load_test_data('mock_trial_data.json')
    
    def test_randomization(self):
        """测试分层随机化平衡性"""
        groups = []
        for _ in range(1000):
            groups.append(trial.randomize_patient(baseline))
        
        # 检验各组比例是否均衡
        _, pval = stats.chisquare(np.unique(groups, return_counts=True)[1])
        self.assertGreater(pval, 0.05)
