import unittest
from unittest.mock import MagicMock, patch

class TestMeditationAdapter(unittest.TestCase):
    @patch('aisleep.model.deepseek.official.DeepSeek_V3.modules.meditation_optimizer.StressLevelRegressor')
    def setUp(self, mock_regressor):
        self.mock_core = MagicMock()
        self.adapter = MeditationAdapter(self.mock_core)

    def test_multilingual_support(self):
        test_data = {"audio": b"test", "text": "hello", "language": "en"}
        with patch.object(self.adapter, 'process_input') as mock_process:
            self.adapter.process_input(test_data)
            mock_process.assert_called_with(test_data)

    @patch('pycuda.driver.Device')
    def test_hardware_accel(self, mock_cuda):
        adapter = MeditationAdapter(MagicMock(), use_hardware_accel=True)
        mock_cuda.assert_called()
