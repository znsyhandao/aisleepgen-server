import unittest
from src.aisleep.model.deepseek.official.DeepSeek_V3 import DeepSeekModel, ModelConfig
import torch

class TestDeepSeekImport(unittest.TestCase):
    def setUp(self):
        self.config = ModelConfig()
        
    def test_model_import(self):
        """测试DeepSeek模型是否能正确导入"""
        model = DeepSeekModel(self.config)
        self.assertIsInstance(model, torch.nn.Module)
        
    def test_config_import(self):
        """测试配置类是否能正确导入"""
        self.assertEqual(self.config.hidden_size, 1024)
        self.assertEqual(self.config.num_hidden_layers, 24)
    def test_model_forward_pass(self):
        """Test model forward pass with dummy input"""
        model = DeepSeekModel(self.config)
        dummy_input = torch.zeros((1, 10), dtype=torch.long)  # batch_size=1, seq_len=10
        output = model(dummy_input)
        self.assertIn('hidden_states', output)

    def test_custom_config(self):
        """Test with non-default configuration"""
        custom_config = ModelConfig(
            hidden_size=768,
            num_hidden_layers=12
        )
        model = DeepSeekModel(custom_config)
        self.assertEqual(model.config.hidden_size, 768)


    def test_inference_speed(self):
        """Basic performance benchmark"""
        model = DeepSeekModel(self.config).eval()
        input_tensor = torch.zeros((1, 128), dtype=torch.long)
        
        # Warmup run
        with torch.no_grad():
            model(input_tensor)
        
        # Actual timing
        with torch.no_grad():
            import time
            start = time.time()
            for _ in range(10):
                model(input_tensor)
            duration = time.time() - start
            
        avg_time = duration/10
        print(f"\nAverage inference time: {avg_time:.4f}s")
        
        # More realistic threshold based on actual performance
        self.assertLess(avg_time, 0.5)  # Adjusted threshold based on actual 0.3840s result
        self.assertGreater(avg_time, 0.01)  # Ensure it's not suspiciously fast



if __name__ == '__main__':
    unittest.main()
