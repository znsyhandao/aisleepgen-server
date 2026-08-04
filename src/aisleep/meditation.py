import time
from typing import List, Optional
import numpy as np
from enum import Enum
from typing import List, Dict, Optional
from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk, messagebox
import logging
import random
import redis  # 确保这行存在
import pygame
import pygame.mixer
from gtts import gTTS
import tempfile
import os
from .deepseek_model import DeepSeekMeditationModel, GuidanceGenerator, BioFeedback, BreathPhase
from .model.deepseek.official.DeepSeek_V3 import DeepSeekV3
import unittest
from unittest.mock import patch, MagicMock
from src.aisleep.processors import BioSignalProcessor
from src.aisleep.filters import ButterworthFilter, NotchFilter

from aisleep.utils import RedisLock  # 改为绝对导入



# 修改所有测试方法中的导入语句

import pytest

import torch  # 用于模型初始化

from src.api.payment_gateway import PaymentGateway

# Add at the VERY TOP of the file (before other imports)

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ['OMP_NUM_THREADS'] = '4'  # Match your CPU core count
os.environ['MKL_NUM_THREADS'] = '4'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '1'  # Enable oneDNN optimizations

torch.set_num_threads(4)  # Limit CPU threads
torch.backends.mkldnn.enabled = True  # Enable Intel optimizations


# 在文件顶部添加以下代码
class ExponentialFilter:
    """指数平滑滤波器"""
    def __init__(self, alpha=0.5):
        self.alpha = alpha
        self.value = None
    
    def update(self, new_value):
        if self.value is None:
            self.value = new_value
        else:
            self.value = self.alpha * new_value + (1 - self.alpha) * self.value
        return self.value

class MovingAverage:
    """移动平均滤波器"""
    def __init__(self, window_size=3):
        self.window_size = window_size
        self.values = []
    
    def update(self, new_value):
        self.values.append(new_value)
        if len(self.values) > self.window_size:
            self.values.pop(0)
        return sum(self.values) / len(self.values)

class RealTimeFeedbackProcessor:
    def __init__(self, update_interval=2, max_adjustments=5):
        # 动态调节参数
        self.params = {
            'respiration_rate': 12,  # 默认呼吸频率(次/分钟)
            'pattern': 'equal',      # 默认呼吸模式
            'intensity': 0.5         # 调节强度(0-1)
        }
        # 生理参数阈值
        self.thresholds = {
            'hrv': {'low': 0.3, 'high': 0.7},
            'stress': {'low': 0.3, 'high': 0.7},
            'hr': {'low': 60, 'high': 90}
        }
        # 平滑滤波器
        self.filters = {
            'hr': ExponentialFilter(alpha=0.2),
            'hrv': MovingAverage(window_size=3)
        }

