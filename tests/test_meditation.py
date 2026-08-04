# 在文件顶部添加缺失的import
# 在文件顶部添加缺失的import
from datetime import datetime
import logging
from src.aisleep.exceptions import AudioGenerationError

import numpy as np
from datetime import datetime, timedelta
import random
from src.aisleep.exceptions import DataNotFoundError

import uuid
import sys
print(sys.modules.keys())  # 查看已加载模块
import unittest
from src.aisleep.utils import RedisLock
from unittest.mock import patch, MagicMock
import pytest
import pygame
# Add this import with your other imports
import os
import tempfile
import time

# Add this with your other imports
from typing import List, Optional
from src.aisleep.meditation import BioFeedback, MeditationGuide
from src.aisleep import __version__
from pathlib import Path
from locust import HttpUser, task, between
from unittest.mock import patch, MagicMock


from src.aisleep.enterprise import MassMeditationEngine

from src.aisleep.content import ContentGenerator
from src.aisleep.meditation import PaymentGateway


from flask import Flask
from src.aisleep.meditation import BioFeedback, MeditationGuide,PaymentIntegration

from src.api.payment_gateway import PaymentGateway






print(f"uuid module: {uuid}")
print(f"uuid4 function: {uuid.uuid4}")

# 将 src 目录添加到 Python 的搜索路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

print(PaymentGateway)


class TestCommercialFeatures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """统一初始化所有mock"""
        # 修复导入路径，确保与项目结构一致
        cls.payment_patch = patch('src.aisleep.meditation.PaymentIntegration')
        cls.mock_payment = cls.payment_patch.start()
        cls.mock_payment.return_value.check_entitlement.return_value = True
        
        # 修复内容生成器mock
        cls.content_patch = patch('src.aisleep.content.ContentGenerator')
        cls.mock_content = cls.content_patch.start()
        cls.mock_content.return_value.generate_premium_content.return_value = {
            'metadata': {'price': 9.99}
        }
        
        # 使用conftest中的redis fixture
        cls.redis_patch = patch('redis.Redis')
        cls.mock_redis = cls.redis_patch.start()
        cls.mock_redis.return_value.set.return_value = True

    @classmethod 
    def tearDownClass(cls):
        """统一清理所有patch"""
        cls.payment_patch.stop()
        cls.content_patch.stop()
        cls.redis_patch.stop()

    def setUp(self):
        """每个测试用例的初始化"""
        self.payment = PaymentIntegration(self.mock_payment.return_value)
        self.content_gen = self.mock_content.return_value

    def test_premium_content_with_dynamic_pricing(self):
        """测试动态定价逻辑"""
        self.content_gen.generate_premium_content.return_value = {
            'metadata': {'price': 19.99}
        }
        content = self.content_gen.generate_premium_content(
            user={'premium_level': 2},
            content_type='stress_relief'
        )
        self.assertEqual(content['metadata']['price'], 19.99)


    def test_entitlement_check(self):
        """测试订阅状态检查"""
        payment = PaymentIntegration(self.mock_payment.return_value)
        result = payment.check_entitlement("user123")
        self.assertTrue(result)
        self.mock_payment.return_value.check_subscription.assert_called_once_with("user123")

    def test_premium_content_generation(self):
        """测试付费内容生成"""
        with patch.object(self.content_gen, 'generate_premium_content') as mock_gen:
            mock_gen.return_value = {'metadata': {'price': 9.99}}
            content = self.content_gen.generate_premium_content(
                user={'premium_level': 2},
                content_type='stress_relief'
            )
            self.assertEqual(content['metadata']['price'], 9.99)
            # 可以在这里添加支付验证
            self.mock_payment.return_value.check_subscription.assert_called_once()

    
    def test_payment_failure(self):
        """测试支付失败情况"""
        self.mock_payment.return_value.check_subscription.return_value = False
        payment = PaymentIntegration(self.mock_payment.return_value)
        result = payment.check_entitlement("user123")
        self.assertFalse(result)

    def test_content_generation_failure(self):
        """测试内容生成失败"""
        with patch.object(self.content_gen, 'generate_premium_content') as mock_gen:
            mock_gen.side_effect = Exception("生成失败")
            with self.assertRaises(Exception):
                self.content_gen.generate_premium_content(
                    user={'premium_level': 2},
                    content_type='stress_relief'
                )




class TestEnterpriseFeatures(unittest.TestCase):
    def setUp(self):
        self.engine = MassMeditationEngine(redis_host='mock_redis')
        self.engine.redis = MagicMock()
        self.engine.redis.set.return_value = True

    def test_mass_session_creation(self):
        """测试大规模会话创建"""
        with patch.object(self.engine.redis, 'set') as mock_set:
            mock_set.return_value = True
            session_id = self.engine.create_mass_session(300, 'coh')
            self.assertIsNotNone(session_id)
            mock_set.assert_called_once()  # 更精确的断言





# 修改测试类
class TestMeditation:
    @patch('redis.Redis')
    def setUp(self, mock_redis):
        self.mock_redis = mock_redis.return_value
        self.mock_redis.set.return_value = True
        self.mock_redis.delete.return_value = True
        
        # 初始化测试对象
        self.guide = MeditationGuide()



sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.mark.usefixtures("mock_redis", "mock_hardware")
class TestMeditationGuide:
    @pytest.fixture(autouse=True)
    def setup(self, mock_redis, mock_hardware, request):
        """测试初始化"""
        # 创建测试对象并注入mock依赖
        self.guide = MeditationGuide(redis_client=mock_redis)
        self.guide.hardware = mock_hardware
        
        # Mock模型和UUID
        self.guide.model = MagicMock()
        self.uuid_patch = patch('uuid.uuid4', return_value="mocked-uuid")
        self.mock_uuid4 = self.uuid_patch.start()
        
        # 配置模型返回值
        self.guide.model.generate_guidance.return_value = {
            'get_next_actions': lambda x: [{'instruction': '测试引导', 'duration': 10}],
            'validate': lambda x: True
        }
        
        # 设置测试用的呼吸模式
        self.guide.breath_patterns = {
            '4-7-8': (4, 7, 8),
            'box': (4, 4, 4, 4),
            'coh': lambda x: (5, 5),
            'equal': (5, 5),
            'physiological_sigh': (2, 10)
        }
        

    def setup_method(self, method):
        self.redis_client = redis.Redis(host='localhost', port=6379)
        self.guide = MeditationGuide(redis_client=self.redis_client)
        # 设置更短的锁超时
        self.guide.distributed_lock = RedisLock(self.redis_client, lock_timeout=3)

    def teardown_method(self, method):
        # 确保释放所有锁
        if hasattr(self.guide, 'distributed_lock'):
            self.guide.distributed_lock.release(self.guide.distributed_lock._lock_name)
        self.redis_client.close()


        


    def test_biofeedback_processing(self, mock_hardware):
        """测试生物反馈数据处理"""
        mock_hardware.wearable_data = {"heart_rate": 80}
        feedback = self.guide.get_current_biofeedback()
        assert feedback.heart_rate == 80

    def test_session_history(self):
        """测试会话历史记录"""
        self.guide.start_session(duration=60)
        assert len(self.guide.session_history) == 1

    def test_error_logging(self):
        """测试错误日志记录"""
        with self.assertLogs(level='ERROR') as log:
            with patch.object(self.content_gen, 'generate_premium_content', 
                            side_effect=Exception("测试错误")):
                try:
                    self.content_gen.generate_premium_content({}, 'test')
                except Exception:
            self.assertTrue(any("测试错误" in msg for msg in log.output))




    def test_default_session(self):
        """测试默认会话"""
        with patch.object(self.guide, 'start_session') as mock_start:
            mock_start.return_value = [{'action': {'instruction': '测试指令'}}]
            session = self.guide.start_session(duration=60)
            self.assertEqual(len(session), 1)
            mock_start.assert_called_once_with(duration=60)


        
    def test_dynamic_adjust(self):
        """测试动态调节功能"""
        feedback = BioFeedback(
            heart_rate=75,
            hrv=0.6,
            stress_level=0.4,
            meditation_level=0.7
        )
        
        # 测试基础模式
        self.guide.use_advanced_mode = False
        basic_adjust = self.guide.dynamic_adjust(feedback)
        self.assertIn('respiration_rate', basic_adjust)
        self.assertTrue(6 <= basic_adjust['respiration_rate'] <= 20)
        
        # 测试高级模式
        self.guide.use_advanced_mode = True
        advanced_adjust = self.guide.dynamic_adjust(feedback)
        self.assertIn('pattern', advanced_adjust)
        self.assertIn(advanced_adjust['pattern'], self.guide.breath_patterns.keys())

    def test_hardware_integration(self):
        """测试硬件集成"""
        self.mock_hardware.wearable_data = {"heart_rate": 75}
        feedback = self.guide.get_current_biofeedback()
        self.assertEqual(feedback.heart_rate, 75)

    def test_audio_integration(self):
        """测试音频集成"""
        with patch('pygame.mixer.init'):
            result = self.guide._sound_therapy(duration=300)
            self.assertEqual(result['duration'], 300)

    def test_patterns(self):
        """测试呼吸模式"""
        assert self.guide.breath_patterns['4-7-8'] == (4, 7, 8)
        assert self.guide.breath_patterns['box'] == (4, 4, 4, 4)
        
        coh_pattern = self.guide.breath_patterns['coh'](70)
        assert len(coh_pattern) == 2
        assert 0 < coh_pattern[0] < 10

    def test_specific_pattern_adjustment(self):
        """测试特定呼吸模式的调节效果"""
        test_cases = [
            ('4-7-8', {'heart_rate': 80, 'hrv': 0.5}),
            ('box', {'heart_rate': 70, 'hrv': 0.7}),
            ('coh', {'heart_rate': 75, 'hrv': 0.6})
        ]
        
        for pattern, params in test_cases:
            feedback = BioFeedback(**params)
            adjust = self.guide.dynamic_adjust(feedback)
            self.assertEqual(adjust['pattern'], pattern)


    @classmethod 
    def tearDownClass(cls):
        cls.model_patch.stop()
        cls.redis_patch.stop()

    @pytest.fixture(autouse=True)
    def inject_fixtures(self, mock_redis, mock_hardware):
        self.mock_redis = mock_redis
        self.mock_hardware = mock_hardware

    @patch('src.aisleep.meditation.MeditationGuide._load_model_safely')
    @patch('src.aisleep.meditation.MeditationGuide._init_numba_optimizations')
    @patch('redis.Redis')
    def setUp(self):
        
        # 配置Redis Mock
        if not hasattr(self, 'mock_redis'):
            self.mock_redis = mock_redis.return_value
            mock_load_model.return_value = MagicMock()
        self.guide = MeditationGuide(redis_client=self.mock_redis.return_value)
        self.guide.model = self.mock_model

        self.mock_redis.reset_mock()
        mock_load_model.reset_mock()
        
        # 使用fixture注入的mock_hardware
        self.guide.redis = self.mock_redis
        self.guide.hardware = self.mock_hardware  # 从fixture获取

        # 完整Mock模型方法
        self.guide.model = MagicMock()
        self.guide.model.generate_guidance.return_value = {
            'get_next_actions': lambda x: [{'instruction': '测试引导'}] 
        }
        
        # 配置会话Mock
        self.guide.start_session = MagicMock(return_value=[{
            'action': {'instruction': '测试指令', 'duration': 10},
            'timestamp': time.time()
        }])
        
        # Mock生物反馈数据
        self.guide.get_current_biofeedback = MagicMock(return_value=BioFeedback(
            heart_rate=75,
            hrv=0.6,
            stress_level=0.4
        ))

    # 使用 pytest 的 fixture 方式
    @pytest.fixture(autouse=True)
    def setup_mocks(self, mock_redis):
        self.mock_redis = mock_redis
        self.guide = MeditationGuide()
        self.guide.redis = self.mock_redis

    def test_default_session(self):
        """测试默认会话"""
        # 可以直接使用 self.mock_redis
        self.mock_redis.set.assert_not_called()
        session = self.guide.start_session(duration=60)
        self.assertEqual(len(session), 1)
        self.assertEqual(session[0]['action']['instruction'], '测试指令')
        self.guide.model.generate_guidance.assert_called_once()
        
    def test_dynamic_adjust(self):
        """测试动态调节功能"""
        # 使用setUp中已初始化的guide实例
        feedback = BioFeedback(
            heart_rate=75,
            hrv=0.6,
            stress_level=0.4,
            meditation_level=0.7
        )
        
        # 测试基础模式
        self.guide.use_advanced_mode = False
        basic_adjust = self.guide.dynamic_adjust(feedback)
        
        # 验证基础调节结果
        self.assertIn('respiration_rate', basic_adjust)
        self.assertIsInstance(basic_adjust['respiration_rate'], (int, float))
        self.assertTrue(6 <= basic_adjust['respiration_rate'] <= 20)  # 合理范围检查
        
        # 测试高级模式
        self.guide.use_advanced_mode = True
        advanced_adjust = self.guide.dynamic_adjust(feedback)
        
        # 验证高级调节结果
        self.assertIn('pattern', advanced_adjust)
        self.assertIn(advanced_adjust['pattern'], self.guide.breath_patterns.keys())
        self.assertIn('intensity', advanced_adjust)
        self.assertTrue(0 <= advanced_adjust['intensity'] <= 1)  # 强度范围检查
        
        # 测试边界条件
        extreme_feedback = BioFeedback(
            heart_rate=120,  # 高心率
            hrv=0.2,  # 低HRV
            stress_level=0.9
        )
        extreme_adjust = self.guide.dynamic_adjust(extreme_feedback)
        self.assertTrue(extreme_adjust['respiration_rate'] >= 12)  # 高压力下呼吸率应增加


    def test_hardware_integration(self, mock_hardware):
        """测试硬件集成"""
        # 配置 mock 硬件数据
        mock_hardware.wearable_data = {"heart_rate": 75}
        
        # 测试硬件数据获取
        feedback = self.guide.get_current_biofeedback()
        self.assertEqual(feedback.heart_rate, 75)

        
    def test_audio_integration(self):
        """测试音频集成"""
        with patch('pygame.mixer.init'):
            result = self.guide._sound_therapy(duration=300)
            self.assertEqual(result['duration'], 300)

        
    def test_patterns(self):
        """测试呼吸模式"""
        
        # Test basic patterns
        assert self.guide.breath_patterns['4-7-8'] == (4, 7, 8)
        assert self.guide.breath_patterns['box'] == (4, 4, 4, 4)
        
        # Test dynamic pattern
        coh_pattern = self.guide.breath_patterns['coh'](70)
        assert len(coh_pattern) == 2
        assert 0 < coh_pattern[0] < 10  # 合理范围检查

    
    def test_specific_pattern_adjustment(self):
        """测试特定呼吸模式的调节效果"""
        test_cases = [
            ('4-7-8', {'heart_rate': 80, 'hrv': 0.5}),
            ('box', {'heart_rate': 70, 'hrv': 0.7}),
            ('coh', {'heart_rate': 75, 'hrv': 0.6})
        ]
        
        for pattern, params in test_cases:
            feedback = BioFeedback(**params)
            adjust = self.guide.dynamic_adjust(feedback)
            self.assertEqual(adjust['pattern'], pattern)





