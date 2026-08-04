import pytest
from pathlib import Path
from aisleep.audio_generation import generate_workout_music

def test_generate_workout_music(tmp_path):
    # 使用临时路径测试
    output_path = Path(tmp_path) / "test_output.wav"
    
    # 先调用函数生成音频
    result_path = generate_workout_music(duration=5)  # 不传output_path参数
    generate_workout_music(bpm=130)  # 更快节奏
    generate_workout_music(bpm=140)  # 高强度训练节奏
    
    # 获取预期输出目录
    output_dir = Path(__file__).parent.parent / 'data'
    print(f"输出目录: {output_dir}")
    print(f"输出路径: {result_path}")
    
    try:
        output_dir.mkdir(exist_ok=True, parents=True)
    except Exception as e:
        print(f"无法创建目录: {e}")
    
    assert Path(result_path).exists()
    assert Path(result_path).stat().st_size > 0

def test_generate_workout_music_with_custom_path(tmp_path):
    """测试自定义输出路径功能"""
    custom_path = Path(tmp_path) / "custom_output.wav"
    result_path = generate_workout_music(duration=5, output_path=str(custom_path))
    
    assert result_path == str(custom_path)
    assert custom_path.exists()
    assert custom_path.stat().st_size > 0