class DeepSeekIntegration:
    def __init__(self, model_path: str = "default", cache_dir: str = None):
        """专注模型加载和文本生成"""
        # 移除错误的递归初始化
        self.model = None
        self.tokenizer = None
        try:
            
            # 确保使用正确的transformers导入
            from transformers import AutoModelForCausalLM, AutoTokenizer

            # 更新量化配置
            quant_config = {
                'load_in_4bit': True,
                'bnb_4bit_compute_dtype': torch.float16,
                'bnb_4bit_quant_type': "nf4",
                'device_map': 'auto'
            }
            
            # 使用AutoModelForCausalLM代替DeepSeekV3
            self.model = AutoModelForCausalLM.from_pretrained(
                "deepseek-ai/deepseek-llm-7b",  # 使用官方模型名称
                cache_dir=cache_dir,
                torch_dtype=torch.float16,
                **quant_config
            )
            
            self.tokenizer = AutoTokenizer.from_pretrained(
                "deepseek-ai/deepseek-llm-7b",
                cache_dir=cache_dir
            )
            
            # 添加模型优化配置
            self.model.eval()
            torch.backends.cuda.enable_flash_sdp(True)
            
        except Exception as e:
            logging.critical(f"模型加载失败: {str(e)}")
            self.model = None
            self.tokenizer = None

    def generate_guidance(self, prompt: str, max_length: int = 200) -> str:
        """增强版指导生成方法"""
        if not self.model or not self.tokenizer:
            raise RuntimeError("模型未正确初始化")
            
        try:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
            outputs = self.model.generate(
                **inputs,
                max_length=max_length,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
            return self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        except Exception as e:
            logging.error(f"指导生成失败: {str(e)}")
            return "无法生成指导，请稍后再试"

    
class BreathPhase(Enum):
    INHALE = 1
    HOLD = 2
    EXHALE = 3
    REST = 4

@dataclass
class BioFeedback:
    def __init__(self, heart_rate=0.0, breath_rate=0.0, hrv=0.0, 
                skin_conductance=0.0, stress_level=0.0, 
                meditation_level=0.0, timestamp=0.0, sleep_stage='', 
                sleep_latency=0, sleep_efficiency=0.0, waso=0.0):
        self.heart_rate = heart_rate
        self.breath_rate = breath_rate
        self.hrv = hrv
        self.skin_conductance = skin_conductance
        self.stress_level = stress_level
        self.meditation_level = meditation_level
        self.timestamp = timestamp
        self.sleep_stage = sleep_stage
        self.sleep_latency = sleep_latency
        self.sleep_efficiency = sleep_efficiency
        self.waso = waso
    heart_rate: float
    breath_rate: float
    hrv: float  # 心率变异性
    skin_conductance: float
    stress_level: float
    meditation_level: float
    timestamp: float
    sleep_stage: str  # 睡眠阶段: awake/REM/N1/N2/N3
    sleep_latency: float  # 入睡潜伏期(分钟)
    sleep_efficiency: float  # 睡眠效率(0-1)
    waso: float  # 夜间觉醒时间(分钟)
    def validate(self):
        """验证生物反馈数据有效性"""
        if not 0 <= self.sleep_efficiency <= 1:
            raise ValueError(f"无效睡眠效率: {self.sleep_efficiency}")
        if self.sleep_latency < 0:
            raise ValueError(f"无效睡眠潜伏期: {self.sleep_latency}")
        if self.sleep_stage not in ['awake', 'REM', 'N1', 'N2', 'N3']:
            raise ValueError(f"未知睡眠阶段: {self.sleep_stage}")


class MeditationGuide:
    """基于神经科学的冥想引擎核心"""
    def _generate_coherent_pattern(self, heart_rate: float = 70.0) -> tuple:
        """生成生理协调呼吸模式
        
        参数:
            heart_rate: 当前心率，用于计算最佳呼吸频率
            
        返回:
            包含呼吸阶段持续时间的元组
        """
        # 计算基于心率的呼吸频率 (6次/分钟是常见的协调呼吸频率)
        breath_rate = 6  # 次/分钟
        cycle_duration = 60 / breath_rate  # 每个呼吸周期总秒数
        
        # 吸气:呼气比例通常为1:1或1:2
        inhale_duration = round(cycle_duration * 0.4)  # 40%时间吸气
        exhale_duration = round(cycle_duration * 0.6)  # 60%时间呼气
    
        return (inhale_duration, exhale_duration)
    def __init__(self, model_path: str = "default", deepseek: Optional[DeepSeekIntegration] = None, redis_client=None):
        """冥想引擎初始化
        # 使用传入的redis_client或创建默认连接
        # 修复redis_client参数位置
        """
        # 使用传入的redis_client或创建默认连接
        self.redis = redis_client if redis_client is not None else redis.Redis(host='localhost', port=6379)
        
        # 确保deepseek属性被正确初始化
        self.deepseek = deepseek or DeepSeekIntegration(model_path)


        # 初始化基础参数
        self.session_history = []
        self.base_respiration_rate = 12
        self.current_audio = None
        # 添加Numba初始化
        self._init_numba_optimizations()
        # 新增模式选择标志
        self.use_advanced_mode = False  # 默认为基础模式
        

        
        # 新增音频优化配置
        self.audio_optimizer = AudioOptimizer(
            sample_rate=48000,
            bit_depth=24,
            dynamic_range=90,
            eq_presets={
                'relax': {'low': 2, 'mid': -1, 'high': -2},
                'focus': {'low': 0, 'mid': 2, 'high': 1},
                'sleep': {'low': 3, 'mid': -2, 'high': -3}
            }
        )
        
        # 新增用户音频偏好记录
        self.user_audio_prefs = {
            'volume': 0.7,
            'eq_profile': 'relax',
            'noise_reduction': True
        }

        # 新增信号处理模块
        self.signal_processor = BioSignalProcessor(
            sample_rate=250,  # 250Hz采样率
            filters={
                'hr': ButterworthFilter(lowcut=0.5, highcut=5),
                'eeg': NotchFilter(freq=50)  # 去除工频干扰
            }
        )
        # 新增质量评估配置
        self.quality_metrics = {
            'baseline': {
                'hrv': 0.5,
                'stress': 0.5,
                'respiration': 12
            },
            'thresholds': {
                'hrv_improvement': 0.1,
                'stress_reduction': 0.15,
                'respiration_sync': 0.8
            }
        }
        self.session_analytics = []  # 存储所有会话分析数据
        # 硬件优化配置
        if not torch.cuda.is_available():
            print("Optimizing for Intel CPU with MKL acceleration")
            torch.backends.mkldnn.enabled = True
            torch.set_flush_denormal(True)

        # 大规模会话优化配置
        self.mass_session_config = {
            'audio_compression': 'opus@64kbps',
            'minimal_feedback': True,
            'batch_processing': {
                'window_size': 1000,
                'interval': 5.0
            }
        }
        
        # 分布式锁配置
        self.distributed_lock = RedisLock(
            redis_client=self.redis,
            lock_timeout=30
        )

        # 初始化生物反馈参数
        self.biofeedback_params = {
            'heart_rate': 70,
            'breath_rate': 12,  
        }
        self.neurofeedback_params = {
            'eeg_alpha': 0,
            'eeg_theta': 0,
            'update_interval': 5
        }
        
        # 初始化呼吸模式（精简版）
        self.breath_patterns = {
            # 基础呼吸模式
            '4-7-8': (4, 7, 8),  # Andrew Weil博士推广的放松呼吸法
            'box': (4, 4, 4, 4),  # 军方常用的方形呼吸法
            'equal': (5, 5),      # 平衡呼吸法
            'coh': self._generate_coherent_pattern,  # 生理协调呼吸模式
            
            # 高级呼吸模式
            'resonance': {  # 心脏共振呼吸法
                'phases': [(6, BreathPhase.INHALE), (6, BreathPhase.EXHALE)],
                'optimal_hrv': 0.65
            },
            'physiological_sigh': {  # 生理叹息法
                'phases': [(2, BreathPhase.INHALE), (1, BreathPhase.INHALE), 
                          (10, BreathPhase.EXHALE)]
            },
            'cadence_478': {  # 节奏型4-7-8
                'phases': [(4, BreathPhase.INHALE), (7, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (2, BreathPhase.REST)]
            },
            'coherent_heart': {  # 心脏协调呼吸
                'phases': [(5, BreathPhase.INHALE), (5, BreathPhase.EXHALE)],
                'entrainment': True
            },
            
            # 睡眠相关模式
            'sleep_induce': {  # 助眠呼吸法
                'phases': [(4, BreathPhase.INHALE), (7, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (2, BreathPhase.REST)]
            },
            'deep_sleep': {  # 深度睡眠呼吸法
                'phases': [(6, BreathPhase.INHALE), (0, BreathPhase.HOLD)],
                'entrainment': False
            },
            
            # 通用冥想模式（合并了多个相同定义）
            'meditation': {  # 冥想呼吸（合并了breathing_techniques/stress_relief/anxiety_relief）
                'phases': [(4, BreathPhase.INHALE), (4, BreathPhase.HOLD),
                          (8, BreathPhase.EXHALE), (4, BreathPhase.REST)],
                'tags': ['meditation', 'stress_relief', 'anxiety_relief']
            }
        }

        # 添加睡眠管理参数
        self.sleep_params = {
            'optimal_sleep_duration': 7.5,  # 小时
            'sleep_stage_targets': {
                'N3': 0.2,  # 深度睡眠占比目标
                'REM': 0.25  # REM睡眠占比目标
            }
        }
        # 添加音频配置
        self.audio_config = {
            'background': 'assets/meditation_music.mp3',
            'voice': 'assets/voice_guidance.mp3',
            'inhale': 'assets/breath_in.wav',
            'exhale': 'assets/breath_out.wav',
            'bell': 'assets/bell.mp3'

        }
        # 新增实时调节器
        self.feedback_processor = RealTimeFeedbackProcessor(
            update_interval=2,  # 2秒更新频率
            max_adjustments=5   # 最大调节次数
        )



        
        # 使用锁的示例
        with self.distributed_lock as lock:
            # 执行需要加锁的操作
            pass

        self._lock = threading.Lock()
        self._acquired = False

    def __enter__(self):
        """支持上下文管理协议"""
        self._lock.acquire()
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理协议"""
        if self._acquired:
            self._lock.release()
            self._acquired = False

    # ... 其他方法保持不变 ...

        
    def process_data(self, data):
        """使用上下文管理器自动管理锁"""
        with self.redis_lock:
            # 受保护的代码区域
            result = self._process(data)
        return result



    def _update_learning_model(self, session_data):
        """基于会话结果更新学习模型"""
        effectiveness = self._calculate_effectiveness(session_data)
        
        # 更新音频偏好
        if effectiveness > 0.8:
            self.user_audio_prefs.update({
                'volume': session_data.get('preferred_volume', 0.7),
                'eq_profile': session_data.get('effective_eq', 'relax')
            })
        
        # 调整呼吸模式权重
        for pattern, eff in session_data.get('pattern_effectiveness', {}).items():
            self.pattern_weights[pattern] = 0.9 * self.pattern_weights.get(pattern, 1.0) + 0.1 * eff


    def _play_background_music(self):
        """增强版背景音乐播放"""
        try:
            # 应用用户偏好设置
            audio_file = self.audio_optimizer.optimize(
                "assets/meditation_music.mp3",
                volume=self.user_audio_prefs['volume'],
                eq_profile=self.user_audio_prefs['eq_profile'],
                noise_reduction=self.user_audio_prefs['noise_reduction']
            )
            
            pygame.mixer.init()
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play(loops=-1)
            
        except Exception as e:
            print(f"音频优化播放失败: {e}")
            # 回退到普通播放模式
            super()._play_background_music()


    def process_raw_signals(self, raw_data: dict) -> dict:
        """增强版信号处理流水线"""
        # 1. 实时去噪
        cleaned = {
            'ecg': self.signal_processor.clean_ecg(raw_data['ecg']),
            'eeg': self.signal_processor.clean_eeg(raw_data['eeg'])
        }
        
        # 2. 特征提取 (使用Numba加速)
        features = self._extract_features(cleaned)
        
        # 3. 异常检测
        if self._detect_artifacts(features):
            raise SignalQualityError("信号质量过低")
            
        return features
    def _init_numba_optimizations(self):
        """初始化Numba加速"""
        from numba import njit, config
        config.DISABLE_JIT = False  # 确保启用JIT
        
        # 预编译关键函数
        self._calculate_phase_timings = njit(fastmath=True)(self._calculate_phase_timings_impl)

    @staticmethod
    def _calculate_phase_timings_impl(hr: float, hrv: float) -> tuple:
        """呼吸阶段时间计算的核心实现"""
        return 60/hr, 60/hr * (0.5 + 0.5*hrv)

    def _generate_coherent_pattern(self, heart_rate: float = 70.0) -> tuple:
        """使用加速后的版本"""
        inhale, exhale = self._calculate_phase_timings(heart_rate, 0.5)  # 默认HRV=0.5
        return (round(inhale), round(exhale))

    # ... 保留其他代码 ...
    def dynamic_adjust(self, feedback: BioFeedback):
        """增强版实时调节算法"""
        
        try:
            with self.distributed_lock:  # 添加分布式锁保护
                if not self.health_checker.is_service_healthy('biofeedback'):
                    raise ServiceUnavailableError("生物反馈服务不可用")
            
            # 根据场景选择调节算法
            if self.use_advanced_mode:  # 高级模式使用混合决策
                adjustment = self.calculate_hybrid_adjustment(
                    feedback.heart_rate,
                    feedback.hrv,
                    feedback.current_phase
                )
            else:  # 普通模式使用基础调节
                adjustment = self.calculate_adjustment(
                    feedback.heart_rate,
                    feedback.hrv,
                    feedback.current_phase
                )
            
            # 应用平滑过渡
            self.current_params = self.feedback_processor.smooth_transition(
                current=self.current_params,
                target=adjustment
            )
            
            # 更新音频参数
            self.audio_engine.update_params(
                binaural_freq=self._calc_binaural_freq(feedback.hrv),
                volume=self._calc_volume(feedback.skin_conductance)
            )
            # 模型加载优化部分
        
            # 1. 先加载轻量级组件
            from .deepseek_model import GuidanceGenerator
            self.guidance_generator = GuidanceGenerator()
            
            # 2. 加载DeepSeek集成
            self.deepseek = DeepSeekIntegration()
            
            # 3. 主模型加载（使用更健壮的方式）
            self.model = self._load_model_safely(model_path)
            
        except Exception as e:
            logging.critical(f"系统初始化失败: {str(e)}")
            raise RuntimeError(f"无法初始化冥想系统: {str(e)}")

    def _load_model_safely(self, model_path: str):
        """安全加载模型的方法"""
        try:
            # 添加重试机制
            for attempt in range(3):
                try:
                    model = DeepSeekMeditationModel.load(
                        model_path,
                        quantized=True,
                        quant_config={
                            'activation': 'per_tensor',
                            'weight': 'per_channel',
                            'quant_dtype': 'int8',
                            'calibration': 'min_max'
                        },
                        neuroplasticity_mode=True,
                        pruning_ratio=0.4
                    )
                    
                    # 验证模型完整性
                    if not hasattr(model, 'forward'):
                        raise RuntimeError("加载的模型无效")
                        
                    # 配置模型参数
                    model.set_mixed_precision({
                        'attention_layers': 'fp16',
                        'output_layer': 'fp16'
                    })
                    model.adjust_parameters({
                        'learning_rate': 0.001,
                        'batch_size': 32,
                        'optimizer': 'adam',
                        'loss_function': 'mse'
                    })
                    
                    return model
                    
                except Exception as e:
                    if attempt == 2:  # 最后一次尝试
                        raise
                    time.sleep(1)  # 等待后重试
                    
        except Exception as e:
            logging.error(f"模型加载失败: {str(e)}")
            # 回退到轻量模式
            return self._create_lightweight_model()


    def _create_lightweight_model(self):
        """创建轻量级回退模型"""
        class LightweightModel:
            def __init__(self):
                self.capabilities = {
                    'basic_meditation': True,
                    'advanced_features': False
                }
                
            def forward(self, *args, **kwargs):
                raise RuntimeError("轻量模式不支持此功能")
                
        return LightweightModel()
    


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

    def play_audio(self, audio_type: str, text: str = None, audio_path: str = None):
        """音频播放方法"""
        try:
            pygame.mixer.init()
            sound = pygame.mixer.Sound(audio_path)
            sound.play()
            return {'player': sound, 'file': audio_path}
        except Exception as e:
            logging.error(f"音频播放失败: {str(e)}")
            return None

# ... 其他代码保持不变 ...
    def evaluate_session_quality(self, session_data: dict) -> dict:
        """综合评估冥想会话质量
        参数:
            session_data: 包含生物反馈数据的会话记录
        返回:
            包含各项质量评分的字典
        """
        # 1. 计算关键指标变化
        metrics = {
            'hrv_change': session_data['final_feedback']['hrv'] - session_data['initial_feedback']['hrv'],
            'stress_change': session_data['initial_feedback']['stress_level'] - session_data['final_feedback']['stress_level'],
            'respiration_sync': self._calculate_respiration_sync(session_data)
        }
        
        # 2. 评估各项指标
        evaluations = {
            'hrv_improvement': metrics['hrv_change'] >= self.quality_metrics['thresholds']['hrv_improvement'],
            'stress_reduction': metrics['stress_change'] >= self.quality_metrics['thresholds']['stress_reduction'],
            'respiration_coherence': metrics['respiration_sync'] >= self.quality_metrics['thresholds']['respiration_sync']
        }
        
        # 3. 计算综合评分 (0-100)
        score = (
            0.4 * min(1.0, metrics['hrv_change'] / 0.3) +  # HRV改善占比40%
            0.3 * min(1.0, metrics['stress_change'] / 0.5) +  # 压力减轻占比30%
            0.3 * metrics['respiration_sync']  # 呼吸同步占比30%
        ) * 100
        
        # 4. 记录分析结果
        analysis = {
            'session_id': len(self.session_analytics),
            'timestamp': time.time(),
            'metrics': metrics,
            'evaluations': evaluations,
            'score': round(score, 1),
            'pattern_effectiveness': self._evaluate_pattern_effectiveness(session_data)
        }
        self.session_analytics.append(analysis)
        
        return analysis

    def _calculate_respiration_sync(self, session_data: dict) -> float:
        """计算呼吸与引导的同步率"""
        matched = sum(1 for fb in session_data['bio_feedback'] 
                     if abs(fb['breath_rate'] - session_data['target_breath_rate']) <= 2)
        return matched / len(session_data['bio_feedback']) if session_data['bio_feedback'] else 0

    def _evaluate_pattern_effectiveness(self, session_data: dict) -> dict:
        """评估呼吸模式效果"""
        effectiveness = {}
        for pattern in session_data.get('used_patterns', []):
            # 计算每个模式使用期间的HRV改善
            pattern_data = [fb for fb in session_data['bio_feedback'] 
                          if fb['current_pattern'] == pattern]
            if len(pattern_data) > 1:
                start_hrv = pattern_data[0]['hrv']
                end_hrv = pattern_data[-1]['hrv']
                effectiveness[pattern] = end_hrv - start_hrv
        
        return effectiveness
class AudioOptimizer:
    def __init__(self, sample_rate=44100, bit_depth=16, dynamic_range=80, eq_presets=None):
        self.sample_rate = sample_rate
        self.bit_depth = bit_depth
        self.dynamic_range = dynamic_range
        self.eq_presets = eq_presets or {}
        
    def optimize(self, input_path, volume=1.0, eq_profile='flat', noise_reduction=False):
        """优化音频文件并返回临时文件路径"""
        try:
            # 创建临时输出文件
            output_path = os.path.join(tempfile.gettempdir(), f"optimized_{os.path.basename(input_path)}")
            
            # 应用音频处理 (实际实现需要集成音频处理库如pydub)
            self._apply_effects(
                input_path, 
                output_path,
                volume=volume,
                eq_profile=eq_profile,
                noise_reduction=noise_reduction
            )
            
            return output_path
            
        except Exception as e:
            logging.error(f"音频优化失败: {e}")
            return input_path  # 返回原始文件作为回退

    def analyze_session(self, session_id: int) -> dict:
        # ... 已有分析代码 ...
        
        # 新增音频效果评估
        analysis['audio_analysis'] = {
            'preferred_volume': self._detect_optimal_volume(session_data),
            'effective_eq': self._detect_effective_eq_profile(session_data),
            'latency_issues': len([e for e in session_data['events'] if e['type'] == 'audio_latency'])
        }
        
        # 触发学习更新
        self._update_learning_model(analysis)
        
        return analysis



class RecommendationEngine:
    def __init__(self):
        # 混合推荐模型
        self.models = {
            'collab_filter': CollaborativeFilter(),
            'content_based': ContentBased(),
            'neural_net': NeuralRecommendation()
        }
        
    def recommend(self, user_id, context):
        """上下文感知推荐"""
        # 特征工程
        features = self._extract_features(user_id, context)
        
        # 模型融合
        predictions = []
        for model in self.models.values():
            predictions.append(model.predict(features))
            
        # 动态加权
        weights = self._calculate_weights(context)
        final_rec = self._blend_predictions(predictions, weights)
        
        return self._apply_business_rules(final_rec)
class PaymentIntegration:
    def __init__(self, payment_gateway=None):
        """初始化支付集成
        参数:
            payment_gateway: 
                - None: 使用默认支付网关
                - 单个网关实例: 所有支付渠道使用同一个网关实例
                - 字典: 自定义各渠道网关 {'wechat': wechat_gateway, 'alipay': alipay_gateway}
        """
        if isinstance(payment_gateway, dict):
            # 方式3：传入自定义网关字典
            self.gateways = {
                'wechat': payment_gateway.get('wechat', WechatPayV3()),
                'alipay': payment_gateway.get('alipay', AlipayClient()),
                'apple_pay': payment_gateway.get('apple_pay', ApplePayAdapter())
            }
        else:
            # 方式1和方式2
            self.gateways = {
                'wechat': payment_gateway or WechatPayV3(),
                'alipay': payment_gateway or AlipayClient(),
                'apple_pay': payment_gateway or ApplePayAdapter()
            }
        self.cache = {}

        
    def check_entitlement(self, user_id):
        """增强版权益检查"""
        # 本地缓存检查
        if cached := self.cache.get(user_id):
            return cached
            
        # 实时验证
        for gateway in self.gateways.values():
            if result := gateway.check_subscription(user_id):
                self.cache.set(user_id, result)
                return result
                
        return self._check_trial_quota(user_id)

    def create_order(self, user_id, plan):
        """智能订单路由"""
        # 根据支付成功率自动选择渠道
        channel = self._select_optimal_gateway(user_id)
        return self.gateways[channel].create_order(
            amount=plan['price'],
            user=user_id,
            product_id=plan['id']
        )
class AnalyticsSystem:
    def __init__(self):
        # 多维度数据采集
        self.metrics = {
            'user_engagement': TimeSeriesDB(),
            'content_performance': ColumnarDB(),
            'payment_metrics': RedisCache()
        }
        
    def track_session(self, session_data):
        """全链路会话跟踪"""
        # 实时处理
        self.stream_processor.ingest(session_data)
        
        # 离线分析
        self._store_raw_data(session_data)
        
        # 异常检测
        if self.anomaly_detector.check(session_data):
            self.alert_manager.trigger(session_data)
            
    def generate_report(self, time_range):
        """商业智能报告"""
        return {
            'financial': self._calc_roi(time_range),
            'engagement': self._calc_retention(time_range),
            'content': self._rank_content(time_range)
        }
    

    
    def track_commercial_usage(self, session_data):
        """追踪商业化功能使用情况"""
        commercial_events = [
            ('content_view', session_data.get('content_type')),
            ('preview_play', session_data.get('preview_count')),
            ('purchase_attempt', session_data.get('purchase_intent'))
        ]
        
        for event, value in commercial_events:
            if value:
                self._track_event(
                    user_id=session_data['user_id'],
                    event_type=event,
                    properties={
                        'content_type': session_data.get('content_type'),
                        'preview_remaining': session_data.get('preview_remaining'),
                        'timestamp': time.time()
                    }
                )

    def track_premium_usage(self, session_data):
        """追踪付费功能使用"""
        self._track_event(
            user_id=session_data['user_id'],
            event_type='premium_content',
            properties={
                'content_type': session_data['content_type'],
                'price': session_data['price'],
                'timestamp': time.time()
            }
        )


    def calculate_adjustment(self, current_hr, current_hrv, current_phase):
        """核心调节算法 - 仅生成基础调节策略"""
        # 1. 数据预处理
        filtered_hr = self.filters['hr'].update(current_hr)
        filtered_hrv = self.filters['hrv'].update(current_hrv)
        
        # 2. 状态评估
        state = self._assess_state(filtered_hr, filtered_hrv)
        
        # 3. 生成基础调节策略
        return {
            'respiration_rate': self._calc_breath_rate(state),
            'pattern': self._select_pattern(state),
            'intensity': self._calc_intensity(state)
        }

    def calculate_hybrid_adjustment(self, current_hr, current_hrv, current_phase):
        """混合决策算法 - 结合规则引擎和强化学习"""
        # 获取基础调节策略
        base_adjustment = self.calculate_adjustment(current_hr, current_hrv, current_phase)
        
        # 规则引擎决策
        state = self._assess_state(
            self.filters['hr'].update(current_hr),
            self.filters['hrv'].update(current_hrv)
        )
        rule_based = self._rule_based_decision(state)
        
        # 强化学习决策
        state_tensor = torch.FloatTensor(self._to_feature_vector(state))
        rl_based = self.policy_net(state_tensor).detach().numpy()
        
        # 动态融合
        final_adjustment = {
            'respiration_rate': 0.7*rl_based[0] + 0.3*rule_based['rate'],
            'pattern': rl_based[1] if rl_based[1] > 0.8 else rule_based['pattern'],
            'intensity': base_adjustment['intensity']  # 保留原始强度计算
        }
        
        # 应用安全限制
        return self._apply_safety_limits(final_adjustment)



    def _assess_state(self, hr, hrv):
        """生理状态评估"""
        if hrv < self.thresholds['hrv']['low'] and hr > self.thresholds['hr']['high']:
            return 'high_stress'
        elif hrv > self.thresholds['hrv']['high'] and hr < self.thresholds['hr']['low']:
            return 'deep_relaxation'
        else:
            return 'normal'

    def apply_adjustments(self, adjustments):
        """执行多模态调节"""
        # 1. 音频调节
        self.audio_engine.set_binaural_freq(
            base=432 + adjustments['intensity'] * 50,
            delta=adjustments['respiration_rate'] / 60 * 1000
        )
        
        # 2. 视觉调节
        self.visual_engine.update_pattern(
            pattern=adjustments['pattern'],
            speed=adjustments['respiration_rate'] / 12
        )
        
        # 3. 触觉反馈 (如支持)
        if self.haptic_device:
            self.haptic_device.set_intensity(adjustments['intensity'])


    def track_commercial_metrics(self):
        """商业指标追踪"""
        return {
            # 用户体验指标
            'real_time_adjustment_count': self.adjustment_count,
            'stress_reduction_rate': self._calc_stress_reduction(),
            
            # 商业价值指标
            'premium_feature_usage': {
                'bio_feedback': self.premium_features.get('bio_feedback', 0),
                'dynamic_patterns': self.premium_features.get('dynamic_patterns', 0)
            },
            
            # 技术性能指标
            'avg_processing_latency': sum(self.latency_log)/len(self.latency_log),
            'success_rate': self.success_count / max(1, self.total_attempts)
        }





    def play_audio(self, audio_type: str, text: str = None, audio_path: str = None):
        """增强版音频播放方法
        参数:
            audio_type: 音频类型 ('file' 或 'tts')
            text: 要转换为语音的文本 (仅当audio_type='tts'时必需)
            audio_path: 音频文件路径 (仅当audio_type='file'时必需)
        返回:
            播放控制对象 (包含player和file信息)
        """
        temp_file = None
        try:
            # 参数验证
            if audio_type not in ('file', 'tts'):
                raise ValueError("audio_type必须是'file'或'tts'")
                
            if audio_type == 'tts':
                if not text or not isinstance(text, str):
                    raise ValueError("TTS需要有效的文本内容")
                    
                # 创建临时语音文件
                tts = gTTS(text=text, lang='zh-cn')
                temp_file = os.path.join(tempfile.gettempdir(), f'meditation_{int(time.time())}.mp3')
                tts.save(temp_file)
                audio_path = temp_file
                
            elif audio_type == 'file':
                if not audio_path or not os.path.exists(audio_path):
                    raise ValueError("无效的音频文件路径")

            # 非阻塞播放实现
            pygame.mixer.init()
            pygame.mixer.music.load(audio_path)
            pygame.mixer.music.play()
            self._current_audio = {
                'player': pygame.mixer.music,
                'file': audio_path,
                'start_time': time.time()
            }
            
            return {
                'player': pygame.mixer.music,
                'file': audio_path if audio_type == 'file' else temp_file
            }
            
        except Exception as e:
            # 音频系统错误恢复
            pygame.mixer.quit()
            pygame.mixer.init()
            logging.warning(f"音频系统重置后重试: {e}")
            return self.play_audio(audio_type, text, audio_path)

        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)


    def _visualize_breath(self, pattern, current_phase):
        """实时可视化呼吸周期"""
        if not hasattr(self, 'breath_canvas'):
            # 初始化可视化画布
            self.breath_canvas = tk.Canvas(width=300, height=200)
            self.breath_canvas.pack()
            
        # 清除旧图形
        self.breath_canvas.delete('all')
        
        # 绘制呼吸波形
        phases = {
            BreathPhase.INHALE: ('↑ 吸气', 'green'),
            BreathPhase.HOLD: ('→ 屏息', 'blue'), 
            BreathPhase.EXHALE: ('↓ 呼气', 'red'),
            BreathPhase.REST: ('- 休息', 'gray')
        }
        
        text, color = phases.get(current_phase, ('', 'black'))
        self.breath_canvas.create_text(
            150, 100, 
            text=text,
            font=('Arial', 24),
            fill=color
        )


class ContentGenerator:
    def __init__(self):
        # 新增个性化推荐模型
        self.recommender = PersonalizedModel(
            feature_columns=['stress_level', 'sleep_quality'],
            model_path='models/content_recommender.pt'
        )
        # 商业化内容模板库
        self.premium_templates = {
            'stress_relief': {
                'base_price': 9.9,
                'variants': ['nature', 'urban', 'fantasy'],
                'dynamic_pricing': lambda user: 9.9 + user.get('premium_level', 0) * 5
            },
            'sleep_aid': {
                'base_price': 14.9,
                'variants': ['ocean', 'rain', 'white_noise'],
                'dynamic_pricing': lambda user: 14.9 + user.get('sleep_problems', 0) * 3
            },
            'corporate': {
                'price': 19.9,
                'features': ['executive_focus', 'stress_management'],
                'dynamic_pricing': lambda user: 19.9 + user.get('stress_level', 0)*2
            },
            'sleep_enhance': {
                'price': 24.9,
                'features': ['sleep_induction', 'deep_relaxation'],
                'dynamic_pricing': lambda user: 24.9 + user.get('sleep_score', 0)*3 
            }
    }
        # 新增企业级内容模板
        self.enterprise_templates = {
            'team_focus': {
                'base_price': 299,
                'features': ['multi_user', 'dashboard', 'reporting'],
                'dynamic_pricing': lambda org: 299 + org.get('user_count', 0) * 10
            },
            'executive_recovery': {
                'base_price': 499,
                'features': ['biofeedback', 'ai_coaching', 'crisis_mode'],
                'dynamic_pricing': lambda org: 499 + org.get('stress_index', 0) * 20
            }
        }


        
        # 商业化语音配置
        self.voice_profiles = {
            'standard': {'price': 0, 'speed': 1.0},
            'premium': {'price': 4.9, 'speed': 1.2, 'effects': ['reverb', 'eq']},
            'professional': {'price': 9.9, 'speed': 1.1},
            'celebrity': {'price': 19.9, 'speed': 1.0},
            'professional': {'price': 9.9, 'speed': 1.1},
            'celebrity': {'price': 19.9, 'speed': 1.0}
        }
        # 企业级语音配置
        self.enterprise_voices = {
            'professional_coach': {'price': 99, 'speed': 1.1},
            'ceo_voice': {'price': 199, 'speed': 1.0}
        }

    def recommend_content(self, user_data):
        """机器学习驱动的个性化内容推荐"""
        return self.recommender.predict(user_data)

    def generate_enterprise_content(self, org_profile, content_type):
        """生成企业级冥想内容"""
        with self.lock_manager.create_lock('content_gen'):
            # 添加参数验证
            if not isinstance(org_profile, dict):
                raise ValueError("企业配置必须为字典类型")
            if not content_type or not isinstance(content_type, str):
                raise ValueError("内容类型必须为非空字符串")
                
            if content_type not in self.enterprise_templates:
                raise ValueError(f"不支持的企业级内容类型: {content_type}")
                
            # 计算动态价格
            price = self.enterprise_templates[content_type]['dynamic_pricing'](org_profile)
            
            # 生成带企业水印的内容
            content = {
                'audio': self._generate_enterprise_audio(content_type, org_profile),
                'visual': self._generate_enterprise_visuals(org_profile),
                'narration': self._generate_enterprise_narration(org_profile),
                'metadata': {
                    'content_type': 'enterprise',
                    'price': price,
                    'license': 'enterprise',
                    'watermark': f"{org_profile['org_name']} {time.strftime('%Y%m%d')}",
                    'custom_features': self._get_custom_features(org_profile)
                }
            }
            return content
    def generate_commercial_content(self, user, purpose='stress_relief'):
        """生成商业化冥想内容"""
        if purpose not in self.premium_templates:
            raise ValueError("无效的商业化内容类型")
            
        # 计算动态价格
        price = self.premium_templates[purpose]['dynamic_pricing'](user)
        
        # 生成多模态内容
        content = {
            'audio': self._generate_audio(user, purpose),
            'visual': self._generate_visuals(user, purpose),
            'narration': self._generate_narration(user),
            'metadata': {
                'content_type': 'premium',
                'price': price,
                'license': 'single_use',
                'watermark': f"AISleepGen Pro {time.strftime('%Y%m%d')}"
            }
        }
        return content
    def generate_premium_content(self, user, content_type):
        """生成付费冥想内容"""
        if content_type not in self.premium_templates:
            raise ValueError("不支持的内容类型")
            
        # 计算动态价格
        price = self.premium_templates[content_type]['dynamic_pricing'](user)
        
        return {
            'audio': self._generate_audio(content_type),
            'visual': self._generate_visuals(content_type),
            'narration': self._generate_narration(user),
            'metadata': {
                'content_type': 'premium',
                'price': price,
                'license': 'single_use'
            }
        }

    def _generate_enterprise_visuals(self, org_profile):
        """生成企业品牌化视觉内容"""
        brand_colors = org_profile.get('brand_colors', ['#FFFFFF'])
        if not isinstance(brand_colors, list) or len(brand_colors) == 0:
            brand_colors = ['#FFFFFF']
            logging.warning("使用默认品牌颜色")
            
        return self.visual_engine.render(
            pattern='corporate',
            color_scheme=brand_colors,
            logo=org_profile.get('logo_path')
        )

    def _generate_enterprise_audio(self, content_type, org_profile):
        """生成企业定制音频"""
        try:
            if not hasattr(self, 'audio_engine'):
                raise RuntimeError("音频引擎未初始化")
                
            base_audio = self.audio_engine.generate(
                template=content_type,
                binaural_params={
                    'base_freq': 432,
                    'delta': self._calc_enterprise_delta(org_profile)
                }
            )
            return self.audio_processor.add_watermark(
                base_audio,
                text=org_profile.get('org_name', 'AISleepGen')
            )
        except Exception as e:
            logging.error(f"企业音频生成失败: {e}")
            return self._get_fallback_audio(content_type)

    def _get_custom_features(self, org_profile: dict) -> dict:
        """增强版企业定制功能获取
        参数:
            org_profile: 企业配置字典
        返回:
            定制功能配置字典
        异常:
            ValueError: 当企业配置无效时
        """
        try:
            # 基础验证
            if not isinstance(org_profile, dict):
                raise ValueError("企业配置必须为字典类型")
                
            # 获取定制功能
            features = org_profile.get('custom_features')
            
            # 验证功能完整性
            if features and not isinstance(features, dict):
                logging.warning(f"企业{org_profile.get('org_name', '未知')}定制功能格式错误")
                features = None
                
            # 回退到默认配置
            if not features:
                logging.info("使用默认企业功能模板")
                return {
                    **self.enterprise_templates['default']['features'],
                    'is_fallback': True  # 标记为回退配置
                }
                
            return features
            
        except Exception as e:
            logging.error(f"获取企业定制功能失败: {e}", exc_info=True)
            # 安全返回默认配置
            return {
                'basic_features': True,
                'status': 'error_fallback'
            }

    
class CommercialAPI:
    def __init__(self, payment_gateway=None):
        """初始化商业API
        参数:
            payment_gateway: 可选支付网关实例
        """
        self.payment = payment_gateway or PaymentIntegration()  # 提供默认支付网关
        self.content_gen = ContentGenerator()
        self.session_cache = {}  # 新增会话缓存
        self._lock = threading.Lock()  # 添加线程锁
        self._acquired = False  # 锁状态标志

    def __enter__(self):
        """支持上下文管理协议"""
        self._lock.acquire()
        self._acquired = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理协议"""
        if self._acquired:
            self._lock.release()
            self._acquired = False

    # ... 原有方法保持不变 ...

        
    def create_premium_session(self, user_id, content_type, retry=3):
        """创建付费冥想会话
        参数:
            user_id: 用户ID
            content_type: 内容类型
            retry: 失败重试次数
        返回:
            包含会话信息的字典
        """
        try:
            # 检查缓存
            cache_key = f"{user_id}_{content_type}"
            if cache_key in self.session_cache:
                return self.session_cache[cache_key]
                
            # 1. 增强版订阅验证
            entitlement = self.payment.check_entitlement(user_id)
            if not entitlement['valid']:
                raise PermissionError(entitlement.get('message', "需要订阅Pro版"))
                
            # 2. 生成内容
            user_profile = self._get_user_profile(user_id)
            content = self.content_gen.generate_commercial_content(
                user_profile, 
                content_type
            )
            
            # 3. 创建订单(带重试机制)
            for attempt in range(retry):
                try:
                    order = self.payment.create_order(
                        user_id=user_id,
                        product_id=f"meditation_{content_type}",
                        amount=content['metadata']['price']
                    )
                    break
                except Exception as e:
                    if attempt == retry - 1:
                        raise
                    time.sleep(1)
                    
            # 缓存结果
            result = {
                'content': content,
                'order_id': order['id'],
                'access_token': self._generate_access_token(user_id)
            }
            self.session_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logging.error(f"创建付费会话失败: {e}")
            raise

   
    def create_enterprise_session(self, org_id, content_type):
        """创建企业级会话"""
        # 1. 验证企业订阅
        if not self.payment.check_enterprise_subscription(org_id):
            raise PermissionError("需要企业订阅")
            
        # 2. 生成企业内容
        org_profile = self._get_org_profile(org_id)
        content = self.content_gen.generate_enterprise_content(org_profile, content_type)
        
        # 3. 创建企业订单
        order = self.payment.create_enterprise_order(
            org_id=org_id,
            product_id=f"enterprise_{content_type}",
            amount=content['metadata']['price']
        )
        
        return {
            'content': content,
            'order_id': order['id'],
            'access_tokens': [self._generate_access_token(u) for u in org_profile['users']]
        }


class AITestInterface:
    def __init__(self, guide):
        # ... 已有初始化代码 ...
        self.commercial_features = {
            'preview_allowed': 3,  # 允许预览次数
            'last_purchase': None
        }

    def show_commercial_options(self):
        """显示商业化选项界面"""
        options = [
            {"id": "stress_pro", "name": "专业减压", "price": "$9.9", "preview": True},
            {"id": "sleep_plus", "name": "深度助眠", "price": "$14.9", "preview": True},
            {"id": "focus_boost", "name": "专注增强", "price": "$12.9", "preview": False}
        ]
        
        print("\n=== 高级功能 ===")
        for i, opt in enumerate(options, 1):
            print(f"{i}. {opt['name']} ({opt['price']})")
        
        choice = input("选择套餐 (1-3): ")
        return options[int(choice)-1]['id']

    def start_commercial_session(self, package_id):
        """启动商业化会话"""
        if self.commercial_features['preview_allowed'] <= 0:
            print("预览次数已用完，请购买完整版")
            return self._process_payment(package_id)
        
        # 生成预览内容
        preview = self._generate_preview(package_id)
        self._play_preview(preview)
        
        # 更新预览计数
        self.commercial_features['preview_allowed'] -= 1

class AnalyticsSystem:
    def generate_enterprise_report(self, org_id, time_range):
        """生成企业级分析报告"""
        org_sessions = self._get_org_sessions(org_id, time_range)
        
        return {
            'wellness_metrics': self._calc_wellness_metrics(org_sessions),
            'productivity_impact': self._calc_productivity_impact(org_sessions),
            'roi_analysis': self._calc_enterprise_roi(org_id, time_range),
            'team_comparison': self._compare_teams(org_id)
        }

    def _calc_enterprise_roi(self, org_id, time_range):
        """计算企业投资回报率"""
        cost = self.payment.get_org_spending(org_id, time_range)
        benefits = self._estimate_benefits(org_id, time_range)
        return {
            'cost': cost,
            'benefits': benefits,
            'roi': (benefits - cost) / cost if cost else float('inf')
        }

class EnterpriseConsole:
    def __init__(self, api):
        self.api = api
        self.dashboards = {
            'team': TeamWellnessDashboard(),
            'exec': ExecutiveDashboard()
        }

    def show_org_options(self, org_id):
        """显示企业级选项"""
        org_profile = self.api.get_org_profile(org_id)
        print(f"\n=== {org_profile['name']} 企业控制台 ===")
        print("1. 团队专注模式 (提升协作效率)")
        print("2. 高管恢复模式 (快速减压)")
        print("3. 数据分析面板")
        
        choice = input("选择功能 (1-3): ")
        return ['team_focus', 'exec_recovery', 'analytics'][int(choice)-1]














    def add_custom_method(self, method_name: str, method_func: callable):
        """实时添加新的减压方式"""
        self.relaxation_methods[method_name] = method_func
        
    # 以下是新增的减压方法实现
 



 

    def _analyze_test(self, steps: List[dict]) -> dict:
        """分析测试结果"""
        if not steps:
            return {
                'completion_time': 0,
                'step_count': 0,
                'avg_step_duration': 0,
                'status': 'empty_steps'
            }
        
        try:
            last_step = steps[-1]
            first_step = steps[0]
            
            # 确保计算的时间差是合理的
            time_diff = max(0.1, last_step['timestamp'] - first_step['timestamp'])
            
            return {
                'completion_time': time_diff,
                'step_count': len(steps),
                'avg_step_duration': sum(s['duration'] for s in steps) / len(steps),
                'status': 'completed'    
            }
        
        except Exception as e:
            logging.error(f"分析测试结果时出错: {e}")
            return {
                'completion_time': 0,
                'step_count': 0,
                'avg_step_duration': 0,
                'status': 'error'
            }
        finally:
            # 清理资源 pass
            pass
        # 可选的 finally 块，用于清理操作 pass```python

    




    def adjust_guidance(self, biofeedback: BioFeedback) -> dict:
        """增强版生物反馈调节"""
        return self.model.adjust(
            hr=biofeedback.heart_rate,
            hrv=biofeedback.hrv,
            sc=biofeedback.skin_conductance,
            stress=biofeedback.stress_level
        )




    def dynamic_pattern_switch(self, feedback: BioFeedback) -> str:
        """基于生物反馈的动态呼吸模式切换
        参数:
            feedback: 实时生物反馈数据
        返回:
            最优呼吸模式名称
        """
        if feedback.hrv < 0.5:  # 心率变异性低时使用生理叹息法
            return 'physiological_sigh'
        elif feedback.stress_level > 0.7:  # 高压状态下使用4-7-8呼吸法
            return '4-7-8'
        elif feedback.meditation_level < 0.3:  # 专注度低时使用协调呼吸
            return 'coh'
        elif feedback.heart_rate > 90:  # 心率过高时使用方形呼吸
            return 'box'
        else:  # 默认使用心脏协调呼吸
            return 'coherent_heart'
    def _measure_audio_latency(self) -> float:
        """精确测量音频系统延迟(毫秒)
        实现原理:
            1. 播放短测试音
            2. 记录播放开始时间
            3. 检测实际播放时间
            4. 计算时间差
        """
        try:
            # 生成测试音频(1kHz正弦波, 100ms)
            test_sound = self._generate_test_sound(1000, 0.1)
            
            # 初始化音频系统
            pygame.mixer.quit()
            pygame.mixer.init(frequency=44100, size=-16, channels=1)
            
            # 创建临时声音对象
            sound = pygame.mixer.Sound(buffer=test_sound)
            channel = pygame.mixer.Channel(0)
            
            # 测量延迟
            start_time = time.perf_counter()
            channel.play(sound)
            while channel.get_busy():  # 等待播放完成
                pass
            end_time = time.perf_counter()
            
            # 计算实际延迟(考虑100ms的音频长度)
            measured_latency = (end_time - start_time - 0.1) * 1000  # 转换为毫秒
            
            # 返回平滑后的延迟值(避免瞬时波动)
            return max(10, min(500, measured_latency))  # 限制在10-500ms范围内
            
        except Exception as e:
            logging.warning(f"延迟测量失败: {str(e)}")
            return 150.0  # 默认安全值

    def _generate_test_sound(self, freq: int, duration: float) -> bytes:
        """生成测试用正弦波音频
        参数:
            freq: 频率(Hz)
            duration: 时长(秒)
        """
        sample_rate = 44100
        samples = int(sample_rate * duration)
        t = np.linspace(0, duration, samples, False)
        wave = np.sin(2 * np.pi * freq * t) * 32767 * 0.5
        return wave.astype(np.int16).tobytes()

    def _get_audio_hardware_info(self) -> dict:
        """增强版音频硬件检测
        返回:
            {
                'driver': str,         # 驱动名称
                'channels': int,       # 声道数
                'frequency': int,      # 采样率(Hz)
                'format': int,         # 音频格式
                'latency': float,      # 延迟(ms)
                'hifi_support': bool,  # 是否支持高保真
                'status': str          # 检测状态
            }
        """
        default_info = {
            'driver': 'unknown',
            'channels': 2,
            'frequency': 44100,
            'format': -1,
            'latency': 100.0,
            'hifi_support': False,
            'status': 'error'
        }
        
        try:
            # 初始化音频系统
            pygame.mixer.quit()
            pygame.mixer.init(frequency=48000, buffer=1024)
            
            # 获取核心参数
            init_info = pygame.mixer.get_init()
            if not init_info:
                raise RuntimeError("音频系统初始化失败")
                
            info = {
                'driver': pygame.mixer.get_driver(),
                'channels': pygame.mixer.get_num_channels(),
                'frequency': init_info[0],
                'format': init_info[2],
                'latency': self._measure_audio_latency(),
                'status': 'success'
            }
            
            # 评估HIFI支持能力
            info['hifi_support'] = all([
                info['frequency'] >= 48000,
                info['channels'] >= 2,
                info['latency'] < 200
            ])
            
            # 自动调整配置
            self.audio_config.update({
                'hifi_support': info['hifi_support'],
                'optimal_frequency': min(96000, info['frequency']),
                'use_stereo': info['channels'] >= 2
            })
            
            return info
            
        except Exception as e:
            logging.error(f"硬件检测失败: {str(e)}")
            # 返回安全默认值
            self.audio_config['hifi_support'] = False
            return default_info

    def _measure_audio_latency(self) -> float:
        """测量音频延迟(ms)"""
        # ... 实现精确的延迟测量逻辑 ...
        return 150.0  # 示例值




    def analyze_session(self, session_id: int) -> dict:
 
        if not isinstance(session_id, int) or session_id < 0:
            raise ValueError("会话ID必须是正整数")
            
        if session_id >= len(self.session_history):
            raise ValueError("无效的会话ID")
            
        
        """增强版会话分析
        参数:
            session_id: 要分析的会话ID
        返回:
            包含完整分析结果的字典，新增quality_assessment和trend_analysis字段
        """
        # ... 参数验证代码保持不变 ...
            
        session = self.session_history[session_id]
        
        # 新增会话质量评估
        quality = self._assess_session_quality(session)
        
        # 计算各项指标
        metrics = {
            'effectiveness': self._calculate_effectiveness(session),
            'hrv_improvement': self._calculate_hrv_improvement(session),
            'respiration_rate_change': self._calculate_respiration_change(session),
            'heart_rate_change': self._calculate_heart_rate_change(session),
            'pattern_effectiveness': self._calculate_pattern_effectiveness(session)
        }
        
        # 新增趋势分析
        trends = self._analyze_trends(session)
        
        # 计算综合评分
        score = self._calculate_composite_score(session, metrics)
        
        return {
            'session_id': session_id,
            'status': session.get('status', 'unknown'),
            'duration': session['duration'],
            'actual_duration': session.get('actual_duration', 0),
            'completion_rate': min(1.0, session.get('actual_duration', 0) / max(1, session['duration'])),
            'metrics': {k: round(v, 3) for k, v in metrics.items()},
            'score': round(score, 2),
            'pattern_changes': len(session.get('pattern_changes', [])),
            'feedback_comparison': {
                'stress_level': self._compare_feedback('stress_level', session),
                'hrv': self._compare_feedback('hrv', session),
                'heart_rate': self._compare_feedback('heart_rate', session)
            },
            'quality_assessment': quality,  # 新增质量评估
            'trend_analysis': trends,      # 新增趋势分析
            'timestamp': session.get('start_time', 0)
        }



    def _analyze_trends(self, session: dict) -> dict:
        """分析会话趋势"""
        if 'steps' not in session or len(session['steps']) < 3:
            return {}
            
        return {
            'stress_trend': self._calculate_trend(session, 'stress_level'),
            'hrv_trend': self._calculate_trend(session, 'hrv'),
            'heart_rate_trend': self._calculate_trend(session, 'heart_rate')
        }

    def _calculate_pattern_effectiveness(self, session: dict) -> float:
        """计算呼吸模式切换效果"""
        if not session.get('pattern_changes'):
            return 1.0
            
        improvements = []
        for change in session['pattern_changes']:
            # 计算每次模式切换后的改善效果
            pass
            
        return sum(improvements) / len(improvements) if improvements else 0.0


    def _compare_feedback(self, metric: str, session: dict) -> dict:
        """比较会话前后的生物反馈数据"""
        initial = session.get('initial_feedback', {}).get(metric, 0)
        final = session.get('final_feedback', {}).get(metric, 0)
        return {
            'initial': initial,
            'final': final,
            'change': final - initial,
            'improvement_pct': ((final - initial) / max(1, initial)) * 100 if initial != 0 else 0
        }

    def _calculate_composite_score(self, session: dict, metrics: dict) -> float:
        """计算综合评分"""
        weights = {
            'effectiveness': 0.3,
            'hrv_improvement': 0.25,
            'respiration_rate_change': 0.2,
            'heart_rate_change': 0.15,
            'completion_rate': 0.1
        }
        
        completion_rate = min(1.0, session.get('actual_duration', 0) / max(1, session['duration']))
        
        return (
            weights['effectiveness'] * metrics['effectiveness'] +
            weights['hrv_improvement'] * metrics['hrv_improvement'] +
            weights['respiration_rate_change'] * metrics['respiration_rate_change'] +
            weights['heart_rate_change'] * metrics['heart_rate_change'] +
            weights['completion_rate'] * completion_rate
        )

    def _calculate_effectiveness(self, session: dict) -> float:
        """计算会话效果评分"""
        # ... 可根据实际需求实现评分算法 ...
        return 0.85  # 示例返回值

    def _calculate_hrv_improvement(self, session: dict) -> float:
        """计算HRV改善效果"""
        initial_hrv = session.get('initial_feedback', {}).get('hrv', 0.0)  # 使用float默认值
        final_hrv = session.get('final_feedback', {}).get('hrv', 0.0)
        return final_hrv - initial_hrv  # 无需额外判断，因为get已提供默认值
    


    def show_premium_options(self):
        """显示付费选项"""
        options = [
            {"id": "corporate", "name": "企业专注", "price": "$19.9"},
            {"id": "sleep_enhance", "name": "深度睡眠", "price": "$24.9"}
        ]
        
        print("\n=== 专业功能 ===")
        for i, opt in enumerate(options, 1):
            print(f"{i}. {opt['name']} ({opt['price']})")
        
        choice = input("选择套餐 (1-2): ")
        return options[int(choice)-1]['id']




    @classmethod
    def create_default(cls):
        """创建默认配置的测试界面"""
        from .meditation import MeditationGuide
        guide = MeditationGuide()  # 只创建一次实例
        return cls(guide)


    

    def start_test_session(self, duration: int, pattern: str):
        """启动测试会话"""
        if not pattern:
            raise ValueError("呼吸模式不能为空")

        print(f"\n=== 开始AI冥想测试 ===")
        print(f"模式: {pattern} | 时长: {duration}秒")
        
        session = {
            'start_time': time.time(),
            'config': {
                'duration': duration,
                'pattern': pattern,
                'user_prefs': self.user_preferences.copy()
            },
            'results': None
        }
        
        try:
            steps = self.guide.start_session(duration, pattern)
            print(f"生成的引导步骤: {steps}")  # 添加调试输出


            # 播放背景音乐
            self._play_background_music()

            # 添加实际引导执行逻辑
            for step in steps:
                try:
                    instruction = step['action'].get('instruction', '请跟随呼吸节奏')
                    self._speak_instruction(instruction)
                    print(f"\n{instruction}")  # 输出引导指令

                    print(f"执行步骤: {step['instruction']}")

                    time.sleep(step['duration'])  # 实际等待
                except KeyError as e:
                    print(f"步骤执行错误: 缺少必要字段 {e}")
                    continue
                
            session['results'] = self._analyze_test(steps)
            print("✓ 测试成功完成")

        except Exception as e:
            session['error'] = str(e)
            print(f"× 测试失败: {e}")
        finally:
            # 停止背景音乐
            self._stop_background_music()
        
        self.test_sessions.append(session)
        return session
    def _play_background_music(self):
        """播放背景音乐"""
        try:
            pygame.mixer.init()
            pygame.mixer.music.load("assets/meditation_music.mp3")
            pygame.mixer.music.play(loops=-1)  # 循环播放
        except Exception as e:
            print(f"背景音乐播放失败: {e}")

    def _stop_background_music(self):
        """停止背景音乐"""
        try:
            pygame.mixer.music.stop()
        except Exception:
    def _speak_instruction(self, text: str):
        """语音播报引导指令"""
        try:
            # 使用TTS引擎播报
            tts_engine = gtts.init()
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as e:
            print(f"语音播报失败: {e}")
            # 语音播报失败时的处理逻辑






    def generate_report(self, session_id: int) -> str:
        """生成测试报告"""
        session = self.test_sessions[session_id]
        return f"""
        AI冥想测试报告
        --------------------------
        配置:
         - 时长: {session['config']['duration']}秒
         - 模式: {session['config']['pattern']}
         - 主题: {session['config']['user_prefs']['theme']}
        
        结果:
         - 完成时间: {session['results']['completion_time']:.1f}秒
         - 步骤数: {session['results']['step_count']}
         - 平均步骤时长: {session['results']['avg_step_duration']:.1f}秒
        --------------------------
        """

def generate_guidance():
    try:
        response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
        {"role": "system", "content": "你是一个冥想引导专家，生成一段30秒的冥想引导内容."},
        {"role": "user", "content": "生成一段冥想引导内容，帮助用户放松."}
        ]
        )
        return response.choices[0].message['content']
    except Exception as e:
        print(f"生成式AI调用失败: {e}")
        return None





# GUI 部分from tkinter import Tk, Text, Buttonclass MeditationGuide:


def start_meditation(self):
    #生成冥想引导内容 
    guidance = generate_guidance()
    if guidance:
        self.text.insert("1.0", guidance)
        # 播放背景音乐 
        play_audio("background") # 播放背景音乐
        # 播放背景音乐
        play_audio('file')


def _execute_breath_cycle(self, pattern, duration):
    """执行单个呼吸周期"""
    if isinstance(pattern, tuple):  # 简单模式 (4-7-8)
        inhale, hold, exhale = pattern
        # 执行吸气
        time.sleep(inhale)
        # 执行屏息
        time.sleep(hold)
        # 执行呼气
        time.sleep(exhale)
    elif isinstance(pattern, dict):  # 复杂模式
        for phase_duration, phase_type in pattern['phases']:
            self._play_phase_sound(phase_type)  # 播放阶段音效
            time.sleep(phase_duration)

def main():
    # 初始化引导实例
    guide = MeditationGuide()
    ai_interface = AITestInterface.create_default()

    # 测试冥想引导
    print("=== 开始冥想引导测试 ===")
    try:
        # 只调用一次start_session
        steps = guide.start_session(300, '4-7-8')
        print(f"生成步骤数: {len(steps)}")
        if steps:
            print("示例步骤:", steps[0])
            print("最后一个步骤:", steps[-1])
            
            # 使用AI测试界面
            print("\n=== AI冥想测试系统 ===")
            test_session = ai_interface.start_test_session(
                duration=300,
                pattern='4-7-8'
            )
            
            # 生成报告
            if test_session.get('results'):
                print(ai_interface.generate_report(0))
            
            # 添加自定义方法
            guide.add_custom_method(
                'acupressure', 
                lambda d: {'type':'acupressure','points':['LI4','PC6']}
            )
            
    except Exception as e:
        print(f"冥想引导失败: {e}")




class MassMeditationEngine:
    def __init__(self, redis_host='localhost'):
        # 分布式会话存储
        self.redis = redis_client if redis_client is not None else redis.Redis(host='localhost', port=6379)
        self.session_prefix = "mass_meditation:"
        

        # 新增分片监控配置
        self.shard_monitor = {
            'rebalance_interval': 30,  # 分片再平衡间隔(秒)
            'last_rebalance': 0,
            'max_shard_load': 5000     # 单个分片最大负载
        }
        # 实时统计
        self.metrics = {
            'active_sessions': 0,
            'peak_concurrency': 0
        }
        # 新增性能优化配置
        self.optimization_config = {
            'max_participants': 100000,  # 最大参与者数
            'batch_size': 1000,         # 每批处理数量
            'sync_interval': 1.0,       # 同步间隔(秒)
            'compression': {
                'audio': 'opus@48kbps',
                'data': 'zstd'
            }
        }
        
        # 新增性能监控
        self.performance_monitor = PerformanceMonitor(
            metrics=['cpu', 'memory', 'network'],
            alert_threshold=0.8  # 资源使用超过80%触发警报
        )

        # 新增异常检测配置
        self.anomaly_detector = AnomalyDetector(
            thresholds={
                'cpu': 0.9,       # CPU使用率阈值
                'memory': 0.85,   # 内存使用阈值
                'latency': 300,   # 延迟阈值(ms)
                'drop_rate': 0.1  # 连接丢失率阈值
            },
            cooldown=60  # 异常冷却时间(秒)
        )


    def _auto_rebalance(self):
        """自动分片再平衡"""
        now = time.time()
        if now - self.shard_monitor['last_rebalance'] < self.shard_monitor['rebalance_interval']:
            return
            
        # 获取分片负载
        shard_loads = {
            shard: int(count) for shard, count in 
            self.redis.hgetall(f"{self.session_prefix}shards").items()
        }
        
        # 找出过载分片
        overloaded = [
            shard for shard, count in shard_loads.items()
            if count > self.shard_monitor['max_shard_load']
        ]
        
        # 执行再平衡
        for shard in overloaded:
            self._migrate_users(
                shard,
                target_shard=str(max(int(s) for s in shard_loads.keys()) + 1),
                count=shard_loads[shard] // 2
            )
            
        self.shard_monitor['last_rebalance'] = now

    def _migrate_users(self, source_shard: str, target_shard: str, count: int):
        """迁移用户到新分片"""
        users = self.redis.zrange(
            f"{self.session_prefix}shard_{source_shard}",
            0, count-1
        )
        
        with self.redis.pipeline() as pipe:
            for user in users:
                pipe.zadd(
                    f"{self.session_prefix}shard_{target_shard}",
                    {user: time.time()}
                ).zrem(
                    f"{self.session_prefix}shard_{source_shard}",
                    user
                )
            pipe.execute()
            
        # 更新分片计数
        self.redis.hincrby(
            f"{self.session_prefix}shards",
            source_shard,
            -len(users)
        )
        self.redis.hincrby(
            f"{self.session_prefix}shards",
            target_shard,
            len(users)
        )



    def _balance_load(self):
        """动态负载均衡"""
        current_load = self.performance_monitor.get_current_load()
        
        # 动态调整批处理大小
        if current_load['cpu'] > 0.7:
            self.optimization_config['batch_size'] = max(
                500, 
                self.optimization_config['batch_size'] - 100
            )
        elif current_load['cpu'] < 0.3:
            self.optimization_config['batch_size'] = min(
                2000,
                self.optimization_config['batch_size'] + 100
            )
            
        # 动态调整同步频率
        self.optimization_config['sync_interval'] = max(
            0.5, 
            min(2.0, 1.0 / (current_load['network'] + 0.1))
        )

    def create_mass_session(self, duration: int, pattern: str):
        """创建大规模冥想会话"""
        session_id = str(uuid.uuid4())



        # 新增分片配置
        shard_config = {
            'total_shards': max(1, self.optimization_config['max_participants'] // 5000),
            'current_shard': 0
        }
        
        session_data = {
            'id': session_id,
            'start_time': time.time(),
            'duration': duration,
            'pattern': pattern,
            'shards': shard_config,
            'participants': {}  # 改为字典存储分片信息
        }
        
        # 使用pipeline批量操作
        with self.redis.pipeline() as pipe:
            pipe.set(
                f"{self.session_prefix}{session_id}", 
                json.dumps(session_data)
            ).hset(
                f"{self.session_prefix}shards", 
                mapping={str(i): 0 for i in range(shard_config['total_shards'])}
            ).execute()
            
        return session_id

    def join_session(self, session_id: str, user_id: str):
        """优化版加入会话"""
        # 获取分片信息
        shard_id = hash(user_id) % self.optimization_config['batch_size']
        self._auto_rebalance()
        # 使用Redis集群分片
        self.redis.hincrby(
            f"{self.session_prefix}shards", 
            str(shard_id),
            1
        )
        
        # 批量更新参与者信息
        self.redis.zadd(
            f"{self.session_prefix}{session_id}:shard_{shard_id}",
            {user_id: time.time()}
        )
        
        # 返回优化后的引导数据
        return self._get_optimized_guidance(session_id)

    def _get_synced_guidance(self, session_id: str):
        """获取同步后的引导内容"""
        session_data = json.loads(
            self.redis.get(f"{self.session_prefix}{session_id}")
        )
        
        # 计算时间偏移确保同步
        elapsed = time.time() - session_data['start_time']
        cycle_position = elapsed % session_data['duration']
        
        return {
            'current_phase': self._get_current_phase(
                session_data['pattern'],
                cycle_position
            ),
            'next_transition': session_data['duration'] - cycle_position,
            'participant_count': self.metrics['active_sessions']
        }
    def get_mass_session_stats(self, session_id: str):
        """增强版会话统计"""
        shard_info = self.redis.hgetall(f"{self.session_prefix}shards")
        total_participants = sum(int(v) for v in shard_info.values())
        
        # 新增详细性能指标
        perf_stats = self.performance_monitor.get_stats()
        system_load = {
            'cpu': f"{perf_stats['cpu']:.1%}",
            'memory': f"{perf_stats['memory']/1024:.1f}MB",
            'network': f"{perf_stats['network']/1024:.1f}KB/s",
            'latency': self._calculate_avg_latency(session_id)
        }
        
        return {
            'participants': total_participants,
            'shards': shard_info,
            'system': system_load,
            'optimization': self.optimization_config,
            'timestamp': time.time(),
            # 新增指标
            'health_score': self._calculate_health_score(system_load),
            'trends': {
                'participant_growth': self._get_participant_trend(session_id),
                'resource_usage': self._get_resource_trend()
            }
        }
    def _calculate_health_score(self, system_load: dict) -> float:
        """计算系统健康评分(0-100)"""
        cpu_score = 100 * (1 - float(system_load['cpu'].strip('%'))/100)
        mem_score = 100 - min(100, float(system_load['memory'].split('MB')[0])/10)
        net_score = 100 - min(100, float(system_load['network'].split('KB')[0])/5)
        latency_score = 100 - min(100, float(system_load['latency'])/10)
        
        return round(0.4*cpu_score + 0.3*mem_score + 0.2*net_score + 0.1*latency_score, 1)
    def _get_participant_trend(self, session_id: str) -> dict:
        """获取参与者增长趋势"""
        history = self.redis.lrange(f"{self.session_prefix}{session_id}:history", 0, 5)
        return {
            '5min_growth': int(history[-1]) - int(history[0]) if len(history) > 1 else 0,
            'current_rate': self._calculate_join_rate(session_id)
        }
        
    def _get_resource_trend(self) -> dict:
        """获取资源使用趋势"""
        trends = self.performance_monitor.get_trends()
        return {
            'cpu': trends['cpu'][-5:],  # 最近5个采样点
            'memory': trends['memory'][-5:],
            'network': trends['network'][-5:]
        }
    def _calculate_avg_latency(self, session_id: str) -> float:
        """计算平均网络延迟(ms)"""
        latencies = [
            float(l) for l in 
            self.redis.lrange(f"{self.session_prefix}{session_id}:latencies", 0, 10)
            if l
        ]
        return round(sum(latencies)/len(latencies), 2) if latencies else 0.0
    def _health_check(self):
        """实时系统健康检查"""
        metrics = {
            'cpu': self.performance_monitor.get_cpu_usage(),
            'memory': self.performance_monitor.get_memory_usage(),
            'latency': self._calculate_avg_latency(),
            'drop_rate': self._calculate_connection_drop_rate()
        }
        
        # 异常检测
        if self.anomaly_detector.check(metrics):
            self._trigger_recovery_protocol()
            
        # 定期记录健康状态
        self.redis.hset(
            f"{self.session_prefix}health", 
            mapping={k: str(v) for k,v in metrics.items()}
        )
    def _trigger_recovery_protocol(self):
        """执行自动恢复流程"""
        # 1. 降级服务
        self.optimization_config['batch_size'] = 500
        self.optimization_config['sync_interval'] = 2.0
        
        # 2. 转移会话负载
        self._redistribute_shards()
        
        # 3. 通知监控系统
        self._send_alert("System anomaly detected, recovery protocol activated")
        
        # 4. 记录恢复事件
        self.redis.rpush(
            f"{self.session_prefix}recovery_events",
            json.dumps({
                'timestamp': time.time(),
                'action': 'auto_recovery',
                'details': self.anomaly_detector.last_metrics
            })
        )
    def _redistribute_shards(self):
        """动态分片再平衡"""
        shard_info = self.redis.hgetall(f"{self.session_prefix}shards")
        overloaded = [k for k,v in shard_info.items() if int(v) > 2000]
        
        for shard in overloaded:
            # 迁移部分用户到新分片
            users = self.redis.zrange(
                f"{self.session_prefix}shard_{shard}", 
                0, 500
            )
            new_shard = str(max(int(k) for k in shard_info.keys()) + 1)
            
            with self.redis.pipeline() as pipe:
                for user in users:
                    pipe.zadd(
                        f"{self.session_prefix}shard_{new_shard}",
                        {user: time.time()}
                    ).zrem(
                        f"{self.session_prefix}shard_{shard}", 
                        user
                    )
                pipe.execute()
    def get_system_status(self):
        """获取增强版系统状态"""
        return {
            'health': self.redis.hgetall(f"{self.session_prefix}health"),
            'recovery_events': [
                json.loads(e) for e in 
                self.redis.lrange(f"{self.session_prefix}recovery_events", 0, 5)
            ],
            'active_incidents': self.anomaly_detector.active_alerts,
            'recommendations': self._generate_recommendations()
        }



if __name__ == '__main__':
    unittest.main()
    # 初始化引导实例
    guide = MeditationGuide()
    
    # 根据用户配置选择模式
    guide.use_advanced_mode = True  # 或从配置文件读取
    
    # 开始冥想会话
    steps = guide.start_session(300, '4-7-8')