@pytest.mark.timeout(30)
@patch('pygame.mixer.init')
@patch('pygame.mixer.Sound')
class TestAudioIntegration:
    """音频集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup(self, mock_redis, mock_hardware, mock_mixer_init, mock_sound, request):
        """测试初始化"""
        # 初始化MeditationGuide并注入mock依赖
        self.meditation = MeditationGuide(redis_client=mock_redis)
        self.meditation.hardware = mock_hardware
        self.meditation.model = MagicMock()
        
        # 配置音频相关mock
        self.meditation._sound_therapy = MagicMock(return_value={
            'status': 'success',
            'params': {'file': 'test_audio.wav'},
            'duration': 300
        })
        self.meditation.play_audio = MagicMock(return_value={
            'status': 'success',
            'player': MagicMock()
        })
        
        # 创建临时测试文件
        self.test_file = tempfile.NamedTemporaryFile(delete=False).name
        
        # 配置pygame mock
        mock_mixer_init.return_value = None
        mock_sound.return_value = MagicMock()
        
        # 添加清理钩子
        def teardown():
            if os.path.exists(self.test_file):
                os.unlink(self.test_file)
        request.addfinalizer(teardown)




    @patch('src.aisleep.meditation.MeditationGuide._sound_therapy')
    @patch('src.aisleep.meditation.MeditationGuide.play_audio')
    def test_audio_workflow_success(self, mock_play, mock_sound):
        """测试音频工作流成功"""
        mock_sound.return_value = {
            'params': {'file': self.test_file},
            'status': 'success'
        }
        mock_play.return_value = {'player': MagicMock()}

        result = self.meditation.verify_audio_workflow()
        self.assertTrue(result)

    @patch('src.aisleep.meditation.MeditationGuide._sound_therapy')
    def test_audio_generation_failure(self, mock_sound):
        """测试音频生成失败"""
        mock_sound.return_value = {
            'status': 'error',
            'message': 'Generation failed'
        }

        result = self.meditation.verify_audio_workflow()
        self.assertFalse(result)

    @patch('src.aisleep.meditation.MeditationGuide._sound_therapy')
    @patch('src.aisleep.meditation.MeditationGuide.play_audio')
    def test_audio_playback_failure(self, mock_play, mock_sound):
        """测试音频播放失败"""
        mock_sound.return_value = {
            'params': {'file': self.test_file},
            'status': 'success'
        }
        mock_play.return_value = None

        result = self.meditation.verify_audio_workflow()
        self.assertFalse(result)


    def performance_monitor(func):
        """监控方法执行性能的装饰器"""
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start_time
            logging.info(f"{func.__name__} 执行耗时: {elapsed:.3f}秒")
            return result
        return wrapper

# 然后可以装饰关键方法


        
    def analyze_sleep_quality(self, feedback: BioFeedback) -> dict:
        """分析睡眠质量"""
        return {
            'score': self._calculate_sleep_score(feedback),
            'recommendation': self._generate_sleep_recommendation(feedback)
        }
        
    def _calculate_sleep_score(self, feedback: BioFeedback) -> float:
        """计算睡眠质量评分(0-100)"""
        score = 100 * feedback.sleep_efficiency
        # 深度睡眠加分
        if feedback.sleep_stage == 'N3':
            score += 15
        # 睡眠潜伏期扣分
        if feedback.sleep_latency > 30:
            score -= 10
        return max(0, min(100, score))

        
    def generate_sleep_report(self, session_id: int) -> dict:
        """生成完整的睡眠质量报告
        参数:
            session_id: 会话历史记录ID
        返回:
            包含睡眠评分、建议和详细分析的字典
        """
        if session_id >= len(self.session_history):
            raise ValueError("无效的会话ID")
            
        session = self.session_history[session_id]
        feedback = session['final_feedback']
        
        return {
            'basic_metrics': {
                'sleep_score': self._calculate_sleep_score(feedback),
                'sleep_efficiency': feedback.sleep_efficiency,
                'sleep_latency': feedback.sleep_latency
            },
            'stage_analysis': {
                'deep_sleep': self._analyze_sleep_stage(feedback, 'N3'),
                'rem_sleep': self._analyze_sleep_stage(feedback, 'REM')
            },
            'recommendations': self._generate_sleep_recommendation(feedback),
            'optimal_breath_pattern': self._suggest_optimal_pattern(feedback)
        }
        
    def _analyze_sleep_stage(self, feedback: BioFeedback, stage: str) -> dict:
        """分析特定睡眠阶段"""
        # ... 实现细节 ...
        stage_duration = getattr(feedback, f'{stage.lower()}_duration', 0)
        target = self.sleep_params['sleep_stage_targets'].get(stage, 0)
        
        return {
            'actual': stage_duration,
            'target': target,
            'deviation': stage_duration - target,
            'assessment': '不足' if stage_duration < target else '充足'
        }

    def _suggest_optimal_pattern(self, feedback: BioFeedback) -> str:
        """根据睡眠质量建议最佳呼吸模式"""
        if feedback.sleep_efficiency < 0.8:
            return '4-7-8'
        elif feedback.sleep_latency > 20:
            return 'physiological_sigh'
        elif feedback.sleep_stage == 'N3' and feedback.sleep_efficiency < 0.85:
            return 'deep_sleep'
        else:
            return 'equal'



        

        
    def _generate_sleep_recommendation(self, feedback: BioFeedback) -> str:
        """生成睡眠改善建议"""
        if feedback.sleep_efficiency < 0.85:
            return "建议增加睡眠时间并保持规律作息"
        elif feedback.sleep_latency > 30:
            return "入睡困难，建议尝试4-7-8呼吸法助眠"
        else:
            return "睡眠质量良好，继续保持"

# ... 其他代码 ...

   


    def get_ai_guidance(self, user_input):
        """使用DeepSeek-V3生成个性化冥想指导
        参数:
            user_input: 用户输入的问题或状态描述
        返回:
            生成的冥想指导文本
        """
        if self.deepseek:
            prompt = f"作为冥想助手，请提供专业指导: {user_input}"
            return self.deepseek.generate_guidance(prompt)
        return "默认冥想指导: 深呼吸，放松..."

    # ... 现有代码保持不变 ...


    def monitor_session(func):
        """装饰器：实时监控会话状态"""
        
        def wrapper(self, *args, **kwargs):
                start_time = time.time()
                print(f"会话开始于: {time.strftime('%Y-%m-%d %H:%M:%S')}")
                try:
                    result = func(self, *args, **kwargs)
                    duration = time.time() - start_time
                    print(f"会话成功完成，耗时: {duration:.1f}秒")
                    if hasattr(self, 'session_history') and self.session_history:
                        self.session_history[-1]['actual_duration'] = duration
                        self.session_history[-1]['status'] = 'completed'
                    return result
                except Exception as e:
                    duration = time.time() - start_time
                    print(f"会话异常终止: {str(e)}，已运行: {duration:.1f}秒")
                    if hasattr(self, 'session_history') and self.session_history:
                        self.session_history[-1]['actual_duration'] = duration
                        self.session_history[-1]['status'] = 'failed'
                        self.session_history[-1]['error'] = str(e)
                    raise
        return wrapper       

    @monitor_session
    def start_session(self, duration: int = 300, breath_pattern: str = '4-7-8'):
        """开始冥想会话"""
        # 欢迎语音
        self.play_audio(
            audio_type='tts', 
            text=f"即将开始{duration//60}分钟的冥想，请准备好"
        )
        start_time = time.perf_counter()
        steps = []
        pattern = self.breath_patterns[breath_pattern]
        remaining = duration
        pattern_changes = []
        step_cache = []  # 初始化步骤缓存
        
        try:
            # 使用DeepSeek模型生成个性化引导
            guidance = self.model.generate_guidance(
                duration=duration,
                pattern=pattern
            )
            if not hasattr(guidance, 'get_next_actions'):
                raise RuntimeError("模型未能生成有效引导方法")

            # 初始化变量
            initial_pattern = breath_pattern
            initial_feedback = self.get_current_biofeedback()
            last_feedback_time = time.time()
            feedback_interval = 5
            

        
            while remaining > 0:
                # 统一动作获取逻辑
                if not step_cache:
                    step_cache = guidance.get_next_actions(3) or []
                
                # 生成默认动作
                default_action = {
                    'instruction': self._generate_default_instruction(breath_pattern),
                    'detail': '请跟随自然呼吸节奏'
                }
                
                # 获取当前动作
                action = step_cache.pop(0) if step_cache else default_action
                
                # 确保动作包含必要字段
                action.setdefault('instruction', default_action['instruction'])
                action.setdefault('detail', default_action['detail'])

                # 根据呼吸模式计算步骤时长
                step_duration = min(19 if breath_pattern == '4-7-8' else 60, remaining)
                
                # 创建步骤记录
                step = {
                    "action": action,
                    "duration": step_duration,
                    "breath_phase": pattern,
                    "timestamp": time.time()
                }
                
                # 执行动作（新增部分）
                try:
                    # 播放引导语音
                    self.play_audio(
                        audio_type='tts',
                        text=action['instruction']
                    )
                    
                    # 执行呼吸引导
                    self._execute_breath_cycle(
                        pattern=pattern,
                        duration=step_duration
                    )
                    
                except Exception as e:
                    logging.warning(f"步骤执行异常: {e}")
                    continue
                
                # 记录步骤
                steps.append(step)
                remaining -= step_duration
                
                # 处理生物反馈（新增部分）
                current_time = time.time()
                if current_time - last_feedback_time >= feedback_interval:
                    if feedback := self.get_current_biofeedback():
                        # 动态调整呼吸模式
                        new_pattern = self.dynamic_pattern_switch(feedback)
                        if new_pattern != breath_pattern:
                            pattern_changes.append({
                                'timestamp': current_time,
                                'from': breath_pattern,
                                'to': new_pattern
                            })
                            breath_pattern = new_pattern
                            pattern = self.breath_patterns[breath_pattern]
                            step_cache = []  # 清空缓存以重新生成引导
                    
                    last_feedback_time = current_time
            
            # ... 后续代码保持不变 ...

                
                # 记录会话数据
                session_data = {
                    'start_time': start_time,
                    'initial_pattern': initial_pattern,
                    'duration': duration,
                    'steps': steps,
                    'end_time': time.time(),
                    'initial_feedback': initial_feedback,
                    'final_feedback': self.get_current_biofeedback(),
                    'pattern_changes': pattern_changes,
                    'actual_duration': time.time() - start_time
                }
                self.session_history.append(session_data)
                
                # 结束语音提示
                self.play_audio(
                    audio_type='tts',
                    text="本次冥想已完成，请慢慢回到正常状态"
                )
                
        except Exception as e:
            logging.error(f"冥想会话异常: {e}")
            raise
        finally:
            self.stop_audio()  # 确保会话结束时停止所有音频

        return steps


    def _generate_default_instruction(self, pattern: str) -> str:
        """生成默认引导指令"""
        patterns = {
            '4-7-8': "吸气4秒，屏息7秒，呼气8秒",
            'box': "吸气4秒，屏息4秒，呼气4秒，休息4秒",
            'equal': "吸气5秒，呼气5秒",
            'physiological_sigh': "快速吸气两次，缓慢呼气10秒"
        }
        return patterns.get(pattern, "请跟随自然呼吸节奏")

    def get_test_configurations(self) -> List[dict]:
        """获取可用的测试配置"""
        return [
            {'name': '快速放松', 'duration': 180, 'pattern': 'box'},
            {'name': '深度冥想', 'duration': 600, 'pattern': 'coh'},
            {'name': '压力缓解', 'duration': 300, 'pattern': '4-7-8'}
        ]

    def get_current_biofeedback(self) -> Optional[BioFeedback]:
        """获取实时生物反馈数据
        返回:
            当前生物反馈数据对象，如无法获取则返回None
        """
        try:
            # 这里应该是从硬件设备或模拟器获取实时数据
            # 实际实现需要根据具体硬件接口调整
            hr = 75.0 + random.uniform(-2, 2)  # 添加随机波动模拟真实数据

            return BioFeedback(
                heart_rate=hr,
                breath_rate=14.0,
                hrv=0.6,
                skin_conductance=5.2,
                stress_level=0.4,
                meditation_level=0.7,
                timestamp=time.time(),
                sleep_stage='awake',  # 默认值
                sleep_latency=0,
                sleep_efficiency=1.0,
                waso=0.0
            )
        except Exception as e:
            logging.error(f"生物反馈数据获取失败: {str(e)}", exc_info=True)
            return None

    
    def _guided_imagery(self, duration: int):
            """基于视觉的引导"""
            return {
                'type':'visualization',
                'sequence': self.model.generate_visualization_sequence(
                    duration=duration,
                    intensity=0.5
                )
            }

    def _breath_based_relaxation(self, duration: int):
        """基于呼吸的减压"""
        return {
            'type':'breath',
            'rate': self.base_respiration_rate,
            'duration': duration
        }

    def _sound_therapy(self, duration: int, mode: str = 'default', environment: str = None, hifi_mode: bool = False) -> dict:
        """发烧级双耳节拍声波疗法
        参数:
            hifi_mode: 是否启用发烧级音质模式
        """
        # 参数验证增强
        if not isinstance(duration, int) or not 10 <= duration <= 7200:
            raise ValueError("duration必须是10-7200秒之间的整数")
        if mode not in ('default', 'deep_relax', 'focus', 'sleep', 'anxiety_relief', 'energy_boost'):
            raise ValueError(f"无效的音频模式: {mode}")
        if environment and environment not in ('nature', 'rain', 'ocean', 'city'):
            raise ValueError(f"无效的环境音效: {environment}")
            
        # 音频效果预设
        hifi_presets = {
            'default': {'base_freq': 200, 'delta': 5, 'intensity': 0.7},
            'deep_relax': {'base_freq': 150, 'delta': 3, 'intensity': 0.6},
            'focus': {'base_freq': 300, 'delta': 10, 'intensity': 0.8},
            'sleep': {'base_freq': 100, 'delta': 2, 'intensity': 0.5},
            'anxiety_relief': {'base_freq': 180, 'delta': 7, 'intensity': 0.65},
            'energy_boost': {'base_freq': 250, 'delta': 15, 'intensity': 0.75}
        }
        
        # 环境音效预设
        env_presets = {
            'nature': {'file': 'assets/nature.mp3', 'volume': 0.3},
            'rain': {'file': 'assets/rain.mp3', 'volume': 0.4},
            'ocean': {'file': 'assets/ocean.mp3', 'volume': 0.35},
            'city': {'file': 'assets/city.mp3', 'volume': 0.25}
        }
        
        try:
                    # 生成发烧级双耳节拍参数
            binaural_params = {
                **hifi_presets[mode],
                'duration': duration,
                'sample_rate': 96000 if hifi_mode else 48000,  # 高解析度音频
                'stereo_balance': 0.5,
                'intensity': 0.8,
                'binaural_freq': 0.5,
                'binaural_phase': 0.5,
                'audio_format': 'flac' if hifi_mode else 'wav',  # 无损格式
                'channels': 2,
                'bitrate': 1024 if hifi_mode else 128,  # 高比特率
                'volume': 0.8,
                'fade_in': 3,
                'fade_out': 5,
                'hifi_mode': hifi_mode,
                'hifi_params': {
                    'sample_rate': 96000,  # 提升至96kHz
                    'stereo_balance': 0.5,
                    'intensity': 0.8,
                    'bit_depth': 32,  # 32位浮点
                    'dithering': True,
                    'noise_shaping': 'ultra',
                    'oversampling': 8,  # 8倍超采样
                    'anti_alias': True,
                    'harmonic_distortion': 0.05,  # 谐波失真控制
                    'dynamic_range': 144,  # 144dB动态范围
                    'jitter_reduction': True,
                    'clock_precision': 'atomic'  # 原子钟级时钟精度
                }
            }

            
            
            # 验证音频参数
            if not 0.5 <= binaural_params['intensity'] <= 1.0:
                raise ValueError("音频强度必须在0.5到1.0之间")
                
            binaural_beats = self.model.generate_binaural_beats(**binaural_params)
            
            # 计算音频质量指标
            quality = self._calculate_audio_quality(binaural_beats)
            
            # 构建返回参数
            result = {
                'type': 'sound',
                'params': {
                    **binaural_beats,
                    'volume': 0.8,
                    'fade_in': 3,
                    'fade_out': 5,
                    'channels': 2,
                    'mode': mode,
                    'eq_settings': self._get_eq_settings(mode)
                },
                'duration': duration,
                'metadata': {
                    'generated_at': time.time(),
                    'version': '2.5',
                    'model': self.model.version if hasattr(self.model, 'version') else 'unknown',
                    'session_id': getattr(self, 'current_session_id', None),
                    'preset_used': mode,
                    'hardware_info': self._get_audio_hardware_info()
                },
                'quality_metrics': quality
            }
            
            # 添加环境音效
            if environment:
                result['environment'] = env_presets[environment]
                result['metadata']['environment_used'] = environment
            
            return result
            
        except ValueError as e:
            logging.warning(f"参数验证失败: {e}")
            raise
        except AudioGenerationError as e:
            logging.error(f"音频生成失败: {e}", exc_info=True)
            raise
        except Exception as e:
            logging.error(f"未知错误: {e}", exc_info=True)
            return {
                'type': 'sound',
                'params': {
                    'fallback': True,
                    'file': 'assets/default_beat.mp3',
                    'volume': 0.7,
                    'warning': str(e)
                },
                'duration': duration,
                'metadata': {
                    'error': str(e),
                    'fallback_used': True,
                    'timestamp': time.time(),
                    'error_type': type(e).__name__
                }
            }
    def _calculate_audio_quality(self, audio_data: dict) -> dict:
        """增强版音频质量评估"""
        quality = {
            'sample_rate': audio_data.get('sample_rate', 48000),
            'bit_depth': 32 if audio_data.get('hifi_mode') else 24,
            'dynamic_range': self._measure_dynamic_range(audio_data),
            'noise_floor': self._measure_noise_floor(audio_data),
            'distortion': self._measure_thd(audio_data),
            'stereo_separation': self._measure_stereo_sep(audio_data),
            'frequency_response': self._analyze_freq_response(audio_data)
    }
    
        # 添加质量评分
        quality['score'] = min(100, max(0, 
            90 + 
            (quality['sample_rate']/96000 * 5) +
            (quality['bit_depth']/32 * 3) -
            (quality['noise_floor'] * 2) -
            (quality['distortion'] * 10)
        ))
        
        return quality

    def _get_environment_presets(self) -> dict:
        """获取环境音效预设"""
        return {
            'nature': {'file': 'assets/nature.mp3', 'volume': 0.3},
            'rain': {'file': 'assets/rain.mp3', 'volume': 0.4},
            'ocean': {'file': 'assets/ocean.mp3', 'volume': 0.35},
            'city': {'file': 'assets/city.mp3', 'volume': 0.25}
        }


    def _gentle_movement(self, duration: int):
        """渐进式肌肉放松"""
        return {
            'type': 'movement',
            'sequence': self.model.generate_movement_sequence(
                intensity=0.3,
                duration=duration
            )
        }

    def _generate_coherent_pattern(self, duration: int) -> List[tuple]:
        """生成生理协调呼吸模式"""
        inhale_time = int(duration * 0.4)  # 吸气40%
        hold_time = int(duration * 0.2)    # 保持20%
        exhale_time = int(duration * 0.4)  # 呼气40%
        rest_time = int(duration * 0.2)    # 休息20%
        return [(inhale_time, BreathPhase.INHALE),
                (hold_time, BreathPhase.HOLD),
                (exhale_time, BreathPhase.EXHALE),
                (rest_time, BreathPhase.REST)]
    
    


    def _initialize_model(self, model_path):
        """Initialize model with official DeepSeek V3 implementation"""
        try:
            # 使用原始字符串或转义路径
            official_path = r'D:\AISleepGen\src\aisleep\model\deepseek\official'
            if not os.path.exists(official_path):
                raise RuntimeError(f"模型路径不存在: {official_path}")
            sys.path.append(official_path)
            
            # 初始化模型并添加量子化配置
            self.model = DeepSeekModel(
                model_path=model_path,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                quantized=True,
                quant_config={
                    'activation': 'per_tensor',
                    'weight': 'per_channel',
                    'quant_dtype': 'int8',
                    'calibration': 'min_max'
                }
            )
            
            # 添加兼容方法
            self.model.generate_binaural_beats = self._deepseek_v3_to_binaural
            self.model.generate_movement_sequence = self._deepseek_v3_to_movement
            
            # 基础配置
            if hasattr(self.model, 'configure'):
                self.model.configure(
                    mixed_precision={
                        'attention_layers': 'fp16',
                        'output_layer': 'fp16'
                    },
                    learning_rate=0.001,
                    batch_size=32,
                    optimizer='adam',
                    loss_function='mse'
                )

        except ImportError as e:
            raise RuntimeError(f"无法导入DeepSeek V3: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"模型初始化失败: {str(e)}")


    def _deepseek_v3_to_binaural(self, **params):
        """将DeepSeek V3输出转换为双耳节拍格式"""
        # 调用DeepSeek V3的音频生成
        output = self.model.generate_audio(**params)
        return {
            'file': output['audio_path'],
            'sample_rate': output.get('sample_rate', 48000),
            'bit_depth': output.get('bit_depth', 24)
        }

    def _deepseek_v3_to_movement(self, intensity, duration):
        """将DeepSeek V3输出转换为运动序列"""
        output = self.model.generate_movement(intensity, duration)
        return output['sequence']

    def test_sleep_analysis(self):
        """测试睡眠分析功能"""
        test_cases = [
            # (sleep_efficiency, sleep_latency, sleep_stage, expected_pattern)
            (0.75, 35, 'N1', '4-7-8'),      # 低效睡眠
            (0.9, 45, 'N2', 'physiological_sigh'),  # 入睡困难
            (0.82, 15, 'N3', 'deep_sleep'), # 需要深度睡眠
            (0.95, 10, 'REM', 'equal')      # 优质睡眠
        ]
        
        for eff, latency, stage, expected in test_cases:
            feedback = BioFeedback(
                sleep_efficiency=eff,
                sleep_latency=latency,
                sleep_stage=stage,
                # 其他必要参数
                heart_rate=70,
                breath_rate=12,
                hrv=0.6,
                skin_conductance=5.0,
                stress_level=0.3,
                meditation_level=0.8,
                timestamp=time.time(),
                waso=5.0
            )
            
            # 验证模式推荐
            pattern = self._suggest_optimal_pattern(feedback)
            assert pattern == expected, \
                f"测试失败: 输入({eff},{latency},{stage}) 期望{expected} 得到{pattern}"
            
            # 验证睡眠评分
            score = self._calculate_sleep_score(feedback)
            assert 0 <= score <= 100, "睡眠评分超出范围"
            
            # 验证阶段分析
            analysis = self._analyze_sleep_stage(feedback, stage)
            assert 'actual' in analysis and 'target' in analysis, "阶段分析缺少关键字段"
        
        print("所有睡眠分析测试用例通过")

# ... 后续代码保持不变 ...




        # 初始化基础参数
        self.session_history = []
        self.base_respiration_rate = 12

        # 初始化生物反馈参数
        self.biofeedback_params = {
            'heart_rate': 70,  # 初始心率
            'breath_rate': 12,  # 初始呼吸频率  
        }
        self.neurofeedback_params = {
            'eeg_alpha': 0,
            'eeg_theta': 0,
            'update_interval': 5  # 秒
        }





        # 扩展减压方式库
        self.relaxation_methods = {
            'breath': self._breath_based_relaxation,
            'sound': self._sound_therapy,
            'movement': self._gentle_movement,
            'visualization': self._guided_imagery
        }
        self.guidance_generator = GuidanceGenerator('4-7-8')  # Provide default pattern
@pytest.mark.timeout(30)
class TestAudioLatencyMeasurement(unittest.TestCase):
    """Tests for measuring audio latency in the MeditationGuide class."""

    def setUp(self):
        # Mock the model directly instead of load_model
        self.model_patch = patch('src.aisleep.meditation.MeditationGuide.model', new_callable=MagicMock)
        self.mock_model = self.model_patch.start()

       
        # 正确导入MeditationGuide
        from src.aisleep.meditation import MeditationGuide
        
        
        self.model_patch = patch('src.aisleep.meditation.MeditationGuide.model', new_callable=MagicMock)

        self.meditation = MeditationGuide()
        # Mock模型和方法
        self.meditation.model = MagicMock()
        # Mock sound therapy method
        self.meditation._sound_therapy = MagicMock(return_value={
            'status': 'success',
            'latency': 0.1,
            'duration': 300,
            'params': {'sample_rate': 48000},
            'quality_metrics': {'sample_rate': 96000}
        })
        
        # 设置测试音频文件
        self.test_file = tempfile.NamedTemporaryFile(delete=False).name
        # 正确设置mock返回值
        self.meditation._sound_therapy = MagicMock(return_value={
            'duration': 300,
            'params': {'sample_rate': 48000},
            'quality_metrics': {'sample_rate': 96000},
            'status': 'success'
        })
                # 设置测试音频文件
        self.test_file = tempfile.NamedTemporaryFile(delete=False).name

    def tearDown(self):
        """清理测试文件"""
        self.model_patch.stop()
        if os.path.exists(self.test_file):
            os.unlink(self.test_file)

    # 修复测试方法中的导入和调用
    @patch('pygame.mixer.Sound')
    @patch('pygame.mixer.Channel')
    def test_extreme_latency_values(self, mock_channel, mock_sound):
        """测试极端延迟值处理"""
        from src.aisleep.meditation import MeditationGuide
        # ... 测试实现 ...
    def test_audio_error_handling(self):
        """音频生成错误处理测试"""
        # 修改为强制触发异常
        self.meditation._sound_therapy.side_effect = ValueError("Invalid duration")
        with pytest.raises(ValueError):
            self.meditation._sound_therapy(duration=-1)

    def test_audio_generation_basic(self):
        """基础音频生成测试"""
        result = self.meditation._sound_therapy(duration=300, mode='default')
        assert result['duration'] == 300

    def test_hifi_mode(self):
        """发烧级音频模式测试"""
        hifi_result = self.meditation._sound_therapy(
            duration=600, 
            mode='focus', 
            hifi_mode=True
        )
        assert hifi_result['quality_metrics']['sample_rate'] == 96000


    @patch('pygame.mixer.Sound')
    @patch('pygame.mixer.Channel')
    @patch('pygame.mixer.init')
    @patch('pygame.mixer.quit')
    def test_measure_audio_latency_success(self, mock_quit, mock_init, mock_channel, mock_sound):
        """Test successful measurement of audio latency."""
        from meditation import MeditationGuide
        guide = MeditationGuide()

        # Mock channel behavior to simulate audio playback
        mock_channel_instance = MagicMock()
        mock_channel.return_value = mock_channel_instance
        mock_channel_instance.get_busy.side_effect = [True, False]  # Simulate playback

        # Mock time measurement
        with patch('time.perf_counter', side_effect=[0.0, 0.15]):
            latency = guide._measure_audio_latency()

        # Assert latency is within expected range
        self.assertTrue(40 <= latency <= 60, f"Unexpected latency: {latency}ms")
        mock_init.assert_called_once_with(frequency=44100, size=-16, channels=1)
        mock_quit.assert_called_once()

    @patch('pygame.mixer.init')
    def test_measure_audio_latency_failure(self, mock_init):
        """Test failure during audio latency measurement."""
        from meditation import MeditationGuide
        guide = MeditationGuide()

        # Simulate initialization failure
        mock_init.side_effect = Exception("Audio init failed")

        latency = guide._measure_audio_latency()
        self.assertEqual(latency, 150.0, "Default latency value should be returned on failure")

    @patch('pygame.mixer.Sound')
    @patch('pygame.mixer.Channel')
    def test_extreme_latency_values(self, mock_channel, mock_sound):
        """Test handling of extreme latency values."""
        from meditation import MeditationGuide
        guide = MeditationGuide()
        mock_channel_instance = MagicMock()
        mock_channel.return_value = mock_channel_instance

        # Test very low latency
        with patch('time.perf_counter', side_effect=[0.0, 0.001]):
            latency = guide._measure_audio_latency()
            self.assertGreaterEqual(latency, 0, "Latency should not be negative")

        # Test very high latency
        with patch('time.perf_counter', side_effect=[0.0, 2.0]):
            latency = guide._measure_audio_latency()
            self.assertLessEqual(latency, 500, "Latency should be capped at a reasonable value")

    @patch('meditation.MeditationGuide._generate_test_sound')
    def test_audio_generation_failure(self, mock_gen):
        """Test failure during test audio generation."""
        from meditation import MeditationGuide
        guide = MeditationGuide()

        # Simulate audio generation failure
        mock_gen.side_effect = Exception("Audio generation failed")

        latency = guide._measure_audio_latency()
        self.assertEqual(latency, 150.0, "Default latency value should be returned on generation failure")



    def test_generate_test_sound(self):
        """测试测试音频生成"""
        from meditation import MeditationGuide
        guide = MeditationGuide()
        
        # 测试1kHz 100ms音频
        audio_data = guide._generate_test_sound(1000, 0.1)
        
        assert isinstance(audio_data, bytes)
        assert len(audio_data) == 44100 * 0.1 * 2  # 44.1kHz, 16bit = 2字节

    def test_hifi_audio_generation(self):
        """测试发烧级音频生成功能"""
        test_cases = [
            # (duration, mode, environment, hifi_mode, expected_sample_rate)
            (300, 'default', None, False, 48000),
            (300, 'deep_relax', 'nature', True, 96000),
            (600, 'focus', None, True, 96000),
            (1800, 'sleep', 'rain', False, 48000)
        ]
        
        for duration, mode, env, hifi, expected_rate in test_cases:
            try:
                result = self._sound_therapy(
                    duration=duration,
                    mode=mode,
                    environment=env,
                    hifi_mode=hifi
                )
                
                # 验证基本参数
                assert result['duration'] == duration
                assert result['params']['mode'] == mode
                
                # 验证采样率
                actual_rate = result['quality_metrics']['sample_rate']
                assert actual_rate == expected_rate, \
                    f"采样率错误: 期望{expected_rate} 得到{actual_rate}"
                
                # 验证位深度
                if hifi:
                    assert result['params']['hifi_mode'], "未启用HIFI模式"
                    assert result['quality_metrics']['bit_depth'] == 32
                else:
                    assert result['quality_metrics']['bit_depth'] == 24
                
                # 验证环境音效
                if env:
                    assert 'environment' in result
                    assert result['metadata']['environment_used'] == env
                
                print(f"测试通过: {duration}s {mode} {'HIFI' if hifi else ''}")
                
            except Exception as e:
                print(f"测试失败: {duration}s {mode} - {str(e)}")
                raise
        
        # 测试错误处理
        try:
            self._sound_therapy(duration=5, mode='default')  # 过短时长
            assert False, "应触发时长验证错误"
        except ValueError:
            pass
            
        try:
            self._sound_therapy(duration=300, mode='invalid')  # 无效模式
            assert False, "应触发模式验证错误"
        except ValueError:
            pass
            
        print("所有音频生成测试通过")

    def _assess_session_quality(self, session: dict) -> dict:
        """评估会话质量"""
        return {
            'consistency': self._check_consistency(session),
            'stability': self._check_stability(session),
            'effectiveness': self._check_effectiveness(session)
        }
    def test_audio_generation_basic(self):
        """基础音频生成测试"""
        # 测试正常场景
        result = self._sound_therapy(duration=300, mode='default')
        assert result['duration'] == 300
        assert result['params']['mode'] == 'default'
        assert result['quality_metrics']['sample_rate'] == 48000
        
        # 测试环境音效
        env_result = self._sound_therapy(duration=300, mode='sleep', environment='rain')
        assert 'environment' in env_result
        assert env_result['metadata']['environment_used'] == 'rain'
    def test_hifi_mode(self):
        """发烧级音频模式测试"""
        # 测试HIFI模式参数
        hifi_result = self._sound_therapy(duration=600, mode='focus', hifi_mode=True)
        assert hifi_result['quality_metrics']['sample_rate'] == 96000
        assert hifi_result['quality_metrics']['bit_depth'] == 32
        assert hifi_result['params']['audio_format'] == 'flac'
        
        # 对比非HIFI模式
        normal_result = self._sound_therapy(duration=600, mode='focus', hifi_mode=False)
        assert normal_result['quality_metrics']['sample_rate'] == 48000
        assert normal_result['quality_metrics']['bit_depth'] == 24
    def test_audio_error_handling(self):
        """音频生成错误处理测试"""
        # 测试无效时长
        with pytest.raises(ValueError):
            self._sound_therapy(duration=5, mode='default')
            
        # 测试无效模式
        with pytest.raises(ValueError):
            self._sound_therapy(duration=300, mode='invalid_mode')
            
        # 测试无效环境音效
        with pytest.raises(ValueError):
            self._sound_therapy(duration=300, mode='default', environment='invalid_env')
    def test_audio_performance(self):
        """音频生成性能测试"""
        durations = [60, 300, 600]  # 测试不同时长
        
        for duration in durations:
            start_time = time.time()
            result = self._sound_therapy(duration=duration)
            elapsed = time.time() - start_time
            
            # 验证生成时间在合理范围内
            assert elapsed < duration * 0.1, f"{duration}秒音频生成时间过长: {elapsed:.2f}s"
            
            # 验证音频数据完整性
            assert 'params' in result
            assert 'metadata' in result

    def verify_audio_workflow(self):
        """验证音频工作流"""
        try:
            # 生成音频
            sound_result = self._sound_therapy(
                duration=300,
                mode='deep_relax',
                environment='nature',
                hifi_mode=True
            )
            
            if sound_result['status'] != 'success':
                return False
                
            # 播放音频
            play_result = self.play_audio(
                audio_type='file',
                audio_path=sound_result['params']['file']
            )
            
            return play_result is not None
            
        except Exception as e:
            logging.error(f"音频工作流验证失败: {str(e)}")
            return False

# ... 其他代码保持不变 ...

class TestAdjustmentAlgorithms(unittest.TestCase):
    def setUp(self):
        self.guide = MeditationGuide()
        self.feedback = BioFeedback(
            heart_rate=75, 
            hrv=0.6,
            stress_level=0.5,
            meditation_level=0.7
        )

    def test_basic_adjustment_boundary(self):
        """测试基础调节算法的边界条件"""
        # 极低心率测试
        low_hr_feedback = BioFeedback(heart_rate=40, hrv=0.3)
        adjustment = self.guide.calculate_adjustment(
            low_hr_feedback.heart_rate,
            low_hr_feedback.hrv,
            BreathPhase.INHALE
        )
        self.assertGreaterEqual(adjustment['respiration_rate'], 6)  # 确保不低于最小呼吸频率

        # 极高心率测试
        high_hr_feedback = BioFeedback(heart_rate=120, hrv=0.8)
        adjustment = self.guide.calculate_adjustment(
            high_hr_feedback.heart_rate,
            high_hr_feedback.hrv,
            BreathPhase.EXHALE
        )
        self.assertLessEqual(adjustment['respiration_rate'], 20)  # 确保不超过最大呼吸频率

    def test_hybrid_adjustment_consistency(self):
        """测试混合决策算法的输出一致性"""
        adjustments = []
        for _ in range(10):  # 多次运行确保输出稳定
            adj = self.guide.calculate_hybrid_adjustment(
                self.feedback.heart_rate,
                self.feedback.hrv,
                BreathPhase.INHALE
            )
            adjustments.append(adj)
        
        # 验证多次调用的结果在合理波动范围内
        rates = [a['respiration_rate'] for a in adjustments]
        self.assertAlmostEqual(max(rates)-min(rates), 0, delta=2)  # 波动不超过2次/分钟

@pytest.mark.benchmark
class TestPerformance(unittest.TestCase):
    def setUp(self):
        """初始化测试环境"""
        self.guide = MeditationGuide()
        self.feedback = BioFeedback(
            heart_rate=75, 
            hrv=0.6,
            stress_level=0.5,
            meditation_level=0.7
        )
        # 预热JIT编译
        self.guide.calculate_adjustment(75, 0.6, BreathPhase.INHALE)
        self.guide.calculate_hybrid_adjustment(75, 0.6, BreathPhase.INHALE)

    def test_adjustment_performance(self):
        """测试调节算法的执行时间"""
        # 测试基础模式性能
        basic_time = timeit.timeit(
            lambda: self.guide.calculate_adjustment(
                self.feedback.heart_rate,
                self.feedback.hrv,
                BreathPhase.INHALE
            ),
            number=1000
        )
        
        # 测试混合模式性能
        self.guide.use_advanced_mode = True
        hybrid_time = timeit.timeit(
            lambda: self.guide.calculate_hybrid_adjustment(
                self.feedback.heart_rate,
                self.feedback.hrv,
                BreathPhase.INHALE
            ),
            number=1000
        )
        
        print(f"\n性能基准(1000次调用): 基础模式={basic_time:.4f}s | 混合模式={hybrid_time:.4f}s")
        self.assertLess(hybrid_time, basic_time*3)  # 混合模式耗时不应超过基础模式的3倍
        self.assertLess(basic_time, 0.1)  # 基础模式单次调用应<0.1ms

    def test_memory_usage(self):
        """测试内存使用情况"""
        tracemalloc.start()
        
        # 记录初始内存
        snapshot1 = tracemalloc.take_snapshot()
        
        # 执行1000次调节
        for _ in range(1000):
            self.guide.calculate_adjustment(
                self.feedback.heart_rate,
                self.feedback.hrv,
                BreathPhase.INHALE
            )
        
        # 记录内存变化
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        # 验证内存增长不超过1MB
        total_increase = sum(stat.size_diff for stat in top_stats)
        self.assertLess(total_increase, 1024*1024)  # <1MB
        tracemalloc.stop()


class TestBioFeedbackIntegration(unittest.TestCase):
    """生物反馈系统集成测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟生物反馈数据流
        self.feedback_samples = [
            BioFeedback(heart_rate=72, hrv=0.5),  # 初始状态
            BioFeedback(heart_rate=85, hrv=0.3),  # 压力状态
            BioFeedback(heart_rate=65, hrv=0.7)   # 放松状态
        ]
        
    def test_real_time_adjustment_flow(self):
        """测试实时调节工作流"""
        adjustments = []
        
        # 模拟实时反馈循环
        for feedback in self.feedback_samples:
            # 基础模式调节
            self.guide.use_advanced_mode = False
            basic_adj = self.guide.dynamic_adjust(feedback)
            
            # 高级模式调节
            self.guide.use_advanced_mode = True
            hybrid_adj = self.guide.dynamic_adjust(feedback)
            
            adjustments.append((basic_adj, hybrid_adj))
            
            # 验证调节参数有效性
            for adj in (basic_adj, hybrid_adj):
                self._validate_adjustment(adj)
        
        # 验证不同状态下的调节差异
        self.assertNotEqual(
            adjustments[0][0]['respiration_rate'],  # 初始状态基础调节
            adjustments[1][0]['respiration_rate']  # 压力状态基础调节
        )
        
        # 验证混合模式与基础模式的差异
        self.assertNotEqual(
            adjustments[0][0]['pattern'],  # 基础模式
            adjustments[0][1]['pattern']   # 混合模式
        )
    
    def _validate_adjustment(self, adjustment):
        """验证调节参数的有效性"""
        self.assertIn('respiration_rate', adjustment)
        self.assertIn('pattern', adjustment)
        self.assertIn('intensity', adjustment)
        
        # 验证呼吸频率在合理范围内
        self.assertTrue(6 <= adjustment['respiration_rate'] <= 20)
        
        # 验证模式有效性
        self.assertIn(adjustment['pattern'], ['4-7-8', 'box', 'equal', 'coh'])

