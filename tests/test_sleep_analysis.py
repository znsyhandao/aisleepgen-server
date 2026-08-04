import pytest
import time
import sys
import os
from datetime import datetime
# Add this with your other imports
from typing import List
# 更可靠的路径处理
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

try:
    from src.aisleep.meditation import MeditationGuide, BioFeedback
    from src.aisleep import __version__
except ImportError as e:
    print(f"项目结构可能存在问题，请检查以下目录是否存在:\n{project_root}/src/aisleep/meditation.py")
    pytest.exit(f"无法导入模块: {e}", returncode=1)


class TestSleepAnalysis:
    """睡眠分析功能测试套件"""
    
    @pytest.fixture
    def guide(self):
        """创建测试用的MeditationGuide实例"""
        return MeditationGuide(model_path="test")
    
    @pytest.fixture
    def sample_feedback(self):
        """创建标准测试用的生物反馈数据"""
        return BioFeedback(
            heart_rate=65.0,
            breath_rate=12.0,
            hrv=0.7,
            skin_conductance=4.5,
            stress_level=0.3,
            meditation_level=0.8,
            timestamp=time.time(),
            sleep_stage='N2',
            sleep_latency=15.0,
            sleep_efficiency=0.85,
            waso=10.0,
            n1_duration=0.1,
            n2_duration=0.5,
            n3_duration=0.2,
            rem_duration=0.2
        )
    
    def test_sleep_score_calculation(self, guide, sample_feedback):
        """测试睡眠评分计算"""
        # 测试正常情况
        assert 0 <= guide._calculate_sleep_score(sample_feedback) <= 100
        
        # 测试边界情况
        min_feedback = BioFeedback(**{**sample_feedback.__dict__, 'sleep_efficiency': 0})
        max_feedback = BioFeedback(**{**sample_feedback.__dict__, 'sleep_efficiency': 1})
        assert guide._calculate_sleep_score(min_feedback) == 0
        assert guide._calculate_sleep_score(max_feedback) >= 85
        
    def test_sleep_stage_analysis(self, guide, sample_feedback):
        """测试睡眠阶段分析"""
        for stage in ['N1', 'N2', 'N3', 'REM']:
            analysis = guide._analyze_sleep_stage(
                BioFeedback(**{**sample_feedback.__dict__, 'sleep_stage': stage}),
                stage
            )
            assert 'actual' in analysis
            assert 'target' in analysis
            assert analysis['actual'] >= 0
            
    def test_pattern_recommendation(self, guide):
        """测试呼吸模式推荐逻辑"""
        test_cases = [
            (0.75, 35, 'N1', '4-7-8'),
            (0.9, 45, 'N2', 'physiological_sigh'),
            (0.82, 15, 'N3', 'deep_sleep'),
            (0.95, 10, 'REM', 'equal')
        ]
        
        for eff, latency, stage, expected in test_cases:
            feedback = BioFeedback(
                **self.sample_feedback.__dict__,
                sleep_efficiency=eff,
                sleep_latency=latency,
                sleep_stage=stage
            )
            assert guide._suggest_optimal_pattern(feedback) == expected
            
    def test_full_report_integration(self, guide, sample_feedback):
        """测试完整报告生成"""
        guide.session_history.append({
            'start_time': datetime.now(),
            'duration': 1800,
            'final_feedback': sample_feedback
        })
        
        report = guide.generate_sleep_report(0)
        assert 'basic_metrics' in report
        assert 'stage_analysis' in report
        assert 'recommendations' in report
        assert isinstance(report['recommendations'], str)
    def test_invalid_sleep_stage(self, guide, sample_feedback):
        """测试无效睡眠阶段处理"""
        with pytest.raises(ValueError):
            guide._analyze_sleep_stage(sample_feedback, 'INVALID_STAGE')

    def test_empty_session_history(self, guide):
        """测试空会话历史记录"""
        with pytest.raises(ValueError):
            guide.generate_sleep_report(0)
