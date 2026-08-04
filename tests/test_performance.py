import unittest
import time
import sys
import os

# Add parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from data_generator import BioSynthGenerator

class TestGeneratorPerformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = BioSynthGenerator()
    
    def test_basic_performance(self):
        """基础性能测试"""
        metrics = self.generator.run_performance_tests(num_batches=50)
        self.assertGreater(float(metrics['throughput'].split()[0]), 500, 
                         "吞吐量应大于500样本/秒")
    
    def test_batch_size_impact(self):
        """测试批次大小影响"""
        batch_sizes = [16, 32, 64]
        for bs in batch_sizes:
            self.generator.output_signature['batch_size'] = bs
            metrics = self.generator.run_performance_tests(num_batches=30)
            print(f"Batch {bs}: {metrics['throughput']}")

if __name__ == '__main__':
    unittest.main()