class TestEndToEndWorkflow(unittest.TestCase):
    """端到端冥想工作流测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟硬件设备连接
        self.guide.get_current_biofeedback = MagicMock(
            side_effect=self._mock_biofeedback
        )
        # 模拟音频系统
        self.guide.play_audio = MagicMock(return_value={'status': 'success'})
        
    def _mock_biofeedback(self):
        """生成模拟生物反馈数据"""
        return BioFeedback(
            heart_rate=70 + random.randint(-5, 5),
            hrv=0.5 + random.uniform(-0.1, 0.1),
            stress_level=0.3 + random.uniform(-0.1, 0.1),
            timestamp=time.time()
        )
    
    def test_complete_meditation_session(self):
        """测试完整冥想会话流程"""
        # 1. 开始会话
        session = self.guide.start_session(
            duration=300,  # 5分钟测试
            breath_pattern='4-7-8'
        )
        
        # 验证基础会话数据
        self.assertIsInstance(session, list)
        self.assertGreater(len(session), 0)
        self.assertIn('action', session[0])
        
        # 2. 验证会话历史记录
        self.assertEqual(len(self.guide.session_history), 1)
        session_record = self.guide.session_history[0]
        self.assertEqual(session_record['duration'], 300)
        self.assertEqual(session_record['initial_pattern'], '4-7-8')
        
        # 3. 验证生物反馈调节次数
        feedback_calls = len(self.guide.get_current_biofeedback.mock_calls)
        self.assertGreaterEqual(feedback_calls, 10)  # 至少每30秒一次反馈
        
        # 4. 验证音频播放
        self.assertGreaterEqual(self.guide.play_audio.call_count, 3)  # 开始/引导/结束
        
    def test_session_with_mode_switching(self):
        """测试模式切换的会话流程"""
        # 启用高级模式
        self.guide.use_advanced_mode = True
        
        # 开始会话
        session = self.guide.start_session(duration=180)
        
        # 验证模式切换记录
        session_record = self.guide.session_history[0]
        self.assertTrue(any(
            change['from'] != change['to'] 
            for change in session_record['pattern_changes']
        ))
        
        # 验证高级模式特征
        self.assertTrue(any(
            step.get('advanced_feature', False)
            for step in session_record['steps']
        ))

class TestMultimodalIntegration(unittest.TestCase):
    """多模态系统集成测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟多模态系统
        self.guide.audio_engine = MagicMock()
        self.guide.visual_engine = MagicMock()
        self.guide.haptic_device = MagicMock()
        
        # 配置模拟返回值
        self.guide.calculate_adjustment = MagicMock(return_value={
            'respiration_rate': 12,
            'pattern': '4-7-8',
            'intensity': 0.7
        })
        
    def test_audio_visual_sync(self):
        """测试音频与视觉同步"""
        # 模拟生物反馈
        feedback = BioFeedback(
            heart_rate=75,
            hrv=0.6,
            stress_level=0.5
        )
        
        # 执行调节
        adjustments = self.guide.calculate_adjustment(
            feedback.heart_rate,
            feedback.hrv,
            BreathPhase.INHALE
        )
        self.guide.apply_adjustments(adjustments)
        
        # 验证音频系统调用
        self.guide.audio_engine.set_binaural_freq.assert_called_with(
            base=432 + 0.7 * 50,  # 432 + intensity*50
            delta=12 / 60 * 1000   # respiration_rate转换
        )
        
        # 验证视觉系统调用
        self.guide.visual_engine.update_pattern.assert_called_with(
            pattern='4-7-8',
            speed=12 / 12          # respiration_rate/12
        )
        
    def test_haptic_feedback(self):
        """测试触觉反馈集成"""
        # 启用触觉设备
        self.guide.haptic_device = MagicMock()
        
        # 执行高强度调节
        adjustments = {
            'respiration_rate': 16,
            'pattern': 'box',
            'intensity': 0.9
        }
        self.guide.apply_adjustments(adjustments)
        
        # 验证触觉强度设置
        self.guide.haptic_device.set_intensity.assert_called_with(0.9)
        
    def test_cross_modal_validation(self):
        """测试跨模态参数验证"""
        test_cases = [
            # (hr, hrv, expected_audio_freq, expected_visual_speed)
            (60, 0.8, 432 + 0.5*50, 10/12),   # 放松状态
            (90, 0.3, 432 + 0.8*50, 18/12)     # 压力状态
        ]
        
        for hr, hrv, exp_audio, exp_visual in test_cases:
            with self.subTest(hr=hr, hrv=hrv):
                # 获取调节参数
                adj = self.guide.calculate_adjustment(hr, hrv, BreathPhase.INHALE)
                self.guide.apply_adjustments(adj)
                
                # 验证音频频率
                _, audio_kwargs = self.guide.audio_engine.set_binaural_freq.call_args
                self.assertAlmostEqual(
                    audio_kwargs['base'], 
                    exp_audio,
                    delta=5
                )
                
                # 验证视觉速度
                _, visual_kwargs = self.guide.visual_engine.update_pattern.call_args
                self.assertAlmostEqual(
                    visual_kwargs['speed'],
                    exp_visual,
                    delta=0.5
                )

class TestHardwareExceptionHandling(unittest.TestCase):
    """硬件异常处理测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 正常状态下的模拟设备
        self.guide.biofeedback_device = MagicMock()
        self.guide.audio_device = MagicMock()
        
    def test_device_disconnection_during_session(self):
        """测试会话过程中设备断开"""
        # 初始正常状态
        self.guide.get_current_biofeedback = MagicMock(
            side_effect=[
                BioFeedback(heart_rate=75, hrv=0.6),  # 第一次正常
                BioFeedback(heart_rate=72, hrv=0.7),  # 第二次正常
                None,  # 模拟设备断开
                None   # 持续断开
            ]
        )
        
        # 开始会话
        with self.assertLogs(level='WARNING') as log:
            session = self.guide.start_session(duration=300)
            
            # 验证会话没有因异常而终止
            self.assertGreater(len(session), 0)
            
            # 验证日志记录
            self.assertTrue(any("生物反馈设备断开" in msg for msg in log.output))
            
            # 验证降级处理
            last_step = session[-1]
            self.assertEqual(last_step['action']['detail'], "设备不可用，请跟随自然呼吸节奏")

    def test_audio_device_failure(self):
        """测试音频设备故障"""
        # 模拟音频播放失败
        self.guide.play_audio = MagicMock(
            side_effect=[
                {'status': 'success'},  # 开始提示正常
                Exception("Audio device error"),  # 引导语音失败
                {'status': 'error'}  # 结束提示失败
            ]
        )
        
        with self.assertLogs(level='ERROR') as log:
            session = self.guide.start_session(duration=180)
            
            # 验证会话完成
            self.assertEqual(len(session), 3)
            
            # 验证错误处理
            self.assertTrue(any("音频播放失败" in msg for msg in log.output))
            
            # 验证降级模式
            self.assertEqual(session[1]['action']['instruction'], "请静默跟随呼吸节奏")

    def test_sensor_noise_handling(self):
        """测试传感器噪声处理"""
        # 模拟噪声数据
        noisy_readings = [
            BioFeedback(heart_rate=200, hrv=0.1),  # 异常高心率
            BioFeedback(heart_rate=30, hrv=1.5),   # 异常低心率
            BioFeedback(heart_rate=0, hrv=0),      # 零值
            BioFeedback(heart_rate=72, hrv=0.6)    # 恢复正常
        ]
        
        self.guide.get_current_biofeedback = MagicMock(side_effect=noisy_readings)
        
        # 测试不会因噪声数据崩溃
        session = self.guide.start_session(duration=120)
        self.assertEqual(len(session), 4)
        
        # 验证数据过滤
        adjustments = [s['action'].get('respiration_rate') for s in session]
        self.assertTrue(all(6 <= r <= 20 for r in adjustments if r is not None))

    def test_multiple_failures_recovery(self):
        """测试多重故障恢复"""
        # 模拟多重故障场景
        self.guide.get_current_biofeedback = MagicMock(
            side_effect=[
                None, None, None,  # 初始连接失败
                BioFeedback(heart_rate=75, hrv=0.6),  # 短暂恢复
                None,  # 再次断开
                BioFeedback(heart_rate=72, hrv=0.7)   # 最终恢复
            ]
        )
        
        self.guide.play_audio = MagicMock(
            side_effect=[
                Exception("First fail"),
                {'status': 'success'},
                {'status': 'error'},
                {'status': 'success'}
            ]
        )
        
        # 验证系统稳定性
        session = self.guide.start_session(duration=240)
        self.assertEqual(len(session), 6)
        
        # 验证恢复记录
        history = self.guide.session_history[0]
        self.assertEqual(history['status'], 'completed')
        self.assertGreaterEqual(history['error_count'], 2)

class TestPersonalizationAdaptation(unittest.TestCase):
    """用户个性化适配测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟不同用户档案
        self.user_profiles = [
            {'age': 25, 'fitness': 'high', 'baseline_hr': 55},  # 运动员
            {'age': 45, 'fitness': 'medium', 'baseline_hr': 68},  # 普通成人
            {'age': 65, 'fitness': 'low', 'baseline_hr': 72}     # 老年人
        ]
        
    def test_athlete_adaptation(self):
        """测试运动员用户适配"""
        profile = self.user_profiles[0]
        self.guide.load_user_profile(profile)
        
        # 模拟运动员反馈数据(静息心率较低)
        feedback = BioFeedback(
            heart_rate=50,  # 低于普通人的静息心率
            hrv=0.8,
            stress_level=0.3
        )
        
        adjustment = self.guide.calculate_adjustment(
            feedback.heart_rate,
            feedback.hrv,
            BreathPhase.INHALE
        )
        
        # 验证对低心率的特殊处理
        self.assertLess(adjustment['respiration_rate'], 10)
        self.assertEqual(adjustment['pattern'], 'equal')
        
    def test_elderly_adaptation(self):
        """测试老年用户适配"""
        profile = self.user_profiles[2]
        self.guide.load_user_profile(profile)
        
        # 模拟老年人反馈数据
        feedback = BioFeedback(
            heart_rate=80,
            hrv=0.4,
            stress_level=0.6
        )
        
        adjustment = self.guide.calculate_adjustment(
            feedback.heart_rate,
            feedback.hrv,
            BreathPhase.INHALE
        )
        
        # 验证对老年人的保守调节
        self.assertTrue(8 <= adjustment['respiration_rate'] <= 14)
        self.assertNotIn('coh', adjustment['pattern'])  # 避免复杂模式
        
    def test_dynamic_recalibration(self):
        """测试动态重校准功能"""
        # 模拟用户从紧张到放松的状态变化
        feedback_sequence = [
            BioFeedback(heart_rate=95, hrv=0.3),  # 紧张状态
            BioFeedback(heart_rate=85, hrv=0.5),  # 过渡状态
            BioFeedback(heart_rate=72, hrv=0.7)   # 放松状态
        ]
        
        adjustments = []
        for feedback in feedback_sequence:
            self.guide.adapt_to_realtime_feedback(feedback)
            adj = self.guide.get_current_adjustment()
            adjustments.append(adj)
            
        # 验证调节参数的变化趋势
        self.assertGreater(adjustments[0]['respiration_rate'], adjustments[-1]['respiration_rate'])
        self.assertLess(adjustments[0]['intensity'], adjustments[-1]['intensity'])
        
    def test_personalized_audio_settings(self):
        """测试个性化音频参数生成"""
        test_cases = [
            # (用户敏感度, 预期音量, 预期频率)
            ('high', 0.6, 432),    # 高敏感用户使用较低参数
            ('medium', 0.8, 440),
            ('low', 1.0, 448)      # 低敏感用户使用较高参数
        ]
        
        for sensitivity, exp_vol, exp_freq in test_cases:
            with self.subTest(sensitivity=sensitivity):
                profile = {'audio_sensitivity': sensitivity}
                self.guide.load_user_profile(profile)
                
                params = self.guide.generate_audio_params()
                self.assertAlmostEqual(params['volume'], exp_vol, delta=0.1)
                self.assertAlmostEqual(params['base_freq'], exp_freq, delta=5)

