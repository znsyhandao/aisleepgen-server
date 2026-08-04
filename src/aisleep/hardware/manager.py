import time
from typing import Dict, List,Optional
import asyncio
from bleak import BleakClient
from brainflow.board_shim import BoardShim, BoardIds
import logging
from datetime import datetime, timedelta
import numpy as np
from typing import AsyncGenerator
import random
import json
import os
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from aisleep.deepseek_model import RealtimeEngine, DeepSeekError
from aisleep.deepseek_model import DeepSeekMultiModal
from aisleep.deepseek_model import DeepSeekMultiModalError
from src.aisleep.analysis.signal_analyzer import SignalAnalyzer
from src.aisleep.analysis.stress_calculator import StressCalculator



try:
    print("SignalAnalyzer imported successfully.")
except ImportError as e:
    print(f"ImportError: {e}")

# Add this near the top of the file with other imports
class PerformanceMonitor:
    """Performance monitoring utility for tracking method execution times"""
    def __init__(self):
        self.metrics = {}
        
    def track(self, metric_name):
        """Decorator to track method execution time"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                self.metrics[metric_name] = elapsed
                return result
            return wrapper
        return decorator

# Create a global instance
monitor = PerformanceMonitor()

# ... rest of existing code ...

# 在文件顶部添加DeepSeek算法核心类
class DeepSeekProcessor:
    """DeepSeek多模态生物信号处理器"""
    def __init__(self):
        self.metrics = {}
        self.attention_model = self._init_attention_model()
        self.sleep_model = self._init_sleep_model()
        self.signal_processor = SignalAnalyzer()  # 新增信号分析器
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._init_dl_model()
        self.model_versions = {}  # 记录模型版本信息
        self._init_model_registry()  # 初始化模型注册表
        self.model_pool = {
            'full': self.model,  # 完整模型
            'lite': self._init_lite_model(),  # 轻量模型
            'traditional': TraditionalModel()  # 传统算法
        }
        self.route_rules = {
            'high_quality': {'min_quality': 0.8, 'max_load': 0.7, 'model': 'full'},
            'medium_quality': {'min_quality': 0.5, 'max_load': 0.9, 'model': 'lite'},
            'fallback': {'model': 'traditional'}
        }

    def _init_lite_model(self):
        """占位方法，用于初始化轻量模型"""
        print("Initializing lite model...")
        return None  # 返回一个占位值

    def track(self, metric_name):
        """Decorator to track method execution time"""
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                self.metrics[metric_name] = elapsed
                return result
            return wrapper
        return decorator
    # Create a global monitor instance
    monitor = PerformanceMonitor()
    async def smart_route(self, data: Dict) -> Dict:
        """智能路由主逻辑"""
        # 获取路由参数
        quality = self._calc_input_quality(data)
        load = self._get_system_load()
        
        # 匹配最优模型
        for rule in ['high_quality', 'medium_quality']:
            if (quality >= self.route_rules[rule]['min_quality'] and 
                load <= self.route_rules[rule]['max_load']):
                return await self._run_model(
                    self.route_rules[rule]['model'], 
                    data
                )
        return await self._run_model('traditional', data)


    async def _run_model(self, model_key: str, data: Dict) -> Dict:
        """执行指定模型并记录性能"""
        start_time = time.time()
        try:
            model = self.model_pool[model_key]
            if hasattr(model, 'predict'):
                results = model.predict(data)
            else:
                results = model(data)
            return {
                    **results,
                    '_metadata': {
                        'model_used': model_key,
                        'inference_time': time.time() - start_time
                    }
                }
        except Exception as e:
            logger.error(f"Model {model_key} failed: {str(e)}")
            return await self._handle_model_failure(model_key, data)
                

    def _init_model_registry(self):
        """初始化模型注册表"""
        self.model_registry = {
            'attention': {
                'current': 'v1.0',
                'fallback': 'v0.9'
            },
            'sleep': {
                'current': 'v2.1', 
                'fallback': 'v2.0'
            }
        }
    async def update_model(self, model_path: str, model_type: str = 'main'):
        """增强版模型热更新，支持版本回滚"""
        try:
            state_dict = torch.load(model_path)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            
            # 记录模型版本信息
            version = self._extract_version(model_path)
            self.model_versions[model_type] = {
                'version': version,
                'load_time': datetime.now(),
                'path': model_path
            }
            return True
        except Exception as e:
            logger.error(f"Model update failed: {e}")
            return False

    async def rollback_model(self, model_type: str):
        """回滚到上一个稳定版本"""
        if model_type in self.model_registry:
            fallback = self.model_registry[model_type]['fallback']
            return await self.update_model(f"models/{model_type}_{fallback}.pth")
            
    def _init_dl_model(self):
        """初始化深度学习模型"""
        model = BioSignalNN().to(self.device)
        try:
            # 尝试加载预训练权重
            model.load_state_dict(torch.load('models/biosignal_model.pth'))
        except:
            # 如果不存在则初始化新模型
            print("未找到预训练模型，使用随机初始化")
        return model.eval()





    def _init_attention_model(self):
        """初始化注意力检测模型"""
        # 这里可以加载预训练模型
        return {
            'weights': {
                'delta': 0.15,
                'theta': 0.25,
                'alpha': 0.35,
                'beta': 0.25
            }
        }
        
    def _init_sleep_model(self):
        """初始化睡眠分析模型"""
        return {
            'hr_threshold': 60,
            'breath_threshold': 14
        }



    def _preprocess_for_dl(self, data: Dict) -> tuple:
        """为深度学习模型准备数据"""
        eeg = torch.FloatTensor(data.get('bci', {}).get('eeg', [])).unsqueeze(0)
        hr = data.get('wearables', {}).get('heart_rate', 72)
        hrv = data.get('wearables', {}).get('hrv', 0)
        rr = data.get('wearables', {}).get('rr_intervals', [0])
        
        hr_features = torch.FloatTensor([
            hr/100.0, 
            min(hrv/100.0, 1.0),
            len(rr)/10.0
        ]).unsqueeze(0)

        return eeg.to(self.device), hr_features.to(self.device)
    
    def _dl_predict(self, data: Dict) -> Dict:
        """使用深度学习模型进行预测"""
        with torch.no_grad():
            eeg, hr = self._preprocess_for_dl(data)
            outputs = self.model(eeg, hr).sigmoid().cpu().numpy()[0]
            
        return {
            'dl_attention': float(outputs[0]),
            'dl_stress': float(outputs[1]),
            'dl_sleep_quality': float(outputs[2]*100)
        }


    def _calc_attention(self, data: Dict) -> float:
        """基于EEG频谱计算注意力水平"""
        eeg_spectrum = data.get('bci', {}).get('eeg_spectrum', {})
        total = sum(eeg_spectrum.values())
        if total == 0:
            return 0.5
            
        weighted_sum = sum(
            eeg_spectrum.get(band, 0) * self.attention_model['weights'][band]
            for band in ['delta', 'theta', 'alpha', 'beta']
        )
        return min(max(weighted_sum / total, 0), 1)

    def _predict_sleep(self, data: Dict) -> float:
        """预测睡眠质量"""
        hr = data.get('wearables', {}).get('heart_rate', 72)
        breath = data.get('wearables', {}).get('breath_rate', 16)
        
        hr_score = 1 - min(abs(hr - self.sleep_model['hr_threshold']) / 20, 1)
        breath_score = 1 - min(abs(breath - self.sleep_model['breath_threshold']) / 10, 1)
        
        return (hr_score * 0.6 + breath_score * 0.4) * 100

    def _analyze_mental_state(self, data: Dict) -> str:
        """分析心理状态"""
        attention = self._calc_attention(data)
        if attention > 0.7:
            return "高度专注"
        elif attention > 0.4:
            return "正常状态"
        else:
            return "疲劳状态"
    
    def _advanced_eeg_analysis(self, eeg_data: List[float]) -> Dict:
        """高级EEG信号分析"""
        if not eeg_data:
            return {}
            
        np_data = np.array(eeg_data)
        return {
            'entropy': self._calc_sample_entropy(np_data),
            'hurst': self._calc_hurst_exponent(np_data),
            'correlation_dim': self._calc_correlation_dimension(np_data)
        }
    
    def _calc_sample_entropy(self, data: np.ndarray) -> float:
        """计算样本熵(Sample Entropy)"""
        m = 2  # 嵌入维度
        r = 0.2 * np.std(data)  # 容差阈值
        N = len(data)
        
        # 计算匹配模板的数量
        def _phi(m):
            x = np.array([data[i:i+m] for i in range(N - m + 1)])
            C = np.sum([np.sum(np.abs(x[i] - x).max(axis=1) <= r) - 1 for i in range(len(x))])
            return C / ((N - m + 1) * (N - m))
            
        return -np.log(_phi(m+1) / _phi(m)) if _phi(m) != 0 else 0

    def _calc_hurst_exponent(self, data: np.ndarray) -> float:
        """计算Hurst指数"""
        lags = range(2, 20)
        tau = [np.std(np.subtract(data[lag:], data[:-lag])) for lag in lags]
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0]

    def _calc_correlation_dimension(self, data: np.ndarray) -> float:
        """计算关联维数"""
        m = 5  # 嵌入维度
        N = len(data)
        r = np.linspace(0.1 * np.std(data), 0.5 * np.std(data), 10)
        C = []
        
        for radius in r:
            x = np.array([data[i:i+m] for i in range(N - m + 1)])
            count = 0
            for i in range(len(x)):
                for j in range(i+1, len(x)):
                    if np.linalg.norm(x[i] - x[j]) < radius:
                        count += 2
            C.append(count / (len(x) * (len(x) - 1)))
            
        return np.polyfit(np.log(r), np.log(C), 1)[0]

    def process_bio_signals(self, data: Dict) -> Dict:
        """优化版生物信号处理方法 - 支持动态模块加载和容错处理"""
        # 1. 增强数据预处理 + 质量检查
        cleaned_data = self._enhanced_preprocessing(data)
        if not self._validate_input_data(cleaned_data):
            return self._get_fallback_response(data)

        # 2. 动态模块执行器 (可配置模块列表)
        modules_to_run = [
            ('advanced_eeg', self._advanced_eeg_analysis, cleaned_data.get('eeg', [])),
            ('dl_predict', self._dl_predict, cleaned_data),
            ('traditional', self._get_traditional_results, cleaned_data),
            ('hrv', self._analyze_hrv, cleaned_data),
            ('breathing', self._analyze_breathing, cleaned_data)
        ]

        # 3. 并行执行 + 超时控制
        results = {}
        with ThreadPoolExecutor(max_workers=min(4, len(modules_to_run))) as executor:
            futures = {
                name: executor.submit(self._safe_execute_module, func, arg)
                for name, func, arg in modules_to_run
            }
            
            for name, future in futures.items():
                try:
                    results[name] = future.result(timeout=2.0)  # 2秒超时控制
                except TimeoutError:
                    logger.warning(f"Module {name} timeout")
                    results[name] = self._get_module_fallback(name)

        # 4. 智能结果融合 (带质量权重)
        fused_results = self._smart_fusion(
            dl_results=results.get('dl_predict', {}),
            traditional_results=results.get('traditional', {}),
            quality_scores=self._calc_quality_scores(data)
        )

        # 5. 生成带诊断信息的最终结果
        return {
            **fused_results,
            'diagnostics': {
                'module_status': {name: 'success' if res else 'failed' 
                                for name, res in results.items()},
                'timestamps': {
                    'process_start': time.time(),
                    'data_receive': data.get('timestamp', 0)
                },
                'resource_usage': self._get_resource_usage()
            }
        }

    def _safe_execute_module(self, func, arg):
        """带异常处理的模块执行包装器"""
        try:
            return func(arg)
        except Exception as e:
            logger.error(f"Module {func.__name__} error: {str(e)}")
            return None

    def _smart_fusion(self, dl_results: Dict, traditional_results: Dict, quality_scores: Dict) -> Dict:
        """基于数据质量的智能结果融合"""
        # 计算动态权重
        weights = {
            'dl': quality_scores.get('eeg', 0.5) * 0.7,  # 深度学习模型权重
            'traditional': (quality_scores.get('hr', 0.5) * 0.5 + 
                        quality_scores.get('breath', 0.5) * 0.5)
        }
        total_weight = sum(weights.values())
        if total_weight == 0:
            weights = {'dl': 0.5, 'traditional': 0.5}
        else:
            weights = {k: v/total_weight for k, v in weights.items()}

        # 结果融合
        attention = (dl_results.get('dl_attention', 0.5) * weights['dl'] + 
                    traditional_results.get('attention', 0.5) * weights['traditional'])
        
        stress = (dl_results.get('dl_stress', 0.5) * weights['dl'] + 
                traditional_results.get('stress_index', 0.5) * weights['traditional'])
        
        sleep = (dl_results.get('dl_sleep_quality', 50) * weights['dl'] + 
                traditional_results.get('sleep_quality', 50) * weights['traditional'])

        return {
            'final_attention': np.clip(attention, 0, 1),
            'final_stress': np.clip(stress, 0, 1),
            'final_sleep': np.clip(sleep, 0, 100),
            'fusion_weights': weights
        }



    def _get_traditional_results(self, data: Dict) -> Dict:
        """封装传统算法结果获取"""
        return {
            'attention': self._calc_attention(data),
            'sleep_quality': self._predict_sleep(data),
            'mental_state': self._analyze_mental_state(data)
        }

    def _calc_confidence_scores(self, data: Dict) -> Dict:
        """计算各指标的置信度评分"""
        return {
            'eeg': self._calc_data_quality(data.get('bci', {}).get('eeg', [])),
            'hr': self._calc_data_quality(data.get('wearables', {}).get('heart_rate', [])),
            'breath': self._calc_data_quality(data.get('wearables', {}).get('breath_wave', []))
        }



    def _calc_data_quality(self, signal_data, signal_type='eeg') -> float:
        """增强版多模态信号质量评估系统"""
        if not signal_data or len(signal_data) < 10:  # 最小数据长度要求
            return 0.0
            
        # 1. 动态阈值计算（基于信号类型）
        thresholds = {
            'eeg': self._calc_eeg_thresholds(signal_data),
            'ecg': self._calc_ecg_thresholds(signal_data),
            'rsp': self._calc_resp_thresholds(signal_data)
        }.get(signal_type, {})
        
        # 2. 并行计算质量指标
        with ThreadPoolExecutor() as executor:
            futures = {
                'snr': executor.submit(self._calc_snr, signal_data, thresholds),
                'continuity': executor.submit(self._calc_continuity, signal_data),
                'artifact': executor.submit(self._check_artifact, signal_data, thresholds)
            }
            metrics = {k: f.result() for k, f in futures.items()}
        
        # 3. 动态权重调整（基于信号类型）
        weights = self._get_quality_weights(signal_type)
        quality = sum(metrics[k] * weights[k] for k in metrics)
        
        return np.clip(quality, 0, 1)

    def _calc_eeg_thresholds(self, signal):
        """EEG信号动态阈值计算"""
        median = np.median(np.abs(signal))
        return {
            'noise': median * 3,
            'amplitude': median * 10,
            'gradient': np.percentile(np.diff(signal), 95)
        }

    def _calc_snr(self, signal, thresholds) -> float:
        """信噪比计算（并行优化版）"""
        signal_power = np.mean(signal**2)
        noise_mask = np.abs(signal) < thresholds.get('noise', np.inf)
        noise_power = np.mean(signal[noise_mask]**2) if np.any(noise_mask) else 0
        return 10 * np.log10(signal_power/(noise_power + 1e-6))

    def _check_artifact(self, signal, thresholds) -> float:
        """伪迹检测（并行优化版）"""
        abnormal = (
            (np.abs(signal) > thresholds.get('amplitude', 100)) | 
            (np.abs(np.diff(signal, prepend=0)) > thresholds.get('gradient', 50))
        )
        return 1 - (np.sum(abnormal) / len(signal))



    def _analyze_hrv(self, data: Dict) -> Dict:
        """心率变异性分析"""
        rr_intervals = data.get('wearables', {}).get('rr_intervals', [])
        if len(rr_intervals) < 5:
            return {}
        
        import neurokit2 as nk
        hrv_results = nk.hrv(rr_intervals, sampling_rate=1000)
            
        return {
            'rmssd': np.sqrt(np.mean(np.square(np.diff(rr_intervals)))),
            'sdnn': np.std(rr_intervals),
            'lf_hf_ratio': self._calc_lf_hf_ratio(rr_intervals),
            'neurokit_features': hrv_results.to_dict()
        }



    def _calc_lf_hf_ratio(self, rr_intervals: List[float]) -> float:
        """计算LF/HF比率"""
        # 使用Lomb-Scargle周期图进行频谱估计
        t = np.cumsum(rr_intervals)
        f = np.linspace(0.04, 0.4, 100)  # LF: 0.04-0.15Hz, HF: 0.15-0.4Hz
        
        # 计算功率谱密度
        pxx = signal.lombscargle(t, rr_intervals - np.mean(rr_intervals), f)
        
        # 计算LF和HF功率
        lf_power = np.trapz(pxx[(f >= 0.04) & (f <= 0.15)], f[(f >= 0.04) & (f <= 0.15)])
        hf_power = np.trapz(pxx[(f > 0.15) & (f <= 0.4)], f[(f > 0.15) & (f <= 0.4)])
        
        return lf_power / hf_power if hf_power != 0 else 0



    def _analyze_breathing(self, data: Dict) -> Dict:
        """使用neurokit2的呼吸分析"""
        breath_data = data.get('wearables', {}).get('breath_wave', [])
        if len(breath_data) < 10:
            return {}
        
        import neurokit2 as nk
        # 使用专门的呼吸信号处理方法
        signals, info = nk.rsp_process(breath_data, sampling_rate=50)  # 呼吸信号通常采样率较低
        
        return {
            'breath_rate': float(nk.rsp_rate(signals)),
            'regularity': float(nk.entropy_shannon(signals["RSP_Peaks"])),
            'amplitude': float(np.mean(signals["RSP_Amplitude"])),
            'neurokit_features': info
        }

    def _generate_insights(self, data: Dict) -> Dict:
        """生成可操作的见解"""
        insights = {}
        stress_index = self._calculate_stress_index(data)


        if stress_index > 0.7:
            insights['stress_level'] = '高'
            insights['suggestions'] = [
                "减少屏幕使用，增强运动",
                "调整呼吸节奏，放松身心"
            ]
    def _calc_data_quality(self, signal_data, signal_type='eeg') -> float:
        """增强版信号质量评估，支持多种信号类型"""
        if not signal_data or len(signal_data) < 3:
            return 0.0
            
        try:
            import neurokit2 as nk
            return float(nk.signal_quality(signal_data, sampling_rate=self._get_sampling_rate(signal_type)))
        except ImportError:
            return self._custom_signal_quality(signal_data, signal_type)

    def _get_sampling_rate(self, signal_type):
        """获取不同信号的推荐采样率"""
        rates = {
            'eeg': 1000,
            'ecg': 500,
            'rsp': 50,
            'hr': 100
        }
        return rates.get(signal_type, 1000)


    def _custom_signal_quality(self, signal, sampling_rate=1000) -> float:
        """自定义信号质量评估算法"""
        # 1. 振幅范围检测
        amplitude_range = np.ptp(signal)  # Peak-to-peak幅度
        
        # 2. 信号斜率变化率
        diff_signal = np.diff(signal)
        slope_variability = np.std(diff_signal)
        
        # 3. 高频噪声检测 (0.5-100Hz)
        power_spectrum = np.abs(np.fft.fft(signal))**2
        freq = np.fft.fftfreq(len(signal), 1/sampling_rate)
        noise_power = np.sum(power_spectrum[(freq>0.5) & (freq<100)])
        
        # 4. 基线漂移检测 (0-0.5Hz)
        drift_power = np.sum(power_spectrum[(freq>0) & (freq<0.5)])
        
        # 特征归一化和加权计算
        features = {
            'amplitude': min(max(amplitude_range / 500, 0), 1),  # 假设500μV为典型范围
            'noise': min(max(noise_power / 1e6, 0), 1),  # 噪声功率归一化
            'drift': min(max(drift_power / 1e5, 0), 1),  # 漂移功率归一化
            'slope': min(max(slope_variability / 50, 0), 1)  # 斜率变化率归一化
        }
        
        weights = {
            'amplitude': 0.3,
            'noise': 0.4,
            'drift': 0.2,
            'slope': 0.1
        }
        
        quality = 1 - sum(f * weights[w] for w, f in features.items())
        return float(np.clip(quality, 0, 1))


    async def update_model(self, model_path: str):
        """热更新深度学习模型"""
        try:
            state_dict = torch.load(model_path)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            return True
        except Exception as e:
            logger.error(f"Model update failed: {str(e)}")
            return False



    def signal_quality(signal, sampling_rate=1000):
        # 1. 振幅范围检测
        amplitude_range = np.ptp(signal)  # Peak-to-peak幅度
        
        # 2. 信号斜率变化率
        diff_signal = np.diff(signal)
        slope_variability = np.std(diff_signal)
        
        # 3. 高频噪声检测 (0.5-100Hz)
        power_spectrum = np.abs(np.fft.fft(signal))**2
        freq = np.fft.fftfreq(len(signal), 1/sampling_rate)
        noise_power = np.sum(power_spectrum[(freq>0.5) & (freq<100)])
        
        # 4. 基线漂移检测 (0-0.5Hz)
        drift_power = np.sum(power_spectrum[(freq>0) & (freq<0.5)])
        
        # ... 其他特征计算 ...


# 修改HardwareManager类
class HardwareManager:
    def __init__(self):
        # ... 保留原有初始化代码 ...

        self.connections = {}
        self.health_monitor = {
            'last_check': time.time(),
            'status': {}
        }

        self.mock_data = {
            "bci": {"eeg": [0.1, 0.2, 0.15], "attention": 0.75},
            "smartwatch": {"heart_rate": 72, "blood_oxygen": 98}
        }
        self.deepseek = DeepSeekProcessor()  # 添加DeepSeek处理器
        self.monitor = PerformanceMonitor()  # 实例级监控
        self.deepseek = DeepSeekProcessor()



    def _get_hrv(self) -> float:
        """模拟获取 HRV 数据"""
        return 50.0  # 返回一个默认值

    def _calculate_stress_index(self, data: Dict) -> float:
        """计算压力指数"""
        return StressCalculator.calculate_stress_index(data)
    
    def get_hrv(self):
        """获取 HRV 数据"""
        return self._get_hrv()  # 调用现有的 `_get_hrv` 方法
    
    def _get_eeg_spectrum(self):
        """模拟获取 EEG 频谱数据"""
        return [0.1, 0.2, 0.3]

    def _get_gsr(self):
        """模拟获取皮肤电反应数据"""
        return 0.5
    def get_gsr(self) -> float:
        """获取皮肤电反应数据"""
        return self._get_gsr()  # 调用内部方法

    async def stream_state(self):
        """模拟实时状态流"""
        for _ in range(2):  # 假设生成两个状态
            yield {
                "hrv": self._get_hrv(),
                "eeg": self._get_eeg_spectrum(),
                "galvanic_skin": self._get_gsr()
            }
            await asyncio.sleep(1)  # 模拟延迟

    @monitor.track('stream_processing')
    async def _process_stream(self):
        """监控增强版流处理"""
        while True:
            data = await self.processing_queue.get()
            processed = await self.deepseek.smart_route(data)
            self._broadcast_update(processed)



    async def monitor_devices(self):
        """定时检查设备健康状态"""
        while True:
            await asyncio.sleep(60)  # 每分钟检查一次
            self.health_monitor['status'] = {
                'bci': self._check_bci_health(),
                'wearable': self._check_wearable_health()
            }
            self.health_monitor['last_check'] = time.time()
            self.monitor = PerformanceMonitor()
            self.deepseek = DeepSeekProcessor()
    
    @monitor.track('stream_processing')
    async def _process_stream(self):
        """监控增强版流处理"""
        while True:
            data = await self.processing_queue.get()
            processed = await self.deepseek.smart_route(data)
            self._broadcast_update(processed)

    @monitor.track('stream_processing')
    def _check_bci_health(self) -> dict:
        """检查BCI设备状态"""
        if not self.bci_client:
            return {'status': 'disconnected'}
            
        try:
            impedance = self.bci_client.get_impedance()
            return {
                'status': 'connected',
                'impedance': impedance,
                'quality': min(100, max(0, 100 - impedance.mean()/10))
            }
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    async def _process_stream(self):
        """增强版流处理，支持优先级队列"""
        while True:
            try:
                data, priority = await self.processing_queue.get()
                
                # 根据优先级调整处理策略
                if priority == 'high':
                    processed = await self._process_immediately(data)
                else:
                    processed = self.deepseek.process_bio_signals(data)
                
                self._broadcast_update(processed)
                self.processing_queue.task_done()
                
            except Exception as e:
                logger.error(f"Stream processing error: {e}")
                await asyncio.sleep(1)  # 错误恢复间隔

    async def _process_immediately(self, data):
        """高优先级数据的快速处理路径"""
        # 简化处理流程，只运行关键分析
        return {
            'attention': self.deepseek._calc_attention(data),
            'stress': self.deepseek._calculate_stress_index(data),
            'timestamp': time.time()
        }



    # 修改 get_vital_signs 方法为异步方法
    async def get_vital_signs(self) -> Dict:
        """获取关键生命体征"""
        return {
            "hrv": self._get_hrv(),
            "eeg": self._get_eeg_spectrum(),
            "galvanic_skin": self._get_gsr()
        }


    def get_enhanced_data(self) -> Dict:
        """获取增强型硬件数据(集成DeepSeek分析)"""
        raw_data = self.get_latest_data()
        deepseek_results = self.deepseek.process_bio_signals(raw_data)
        
        return {
            **raw_data,
            "deepseek": deepseek_results,
            "stress_index": self._calculate_stress_index(raw_data),
            "sleep_score": self._predict_sleep_score(raw_data)
        }
    


    async def start_real_time_processing(self):
        """启动实时数据处理管道"""
        self.processing_queue = asyncio.Queue()
        self.processing_task = asyncio.create_task(self._process_stream())

    async def _process_stream(self):
        """实时流处理核心逻辑"""
        while True:
            data = await self.processing_queue.get()
            processed = self.deepseek.process_bio_signals(data)
            # 可以添加实时推送逻辑或存储
            self._broadcast_update(processed)

    def push_to_stream(self, data):
        """向处理管道推送数据"""
        self.processing_queue.put_nowait(data)




    def _synchronize_devices(self, data: Dict) -> Dict:
        """多设备数据时间对齐和融合"""
        # 获取所有设备时间戳
        timestamps = {
            'bci': data.get('bci', {}).get('timestamp', 0),
            'wearables': data.get('wearables', {}).get('timestamp', 0)
        }
        
        # 计算时间差并补偿
        time_diff = timestamps['bci'] - timestamps['wearables']
        if abs(time_diff) > 0.1:  # 100ms阈值
            logger.warning(f"Device time mismatch: {time_diff}s")
            
        return {
            **data,
            'synced': True,
            'sync_offset': time_diff
        }


        
    async def connect_device(self, device_type: str, params: Dict):
        if device_type not in self.SUPPORTED_DEVICES:
            raise ValueError("Unsupported device type")
            
        self.connections[device_type] = True
        return {"status": "connected", "device": device_type}
    
    def _get_bci_data(self) -> Dict:
        """Get BCI data with error handling"""
        if not self.bci_client:
            return {}
            
        try:
            data = self.bci_client.get_current_board_data(10)
            return {
                'eeg': data.tolist(),
                'attention': float(data.mean()),
                'timestamp': time.time()
            }
        except Exception as e:
            logger.error(f"BCI data error: {str(e)}")
            return {}

    async def _get_wearable_data(self) -> Dict:
        """Get actual wearable data using BLE"""
        if not self.wearable_client:
            return {}
        try:
            hr = await self.wearable_client.read_gatt_char(self.HEART_RATE_UUID)
            spo2 = await self.wearable_client.read_gatt_char(self.BLOOD_OXYGEN_UUID)
            return {
                'heart_rate': int.from_bytes(hr, byteorder='little'),
                'blood_oxygen': int.from_bytes(spo2, byteorder='little'),  # Fixed comma here
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"Wearable data error: {str(e)}")
            return {}
    
    def _calc_data_quality(self, signal_data, signal_type='eeg') -> float:
        """增强版信号质量评估，支持实时自适应阈值"""
        
        if not signal_data or len(signal_data) < 10:  # 最小数据长度要求
            return 0.0
            
        # 实时计算动态阈值
        dynamic_thresholds = {
            'eeg': np.median(np.abs(signal_data)) * 3,
            'ecg': np.std(signal_data) * 2,
            'rsp': np.ptp(signal_data) * 0.5
        }
        
        # 基于信号特征的复合质量评分
        quality = 0.7 * self._calc_snr(signal_data) + \
                0.2 * self._calc_continuity(signal_data) + \
                0.1 * self._check_artifact(signal_data, dynamic_thresholds.get(signal_type, 0))
        
        return np.clip(quality, 0, 1)


    async def get_latest_data(self) -> Dict:
        """Get all device data asynchronously"""
        return {
            "bci": self._get_bci_data(),
            "wearables": await self._get_wearable_data()
        }
    def get_enhanced_data(self) -> Dict:
        """获取增强型硬件数据"""
        raw_data = self.get_latest_data()
        return {
            **raw_data,
            "stress_index": self._calculate_stress_index(raw_data),
            "sleep_score": self._predict_sleep_score(raw_data)
        }
    

    

    def _predict_sleep_score(self, data: Dict) -> float:
        """预测睡眠质量评分(0-100分)"""
        # 获取睡眠相关特征
        hr_variance = data.get('wearables', {}).get('hr_variance', 0) 
        breath_rate = data.get('wearables', {}).get('breath_rate', 16)
        body_movement = data.get('wearables', {}).get('movement', 0)
        eeg_spectrum = data.get('bci', {}).get('eeg_spectrum', {})
        
        # 计算各频段能量占比
        delta = eeg_spectrum.get('delta', 0)
        theta = eeg_spectrum.get('theta', 0)
        alpha = eeg_spectrum.get('alpha', 0)
        beta = eeg_spectrum.get('beta', 0)
        total = delta + theta + alpha + beta
        
        # 睡眠深度指标
        sleep_depth = (delta + theta) / total if total > 0 else 0
        
        # 综合评分计算
        score = 100 - (
            0.4 * min(body_movement * 10, 40) +  # 体动影响
            0.3 * abs(breath_rate - 14) * 5 +    # 呼吸频率偏离
            0.2 * hr_variance * 2 -              # 心率变异性
            0.1 * sleep_depth * 100              # 睡眠深度
        )
        
        return max(0, min(100, round(score)))



    async def get_vital_signs(self) -> Dict:
        """获取关键生命体征"""
        return {
            "hrv": self._get_hrv(),
            "eeg": self._get_eeg_spectrum(),
            "galvanic_skin": self._get_gsr()
        }
    def get_realtime_data(self) -> Dict:
        """50ms间隔的实时数据"""
        return {
            "timestamps": [time.time()],
            "values": self._read_sensors()
        }


    def _device_specific_processing(self, data):
        """设备特有的信号处理方法"""
        # ... 设备专用逻辑 ...


# 添加深度学习模型定义
class BioSignalNN(nn.Module):
    """多模态生物信号深度学习模型"""
    def __init__(self, eeg_channels=8, hr_features=3):
        super().__init__()
        # 类似DeepSeek的时序特征编码器
        self.eeg_encoder = nn.Sequential(
            nn.Conv1d(eeg_channels, 32, kernel_size=3),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=3),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Flatten()
        )
        # 类似DeepSeek的标量特征处理
        # 但针对生理信号调整了：
        # - 卷积核尺寸（适应EEG采样率）
        # - 特征维度（匹配生物信号特性）
        self.hr_encoder = nn.Sequential(
            nn.Linear(hr_features, 16),
            nn.ReLU(),
            nn.Linear(16, 32)
        )
        
        self.classifier = nn.Sequential(
            nn.Linear(64+32, 128),
            nn.ReLU(),
            nn.Linear(128, 3)  # 输出: 注意力, 压力, 睡眠质量
        )
        
    def forward(self, eeg, hr_features):
        eeg_feat = self.eeg_encoder(eeg)
        hr_feat = self.hr_encoder(hr_features)
        combined = torch.cat([eeg_feat, hr_feat], dim=1)
        return self.classifier(combined)

class TraditionalModel:
        def __init__(self):
            print("TraditionalModel initialized")

class StressCalculator:
        @staticmethod
        def calculate_stress_index(data: Dict) -> float:
            """基于多设备数据计算压力指数(0-1范围)"""
            # 获取基础生理数据
            heart_rate = data.get('wearables', {}).get('heart_rate', 72)
            hrv = data.get('wearables', {}).get('hrv', 0)
            eeg_attention = data.get('bci', {}).get('attention', 0.5)
            gsr = data.get('wearables', {}).get('galvanic_skin', 0)
    
            # 标准化各项指标
            hr_norm = min(max((heart_rate - 60) / 40, 0), 1)  # 假设60-100为正常范围
            hrv_norm = 1 - min(max(hrv / 200, 0), 1)  # HRV越高压力越小
            attention_norm = 1 - eeg_attention  # 注意力越低压力越大
            gsr_norm = min(max(gsr / 20, 0), 1)  # 皮电反应
    
            # 加权计算压力指数
            weights = {
                'hr': 0.3,
                'hrv': 0.25,
                'attention': 0.25,
                'gsr': 0.2
            }
            stress_index = (
                hr_norm * weights['hr'] +
                hrv_norm * weights['hrv'] +
                attention_norm * weights['attention'] +
                gsr_norm * weights['gsr']
            )
    
            return round(stress_index, 2)
    