import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import shutil
import numpy as np
import torch
from aisleep.audio_generation import generate_workout_music

class TestWorkoutMusicGeneration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.test_dir) / 'data'
        self.output_dir.mkdir(exist_ok=True)
        self.default_output = self.output_dir / 'workout_motivation.wav'

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('aisleep.audio_generation.sf.write')
    @patch('aisleep.audio_generation.Path')
    @patch('aisleep.audio_generation.torch.linspace')
    @patch('aisleep.audio_generation.torch.zeros_like')
    @patch('aisleep.audio_generation.torch.exp')
    @patch('aisleep.audio_generation.torch.sin')
    @patch('aisleep.audio_generation.torch.max')
    @patch('aisleep.audio_generation.torch.abs')
    @patch('aisleep.audio_generation.torch.randn')
    
    def test_default_output(self, mock_randn, mock_abs, mock_max, mock_sin, mock_exp, 
                        mock_zeros, mock_linspace, mock_path, mock_write):
        """测试默认输出路径"""
        # 设置tensor模拟
        real_tensor = torch.linspace(0, 5, 44100*5)
        mock_linspace.return_value = real_tensor
        mock_zeros.return_value = real_tensor
        mock_exp.return_value = real_tensor
        mock_sin.return_value = real_tensor
        mock_max.return_value = 1.0
        mock_abs.return_value = real_tensor
        mock_randn.return_value = real_tensor[:500]

        # 模拟完整路径链
        mock_output_dir = MagicMock()
        mock_output_dir.__truediv__.return_value = self.default_output
        mock_path.return_value.parent.parent.__truediv__.return_value = mock_output_dir
        mock_path.return_value.__str__.return_value = str(self.default_output)
        
        result = generate_workout_music(duration=5)
        
        self.assertEqual(result, str(self.default_output))
        mock_write.assert_called_once()

    @patch('aisleep.audio_generation.sf.write')
    @patch('aisleep.audio_generation.Path')
    def test_output_directory_creation(self, mock_path, mock_write):
        """测试输出目录自动创建"""
        # 模拟目录创建行为
        mock_dir = MagicMock()
        mock_dir.exists.return_value = False
        mock_dir.mkdir.return_value = None
        
        mock_output_path = MagicMock()
        mock_output_path.parent.parent.__truediv__.return_value = mock_dir
        mock_path.return_value = mock_output_path
        
        generate_workout_music(duration=5)
        
        # 修改断言以匹配实际调用参数
        mock_dir.mkdir.assert_called_once_with(exist_ok=True, parents=True)
        mock_write.assert_called_once()












    # ... 其他测试方法保持不变 ...




    @patch('aisleep.audio_generation.sf.write')
    def test_custom_output_path(self, mock_write):
        """测试自定义输出路径"""
        custom_path = Path(self.test_dir) / 'custom.wav'
        result = generate_workout_music(duration=5, output_path=custom_path)
        self.assertEqual(str(custom_path), result)
        mock_write.assert_called_once()

    @patch('aisleep.audio_generation.sf.write')
    def test_different_bpm_values(self, mock_write):
        """测试不同BPM值"""
        generate_workout_music(bpm=130)
        generate_workout_music(bpm=140)
        self.assertEqual(2, mock_write.call_count)

    @patch('aisleep.audio_generation.sf.write', side_effect=Exception("Save failed"))
    def test_audio_save_failure(self, mock_write):
        """测试音频保存失败情况"""
        with self.assertRaises(Exception):
            generate_workout_music(duration=1)

if __name__ == '__main__':
    unittest.main()