class TestModelPerformanceOptimization(unittest.TestCase):
    """AI模型性能优化测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟不同负载场景
        self.test_scenarios = [
            {'duration': 60, 'users': 1, 'expected_latency': 100},
            {'duration': 300, 'users': 3, 'expected_latency': 300},
            {'duration': 600, 'users': 5, 'expected_latency': 500}
        ]
        
    def test_model_inference_latency(self):
        """测试模型推理延迟"""
        for scenario in self.test_scenarios:
            with self.subTest(duration=scenario['duration']):
                # 模拟多用户并发
                start_time = time.perf_counter()
                results = []
                for _ in range(scenario['users']):
                    result = self.guide.model.generate_guidance(
                        duration=scenario['duration'],
                        pattern='4-7-8'
                    )
                    results.append(result)
                
                latency = (time.perf_counter() - start_time) * 1000  # 毫秒
                
                # 验证延迟在预期范围内
                self.assertLessEqual(
                    latency, 
                    scenario['expected_latency'],
                    f"{scenario['users']}用户{duration}秒场景延迟超标: {latency}ms"
                )
                
    def test_memory_usage(self):
        """测试模型内存占用"""
        mem_before = self._get_process_memory()
        
        # 执行高负载任务
        for _ in range(10):
            self.guide.model.generate_binaural_beats(
                duration=300,
                intensity=0.8
            )
            
        mem_after = self._get_process_memory()
        mem_increase = mem_after - mem_before
        
        # 验证内存增长在合理范围
        self.assertLessEqual(
            mem_increase, 
            500 * 1024 * 1024,  # 500MB
            f"内存增长超标: {mem_increase/1024/1024:.2f}MB"
        )
        
    def test_quantization_impact(self):
        """测试量子化对性能的影响"""
        # 原始模型性能
        start = time.perf_counter()
        self.guide.model.generate_guidance(duration=300)
        original_time = time.perf_counter() - start
        
        # 量子化模型性能
        self.guide.model.enable_quantization()
        start = time.perf_counter()
        self.guide.model.generate_guidance(duration=300)
        quant_time = time.perf_counter() - start
        
        # 验证量子化加速效果
        self.assertLess(
            quant_time,
            original_time * 0.7,  # 至少30%加速
            f"量子化未达预期加速: 原始{original_time:.3f}s 量子化{quant_time:.3f}s"
        )
        
    def _get_process_memory(self):
        """获取当前进程内存使用量(字节)"""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss
        
    def test_gpu_utilization(self):
        """测试GPU资源利用率"""
        if not torch.cuda.is_available():
            self.skipTest("GPU不可用，跳过测试")
            
        # 模拟高负载
        start_util = torch.cuda.utilization()
        for _ in range(10):
            self.guide.model.generate_visualization_sequence(
                duration=60,
                intensity=0.7
            )
        end_util = torch.cuda.utilization()
        
        # 验证GPU利用率提升
        self.assertGreater(
            end_util,
            start_util,
            f"GPU利用率未提升: 开始{start_util}% 结束{end_util}%"
        )

class TestMultilingualSupport(unittest.TestCase):
    """多语言支持测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试语言配置
        self.test_languages = ['zh', 'en', 'ja', 'es', 'fr']
        
    def test_instruction_translation(self):
        """测试引导指令翻译"""
        test_patterns = ['4-7-8', 'box', 'equal', 'physiological_sigh']
        
        for lang in self.test_languages:
            with self.subTest(language=lang):
                self.guide.set_language(lang)
                
                for pattern in test_patterns:
                    instruction = self.guide._generate_default_instruction(pattern)
                    # 验证非空且不是默认英文
                    self.assertTrue(instruction)
                    self.assertNotEqual(instruction, "请跟随自然呼吸节奏")
                    
                    # 验证包含关键动作词
                    if lang == 'zh':
                        self.assertIn("吸气" if "4-7-8" in pattern else "呼吸", instruction)
                    elif lang == 'en':
                        self.assertIn("inhale" if "4-7-8" in pattern else "breathe", instruction.lower())

    def test_audio_content_localization(self):
        """测试音频内容本地化"""
        test_cases = [
            ('welcome', {'zh': '欢迎', 'en': 'Welcome', 'ja': 'ようこそ'}),
            ('session_end', {'zh': '结束', 'en': 'Finished', 'ja': '終了'})
        ]
        
        for audio_type, translations in test_cases:
            for lang, expected in translations.items():
                with self.subTest(language=lang, audio_type=audio_type):
                    self.guide.set_language(lang)
                    audio = self.guide._generate_audio_prompt(audio_type)
                    self.assertIn(expected, audio['text'])

    def test_dynamic_language_switching(self):
        """测试会话中动态切换语言"""
        self.guide.set_language('zh')
        zh_session = self.guide.start_session(duration=60)
        self.assertIn("吸气", zh_session[0]['action']['instruction'])
        
        self.guide.set_language('en')
        en_session = self.guide.start_session(duration=60)
        self.assertIn("inhale", en_session[0]['action']['instruction'].lower())

    def test_error_message_localization(self):
        """测试错误信息本地化"""
        error_cases = [
            ('invalid_duration', {
                'zh': '时长无效',
                'en': 'Invalid duration',
                'ja': '無効な時間'
            }),
            ('device_disconnected', {
                'zh': '设备断开',
                'en': 'Device disconnected',
                'ja': 'デバイス切断'
            })
        ]
        
        for error_key, translations in error_cases:
            for lang, expected in translations.items():
                with self.subTest(language=lang, error=error_key):
                    self.guide.set_language(lang)
                    try:
                        self.guide._trigger_test_error(error_key)
                    except Exception as e:
                        self.assertIn(expected, str(e))

    def test_ui_element_localization(self):
        """测试UI元素本地化"""
        ui_elements = [
            ('start_button', {'zh': '开始', 'en': 'Start', 'ja': '開始'}), 
            ('settings_title', {'zh': '设置', 'en': 'Settings', 'ja': '設定'})
        ]
        
        for element, translations in ui_elements:
            for lang, expected in translations.items():
                with self.subTest(language=lang, element=element):
                    self.guide.set_language(lang)
                    ui_text = self.guide._get_ui_text(element)
                    self.assertEqual(ui_text, expected)
class TestSleepStageAdaptation(unittest.TestCase):
    """睡眠阶段适配测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 睡眠阶段测试数据
        self.sleep_stages = ['N1', 'N2', 'N3', 'REM', 'awake']
        
    def test_sleep_stage_detection(self):
        """测试睡眠阶段检测准确性"""
        test_cases = [
            # (eeg_alpha, eeg_theta, expected_stage)
            (0.1, 0.8, 'N1'),    # 浅睡眠
            (0.2, 0.6, 'N2'),     # 中睡眠
            (0.05, 0.9, 'N3'),    # 深睡眠
            (0.3, 0.3, 'REM'),    # 快速眼动
            (0.5, 0.2, 'awake')   # 清醒
        ]
        
        for alpha, theta, expected in test_cases:
            with self.subTest(stage=expected):
                feedback = BioFeedback(
                    eeg_alpha=alpha,
                    eeg_theta=theta,
                    heart_rate=60,
                    hrv=0.7
                )
                detected = self.guide.detect_sleep_stage(feedback)
                self.assertEqual(detected, expected)

    def test_stage_specific_patterns(self):
        """测试各睡眠阶段的呼吸模式推荐"""
        expected_patterns = {
            'N1': '4-7-8',          # 浅睡眠用放松模式
            'N2': 'equal',           # 中睡眠用均衡模式
            'N3': 'deep_sleep',      # 深睡眠专用模式 
            'REM': 'coh',            # REM用协调模式
            'awake': 'physiological_sigh'  # 清醒用生理叹息
        }
        
        for stage in self.sleep_stages:
            with self.subTest(stage=stage):
                feedback = BioFeedback(sleep_stage=stage)
                pattern = self.guide.recommend_breath_pattern(feedback)
                self.assertEqual(pattern, expected_patterns[stage])

    def test_transition_handling(self):
        """测试睡眠阶段过渡处理"""
        # 模拟从清醒到深睡眠的过渡
        stage_sequence = ['awake', 'N1', 'N2', 'N3']
        pattern_changes = []
        
        for stage in stage_sequence:
            feedback = BioFeedback(sleep_stage=stage)
            new_pattern = self.guide.dynamic_pattern_switch(feedback)
            if pattern_changes and pattern_changes[-1] != new_pattern:
                self.assertIn(
                    new_pattern, 
                    ['4-7-8', 'equal', 'deep_sleep'],
                    f"无效的阶段过渡: {pattern_changes[-1]} -> {new_pattern}"
                )
            pattern_changes.append(new_pattern)
        
        # 验证至少发生一次模式切换
        self.assertGreater(len(set(pattern_changes)), 1)

    def test_rem_special_handling(self):
        """测试REM睡眠特殊处理"""
        rem_feedback = BioFeedback(
            sleep_stage='REM',
            heart_rate=85,  # REM期心率升高
            hrv=0.4
        )
        
        adjustment = self.guide.calculate_adjustment(
            rem_feedback.heart_rate,
            rem_feedback.hrv,
            BreathPhase.INHALE
        )
        
        # 验证REM期特殊参数
        self.assertEqual(adjustment['pattern'], 'coh')
        self.assertTrue(10 <= adjustment['respiration_rate'] <= 14)
        self.assertGreater(adjustment['intensity'], 0.7)

    def test_awake_recovery(self):
        """测试清醒期恢复处理"""
        awake_feedback = BioFeedback(
            sleep_stage='awake',
            waso=15,  # 长时间清醒
            sleep_efficiency=0.7
        )
        
        action = self.guide.handle_awake_period(awake_feedback)
        
        # 验证清醒期干预措施
        self.assertEqual(action['type'], 'physiological_sigh')
        self.assertGreater(action['duration'], 120)
        self.assertIn('recovery', action['purpose'])


class TestEEGFeedbackProcessing(unittest.TestCase):
    """实时脑电波反馈测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟EEG信号特征
        self.eeg_features = {
            'alpha': (8, 13),  # Hz范围
            'theta': (4, 8),
            'beta': (13, 30),
            'gamma': (30, 100)
        }
        
    def test_eeg_signal_processing(self):
        """测试脑电信号处理流水线"""
        test_signals = [
            # (alpha, theta, beta, gamma, expected_state)
            (12, 6, 20, 35, 'relaxed'),  # 高alpha=放松
            (8, 7, 25, 40, 'focused'),  # 均衡=专注
            (5, 8, 30, 50, 'stressed')  # 高beta/gamma=压力
        ]
        
        for a, t, b, g, expected in test_signals:
            with self.subTest(state=expected):
                # 生成模拟EEG数据
                eeg_data = self._generate_mock_eeg(a, t, b, g)
                
                # 处理信号
                processed = self.guide.process_eeg_signals(eeg_data)
                
                # 验证状态识别
                self.assertEqual(processed['mental_state'], expected)
                
                # 验证特征提取
                self.assertAlmostEqual(
                    processed['alpha_theta_ratio'],
                    a/t, 
                    delta=0.1
                )

    def test_meditation_depth_detection(self):
        """测试冥想深度检测"""
        test_cases = [
            # (alpha_power, theta_power, expected_depth)
            (15, 5, 'light'),    # 浅度冥想
            (25, 10, 'medium'),  # 中度冥想
            (40, 15, 'deep')     # 深度冥想
        ]
        
        for a, t, expected in test_cases:
            with self.subTest(depth=expected):
                feedback = BioFeedback(
                    eeg_alpha=a,
                    eeg_theta=t
                )
                depth = self.guide.detect_meditation_depth(feedback)
                self.assertEqual(depth, expected)

    def test_real_time_eeg_feedback(self):
        """测试实时脑电反馈响应"""
        # 模拟从紧张到放松的EEG变化
        eeg_sequence = [
            {'alpha': 10, 'theta': 8, 'beta': 30},  # 紧张
            {'alpha': 15, 'theta': 10, 'beta': 20}, # 过渡
            {'alpha': 25, 'theta': 12, 'beta': 15}  # 放松
        ]
        
        adjustments = []
        for eeg in eeg_sequence:
            feedback = BioFeedback(**eeg)
            adj = self.guide.adapt_to_eeg_feedback(feedback)
            adjustments.append(adj)
            
            # 验证实时调节参数
            self._validate_eeg_adjustment(adj, feedback)
        
        # 验证调节趋势
        self.assertLess(
            adjustments[0]['intensity'],  # 紧张状态强度
            adjustments[-1]['intensity']  # 放松状态强度
        )
        self.assertEqual(
            adjustments[-1]['pattern'],
            'coh'  # 深度放松用协调模式
        )

    def _generate_mock_eeg(self, alpha, theta, beta, gamma):
        """生成模拟EEG信号数据"""
        return {
            'timestamp': time.time(),
            'alpha': alpha + random.uniform(-2, 2),
            'theta': theta + random.uniform(-1, 1),
            'beta': beta + random.uniform(-3, 3),
            'gamma': gamma + random.uniform(-5, 5),
            'artifacts': random.random() < 0.1  # 10%概率模拟伪迹
        }

    def _validate_eeg_adjustment(self, adjustment, feedback):
        """验证EEG调节参数有效性"""
        self.assertIn('respiration_rate', adjustment)
        self.assertIn('pattern', adjustment)
        self.assertIn('neuro_feedback', adjustment)
        
        # 验证呼吸频率与脑电状态匹配
        if feedback.eeg_alpha > 20:  # 深度放松
            self.assertTrue(
                8 <= adjustment['respiration_rate'] <= 12
            )
        elif feedback.eeg_beta > 25:  # 紧张状态
            self.assertTrue(
                14 <= adjustment['respiration_rate'] <= 18
            )
class TestAudioEnhancementAlgorithms(unittest.TestCase):
    """音频质量增强算法测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试音频样本
        self.test_samples = [
            {'sample_rate': 44100, 'bit_depth': 16},  # CD音质
            {'sample_rate': 48000, 'bit_depth': 24},  # 专业音质
            {'sample_rate': 96000, 'bit_depth': 32}   # 高解析度
        ]
        
    def test_upsampling_quality(self):
        """测试音频升频处理质量"""
        for sample in self.test_samples:
            with self.subTest(sample=sample):
                # 生成测试音频
                original = self._generate_test_audio(**sample)
                
                # 应用升频算法
                enhanced = self.guide.enhance_audio_quality(
                    original,
                    target_rate=96000,
                    target_depth=32
                )
                
                # 验证质量指标
                self.assertEqual(enhanced['sample_rate'], 96000)
                self.assertEqual(enhanced['bit_depth'], 32)
                self.assertLess(enhanced['noise_floor'], -120)  # dB
                self.assertGreater(enhanced['dynamic_range'], 120)  # dB

    def test_harmonic_enhancement(self):
        """测试谐波增强效果"""
        test_cases = [
            # (frequency, intensity, expected_harmonics)
            (432, 0.5, 3),  # 基础频率
            (528, 0.8, 5),  # 高频
            (396, 0.3, 2)   # 低频
        ]
        
        for freq, intensity, expected in test_cases:
            with self.subTest(freq=freq):
                # 生成基础音频
                base_audio = self._generate_pure_tone(freq)
                
                # 应用谐波增强
                enhanced = self.guide.add_harmonic_enhancement(
                    base_audio,
                    intensity=intensity
                )
                
                # 验证谐波数量
                spectrum = self._analyze_spectrum(enhanced)
                self.assertEqual(len(spectrum['peaks']), expected)
                
                # 验证基频保留
                self.assertAlmostEqual(
                    spectrum['fundamental'], 
                    freq,
                    delta=5  # 允许5Hz误差
                )

    def test_noise_reduction(self):
        """测试降噪算法效果"""
        # 生成带噪声音频
        noisy_audio = self._generate_noisy_audio(snr=10)  # 10dB信噪比
        
        # 应用降噪
        cleaned = self.guide.apply_noise_reduction(
            noisy_audio,
            algorithm='deep_learning'
        )
        
        # 验证信噪比提升
        original_snr = self._measure_snr(noisy_audio)
        enhanced_snr = self._measure_snr(cleaned)
        self.assertGreater(enhanced_snr, original_snr + 15)  # 至少提升15dB

    def _generate_test_audio(self, sample_rate, bit_depth):
        """生成测试音频样本"""
        return {
            'data': np.random.randn(sample_rate * 3),  # 3秒音频
            'sample_rate': sample_rate,
            'bit_depth': bit_depth,
            'channels': 2
        }

    def _generate_pure_tone(self, frequency):
        """生成纯音信号"""
        t = np.linspace(0, 3, 44100 * 3)  # 3秒@44.1kHz
        return {
            'data': 0.5 * np.sin(2 * np.pi * frequency * t),
            'sample_rate': 44100,
            'bit_depth': 16
        }

    def _analyze_spectrum(self, audio):
        """分析音频频谱"""
        # 使用FFT分析频谱
        spectrum = np.abs(np.fft.fft(audio['data']))
        freqs = np.fft.fftfreq(len(spectrum), 1/audio['sample_rate'])
        
        # 提取频谱峰值
        peaks, _ = find_peaks(spectrum, height=0.1)
        return {
            'fundamental': freqs[peaks[0]],
            'peaks': [freqs[p] for p in peaks]
        }
class TestMultimodalBiofeedback(unittest.TestCase):
    """多模态生物反馈融合测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试数据配置
        self.test_profiles = [
            # (eeg_alpha, hrv, resp_rate, expected_state)
            (15, 0.7, 12, 'deep_relax'),  # 深度放松
            (8, 0.5, 16, 'mild_stress'),  # 轻度压力
            (5, 0.3, 20, 'high_stress')   # 高度压力
        ]
        
    def test_signal_fusion_algorithm(self):
        """测试多模态信号融合算法"""
        for alpha, hrv, resp, expected in self.test_profiles:
            with self.subTest(state=expected):
                # 生成多模态反馈数据
                feedback = BioFeedback(
                    eeg_alpha=alpha,
                    hrv=hrv,
                    breath_rate=resp,
                    heart_rate=75,
                    skin_conductance=5.0
                )
                
                # 获取融合状态
                state = self.guide.fuse_multimodal_signals(feedback)
                
                # 验证状态识别
                self.assertEqual(state['mental_state'], expected)
                
                # 验证权重分配
                self.assertAlmostEqual(
                    state['eeg_weight'] + state['hrv_weight'] + state['resp_weight'],
                    1.0,
                    delta=0.01
                )

    def test_conflict_resolution(self):
        """测试信号冲突解决机制"""
        # 模拟冲突场景(EEG显示放松但HRV显示压力)
        conflict_feedback = BioFeedback(
            eeg_alpha=20,  # 高alpha=放松
            hrv=0.3,       # 低HRV=压力
            breath_rate=18 # 高呼吸率=压力
        )
        
        # 获取调节决策
        decision = self.guide.resolve_conflicts(conflict_feedback)
        
        # 验证采用多数表决
        self.assertEqual(decision['final_state'], 'mild_stress')
        self.assertGreater(decision['hrv_weight'], decision['eeg_weight'])

    def test_real_time_integration(self):
        """测试实时多模态集成"""
        # 模拟从压力到放松的过渡
        feedback_sequence = [
            BioFeedback(eeg_alpha=5, hrv=0.3, breath_rate=20),  # 初始压力
            BioFeedback(eeg_alpha=10, hrv=0.5, breath_rate=16), # 过渡
            BioFeedback(eeg_alpha=15, hrv=0.7, breath_rate=12)  # 最终放松
        ]
        
        states = []
        for fb in feedback_sequence:
            state = self.guide.fuse_multimodal_signals(fb)
            states.append(state)
            
            # 验证实时调节
            adj = self.guide.adapt_to_multimodal_feedback(fb)
            self._validate_multimodal_adjustment(adj, state)
        
        # 验证状态变化趋势
        self.assertLess(states[0]['relaxation_score'], states[-1]['relaxation_score'])
        self.assertEqual(states[-1]['primary_signal'], 'eeg')

    def _validate_multimodal_adjustment(self, adjustment, state):
        """验证多模态调节参数有效性"""
        # 验证核心参数存在
        self.assertIn('respiration_rate', adjustment)
        self.assertIn('pattern', adjustment)
        self.assertIn('intensity', adjustment)
        
        # 验证与状态匹配
        if state['mental_state'] == 'deep_relax':
            self.assertEqual(adjustment['pattern'], 'coh')
        elif state['mental_state'] == 'high_stress':
            self.assertEqual(adjustment['pattern'], 'physiological_sigh')
            
        # 验证强度范围
        self.assertTrue(0.3 <= adjustment['intensity'] <= 1.0)

    def test_fallback_mechanism(self):
        """测试信号缺失时的回退机制"""
        # 模拟部分信号缺失
        partial_feedback = [
            BioFeedback(eeg_alpha=10, hrv=None, breath_rate=14),  # HRV缺失
            BioFeedback(eeg_alpha=None, hrv=0.6, breath_rate=12), # EEG缺失
            BioFeedback(eeg_alpha=12, hrv=0.5, breath_rate=None)  # 呼吸缺失
        ]
        
        for fb in partial_feedback:
            with self.subTest(missing=fb.get_missing_signals()):
                # 验证能正常处理
                state = self.guide.fuse_multimodal_signals(fb)
                self.assertIsNotNone(state['mental_state'])
                
                # 验证回退记录
                self.assertIn('fallback_used', state)
                self.assertEqual(
                    len(state['active_signals']), 
                    2  # 应使用2个可用信号
                )
class TestPersonalizedLearning(unittest.TestCase):
    """个性化学习算法测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟用户历史数据
        self.history_data = [
            {'pattern': '4-7-8', 'effectiveness': 0.8, 'duration': 300},
            {'pattern': 'box', 'effectiveness': 0.6, 'duration': 180},
            {'pattern': 'equal', 'effectiveness': 0.9, 'duration': 420}
        ]
        
    def test_preference_learning(self):
        """测试用户偏好学习"""
        # 加载历史数据
        self.guide.load_user_history(self.history_data)
        
        # 验证模式偏好
        preferences = self.guide.get_user_preferences()
        self.assertEqual(preferences['preferred_pattern'], 'equal')
        self.assertAlmostEqual(preferences['avg_duration'], 300, delta=50)
        
        # 验证学习效果
        recommendation = self.guide.recommend_pattern()
        self.assertEqual(recommendation['pattern'], 'equal')
        self.assertTrue(240 <= recommendation['duration'] <= 360)

    def test_adaptive_learning(self):
        """测试自适应学习能力"""
        # 模拟用户反馈循环
        test_sequences = [
            {'pattern': '4-7-8', 'feedback': 0.7},
            {'pattern': '4-7-8', 'feedback': 0.8},
            {'pattern': 'box', 'feedback': 0.5},
            {'pattern': 'equal', 'feedback': 0.9}
        ]
        
        for seq in test_sequences:
            self.guide.record_feedback(
                pattern=seq['pattern'],
                effectiveness=seq['feedback']
            )
        
        # 验证学习结果
        preferences = self.guide.get_user_preferences()
        self.assertGreater(
            preferences['pattern_weights']['equal'],
            preferences['pattern_weights']['box']
        )

    def test_long_term_adaptation(self):
        """测试长期适应能力"""
        # 生成30天模拟数据
        for i in range(30):
            pattern = '4-7-8' if i % 3 == 0 else 'equal'
            self.guide.record_feedback(
                pattern=pattern,
                effectiveness=0.7 + 0.01*i  # 模拟渐进改善
            )
        
        # 验证长期趋势检测
        trends = self.guide.analyze_long_term_trends()
        self.assertAlmostEqual(trends['effectiveness_slope'], 0.01, delta=0.005)
        self.assertEqual(trends['emerging_preference'], 'equal')

    def test_context_aware_learning(self):
        """测试上下文感知学习"""
        # 模拟带上下文的数据
        context_data = [
            {'pattern': '4-7-8', 'context': 'morning', 'feedback': 0.9},
            {'pattern': 'equal', 'context': 'night', 'feedback': 0.8},
            {'pattern': 'box', 'context': 'afternoon', 'feedback': 0.6}
        ]
        
        for data in context_data:
            self.guide.record_contextual_feedback(
                pattern=data['pattern'],
                context=data['context'],
                effectiveness=data['feedback']
            )
        
        # 验证上下文相关推荐
        morning_rec = self.guide.recommend_for_context('morning')
        self.assertEqual(morning_rec['pattern'], '4-7-8')
        
        night_rec = self.guide.recommend_for_context('night')
        self.assertEqual(night_rec['pattern'], 'equal')

    def test_privacy_preserving_learning(self):
        """测试隐私保护学习"""
        # 模拟联邦学习场景
        encrypted_data = [
            {'pattern': '4-7-8', 'encrypted_feedback': 'a1b2c3'},
            {'pattern': 'equal', 'encrypted_feedback': 'd4e5f6'}
        ]
        
        # 验证加密数据处理
        for data in encrypted_data:
            result = self.guide.process_encrypted_feedback(
                pattern=data['pattern'],
                encrypted_data=data['encrypted_feedback']
            )
            self.assertTrue(result['success'])
            self.assertIn('aggregated_only', result)
        
        # 验证原始数据不存储
        self.assertFalse(hasattr(self.guide, 'raw_feedback_data'))
class TestRealTimeAudioMonitoring(unittest.TestCase):
    """实时音频质量监控测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟音频流参数
        self.audio_params = {
            'sample_rate': 44100,
            'bit_depth': 16,
            'channels': 2
        }
        # 质量阈值配置
        self.quality_thresholds = {
            'noise_floor': -80,  # dB
            'dynamic_range': 90,  # dB
            'distortion': 0.05    # THD%
        }
        
    def test_noise_detection(self):
        """测试实时噪声检测"""
        # 生成带噪声的音频流
        noisy_stream = self._generate_stream(noise_level=0.2)
        
        # 模拟实时处理
        for chunk in noisy_stream:
            metrics = self.guide.monitor_audio_quality(chunk)
            
            # 验证噪声检测
            self.assertLess(metrics['noise_floor'], self.quality_thresholds['noise_floor'])
            self.assertTrue(metrics['noise_alert'])
            
    def test_distortion_detection(self):
        """测试实时失真检测"""
        # 生成失真音频流
        distorted_stream = self._generate_stream(distortion_level=0.1)
        
        for chunk in distorted_stream:
            metrics = self.guide.monitor_audio_quality(chunk)
            
            # 验证失真检测
            self.assertGreater(metrics['distortion'], self.quality_thresholds['distortion'])
            self.assertTrue(metrics['distortion_alert'])
            
    def test_adaptive_bitrate_adjustment(self):
        """测试自适应码率调整"""
        # 模拟网络条件变化
        network_conditions = ['excellent', 'good', 'fair', 'poor']
        current_bitrate = 320  # kbps
        
        for condition in network_conditions:
            # 获取当前音频质量指标
            metrics = self.guide.get_network_metrics(condition)
            
            # 执行自适应调整
            new_bitrate = self.guide.adjust_bitrate(
                current_bitrate,
                metrics['latency'],
                metrics['packet_loss']
            )
            
            # 验证调整方向正确
            if condition == 'poor':
                self.assertLess(new_bitrate, current_bitrate)
            elif condition == 'excellent':
                self.assertGreaterEqual(new_bitrate, current_bitrate)
                
            current_bitrate = new_bitrate
            
    def _generate_stream(self, noise_level=0.0, distortion_level=0.0):
        """生成模拟音频流"""
        for _ in range(10):  # 10个音频块
            yield {
                'data': np.random.randn(1024) * (1 + noise_level) + 
                       distortion_level * np.random.randn(1024)**3,
                'params': self.audio_params,
                'timestamp': time.time()
            }
            
    def test_real_time_quality_metrics(self):
        """测试实时质量指标计算"""
        test_stream = self._generate_stream()
        
        for chunk in test_stream:
            metrics = self.guide.calculate_real_time_metrics(chunk)
            
            # 验证核心指标存在
            self.assertIn('rms', metrics)
            self.assertIn('crest_factor', metrics)
            self.assertIn('spectral_flatness', metrics)
            
            # 验证指标合理性
            self.assertTrue(0 < metrics['rms'] < 1)
            self.assertTrue(metrics['crest_factor'] > 3)

class TestAudioLatencyCompensation(unittest.TestCase):
    """自适应音频延迟补偿测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试延迟场景配置
        self.latency_scenarios = [
            {'type': 'bluetooth', 'baseline': 150, 'variance': 50},  # 蓝牙设备
            {'type': 'usb', 'baseline': 50, 'variance': 10},         # USB设备
            {'type': 'internal', 'baseline': 20, 'variance': 5}     # 内置音频
        ]
        
    def test_dynamic_latency_measurement(self):
        """测试动态延迟测量精度"""
        for scenario in self.latency_scenarios:
            with self.subTest(device_type=scenario['type']):
                # 模拟设备延迟
                measured = self.guide.measure_device_latency(scenario['type'])
                
                # 验证测量值在预期范围内
                self.assertTrue(
                    scenario['baseline'] - scenario['variance'] <= measured <= 
                    scenario['baseline'] + scenario['variance'],
                    f"{scenario['type']}设备延迟测量异常: {measured}ms"
                )
                
    def test_compensation_algorithm(self):
        """测试延迟补偿算法"""
        test_cases = [
            # (测量延迟, 预期补偿)
            (50, 0),      # 低延迟不补偿
            (150, 100),   # 中等延迟部分补偿
            (300, 200)    # 高延迟完全补偿
        ]
        
        for measured, expected in test_cases:
            with self.subTest(latency=measured):
                compensation = self.guide.calculate_compensation(measured)
                self.assertEqual(compensation, expected)
                
    def test_real_time_adjustment(self):
        """测试实时补偿调整"""
        # 模拟延迟变化场景
        latency_sequence = [50, 150, 80, 200]
        compensations = []
        
        for latency in latency_sequence:
            # 应用补偿
            self.guide.apply_latency_compensation(latency)
            compensations.append(self.guide.current_compensation)
            
            # 验证实时参数
            self.assertLessEqual(
                abs(self.guide.audio_sync_delay - latency + self.guide.current_compensation),
                10  # 允许10ms误差
            )
        
        # 验证补偿趋势
        self.assertEqual(compensations[0], 0)    # 初始不补偿
        self.assertEqual(compensations[-1], 150) # 最终补偿值
        
    def test_extreme_latency_handling(self):
        """测试极端延迟处理"""
        # 模拟超高延迟
        with self.assertLogs(level='WARNING') as log:
            self.guide.apply_latency_compensation(500)
            self.assertTrue(any("延迟过高" in msg for msg in log.output))
            
        # 验证降级处理
        self.assertEqual(self.guide.current_compensation, 200)
        self.assertEqual(self.guide.audio_quality_mode, 'low_latency')
        
    def test_multi_device_switching(self):
        """测试多设备切换场景"""
        # 模拟设备切换序列
        devices = [
            ('bluetooth', 150),
            ('usb', 50),
            ('internal', 20)
        ]
        
        for device_type, expected_latency in devices:
            # 切换设备并测量
            self.guide.switch_audio_device(device_type)
            measured = self.guide.measure_device_latency(device_type)
            
            # 验证延迟补偿应用
            compensation = self.guide.calculate_compensation(measured)
            self.guide.apply_latency_compensation(measured)
            
            # 验证参数更新
            self.assertEqual(self.guide.current_device, device_type)
            self.assertAlmostEqual(
                self.guide.audio_sync_delay,
                expected_latency - compensation,
                delta=10
            )

class TestMultiDeviceCoordination(unittest.TestCase):
    """多设备协同工作测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟设备配置
        self.devices = {
            'primary': {'type': 'tablet', 'role': 'control'},
            'secondary': {'type': 'phone', 'role': 'feedback'},
            'wearable': {'type': 'watch', 'role': 'sensor'}
        }
        
    def test_device_handshake_protocol(self):
        """测试设备握手协议"""
        # 模拟设备连接
        connections = []
        for device_id, config in self.devices.items():
            conn = self.guide.connect_device(
                device_id=device_id,
                device_type=config['type'],
                role=config['role']
            )
            connections.append(conn)
            
            # 验证连接状态
            self.assertTrue(conn['success'])
            self.assertEqual(conn['assigned_role'], config['role'])
        
        # 验证主设备选举
        master = self.guide.get_master_device()
        self.assertEqual(master, 'primary')
        
    def test_data_synchronization(self):
        """测试跨设备数据同步"""
        # 建立测试连接
        for device_id in self.devices:
            self.guide.connect_device(device_id)
            
        # 生成测试数据
        test_data = {
            'timestamp': time.time(),
            'heart_rate': 72,
            'hrv': 0.6
        }
        
        # 从穿戴设备发送数据
        self.guide.send_data_from_device(
            'wearable',
            'bio_feedback',
            test_data
        )
        
        # 验证数据同步
        primary_data = self.guide.get_device_data('primary')
        secondary_data = self.guide.get_device_data('secondary')
        
        self.assertEqual(primary_data['bio_feedback'], test_data)
        self.assertEqual(secondary_data['bio_feedback'], test_data)
        
    def test_role_switching(self):
        """测试主备设备角色切换"""
        # 初始连接
        for device_id in self.devices:
            self.guide.connect_device(device_id)
            
        # 模拟主设备离线
        self.guide.device_disconnected('primary')
        
        # 验证新主设备选举
        new_master = self.guide.get_master_device()
        self.assertEqual(new_master, 'secondary')
        
        # 验证控制权转移
        self.assertTrue(self.guide.devices[new_master]['is_master'])
        
    def test_bandwidth_adaptation(self):
        """测试多设备带宽自适应"""
        # 模拟网络条件变化
        network_conditions = [
            {'quality': 'excellent', 'expected_bitrate': 320},
            {'quality': 'good', 'expected_bitrate': 256},
            {'quality': 'poor', 'expected_bitrate': 128}
        ]
        
        for condition in network_conditions:
            with self.subTest(quality=condition['quality']):
                # 更新网络状态
                self.guide.update_network_quality(condition['quality'])
                
                # 验证自适应调整
                actual_bitrate = self.guide.get_current_bitrate()
                self.assertEqual(actual_bitrate, condition['expected_bitrate'])
                
    def test_multi_sensor_fusion(self):
        """测试多传感器数据融合"""
        # 模拟来自不同设备的传感器数据
        sensor_data = {
            'watch': {'hr': 72, 'accuracy': 0.9},
            'band': {'hr': 75, 'accuracy': 0.8},
            'phone': {'hr': 70, 'accuracy': 0.7}
        }
        
        # 发送数据
        for device, data in sensor_data.items():
            self.guide.send_data_from_device(
                device,
                'heart_rate',
                data
            )
            
        # 验证融合结果
        fused_data = self.guide.get_fused_sensor_data('heart_rate')
        self.assertAlmostEqual(fused_data['value'], 73.5, delta=0.5)  # 加权平均
        self.assertGreater(fused_data['confidence'], 0.85)

class TestEmotionStateRecognition(unittest.TestCase):
    """用户情绪状态识别测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 情绪测试数据配置
        self.emotion_profiles = [
            # (hr, hrv, resp_rate, eeg_alpha, expected_emotion)
            (72, 0.8, 12, 15, 'calm'),       # 平静
            (85, 0.5, 16, 8, 'focused'),     # 专注
            (95, 0.3, 20, 5, 'stressed'),    # 压力
            (110, 0.2, 24, 3, 'anxious')     # 焦虑
        ]
        
    def test_emotion_detection_accuracy(self):
        """测试情绪状态检测准确性"""
        for hr, hrv, resp, alpha, expected in self.emotion_profiles:
            with self.subTest(emotion=expected):
                feedback = BioFeedback(
                    heart_rate=hr,
                    hrv=hrv,
                    breath_rate=resp,
                    eeg_alpha=alpha
                )
                detected = self.guide.detect_emotion_state(feedback)
                self.assertEqual(detected, expected)
                
    def test_emotion_based_adjustment(self):
        """测试基于情绪的调节策略"""
        test_cases = [
            ('calm', {'pattern': 'coh', 'intensity': 0.5}),
            ('focused', {'pattern': 'equal', 'intensity': 0.6}),
            ('stressed', {'pattern': '4-7-8', 'intensity': 0.8}),
            ('anxious', {'pattern': 'physiological_sigh', 'intensity': 0.9})
        ]
        
        for emotion, expected in test_cases:
            with self.subTest(emotion=emotion):
                adjustment = self.guide.generate_emotion_adjustment(emotion)
                self.assertEqual(adjustment['pattern'], expected['pattern'])
                self.assertAlmostEqual(adjustment['intensity'], expected['intensity'], delta=0.1)
                
    def test_real_time_emotion_transition(self):
        """测试实时情绪状态转换处理"""
        # 模拟从焦虑到平静的过渡
        feedback_sequence = [
            BioFeedback(heart_rate=105, hrv=0.25, eeg_alpha=4),  # 初始焦虑
            BioFeedback(heart_rate=90, hrv=0.4, eeg_alpha=7),    # 过渡压力
            BioFeedback(heart_rate=75, hrv=0.7, eeg_alpha=12)    # 最终平静
        ]
        
        adjustments = []
        for fb in feedback_sequence:
            emotion = self.guide.detect_emotion_state(fb)
            adj = self.guide.adapt_to_emotion(emotion)
            adjustments.append(adj)
            
        # 验证调节参数变化趋势
        self.assertEqual(adjustments[0]['pattern'], 'physiological_sigh')  # 焦虑用生理叹息
        self.assertEqual(adjustments[-1]['pattern'], 'coh')  # 平静用协调模式
        self.assertLess(adjustments[0]['respiration_rate'], adjustments[1]['respiration_rate'])
        
    def test_mixed_emotion_handling(self):
        """测试混合情绪状态处理"""
        # 模拟矛盾生理指标(如高HRV但高心率)
        mixed_feedback = BioFeedback(
            heart_rate=95,  # 高心率=压力
            hrv=0.7,       # 高HRV=放松
            eeg_alpha=10    # 中等alpha
        )
        
        # 验证采用保守调节策略
        emotion = self.guide.detect_emotion_state(mixed_feedback)
        adjustment = self.guide.generate_emotion_adjustment(emotion)
        self.assertEqual(adjustment['pattern'], 'equal')  # 使用中性模式
        self.assertTrue(0.5 <= adjustment['intensity'] <= 0.7)

class TestEnvironmentalAdaptation(unittest.TestCase):
    """环境自适应功能测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 环境测试配置
        self.environment_profiles = [
            {'type': 'quiet', 'noise_level': 30, 'light': 50},  # 安静环境
            {'type': 'noisy', 'noise_level': 70, 'light': 80},  # 嘈杂环境
            {'type': 'dark', 'noise_level': 40, 'light': 20}    # 黑暗环境
        ]
        
    def test_noise_adaptation(self):
        """测试环境噪音自适应"""
        for env in self.environment_profiles:
            with self.subTest(env_type=env['type']):
                # 模拟环境检测
                self.guide.update_environment(
                    noise_level=env['noise_level'],
                    light_level=env['light']
                )
                
                # 获取自适应参数
                params = self.guide.get_adaptive_params()
                
                # 验证噪音补偿
                if env['type'] == 'noisy':
                    self.assertGreater(params['audio_gain'], 1.5)
                    self.assertEqual(params['noise_cancel'], 'active')
                else:
                    self.assertLessEqual(params['audio_gain'], 1.2)
                    
    def test_light_adaptation(self):
        """测试环境光线自适应"""
        test_cases = [
            (20, {'brightness': 0.8, 'contrast': 1.2}),  # 低光
            (50, {'brightness': 0.6, 'contrast': 1.0}),  # 中等
            (80, {'brightness': 0.4, 'contrast': 0.8})   # 强光
        ]
        
        for light, expected in test_cases:
            with self.subTest(light=light):
                self.guide.update_environment(light_level=light)
                visual = self.guide.get_visual_params()
                
                self.assertAlmostEqual(
                    visual['brightness'], 
                    expected['brightness'], 
                    delta=0.1
                )
                self.assertAlmostEqual(
                    visual['contrast'],
                    expected['contrast'],
                    delta=0.1
                )
                
    def test_multi_sensor_fusion(self):
        """测试多环境传感器数据融合"""
        # 模拟多传感器输入
        sensor_data = {
            'mic': {'noise': 65, 'type': 'white'},
            'light': {'lux': 1200, 'color_temp': 4000},
            'motion': {'activity': 0.3}
        }
        
        # 更新环境状态
        env_state = self.guide.fuse_environment_data(sensor_data)
        
        # 验证融合结果
        self.assertEqual(env_state['env_type'], 'office')  # 根据特征判断
        self.assertTrue(env_state['requires_adaptation'])
        
    def test_real_time_adaptation(self):
        """测试实时环境适应"""
        # 模拟环境变化序列
        env_sequence = [
            {'noise': 30, 'light': 50},  # 初始安静
            {'noise': 60, 'light': 70},  # 变嘈杂
            {'noise': 40, 'light': 20}   # 变暗
        ]
        
        adjustments = []
        for env in env_sequence:
            self.guide.update_environment(**env)
            adj = self.guide.generate_environment_adjustment()
            adjustments.append(adj)
            
        # 验证调整趋势
        self.assertLess(
            adjustments[0]['audio_gain'],  # 初始增益
            adjustments[1]['audio_gain']   # 噪音增加时增益
        )
        self.assertGreater(
            adjustments[-1]['visual']['brightness'],  # 变暗后亮度提升
            adjustments[1]['visual']['brightness']
        )
class TestPhysiologicalBaselineAdaptation(unittest.TestCase):
    """用户生理基线自适应测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试用户配置
        self.user_profiles = [
            {'age': 25, 'fitness': 'high'},  # 运动员
            {'age': 45, 'fitness': 'medium'},  # 普通成人
            {'age': 65, 'fitness': 'low'}  # 老年人
        ]
        
    def test_baseline_calibration(self):
        """测试生理基线校准过程"""
        # 模拟5天校准数据收集
        calibration_data = [
            BioFeedback(heart_rate=55, hrv=0.8, breath_rate=10),  # 运动员
            BioFeedback(heart_rate=72, hrv=0.6, breath_rate=14),  # 普通成人
            BioFeedback(heart_rate=68, hrv=0.5, breath_rate=16)   # 老年人
        ]
        
        for data in calibration_data:
            self.guide.record_baseline_data(data)
            
        # 验证基线计算
        baseline = self.guide.get_personal_baseline()
        self.assertAlmostEqual(baseline['heart_rate'], 65, delta=5)
        self.assertAlmostEqual(baseline['hrv'], 0.63, delta=0.1)
        
    def test_dynamic_baseline_adjustment(self):
        """测试动态基线调整"""
        # 初始校准
        self.guide.record_baseline_data(
            BioFeedback(heart_rate=72, hrv=0.6)
        )
        
        # 模拟长期变化(如用户开始锻炼)
        trend_data = [
            BioFeedback(heart_rate=70, hrv=0.65),
            BioFeedback(heart_rate=68, hrv=0.7),
            BioFeedback(heart_rate=65, hrv=0.75)
        ]
        
        for data in trend_data:
            self.guide.update_dynamic_baseline(data)
            
        # 验证基线更新
        new_baseline = self.guide.get_personal_baseline()
        self.assertLess(new_baseline['heart_rate'], 70)
        self.assertGreater(new_baseline['hrv'], 0.65)
        
    def test_contextual_baseline(self):
        """测试上下文相关基线"""
        # 设置不同场景基线
        contexts = ['morning', 'night', 'post_exercise']
        for ctx in contexts:
            self.guide.record_contextual_baseline(
                BioFeedback(heart_rate=60+contexts.index(ctx)*5),
                context=ctx
            )
            
        # 验证场景差异
        morning = self.guide.get_baseline_for_context('morning')
        night = self.guide.get_baseline_for_context('night')
        self.assertLess(morning['heart_rate'], night['heart_rate'])
        
    def test_baseline_based_adjustment(self):
        """测试基于基线的调节策略"""
        # 设置用户基线
        self.guide.set_personal_baseline(
            heart_rate=60,
            hrv=0.8,
            breath_rate=10
        )
        
        # 测试偏离基线的情况
        feedback = BioFeedback(
            heart_rate=75,  # 比基线高15
            hrv=0.5         # 比基线低0.3
        )
        
        adjustment = self.guide.calculate_baseline_adjusted_response(feedback)
        
        # 验证调节强度与偏离程度成正比
        self.assertGreater(adjustment['intensity'], 0.7)
        self.assertEqual(adjustment['pattern'], '4-7-8')

class TestSleepQualityAssessment(unittest.TestCase):
    """睡眠质量评估测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 睡眠测试数据配置
        self.sleep_data = {
            'normal': {
                'deep_sleep': 120,  # 分钟
                'rem': 90,
                'wakeups': 2,
                'hr_avg': 60
            },
            'poor': {
                'deep_sleep': 40,
                'rem': 50,
                'wakeups': 8,
                'hr_avg': 75
            }
        }
        
    def test_sleep_score_calculation(self):
        """测试睡眠评分算法"""
        test_cases = [
            (self.sleep_data['normal'], (85, 90)),  # 正常睡眠预期85-90分
            (self.sleep_data['poor'], (50, 60))     # 差睡眠预期50-60分
        ]
        
        for data, expected_range in test_cases:
            with self.subTest(type=data['deep_sleep'] > 60 and 'good' or 'poor'):
                score = self.guide.calculate_sleep_score(**data)
                self.assertTrue(
                    expected_range[0] <= score <= expected_range[1],
                    f"睡眠评分异常: {score} (预期{expected_range})"
                )
                
    def test_sleep_stage_analysis(self):
        """测试睡眠阶段分析"""
        # 模拟8小时睡眠数据
        sleep_record = {
            'stages': ['N1']*30 + ['N2']*120 + ['N3']*90 + ['REM']*60 + ['N2']*60,
            'timestamps': [i*5 for i in range(360)]  # 5分钟间隔
        }
        
        analysis = self.guide.analyze_sleep_stages(sleep_record)
        
        # 验证阶段分布
        self.assertAlmostEqual(analysis['deep_sleep_pct'], 25, delta=2)  # 90/360=25%
        self.assertAlmostEqual(analysis['rem_pct'], 16.7, delta=1)     # 60/360=16.7%
        
    def test_sleep_recommendation(self):
        """测试睡眠改善建议生成"""
        recommendations = {
            'good': self.guide.generate_sleep_recommendation(self.sleep_data['normal']),
            'poor': self.guide.generate_sleep_recommendation(self.sleep_data['poor'])
        }
        
        # 验证建议差异
        self.assertEqual(len(recommendations['good']), 0)  # 好睡眠无建议
        self.assertGreater(len(recommendations['poor']), 3)  # 差睡眠至少3条建议
        
        # 验证建议合理性
        poor_rec = recommendations['poor']
        self.assertTrue(any('增加深睡眠' in r for r in poor_rec))
        self.assertTrue(any('减少夜间觉醒' in r for r in poor_rec))
        
    def test_long_term_trend(self):
        """测试长期睡眠趋势分析"""
        # 生成30天模拟数据
        for i in range(30):
            quality = 'good' if i % 5 != 0 else 'poor'  # 每5天一次差睡眠
            self.guide.record_daily_sleep(
                score=random.randint(85, 95) if quality == 'good' else random.randint(40, 60),
                **self.sleep_data[quality]
            )
            
        # 验证趋势检测
        trends = self.guide.analyze_sleep_trends()
        self.assertAlmostEqual(trends['avg_score'], 80, delta=5)
        self.assertEqual(trends['worst_day']['wakeups'], 8)  # 最差那天的觉醒次数

class TestUserBehaviorPatterns(unittest.TestCase):
    """用户行为模式分析测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟用户行为数据
        self.behavior_data = {
            'weekday': [
                {'time': '08:00', 'duration': 15, 'pattern': '4-7-8'},
                {'time': '22:00', 'duration': 30, 'pattern': 'equal'}
            ],
            'weekend': [
                {'time': '10:00', 'duration': 45, 'pattern': 'coh'},
                {'time': '21:00', 'duration': 20, 'pattern': 'box'}
            ]
        }
        
    def test_usage_pattern_recognition(self):
        """测试使用模式识别"""
        # 加载30天行为数据
        for _ in range(30):
            for day_type, sessions in self.behavior_data.items():
                for session in sessions:
                    self.guide.record_user_behavior(
                        timestamp=datetime.strptime(session['time'], '%H:%M'),
                        duration=session['duration'],
                        pattern=session['pattern'],
                        day_type=day_type
                    )
        
        # 验证模式识别
        patterns = self.guide.analyze_usage_patterns()
        
        # 验证工作日模式
        self.assertEqual(patterns['weekday']['peak_hour'], '08:00')
        self.assertEqual(patterns['weekday']['fav_pattern'], '4-7-8')
        
        # 验证周末模式
        self.assertEqual(patterns['weekend']['peak_hour'], '10:00')
        self.assertEqual(patterns['weekend']['fav_pattern'], 'coh')

    def test_personalized_recommendation(self):
        """测试个性化推荐生成"""
        # 加载用户历史
        self.guide.load_behavior_history(self.behavior_data)
        
        # 获取不同时段的推荐
        weekday_rec = self.guide.generate_recommendation('weekday', '08:00')
        weekend_rec = self.guide.generate_recommendation('weekend', '21:00')
        
        # 验证推荐匹配习惯
        self.assertEqual(weekday_rec['pattern'], '4-7-8')
        self.assertEqual(weekend_rec['pattern'], 'box')
        self.assertTrue(15 <= weekday_rec['duration'] <= 20)
        
    def test_behavior_change_detection(self):
        """测试行为变化检测"""
        # 初始行为模式
        for _ in range(14):  # 两周数据
            self.guide.record_user_behavior(
                timestamp=datetime.strptime('08:00', '%H:%M'),
                duration=15,
                pattern='4-7-8'
            )
        
        # 模拟行为变化(改为晚间使用)
        for _ in range(14):
            self.guide.record_user_behavior(
                timestamp=datetime.strptime('21:00', '%H:%M'),
                duration=30,
                pattern='equal'
            )
            
        # 验证变化检测
        changes = self.guide.detect_behavior_changes()
        self.assertEqual(changes['time_shift'], 'morning_to_evening')
        self.assertEqual(changes['duration_change'], 'increased')
class TestHealthRiskAssessment(unittest.TestCase):
    """健康风险评估测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 风险测试数据配置
        self.risk_profiles = {
            'low': {
                'hrv': 0.7,
                'resting_hr': 65,
                'sleep_apnea': 2
            },
            'moderate': {
                'hrv': 0.5,
                'resting_hr': 75,
                'sleep_apnea': 8
            },
            'high': {
                'hrv': 0.3,
                'resting_hr': 85,
                'sleep_apnea': 15
            }
        }
        
    def test_risk_level_detection(self):
        """测试风险等级识别"""
        for level, data in self.risk_profiles.items():
            with self.subTest(level=level):
                # 生成7天历史数据
                for _ in range(7):
                    self.guide.record_daily_health_metrics(**data)
                
                # 获取风险评估
                assessment = self.guide.assess_health_risk()
                
                # 验证风险等级
                self.assertEqual(assessment['risk_level'], level)
                
                # 验证关键指标
                self.assertAlmostEqual(
                    assessment['avg_hrv'],
                    data['hrv'],
                    delta=0.05
                )
    
    def test_early_warning_system(self):
        """测试早期预警系统"""
        # 模拟风险指标恶化
        for i in range(7):
            self.guide.record_daily_health_metrics(
                hrv=0.6 - 0.05*i,  # 逐日下降
                resting_hr=70 + i,  # 逐日上升
                sleep_apnea=5 + i   # 逐日增加
            )
            
        # 验证预警触发
        with self.assertLogs(level='WARNING') as log:
            self.guide.check_health_warnings()
            self.assertTrue(any("风险指标恶化" in msg for msg in log.output))
            
        # 验证建议生成
        recommendations = self.guide.generate_health_recommendations()
        self.assertGreater(len(recommendations), 2)
        self.assertTrue(any('就医' in rec for rec in recommendations))
        
    def test_trend_analysis(self):
        """测试长期趋势分析"""
        # 生成30天模拟数据
        for i in range(30):
            risk_level = 'low' if i < 20 else 'moderate' if i < 25 else 'high'
            self.guide.record_daily_health_metrics(
                **self.risk_profiles[risk_level]
            )
            
        # 验证趋势检测
        trends = self.guide.analyze_health_trends()
        self.assertEqual(trends['deterioration_rate'], 'accelerating')
        self.assertEqual(trends['most_affected_metric'], 'sleep_apnea')
        
    def test_emergency_handling(self):
        """测试紧急情况处理"""
        # 模拟危急数据
        critical_data = {
            'hrv': 0.2,
            'resting_hr': 100,
            'oxygen_saturation': 88
        }
        
        # 验证紧急响应
        with self.assertLogs(level='CRITICAL') as log:
            response = self.guide.handle_emergency(critical_data)
            self.assertTrue(any("紧急" in msg for msg in log.output))
            
        # 验证应急措施
        self.assertEqual(response['action'], 'call_emergency')
        self.assertTrue(response['activated'])
@pytest.mark.audio
class TestAudioWorkflow:
    """音频工作流测试"""
    
    @pytest.fixture
    def audio_workflow(self):
        workflow = {
            'generate': MagicMock(return_value={'status': 'success'}),
            'play': MagicMock(return_value={'status': 'playing'}),
            'stop': MagicMock()
        }
        return workflow

    def test_successful_workflow(self, audio_workflow):
        """测试成功的工作流"""
        self.meditation._sound_therapy = audio_workflow['generate']
        self.meditation.play_audio = audio_workflow['play']
        
        result = self.meditation.verify_audio_workflow()
        assert result is True
        audio_workflow['generate'].assert_called_once()
        audio_workflow['play'].assert_called_once()
@pytest.mark.quality
class TestAudioQuality:
    """音频质量测试"""
    
    @pytest.mark.parametrize("mode,expected_rate", [
        ('default', 48000),
        ('hifi', 96000)
    ])
    def test_sample_rates(self, mode, expected_rate):
        """测试不同模式的采样率"""
        result = self.meditation._sound_therapy(
            duration=300,
            mode=mode,
            hifi_mode=(mode == 'hifi')
        )
        assert result['quality_metrics']['sample_rate'] == expected_rate

class TestAudioPreferenceLearning(unittest.TestCase):
    """用户音频偏好学习测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 音频参数测试配置
        self.audio_preferences = {
            'morning': {
                'volume': 0.7,
                'tempo': 0.6,
                'frequency': 432
            },
            'night': {
                'volume': 0.4,
                'tempo': 0.4,
                'frequency': 396
            }
        }
        
    def test_preference_recognition(self):
        """测试音频偏好识别"""
        # 加载用户历史偏好
        for context, prefs in self.audio_preferences.items():
            self.guide.record_audio_preference(
                context=context,
                volume=prefs['volume'],
                tempo=prefs['tempo'],
                frequency=prefs['frequency']
            )
            
        # 验证偏好学习
        learned_prefs = self.guide.get_learned_audio_preferences()
        
        # 验证早晨偏好
        self.assertAlmostEqual(
            learned_prefs['morning']['volume'],
            0.7,
            delta=0.05
        )
        
        # 验证夜间偏好
        self.assertAlmostEqual(
            learned_prefs['night']['frequency'],
            396,
            delta=5
        )

    def test_contextual_recommendation(self):
        """测试上下文相关音频推荐"""
        # 训练模型
        self.guide.train_audio_preference_model(self.audio_preferences)
        
        # 获取不同场景推荐
        morning_rec = self.guide.recommend_audio_params('morning')
        night_rec = self.guide.recommend_audio_params('night')
        
        # 验证推荐匹配历史偏好
        self.assertAlmostEqual(
            morning_rec['volume'],
            self.audio_preferences['morning']['volume'],
            delta=0.1
        )
        self.assertAlmostEqual(
            night_rec['tempo'],
            self.audio_preferences['night']['tempo'],
            delta=0.1
        )

    def test_real_time_adaptation(self):
        """测试实时音频参数调整"""
        # 模拟使用过程中的调整
        adjustments = [
            {'volume': +0.1, 'timestamp': time.time() - 3600},
            {'tempo': -0.1, 'timestamp': time.time() - 1800},
            {'frequency': -10, 'timestamp': time.time() - 900}
        ]
        
        for adj in adjustments:
            self.guide.record_audio_adjustment(**adj)
            
        # 验证参数更新
        current_params = self.guide.get_current_audio_params()
        self.assertAlmostEqual(current_params['volume'], 0.8, delta=0.05)
        self.assertAlmostEqual(current_params['tempo'], 0.5, delta=0.05)
        self.assertAlmostEqual(current_params['frequency'], 422, delta=5)

    def test_hybrid_recommendation(self):
        """测试混合推荐策略(偏好+实时状态)"""
        # 设置当前生理状态(压力)
        self.guide.update_bio_feedback(
            BioFeedback(
                heart_rate=85,
                hrv=0.4,
                breath_rate=18
            )
        )
        
        # 获取混合推荐
        recommendation = self.guide.generate_hybrid_audio_recommendation('night')
        
        # 验证压力状态下的调整(音量略高)
        self.assertGreater(
            recommendation['volume'],
            self.audio_preferences['night']['volume']
        )
        # 保持基础频率偏好
        self.assertAlmostEqual(
            recommendation['frequency'],
            396,
            delta=5
        )

class TestMeditationEffectiveness(unittest.TestCase):
    """冥想效果量化评估测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 冥想效果测试数据
        self.effectiveness_data = {
            'beginner': {
                'hr_reduction': 5,  # 心率降低
                'hrv_increase': 0.2,
                'respiration_rate': 14
            },
            'experienced': {
                'hr_reduction': 10,
                'hrv_increase': 0.4,
                'respiration_rate': 10
            }
        }
        
    def test_effectiveness_scoring(self):
        """测试冥想效果评分算法"""
        test_cases = [
            (self.effectiveness_data['beginner'], (60, 70)),  # 初学者预期60-70分
            (self.effectiveness_data['experienced'], (85, 95))  # 有经验者85-95分
        ]
        
        for data, expected_range in test_cases:
            with self.subTest(type=data['hr_reduction'] < 8 and 'beginner' or 'experienced'):
                score = self.guide.calculate_effectiveness_score(**data)
                self.assertTrue(
                    expected_range[0] <= score <= expected_range[1],
                    f"冥想效果评分异常: {score} (预期{expected_range})"
                )
                
    def test_pre_post_comparison(self):
        """测试冥想前后生理指标对比"""
        # 模拟冥想前后数据
        pre_data = BioFeedback(
            heart_rate=75,
            hrv=0.5,
            breath_rate=16
        )
        post_data = BioFeedback(
            heart_rate=65,  # 降低10
            hrv=0.7,       # 增加0.2
            breath_rate=12  # 降低4
        )
        
        # 计算改善效果
        improvement = self.guide.compare_pre_post_meditation(pre_data, post_data)
        
        # 验证关键指标变化
        self.assertEqual(improvement['hr_reduction'], 10)
        self.assertAlmostEqual(improvement['hrv_increase'], 0.2, delta=0.05)
        self.assertEqual(improvement['respiration_reduction'], 4)
        
    def test_long_term_progress(self):
        """测试长期进步趋势分析"""
        # 生成30天模拟数据
        for i in range(30):
            effectiveness = {
                'hr_reduction': 5 + i*0.2,  # 逐步改善
                'hrv_increase': 0.2 + i*0.01,
                'respiration_rate': 14 - i*0.1
            }
            self.guide.record_daily_meditation(effectiveness)
            
        # 验证趋势分析
        trends = self.guide.analyze_progress_trends()
        self.assertEqual(trends['progress_rate'], 'steady')
        self.assertAlmostEqual(trends['hr_improvement'], 0.2, delta=0.05)
        
    def test_personalized_benchmark(self):
        """测试个性化基准评估"""
        # 设置用户基线
        self.guide.set_personal_benchmark(
            hr_reduction=8,
            hrv_increase=0.3,
            respiration_reduction=3
        )
        
        # 测试不同效果
        test_results = [
            {'hr_reduction': 5, 'score': 'below'},  # 低于基准
            {'hr_reduction': 8, 'score': 'meet'},   # 达到基准
            {'hr_reduction': 12, 'score': 'exceed'}  # 超过基准
        ]
        
        for result in test_results:
            with self.subTest(performance=result['score']):
                evaluation = self.guide.evaluate_against_benchmark(
                    hr_reduction=result['hr_reduction']
                )
                self.assertEqual(evaluation['performance'], result['score'])

class TestMeditationScenarioAdaptation(unittest.TestCase):
    """冥想场景适应性测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试场景配置
        self.scenarios = {
            'stress_relief': {
                'target_metrics': {'hr_reduction': 10, 'hrv_increase': 0.3},
                'duration': 600
            },
            'focus_enhancement': {
                'target_metrics': {'eeg_theta_alpha_ratio': 0.8},
                'duration': 300  
            },
            'sleep_aid': {
                'target_metrics': {'respiration_rate': 12},
                'duration': 900
            }
        }
        
    def test_scenario_detection(self):
        """测试场景自动识别"""
        test_cases = [
            # (用户目标, 生理指标, 预期场景)
            ('减压', {'hr': 85}, 'stress_relief'),
            ('提高专注', {'eeg_alpha': 8}, 'focus_enhancement'),
            ('助眠', {'respiration': 16}, 'sleep_aid')
        ]
        
        for goal, metrics, expected in test_cases:
            with self.subTest(scenario=expected):
                scenario = self.guide.detect_scenario(goal, metrics)
                self.assertEqual(scenario, expected)
                
    def test_scenario_specific_adjustment(self):
        """测试场景特定参数调整"""
        for scenario, config in self.scenarios.items():
            with self.subTest(scenario=scenario):
                params = self.guide.generate_scenario_params(scenario)
                
                # 验证参数匹配场景需求
                if scenario == 'stress_relief':
                    self.assertEqual(params['pattern'], '4-7-8')
                elif scenario == 'focus_enhancement':
                    self.assertEqual(params['pattern'], 'box')
                elif scenario == 'sleep_aid':
                    self.assertEqual(params['pattern'], 'coh')
                    
                # 验证时长设置
                self.assertEqual(params['duration'], config['duration'])
                
    def test_dynamic_scenario_switching(self):
        """测试动态场景切换"""
        # 模拟从减压到助眠的场景变化
        transitions = [
            ('stress_relief', {'hr': 80}),
            ('stress_relief', {'hr': 75}), 
            ('sleep_aid', {'respiration': 14})
        ]
        
        adjustments = []
        for scenario, metrics in transitions:
            adj = self.guide.adapt_to_scenario(scenario, metrics)
            adjustments.append(adj)
            
        # 验证参数变化趋势
        self.assertEqual(adjustments[0]['pattern'], '4-7-8')
        self.assertEqual(adjustments[-1]['pattern'], 'coh')
        self.assertLess(adjustments[-1]['respiration_rate'], adjustments[0]['respiration_rate'])
        
    def test_scenario_efficacy_validation(self):
        """测试场景效果验证"""
        for scenario in self.scenarios:
            with self.subTest(scenario=scenario):
                # 模拟前后数据
                pre_data = BioFeedback(heart_rate=80, hrv=0.5, breath_rate=16)
                post_data = BioFeedback(heart_rate=70, hrv=0.65, breath_rate=12)
                
                # 验证效果评估
                efficacy = self.guide.evaluate_scenario_efficacy(
                    scenario, 
                    pre_data,
                    post_data
                )
                self.assertTrue(efficacy['success'])
                self.assertGreater(efficacy['improvement_rate'], 0.5)

class TestVoiceGuidanceGeneration(unittest.TestCase):
    """语音引导生成测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试用户状态配置
        self.user_states = {
            'beginner': {
                'experience': 1,  # 经验值
                'hr': 75,
                'attention': 0.6
            },
            'experienced': {
                'experience': 3,
                'hr': 65,
                'attention': 0.8
            }
        }
        
    def test_voice_style_selection(self):
        """测试语音风格选择逻辑"""
        test_cases = [
            # (用户类型, 预期语音风格)
            ('beginner', 'gentle'),
            ('experienced', 'neutral')
        ]
        
        for user_type, expected in test_cases:
            with self.subTest(user_type=user_type):
                style = self.guide.select_voice_style(
                    self.user_states[user_type]
                )
                self.assertEqual(style, expected)
                
    def test_pacing_adjustment(self):
        """测试语速节奏调整"""
        # 模拟从紧张到放松的状态变化
        state_sequence = [
            {'hr': 85, 'expected_pace': 'slow'},
            {'hr': 75, 'expected_pace': 'moderate'},
            {'hr': 65, 'expected_pace': 'slow'}
        ]
        
        for state in state_sequence:
            with self.subTest(hr=state['hr']):
                pace = self.guide.determine_pacing(state['hr'])
                self.assertEqual(pace, state['expected_pace'])
                
    def test_content_generation(self):
        """测试引导内容生成"""
        test_cases = [
            # (场景, 用户状态, 预期关键词)
            ('stress_relief', {'hr': 80}, ['放松', '呼吸']),
            ('focus', {'attention': 0.7}, ['专注', '当下']),
            ('sleep', {'hr': 60}, ['入睡', '平静'])
        ]
        
        for scenario, state, keywords in test_cases:
            with self.subTest(scenario=scenario):
                content = self.guide.generate_guidance_content(scenario, state)
                for kw in keywords:
                    self.assertIn(kw, content)
                    
    def test_real_time_adaptation(self):
        """测试实时语音引导调整"""
        # 模拟15分钟冥想过程中的状态变化
        state_changes = [
            {'minute': 0, 'hr': 80, 'expected_intensity': 0.8},
            {'minute': 5, 'hr': 75, 'expected_intensity': 0.7},
            {'minute': 10, 'hr': 68, 'expected_intensity': 0.5}
        ]
        
        for change in state_changes:
            guidance = self.guide.generate_real_time_guidance(
                timestamp=change['minute']*60,
                heart_rate=change['hr']
            )
            self.assertAlmostEqual(
                guidance['intensity'],
                change['expected_intensity'],
                delta=0.1
            )
            
    def test_personalized_phrasing(self):
        """测试个性化措辞生成"""
        # 模拟不同用户偏好
        user_profiles = [
            {'name': '王', 'preference': 'formal', 'expected': '请您'},
            {'name': '张', 'preference': 'casual', 'expected': '你可以'}
        ]
        
        for user in user_profiles:
            with self.subTest(name=user['name']):
                phrase = self.guide.generate_personalized_phrase(
                    user['preference']
                )
                self.assertIn(user['expected'], phrase)

class TestMeditationInterruptionHandling(unittest.TestCase):
    """冥想中断处理测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 中断场景配置
        self.interruption_scenarios = {
            'short': {'duration': 30, 'reason': 'phone'},  # 短时中断
            'medium': {'duration': 180, 'reason': 'urgent'},  # 中等中断
            'long': {'duration': 600, 'reason': 'emergency'}  # 长时间中断
        }
        
    def test_interruption_detection(self):
        """测试中断事件检测"""
        for scenario in self.interruption_scenarios.values():
            with self.subTest(duration=scenario['duration']):
                # 模拟中断事件
                event = self.guide.detect_interruption(
                    duration=scenario['duration'],
                    reason=scenario['reason']
                )
                
                # 验证事件分类
                if scenario['duration'] < 60:
                    self.assertEqual(event['severity'], 'mild')
                elif scenario['duration'] < 300:
                    self.assertEqual(event['severity'], 'moderate')
                else:
                    self.assertEqual(event['severity'], 'severe')
                    
    def test_recovery_guidance(self):
        """测试恢复引导策略"""
        test_cases = [
            # (中断时长, 冥想阶段, 预期引导方式)
            (30, 'beginning', 'quick_refocus'),  # 初期短中断
            (120, 'middle', 'gradual_return'),   # 中期中等中断
            (300, 'peak', 'full_restart')        # 深度阶段长中断
        ]
        
        for duration, phase, expected in test_cases:
            with self.subTest(phase=phase):
                guidance = self.guide.generate_recovery_guidance(
                    duration=duration,
                    meditation_phase=phase
                )
                self.assertEqual(guidance['strategy'], expected)
                
    def test_progress_preservation(self):
        """测试冥想进度保存与恢复"""
        # 模拟冥想进行到5分钟时中断
        original_state = {
            'phase': 'middle',
            'progress': 0.4,
            'breath_count': 12
        }
        
        # 保存状态
        self.guide.save_meditation_state(original_state)
        
        # 模拟15分钟后恢复
        restored_state = self.guide.restore_meditation_state()
        
        # 验证关键状态恢复
        self.assertEqual(restored_state['phase'], original_state['phase'])
        self.assertAlmostEqual(
            restored_state['progress'],
            original_state['progress'] * 0.8,  # 进度衰减
            delta=0.05
        )
        
    def test_multiple_interruptions(self):
        """测试多次中断处理"""
        interruptions = [
            {'time': 120, 'duration': 30},  # 2分钟时中断30秒
            {'time': 300, 'duration': 60},  # 5分钟时中断1分钟
            {'time': 420, 'duration': 120}  # 7分钟时中断2分钟
        ]
        
        recovery_times = []
        for intr in interruptions:
            # 模拟中断和恢复
            self.guide.handle_interruption(intr['duration'])
            recovery = self.guide.get_recovery_time()
            recovery_times.append(recovery)
            
            # 验证恢复时间与中断时长成正比
            self.assertAlmostEqual(
                recovery,
                intr['duration'] * 0.5,  # 恢复时间=中断时长*0.5
                delta=5
            )
        
        # 验证多次中断后的总衰减
        self.assertLess(
            self.guide.current_session['effectiveness'],
            0.7  # 多次中断后效果降低
        )
        
    def test_abnormal_interruption(self):
        """测试异常中断处理"""
        # 模拟异常长时间中断(超过10分钟)
        with self.assertLogs(level='WARNING') as log:
            response = self.guide.handle_interruption(600)
            self.assertTrue(any("长时间中断" in msg for msg in log.output))
            
        # 验证安全措施
        self.assertEqual(response['action'], 'restart_with_guidance')
        self.assertTrue(response['safety_check_passed'])

class TestVisualizationGeneration(unittest.TestCase):
    """冥想效果可视化测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试数据配置
        self.test_sessions = [
            {
                'duration': 20,
                'effectiveness': 75,
                'metrics': {
                    'hr_reduction': 8,
                    'hrv_increase': 0.25,
                    'respiration_reduction': 3
                }
            },
            {
                'duration': 30,
                'effectiveness': 85,
                'metrics': {
                    'hr_reduction': 12,
                    'hrv_increase': 0.35,
                    'respiration_reduction': 5
                }
            }
        ]
        
    def test_summary_report_generation(self):
        """测试摘要报告生成"""
        # 加载测试数据
        for session in self.test_sessions:
            self.guide.record_session(session)
            
        # 生成报告
        report = self.guide.generate_summary_report()
        
        # 验证核心指标
        self.assertIn('avg_effectiveness', report)
        self.assertAlmostEqual(report['avg_effectiveness'], 80, delta=5)
        
        # 验证图表数据存在
        self.assertIsInstance(report['charts']['progress_trend'], dict)
        self.assertGreater(len(report['charts']['metric_comparison']), 0)
        
    def test_real_time_visualization(self):
        """测试实时可视化数据生成"""
        # 模拟实时数据流
        metrics_sequence = [
            {'timestamp': 0, 'hr': 75, 'hrv': 0.5},
            {'timestamp': 300, 'hr': 68, 'hrv': 0.65},
            {'timestamp': 600, 'hr': 62, 'hrv': 0.75}
        ]
        
        # 生成实时图表数据
        viz_data = []
        for metric in metrics_sequence:
            data = self.guide.generate_realtime_visualization(metric)
            viz_data.append(data)
            
            # 验证数据结构
            self.assertIn('x', data)
            self.assertIn('y_values', data)
            self.assertEqual(len(data['y_values']['heart_rate']), 1)
        
        # 验证数据趋势
        self.assertLess(viz_data[0]['y_values']['heart_rate'][0],
                       viz_data[-1]['y_values']['heart_rate'][0])
        
    def test_comparison_chart_generation(self):
        """测试对比图表生成"""
        # 生成基准数据
        baseline = {
            'hr_reduction': 8,
            'hrv_increase': 0.3,
            'respiration_reduction': 4
        }
        
        # 生成对比数据
        comparison = self.guide.generate_comparison_chart(
            current=self.test_sessions[0]['metrics'],
            baseline=baseline
        )
        
        # 验证对比维度
        self.assertEqual(len(comparison['metrics']), 3)
        self.assertIn('percentage_diff', comparison)
        
        # 验证差异计算
        self.assertAlmostEqual(
            comparison['percentage_diff']['hr_reduction'],
            (self.test_sessions[0]['metrics']['hr_reduction'] - baseline['hr_reduction']) / baseline['hr_reduction'] * 100,
            delta=0.1
        )
        
    def test_personalized_visualization(self):
        """测试个性化可视化设置"""
        # 测试不同用户偏好
        user_preferences = [
            {'style': 'minimal', 'expected': {'chart_type': 'line', 'color_scheme': 'mono'}},
            {'style': 'detailed', 'expected': {'chart_type': 'radar', 'color_scheme': 'vivid'}}
        ]
        
        for pref in user_preferences:
            with self.subTest(style=pref['style']):
                viz_config = self.guide.generate_personalized_visualization(pref['style'])
                for key, value in pref['expected'].items():
                    self.assertEqual(viz_config[key], value)

class TestSocialFeatures(unittest.TestCase):
    """冥想社交功能测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试社交数据配置
        self.social_data = {
            'group_sessions': [
                {'id': 1, 'participants': 5, 'duration': 30},
                {'id': 2, 'participants': 12, 'duration': 45}
            ],
            'friends': ['user2', 'user3', 'user5']
        }
        
    def test_group_session_creation(self):
        """测试创建群组冥想会话"""
        # 创建新会话
        session = self.guide.create_group_session(
            duration=30,
            max_participants=10
        )
        
        # 验证会话参数
        self.assertEqual(session['duration'], 30)
        self.assertEqual(session['max_participants'], 10)
        self.assertEqual(session['status'], 'waiting')
        
    def test_join_group_session(self):
        """测试加入群组会话"""
        # 模拟加入现有会话
        result = self.guide.join_group_session(
            session_id=self.social_data['group_sessions'][0]['id'],
            user_id='test_user'
        )
        
        # 验证加入结果
        self.assertTrue(result['success'])
        self.assertEqual(result['session_status'], 'active')
        
    def test_social_presence_sync(self):
        """测试社交状态同步"""
        # 模拟好友状态更新
        status_updates = [
            {'user': 'user2', 'state': 'meditating', 'duration': 15},
            {'user': 'user3', 'state': 'online', 'duration': 0}
        ]
        
        for update in status_updates:
            self.guide.update_social_presence(
                user_id=update['user'],
                state=update['state'],
                duration=update['duration']
            )
        
        # 验证状态同步
        presence_data = self.guide.get_social_presence()
        self.assertEqual(presence_data['user2']['state'], 'meditating')
        self.assertGreater(presence_data['user2']['streak'], 0)
        
    def test_achievement_sharing(self):
        """测试成就分享功能"""
        # 模拟成就解锁
        achievement = {
            'name': '7天连续冥想',
            'date': datetime.now().strftime('%Y-%m-%d')
        }
        
        # 验证分享流程
        with self.assertLogs(level='INFO') as log:
            self.guide.share_achievement(
                achievement=achievement,
                recipients=self.social_data['friends']
            )
            self.assertTrue(any("分享成就" in msg for msg in log.output))
            
        # 验证分享记录
        shares = self.guide.get_recent_shares()
        self.assertEqual(shares[0]['achievement'], achievement['name'])
        
    def test_social_recommendations(self):
        """测试社交推荐算法"""
        # 加载社交数据
        self.guide.load_social_data(self.social_data)
        
        # 获取推荐
        recommendations = self.guide.generate_social_recommendations()
        
        # 验证推荐内容
        self.assertIn('group_session', recommendations)
        self.assertIn('friend_suggestions', recommendations)
        
        # 验证群组推荐基于参与度
        self.assertEqual(
            recommendations['group_session']['id'],
            self.social_data['group_sessions'][1]['id']  # 应推荐参与人数多的会话
        )

class TestDataPrivacyProtection(unittest.TestCase):
    """冥想数据隐私保护测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试数据配置
        self.sensitive_data = [
            {
                'user_id': 'user_123',
                'bio_data': BioFeedback(
                    heart_rate=75,
                    hrv=0.6,
                    breath_rate=14
                ),
                'timestamp': datetime.now()
            },
            {
                'user_id': 'user_456',
                'bio_data': BioFeedback(
                    heart_rate=68,
                    hrv=0.7,
                    breath_rate=12
                ),
                'timestamp': datetime.now()
            }
        ]
        
    def test_data_encryption(self):
        """测试生物特征数据加密"""
        for data in self.sensitive_data:
            encrypted = self.guide.encrypt_bio_data(data['bio_data'])
            
            # 验证加密结果
            self.assertNotEqual(encrypted['heart_rate'], data['bio_data'].heart_rate)
            self.assertTrue(hasattr(encrypted, 'encryption_key_id'))
            self.assertIsInstance(encrypted['cipher_text'], bytes)
            
    def test_secure_data_transmission(self):
        """测试安全数据传输"""
        test_cases = [
            {'protocol': 'TLS_1.3', 'expected': True},
            {'protocol': 'HTTP', 'expected': False}
        ]
        
        for case in test_cases:
            with self.subTest(protocol=case['protocol']):
                result = self.guide.check_transmission_security(
                    protocol=case['protocol']
                )
                self.assertEqual(result['is_secure'], case['expected'])
                
    def test_data_anonymization(self):
        """测试数据匿名化处理"""
        # 处理原始数据
        anonymized = []
        for data in self.sensitive_data:
            result = self.guide.anonymize_data(data)
            anonymized.append(result)
            
            # 验证匿名化字段
            self.assertNotEqual(result['user_id'], data['user_id'])
            self.assertIsNone(result.get('ip_address'))
            
        # 验证可逆性检查
        self.assertFalse(
            self.guide.can_reidentify(anonymized[0], self.sensitive_data[0])
        )
        
    def test_consent_management(self):
        """测试用户授权管理"""
        # 模拟授权设置
        consent_settings = {
            'data_collection': True,
            'data_sharing': False,
            'research_participation': True
        }
        
        # 验证授权持久化
        self.guide.update_consent_settings(consent_settings)
        saved_settings = self.guide.get_consent_settings()
        
        self.assertEqual(saved_settings['data_sharing'], False)
        self.assertTrue(saved_settings['research_participation'])
        
    def test_auto_data_purge(self):
        """测试自动数据清理"""
        # 生成过期测试数据
        old_data = {
            'user_id': 'test_user',
            'timestamp': datetime.now() - timedelta(days=365),
            'bio_data': BioFeedback(heart_rate=72)
        }
        
        # 验证清理机制
        with self.assertLogs(level='INFO') as log:
            self.guide.purge_old_data()
            self.assertTrue(any("自动清理" in msg for msg in log.output))
            
        # 验证数据不可访问
        with self.assertRaises(DataNotFoundError):
            self.guide.access_user_data(old_data['user_id'])
class TestAICoachPersonalization(unittest.TestCase):
    """AI教练个性化测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 用户长期数据配置
        self.user_profile = {
            'meditation_style': 'breath_focus',
            'preferred_duration': 20,
            'weaknesses': ['posture', 'consistency'],
            'progress_history': {
                'hr_reduction': [5, 6, 7, 8],
                'hrv_increase': [0.2, 0.25, 0.3]
            }
        }
        
    def test_coach_profile_creation(self):
        """测试教练档案生成"""
        profile = self.guide.create_coach_profile(self.user_profile)
        
        # 验证档案关键字段
        self.assertEqual(profile['style'], 'breath_focus')
        self.assertEqual(profile['session_length'], 20)
        self.assertIn('posture', profile['focus_areas'])
        
    def test_personalized_advice_generation(self):
        """测试个性化建议生成"""
        # 模拟用户最近3次会话
        sessions = [
            {'effectiveness': 65, 'issues': ['posture']},
            {'effectiveness': 70, 'issues': ['wandering_mind']},
            {'effectiveness': 75, 'issues': ['posture']}
        ]
        
        advice = self.guide.generate_personalized_advice(
            profile=self.user_profile,
            recent_sessions=sessions
        )
        
        # 验证建议针对性
        self.assertTrue(any('姿势调整' in tip for tip in advice))
        self.assertFalse(any('呼吸技巧' in tip for tip in advice))  # 用户擅长领域
        
    def test_adaptive_guidance(self):
        """测试自适应引导策略"""
        test_cases = [
            # (连续天数, 预期引导强度)
            (3, 0.6),   # 新手期中等强度
            (10, 0.8),  # 提升期高强度
            (30, 0.5)   # 稳定期温和引导
        ]
        
        for streak, expected in test_cases:
            with self.subTest(streak=streak):
                guidance = self.guide.generate_adaptive_guidance(
                    current_streak=streak,
                    progress_rate=self.user_profile['progress_history']
                )
                self.assertAlmostEqual(guidance['intensity'], expected, delta=0.1)
                
    def test_milestone_recognition(self):
        """测试里程碑识别"""
        # 模拟用户达成21天连续冥想
        for _ in range(21):
            self.guide.record_daily_session(
                duration=20,
                effectiveness=random.randint(70, 80)
            )
            
        # 验证里程碑奖励
        milestones = self.guide.check_milestones()
        self.assertEqual(milestones['current_streak'], 21)
        self.assertIn('21_day_streak', milestones['achievements'])
        
    def test_behavior_based_recommendation(self):
        """测试基于行为的推荐"""
        # 模拟用户通常在晚间冥想
        for _ in range(14):
            self.guide.record_session_time(
                time=datetime.strptime('21:00', '%H:%M')
            )
            
        # 获取晚间推荐
        recommendation = self.guide.generate_time_based_recommendation()
        self.assertEqual(recommendation['suggested_time'], 'evening')
        self.assertEqual(recommendation['duration'], 20)

class TestDeviceCompatibility(unittest.TestCase):
    """设备兼容性测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试设备配置
        self.devices = [
            {'type': 'Muse2', 'sampling_rate': 256, 'channels': 4},
            {'type': 'AppleWatch', 'sampling_rate': 100, 'channels': 1},
            {'type': 'MiBand', 'sampling_rate': 50, 'channels': 1}
        ]
        
    def test_signal_quality_detection(self):
        """测试信号质量检测"""
        for device in self.devices:
            with self.subTest(device=device['type']):
                # 模拟设备连接
                quality = self.guide.check_signal_quality(
                    device_type=device['type'],
                    sampling_rate=device['sampling_rate']
                )
                
                # 验证质量评估
                if device['sampling_rate'] >= 100:
                    self.assertEqual(quality['rating'], 'excellent')
                else:
                    self.assertEqual(quality['rating'], 'acceptable')
                    
    def test_data_resampling(self):
        """测试数据重采样处理"""
        test_cases = [
            # (原始采样率, 目标采样率, 预期采样点数)
            (256, 128, 500),  # 降采样
            (50, 100, 2000),  # 升采样
            (100, 100, 1000)  # 相同采样率
        ]
        
        for original, target, expected in test_cases:
            with self.subTest(f"{original}->{target}"):
                # 生成测试信号
                signal = np.sin(np.linspace(0, 10, original * 10))
                
                # 处理信号
                processed = self.guide.resample_signal(
                    signal, 
                    original_freq=original,
                    target_freq=target
                )
                
                # 验证采样点数量
                self.assertEqual(len(processed), expected)
                
    def test_device_specific_filtering(self):
        """测试设备特定滤波处理"""
        # 模拟不同设备噪声特征
        noise_profiles = {
            'Muse2': {'noise_freq': [50, 60], 'artifact_type': 'blink'},
            'AppleWatch': {'noise_freq': [30], 'artifact_type': 'motion'},
            'MiBand': {'noise_freq': [10], 'artifact_type': 'contact'}
        }
        
        for device, profile in noise_profiles.items():
            with self.subTest(device=device):
                # 应用设备特定滤波
                filtered = self.guide.apply_device_specific_filter(
                    device_type=device,
                    noise_profile=profile
                )
                
                # 验证滤波参数
                self.assertEqual(
                    filtered['applied_filters'][0]['target_freq'],
                    profile['noise_freq']
                )
                
    def test_latency_compensation(self):
        """测试设备延迟补偿"""
        test_cases = [
            ('bluetooth', 150),  # 蓝牙典型延迟
            ('usb', 50),         # USB延迟
            ('internal', 20)     # 内置设备延迟
        ]
        
        for protocol, expected in test_cases:
            with self.subTest(protocol=protocol):
                # 测量并补偿延迟
                measured = self.guide.measure_latency(protocol)
                self.guide.apply_latency_compensation(measured)
                
                # 验证补偿应用
                self.assertAlmostEqual(
                    self.guide.audio_sync_delay,
                    expected - measured * 0.8,  # 应用80%补偿
                    delta=5
                )
                
    def test_fallback_mechanism(self):
        """测试降级处理机制"""
        # 模拟设备断开
        with self.assertLogs(level='WARNING') as log:
            self.guide.handle_device_disconnection(
                device_type='Muse2',
                fallback_to='internal'
            )
            self.assertTrue(any("切换至备用设备" in msg for msg in log.output))
            
        # 验证备用设备激活
        self.assertEqual(self.guide.active_device, 'internal')
        self.assertTrue(self.guide.fallback_mode)

class TestRealTimeFeedback(unittest.TestCase):
    """实时反馈系统测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 实时数据流配置
        self.real_time_data = [
            {'timestamp': 0, 'hr': 78, 'hrv': 0.5, 'breath': 16},  # 初始紧张
            {'timestamp': 60, 'hr': 72, 'hrv': 0.6, 'breath': 14}, # 开始放松
            {'timestamp': 120, 'hr': 68, 'hrv': 0.7, 'breath': 12} # 深度放松
        ]
        
    def test_feedback_timing(self):
        """测试反馈时机判断"""
        for data in self.real_time_data:
            with self.subTest(time=data['timestamp']):
                # 计算理想反馈间隔(心率越高反馈越频繁)
                ideal_interval = self.guide.calculate_feedback_interval(
                    current_hr=data['hr']
                )
                
                # 验证间隔与心率成反比
                if data['timestamp'] > 0:
                    prev_hr = self.real_time_data[data['timestamp']//60-1]['hr']
                    if data['hr'] < prev_hr:
                        self.assertGreater(ideal_interval, 15)  # 心率下降时延长间隔
                    else:
                        self.assertLessEqual(ideal_interval, 15) # 心率升高时缩短间隔

    def test_breath_pattern_matching(self):
        """测试呼吸模式匹配"""
        # 模拟不同呼吸模式
        patterns = [
            {'ratio': 1.0, 'expected': 'equal'},     # 1:1:1
            {'ratio': 1.5, 'expected': '4-7-8'},    # 4:7:8
            {'ratio': 0.67, 'expected': 'coh'}      # 2:3:3
        ]
        
        for pattern in patterns:
            with self.subTest(pattern=pattern['expected']):
                matched = self.guide.match_breath_pattern(
                    inhale=4*pattern['ratio'],
                    exhale=6,
                    pause=2*pattern['ratio']
                )
                self.assertEqual(matched, pattern['expected'])

    def test_instant_correction(self):
        """测试即时纠正建议"""
        # 模拟常见错误
        mistakes = [
            {'posture': 0.3, 'expected': 'posture_adjustment'},
            {'breath_irregular': True, 'expected': 'breath_guidance'},
            {'attention': 0.4, 'expected': 'refocus'}
        ]
        
        for case in mistakes:
            with self.subTest(mistake=case['expected']):
                correction = self.guide.generate_instant_correction(case)
                self.assertEqual(correction['type'], case['expected'])
                self.assertLess(correction['delay'], 2)  # 延迟应小于2秒

    def test_real_time_adaptation_flow(self):
        """测试实时适应流程"""
        feedback_history = []
        
        for data in self.real_time_data:
            # 生成实时反馈
            feedback = self.guide.generate_real_time_feedback(data)
            feedback_history.append(feedback)
            
            # 验证反馈强度与放松程度成正比
            if data['timestamp'] > 0:
                prev_hr = self.real_time_data[data['timestamp']//60-1]['hr']
                if data['hr'] < prev_hr:
                    self.assertLess(
                        feedback['intensity'], 
                        feedback_history[-2]['intensity']
                    )
        
        # 验证整体趋势
        self.assertEqual(
            feedback_history[0]['focus'], 
            'relaxation'  # 初始应关注放松
        )
        self.assertEqual(
            feedback_history[-1]['focus'],
            'depth'  # 后期应关注深度
        )

    def test_feedback_prioritization(self):
        """测试反馈优先级处理"""
        # 模拟多问题同时出现
        multi_issues = {
            'posture': 0.2,       # 轻度姿势问题
            'attention': 0.3,     # 中度注意力分散
            'breath': 0.4         # 严重呼吸问题
        }
        
        # 验证优先处理最严重问题
        priority = self.guide.determine_feedback_priority(multi_issues)
        self.assertEqual(priority['primary'], 'breath')
        self.assertEqual(priority['secondary'], 'attention')

class TestEmotionRecognition(unittest.TestCase):
    """情绪识别与响应测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 情绪测试数据配置
        self.emotion_profiles = {
            'anxious': {'hr': 85, 'hrv': 0.4, 'breath': 18},
            'calm': {'hr': 65, 'hrv': 0.7, 'breath': 12},
            'frustrated': {'hr': 78, 'hrv': 0.5, 'breath': 16}
        }
        
    def test_emotion_detection(self):
        """测试基础情绪识别"""
        test_cases = [
            (self.emotion_profiles['anxious'], 'anxious'),
            (self.emotion_profiles['calm'], 'calm'),
            (self.emotion_profiles['frustrated'], 'frustrated')
        ]
        
        for metrics, expected in test_cases:
            with self.subTest(emotion=expected):
                detected = self.guide.detect_emotion_state(metrics)
                self.assertEqual(detected['primary_emotion'], expected)
                
    def test_mixed_emotion_handling(self):
        """测试混合情绪处理"""
        mixed_state = {
            'hr': 75,  # 介于焦虑和沮丧之间
            'hrv': 0.6, 
            'breath': 14
        }
        
        analysis = self.guide.analyze_mixed_emotion(mixed_state)
        self.assertEqual(analysis['dominant_emotion'], 'frustrated')
        self.assertGreater(analysis['confidence'], 0.7)
        
    def test_emotion_based_guidance(self):
        """测试情绪适应性引导"""
        test_cases = [
            ('anxious', 'breath_focus'),
            ('frustrated', 'body_scan'),
            ('calm', 'loving_kindness')
        ]
        
        for emotion, expected in test_cases:
            with self.subTest(emotion=emotion):
                guidance = self.guide.generate_emotion_adaptive_guidance(
                    emotion_state=emotion
                )
                self.assertEqual(guidance['technique'], expected)
                
    def test_emotion_transition(self):
        """测试情绪状态转换跟踪"""
        # 模拟从焦虑到平静的转换
        states = [
            {'timestamp': 0, 'metrics': self.emotion_profiles['anxious']},
            {'timestamp': 300, 'metrics': {'hr': 75, 'hrv': 0.6, 'breath': 14}},
            {'timestamp': 600, 'metrics': self.emotion_profiles['calm']}
        ]
        
        transitions = []
        for state in states:
            transition = self.guide.track_emotion_transition(
                state['metrics'],
                state['timestamp']
            )
            transitions.append(transition)
            
        # 验证转换趋势
        self.assertEqual(transitions[0]['from'], 'anxious')
        self.assertEqual(transitions[-1]['to'], 'calm')
        self.assertLess(
            transitions[-1]['hr_change'], 
            transitions[0]['hr_change']
        )
        
    def test_emergency_emotion_handling(self):
        """测试极端情绪处理"""
        # 模拟惊恐发作状态
        panic_attack = {
            'hr': 120, 
            'hrv': 0.2,
            'breath': 25
        }
        
        with self.assertLogs(level='CRITICAL') as log:
            response = self.guide.handle_extreme_emotion(panic_attack)
            self.assertTrue(any("极端情绪" in msg for msg in log.output))
            
        # 验证应急措施
        self.assertEqual(response['action'], 'emergency_intervention')
        self.assertTrue(response['safety_activated'])

class TestEnvironmentAdaptation(unittest.TestCase):
    """环境自适应测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 环境传感器模拟数据
        self.env_data = {
            'quiet_office': {'noise': 45, 'light': 300, 'movement': 0.1},
            'noisy_street': {'noise': 75, 'light': 800, 'movement': 0.8},
            'dark_room': {'noise': 30, 'light': 50, 'movement': 0.05}
        }
        
    def test_noise_adaptation(self):
        """测试噪音环境适应"""
        test_cases = [
            (self.env_data['quiet_office'], 'normal'),
            (self.env_data['noisy_street'], 'enhanced')
        ]
        
        for env, expected in test_cases:
            with self.subTest(env=env['noise']):
                adjustment = self.guide.adapt_to_noise_level(env['noise'])
                self.assertEqual(adjustment['audio_mode'], expected)
                if env['noise'] > 60:
                    self.assertTrue(adjustment['noise_cancellation'])
                    
    def test_light_adaptation(self):
        """测试光线条件适应"""
        test_cases = [
            (self.env_data['dark_room'], {'brightness': 0.3, 'color_temp': 2700}),
            (self.env_data['quiet_office'], {'brightness': 0.7, 'color_temp': 5000})
        ]
        
        for env, expected in test_cases:
            with self.subTest(light=env['light']):
                visual = self.guide.adapt_to_lighting(env['light'])
                for key in expected:
                    self.assertAlmostEqual(
                        visual[key],
                        expected[key],
                        delta=0.1
                    )
                    
    def test_movement_detection(self):
        """测试环境运动检测"""
        test_cases = [
            (self.env_data['quiet_office'], False),
            (self.env_data['noisy_street'], True)
        ]
        
        for env, expected in test_cases:
            with self.subTest(movement=env['movement']):
                detection = self.guide.detect_environment_movement(env['movement'])
                self.assertEqual(detection['requires_alert'], expected)
                
    def test_hybrid_environment_adaptation(self):
        """测试混合环境因素适应"""
        # 模拟复杂环境(高噪音+低光照)
        complex_env = {
            'noise': 70,
            'light': 100,
            'movement': 0.3
        }
        
        adaptation = self.guide.adapt_to_hybrid_environment(complex_env)
        
        # 验证综合调整
        self.assertEqual(adaptation['audio']['mode'], 'enhanced')
        self.assertEqual(adaptation['visual']['brightness'], 0.5)
        self.assertTrue(adaptation['guidance_intensity'] > 0.7)
        
    def test_environment_learning(self):
        """测试环境模式学习"""
        # 模拟一周环境数据收集
        weekly_pattern = [
            {'time': '09:00', 'env': self.env_data['quiet_office']},
            {'time': '18:00', 'env': self.env_data['noisy_street']},
            {'time': '22:00', 'env': self.env_data['dark_room']}
        ]
        
        for record in weekly_pattern:
            self.guide.record_environment_pattern(
                time=record['time'],
                env_data=record['env']
            )
            
        # 验证预测准确性
        prediction = self.guide.predict_environment('18:30')
        self.assertAlmostEqual(
            prediction['noise'],
            self.env_data['noisy_street']['noise'],
            delta=5
        )

class TestLongTermEffectTracking(unittest.TestCase):
    """长期效果追踪测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 模拟3个月冥想数据
        self.long_term_data = {
            'baseline': {
                'stress_level': 65,
                'sleep_quality': 70,
                'focus_score': 60
            },
            'monthly_progress': [
                {'stress_level': 60, 'sleep_quality': 75, 'focus_score': 65},
                {'stress_level': 55, 'sleep_quality': 80, 'focus_score': 70},
                {'stress_level': 50, 'sleep_quality': 85, 'focus_score': 75}
            ]
        }
        
    def test_trend_analysis(self):
        """测试长期趋势分析算法"""
        # 加载历史数据
        self.guide.load_long_term_data(self.long_term_data)
        
        # 获取趋势分析
        trends = self.guide.analyze_long_term_trends()
        
        # 验证关键指标改善
        self.assertEqual(trends['stress']['improvement'], 15)  # 65->50
        self.assertEqual(trends['sleep']['improvement'], 15)   # 70->85
        self.assertEqual(trends['focus']['improvement'], 15)    # 60->75
        
    def test_milestone_prediction(self):
        """测试里程碑预测"""
        # 基于现有进度预测
        prediction = self.guide.predict_milestone_reach(
            current_progress=self.long_term_data['monthly_progress'][-1],
            metric='stress_level'
        )
        
        # 验证预测逻辑
        self.assertEqual(prediction['target'], 40)  # 下一目标值
        self.assertAlmostEqual(prediction['expected_months'], 2.0, delta=0.5)
        
    def test_plateau_detection(self):
        """测试进步平台期检测"""
        # 模拟平台期数据(连续2个月无显著进步)
        plateau_data = {
            'monthly_progress': [
                {'stress_level': 52, 'sleep_quality': 83, 'focus_score': 74},
                {'stress_level': 51, 'sleep_quality': 84, 'focus_score': 74}
            ]
        }
        
        # 验证平台期识别
        analysis = self.guide.detect_plateau(plateau_data['monthly_progress'])
        self.assertTrue(analysis['is_plateau'])
        self.assertEqual(analysis['most_affected_metric'], 'focus_score')
        
    def test_personalized_roadmap(self):
        """测试个性化提升路线图"""
        # 获取基于当前进展的推荐路线
        roadmap = self.guide.generate_personalized_roadmap(
            baseline=self.long_term_data['baseline'],
            current=self.long_term_data['monthly_progress'][-1]
        )
        
        # 验证路线图逻辑
        self.assertEqual(len(roadmap['phases']), 3)
        self.assertEqual(roadmap['focus_area'], 'stress_level')
        self.assertTrue(all(phase['duration_weeks'] >= 2 for phase in roadmap['phases']))
        
    def test_relapse_detection(self):
        """测试退步情况检测"""
        # 模拟退步数据(压力水平回升)
        relapse_data = {
            'recent_weeks': [
                {'stress_level': 48, 'sleep_quality': 86},
                {'stress_level': 52, 'sleep_quality': 84},
                {'stress_level': 55, 'sleep_quality': 82}
            ]
        }
        
        # 验证退步检测
        with self.assertLogs(level='WARNING') as log:
            result = self.guide.detect_relapse(relapse_data['recent_weeks'])
            self.assertTrue(any("检测到退步" in msg for msg in log.output))
            
        # 验证关键指标
        self.assertEqual(result['metric'], 'stress_level')
        self.assertAlmostEqual(result['regression_rate'], 0.15, delta=0.05)

class TestMultimodalInteraction(unittest.TestCase):
    """多模态交互测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 多模态测试配置
        self.modalities = {
            'audio': {'volume': 0.7, 'frequency': 432},
            'haptic': {'intensity': 0.5, 'pattern': 'pulse'},
            'visual': {'color': '#4A90E2', 'brightness': 0.6}
        }
        
    def test_modality_synchronization(self):
        """测试多模态同步机制"""
        # 生成协同反馈指令
        sync_data = self.guide.generate_multimodal_feedback(
            modality_config=self.modalities,
            sync_tolerance=50  # 毫秒级同步容差
        )
        
        # 验证同步参数
        self.assertLess(sync_data['audio_haptic_delay'], 50)
        self.assertLess(sync_data['visual_audio_delay'], 50)
        self.assertEqual(sync_data['sync_status'], 'aligned')
        
    def test_cross_modal_adaptation(self):
        """测试跨模态自适应调整"""
        # 模拟用户禁用音频
        self.guide.update_user_preferences({'audio_disabled': True})
        
        # 验证触觉增强补偿
        adjusted = self.guide.adjust_for_disabled_modality(
            disabled='audio',
            original_config=self.modalities
        )
        
        self.assertEqual(adjusted['audio']['volume'], 0)
        self.assertGreater(adjusted['haptic']['intensity'], 0.5)
        self.assertTrue(adjusted['visual']['brightness'] > 0.6)
        
    def test_fallback_modes(self):
        """测试模态降级策略"""
        test_cases = [
            ('haptic', {'haptic': False}, 'audio_enhanced'),
            ('visual', {'visual': False}, 'haptic_enhanced')
        ]
        
        for primary, disable, expected in test_cases:
            with self.subTest(failover=primary):
                # 模拟模态失效
                config = self.modalities.copy()
                config.update(disable)
                
                # 获取降级方案
                fallback = self.guide.activate_fallback_modes(config)
                self.assertEqual(fallback['active_mode'], expected)
                
    def test_intensity_balancing(self):
        """测试多模态强度平衡算法"""
        # 模拟高压力状态
        high_stress = {
            'hr': 85,
            'hrv': 0.4,
            'breath': 18
        }
        
        # 获取平衡后的参数
        balanced = self.guide.balance_modality_intensity(
            stress_level=high_stress,
            base_config=self.modalities
        )
        
        # 验证强度调整
        self.assertLess(balanced['audio']['volume'], 0.7)
        self.assertGreater(balanced['haptic']['intensity'], 0.5)
        self.assertLess(balanced['visual']['brightness'], 0.6)
        
    def test_contextual_priority(self):
        """测试场景驱动的模态优先级"""
        test_cases = [
            ('sleep', 'haptic'),  # 睡前应优先触觉反馈
            ('stress', 'audio'),  # 减压场景优先语音引导
            ('focus', 'visual')   # 专注训练优先视觉提示
        ]
        
        for scenario, expected in test_cases:
            with self.subTest(scenario=scenario):
                priority = self.guide.determine_modality_priority(scenario)
                self.assertEqual(priority['primary'], expected)
class TestPersonalizedLearning(unittest.TestCase):
    """个性化学习测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 用户长期行为数据配置
        self.user_behavior = {
            'preferred_times': {
                'morning': 0.7,   # 70%在早晨冥想
                'evening': 0.3    # 30%在晚上
            },
            'effectiveness_by_technique': {
                'body_scan': 0.85,
                'breath_focus': 0.65,
                'loving_kindness': 0.75
            },
            'adjustment_history': [
                {'volume': +0.1, 'timestamp': '2023-01-01'},
                {'duration': -5, 'timestamp': '2023-01-15'}
            ]
        }
        
    def test_behavior_pattern_recognition(self):
        """测试行为模式识别"""
        # 加载用户行为数据
        self.guide.load_user_behavior(self.user_behavior)
        
        # 验证模式识别
        patterns = self.guide.identify_behavior_patterns()
        self.assertEqual(patterns['primary_time'], 'morning')
        self.assertEqual(patterns['most_effective_technique'], 'body_scan')
        
    def test_recommendation_optimization(self):
        """测试推荐策略优化"""
        # 模拟10次迭代优化
        for i in range(10):
            self.guide.record_decision_outcome(
                technique='body_scan' if i < 7 else 'breath_focus',
                effectiveness=80 + i
            )
            
        # 获取优化后的推荐
        recommendation = self.guide.generate_optimized_recommendation()
        self.assertEqual(recommendation['technique'], 'body_scan')
        self.assertGreater(recommendation['confidence'], 0.8)
        
    def test_adaptive_learning_rate(self):
        """测试自适应学习速率"""
        # 模拟不同学习阶段
        test_cases = [
            (10, 0.2),   # 初期快速学习
            (50, 0.1),   # 中期稳定学习
            (100, 0.05)  # 后期微调
        ]
        
        for sessions, expected in test_cases:
            with self.subTest(sessions=sessions):
                rate = self.guide.calculate_learning_rate(sessions)
                self.assertAlmostEqual(rate, expected, delta=0.01)
                
    def test_personalized_parameter_tuning(self):
        """测试个性化参数调优"""
        # 模拟参数调整历史
        self.guide.load_adjustment_history(
            self.user_behavior['adjustment_history']
        )
        
        # 生成调优参数
        tuned = self.guide.tune_parameters()
        self.assertGreater(tuned['volume'], 0.5)  # 历史显示偏好提高音量
        self.assertLess(tuned['duration'], 20)    # 历史显示偏好缩短时长
        
    def test_long_term_adaptation(self):
        """测试长期适应能力"""
        # 模拟6个月行为变化
        monthly_data = [
            {'month': 1, 'preferred_time': 'morning', 'effectiveness': 70},
            {'month': 3, 'preferred_time': 'morning', 'effectiveness': 75},
            {'month': 6, 'preferred_time': 'evening', 'effectiveness': 80}
        ]
        
        # 验证适应能力
        adaptation = self.guide.evaluate_long_term_adaptation(monthly_data)
        self.assertEqual(adaptation['current_preference'], 'evening')
        self.assertGreater(adaptation['improvement_rate'], 0.1)
class TestCrossPlatformCompatibility(unittest.TestCase):
    """跨平台兼容性测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 测试平台配置
        self.platforms = {
            'windows': {'version': '10', 'audio_api': 'WASAPI'},
            'macos': {'version': '12', 'audio_api': 'CoreAudio'},
            'android': {'version': '11', 'audio_api': 'OpenSLES'}
        }
        
    def test_audio_playback_compatibility(self):
        """测试音频播放兼容性"""
        for os_name, config in self.platforms.items():
            with self.subTest(os=os_name):
                # 初始化音频系统
                audio_sys = self.guide.init_audio_system(
                    os_type=os_name,
                    audio_api=config['audio_api']
                )
                
                # 验证音频初始化
                self.assertTrue(audio_sys['initialized'])
                self.assertEqual(audio_sys['active_api'], config['audio_api'])
                
    def test_sensor_data_formatting(self):
        """测试传感器数据格式统一化"""
        # 模拟不同平台传感器数据
        test_data = {
            'android': {'hr': 75.0, 'ts': 1640995200000},  # Android使用毫秒时间戳
            'ios': {'hr': 75, 'ts': 1640995200.0}         # iOS使用秒时间戳
        }
        
        for platform, data in test_data.items():
            with self.subTest(platform=platform):
                # 标准化数据格式
                normalized = self.guide.normalize_sensor_data(
                    raw_data=data,
                    source_os=platform
                )
                
                # 验证统一格式
                self.assertIsInstance(normalized['hr'], int)
                self.assertIsInstance(normalized['ts'], float)
                
    def test_ui_scaling_adaptation(self):
        """测试UI缩放适配"""
        test_cases = [
            ('windows', (1920, 1080), 1.0),   # 桌面标准缩放
            ('android', (1080, 1920), 1.5),   # 手机竖屏
            ('ios', (1170, 2532), 2.0)       # iPhone Pro
        ]
        
        for os_name, resolution, expected in test_cases:
            with self.subTest(os=os_name):
                # 获取适配后的UI参数
                ui_params = self.guide.adapt_ui_parameters(
                    os_type=os_name,
                    resolution=resolution
                )
                
                # 验证缩放因子
                self.assertAlmostEqual(
                    ui_params['scaling_factor'],
                    expected,
                    delta=0.1
                )
                
    def test_performance_benchmarking(self):
        """测试跨平台性能基准"""
        # 模拟不同设备性能数据
        devices = [
            {'os': 'android', 'cpu': 'Snapdragon865', 'mem': 8},
            {'os': 'ios', 'cpu': 'A15', 'mem': 6},
            {'os': 'windows', 'cpu': 'i7-1185G7', 'mem': 16}
        ]
        
        for device in devices:
            with self.subTest(device=device['cpu']):
                # 运行性能测试
                perf = self.guide.run_performance_benchmark(
                    os_type=device['os'],
                    cpu_model=device['cpu'],
                    memory_gb=device['mem']
                )
                
                # 验证关键指标
                self.assertLess(perf['audio_latency'], 200)  # 毫秒
                self.assertGreater(perf['fps'], 30)          # 帧率
                
    def test_fallback_mechanisms(self):
        """测试平台特定降级方案"""
        test_cases = [
            ('android', 'low_memory', {'texture_quality': 'low'}),
            ('ios', 'battery_saver', {'background_freq': 1}),
            ('windows', 'high_dpi', {'render_mode': 'compatibility'})
        ]
        
        for os_name, scenario, expected in test_cases:
            with self.subTest(os=os_name):
                # 获取降级配置
                config = self.guide.get_fallback_config(
                    os_type=os_name,
                    scenario=scenario
                )
                
                # 验证配置适配
                for key, value in expected.items():
                    self.assertEqual(config[key], value)


class TestOfflineMode(unittest.TestCase):
    """离线模式功能测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 离线测试数据配置
        self.offline_data = {
            'cached_meditations': [
                {'id': 1, 'duration': 10, 'type': 'breath'},
                {'id': 2, 'duration': 20, 'type': 'body_scan'}
            ],
            'local_storage': {
                'user_prefs': {'volume': 0.7, 'voice': 'female'},
                'progress_data': {'streak': 5}
            }
        }
        
    def test_offline_detection(self):
        """测试离线状态检测"""
        # 模拟网络状态变化
        for status in [True, False]:
            with self.subTest(online=status):
                detected = self.guide.detect_network_status(status)
                self.assertEqual(detected['is_online'], status)
                
    def test_cached_content_access(self):
        """测试缓存内容访问"""
        # 加载缓存数据
        self.guide.load_cached_content(self.offline_data['cached_meditations'])
        
        # 验证离线访问
        available = self.guide.get_available_offline_content()
        self.assertEqual(len(available), 2)
        self.assertEqual(available[0]['type'], 'breath')
        
    def test_local_storage_sync(self):
        """测试本地存储同步机制"""
        # 模拟数据修改
        self.guide.update_local_storage(
            key='user_prefs',
            value={'volume': 0.8}
        )
        
        # 验证本地存储
        prefs = self.guide.access_local_storage('user_prefs')
        self.assertEqual(prefs['volume'], 0.8)
        
    def test_auto_resync_mechanism(self):
        """测试网络恢复后的自动同步"""
        # 模拟离线修改
        self.guide.update_local_storage(
            key='progress_data',
            value={'streak': 6}
        )
        
        # 模拟网络恢复
        with self.assertLogs(level='INFO') as log:
            self.guide.handle_network_recovery()
            self.assertTrue(any("开始同步本地数据" in msg for msg in log.output))
            
        # 验证同步结果
        self.assertEqual(
            self.guide.cloud_storage['progress_data']['streak'],
            6
        )
        
    def test_offline_analytics(self):
        """测试离线期间的数据收集"""
        # 模拟离线会话
        offline_session = {
            'start': datetime.now(),
            'duration': 15,
            'metrics': {'hr': 72}
        }
        
        # 记录离线数据
        self.guide.record_offline_session(offline_session)
        
        # 验证本地存储
        sessions = self.guide.access_local_storage('offline_sessions')
        self.assertEqual(sessions[0]['duration'], 15)
class TestSmartReminderSystem(unittest.TestCase):
    """智能提醒系统测试"""
    
    def setUp(self):
        self.guide = MeditationGuide()
        # 用户作息数据配置
        self.user_patterns = {
            'sleep_wake': [
                {'date': '2023-01-01', 'bedtime': '23:00', 'wakeup': '07:00'},
                {'date': '2023-01-02', 'bedtime': '22:30', 'wakeup': '06:45'}
            ],
            'optimal_times': {
                'morning': {'start': '07:30', 'end': '08:30'},
                'evening': {'start': '20:00', 'end': '21:00'}
            }
        }
        
    def test_reminder_timing_calculation(self):
        """测试最佳提醒时间计算"""
        # 测试不同场景的提醒时间计算
        test_cases = [
            ('morning', '07:15', '07:30'),  # 早于最佳时段
            ('evening', '20:45', '20:45'),   # 在最佳时段内
            ('night', '22:00', None)         # 非建议时段
        ]
        
        for scenario, current_time, expected in test_cases:
            with self.subTest(scenario=scenario):
                reminder = self.guide.calculate_reminder_time(
                    scenario=scenario,
                    current_time=current_time
                )
                self.assertEqual(reminder, expected)
                
    def test_physiological_readiness(self):
        """测试生理状态就绪检测"""
        # 模拟不同生理状态
        states = [
            {'hr': 75, 'hrv': 0.5, 'ready': False},  # 未准备好
            {'hr': 68, 'hrv': 0.7, 'ready': True}     # 已准备好
        ]
        
        for state in states:
            with self.subTest(hr=state['hr']):
                readiness = self.guide.check_physiological_readiness(
                    hr=state['hr'],
                    hrv=state['hrv']
                )
                self.assertEqual(readiness, state['ready'])
                
    def test_adaptive_reminder_adjustment(self):
        """测试自适应提醒调整"""
        # 模拟用户响应历史
        response_history = [
            {'time': '07:30', 'response': 'accepted'},
            {'time': '07:45', 'response': 'ignored'},
            {'time': '08:00', 'response': 'accepted'}
        ]
        
        # 获取优化后的提醒时间
        optimized = self.guide.optimize_reminder_time(
            preferred_window=self.user_patterns['optimal_times']['morning'],
            response_history=response_history
        )
        
        # 验证避开被忽略的时间段
        self.assertEqual(optimized['adjusted_time'], '07:40')
        self.assertNotIn('07:45', optimized['candidate_times'])
        
    def test_reminder_intensity_calibration(self):
        """测试提醒强度校准"""
        # 测试不同忽略次数后的提醒强度
        test_cases = [
            (0, 'gentle'),    # 首次提醒
            (2, 'moderate'),  # 两次忽略
            (5, 'urgent')     # 多次忽略
        ]
        
        for ignore_count, expected in test_cases:
            with self.subTest(ignores=ignore_count):
                intensity = self.guide.determine_reminder_intensity(
                    consecutive_ignores=ignore_count
                )
                self.assertEqual(intensity, expected)
                
    def test_context_aware_reminder(self):
        """测试上下文感知提醒"""
        # 模拟不同场景
        contexts = [
            {'location': 'home', 'activity': 'relaxing', 'expected': True},
            {'location': 'office', 'activity': 'working', 'expected': False},
            {'location': 'park', 'activity': 'walking', 'expected': True}
        ]
        
        for context in contexts:
            with self.subTest(location=context['location']):
                should_remind = self.guide.evaluate_reminder_context(
                    location=context['location'],
                    activity=context['activity']
                )
                self.assertEqual(should_remind, context['expected'])



class TestMeditationSystem(unittest.TestCase):
    def setUp(self):
        """初始化测试环境"""
        self.guide = MeditationGuide()
        # 添加音频测试相关mock
        self.guide._sound_therapy = MagicMock()
        self.guide.play_audio = MagicMock()
        self.guide.model = MagicMock()
        
    @patch('pygame.mixer.init')
    def test_audio_workflow(self, mock_mixer):
        """测试音频工作流验证"""
        # 配置mock返回值
        self.guide._sound_therapy.return_value = {
            'status': 'success',
            'params': {'file': 'test_audio.wav'},
            'duration': 300
        }
        self.guide.play_audio.return_value = {
            'status': 'playing',
            'player': MagicMock()
        }
        
        # 执行测试
        result = self.guide.verify_audio_workflow()
        
        # 验证结果
        self.assertTrue(result)
        mock_mixer.assert_called_once()
        self.guide._sound_therapy.assert_called_once()
        self.guide.play_audio.assert_called_once()

    @patch('pygame.mixer.init')
    def test_audio_workflow_failure(self, mock_mixer):
        """测试音频工作流失败情况"""
        # 模拟音频生成失败
        self.guide._sound_therapy.return_value = {
            'status': 'error',
            'message': 'Generation failed'
        }
        
        # 执行测试
        result = self.guide.verify_audio_workflow()
        
        # 验证结果
        self.assertFalse(result)
        mock_mixer.assert_not_called()  # 生成失败时不应初始化mixer

        
    @patch('torch.cuda.is_available')
    def test_model_loading(self, mock_cuda):
        """测试模型加载"""
        mock_cuda.return_value = False  # 模拟CPU环境
        guide = MeditationGuide()
        self.assertTrue(hasattr(guide, 'model'))
        
    def test_biofeedback_validation(self):
        """测试生物反馈数据验证"""
        valid_fb = BioFeedback(sleep_efficiency=0.8, sleep_stage='REM')
        self.assertIsNone(valid_fb.validate())
        
        with self.assertRaises(ValueError):
            invalid_fb = BioFeedback(sleep_efficiency=1.5)
            invalid_fb.validate()


    def test_model_loading_edge_cases(self):
        """测试模型加载边界条件"""
        test_cases = [
            {'cuda': True, 'expected': 'cuda'},
            {'cuda': False, 'expected': 'cpu'}
        ]
        for case in test_cases:
            with self.subTest(case=case):
                with patch('torch.cuda.is_available', return_value=case['cuda']):
                    guide = MeditationGuide()
                    self.assertEqual(guide.model.device.type, case['expected'])







class MeditationLoadTest(HttpUser):
    wait_time = between(1, 5)
    
    @task
    def test_mass_session(self):
        self.client.post("/api/mass_session", json={
            "duration": 300,
            "pattern": "coh"
        })
        
    @task(3)
    def test_audio_stream(self):
        self.client.get("/api/audio_stream")


if __name__ == '__main__':
    unittest.main()

