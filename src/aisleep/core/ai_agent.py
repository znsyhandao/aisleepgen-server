

from src.aisleep.utils.model_loader import load_model# 在文件顶部导入区域添加
class DeviceDisconnectedError(Exception):
    """生物反馈设备断开连接异常"""
    pass

# ... 原有导入保持不变 ...
from aisleep.database.user_db import UserDatabase
from aisleep.deepseek_model import DeepSeekMultiModal
from typing import Dict, List, AsyncGenerator
import asyncio
from ..hardware.manager import HardwareManager
from src.aisleep.database.feedback_database import FeedbackDatabase

from deepseek import DeepSeekModel

from aisleep.analysis.habit_analyzer import HabitAnalyzer
from aisleep.analysis.environment_adjuster import EnvironmentAdjuster 
from aisleep.evaluation.intervention_evaluator import InterventionEvaluator
from src.aisleep.interventions.music_therapy import MusicTherapy
from src.aisleep.interventions.breathing_exercise import BreathingExercise
from src.aisleep.interventions.visual_feedback import VisualFeedback
from src.aisleep.interventions.audio_feedback import AudioFeedback
import time  # 缺少时间模块
from src.aisleep.analysis.stress_calculator import StressCalculator

import numpy as np  # 缺少numpy模块

import time


# 在类顶部添加
import logging
logger = logging.getLogger(__name__)

from scipy.signal import butter, filtfilt

# 测试 numpy
#print(np.array([1, 2, 3]))

# 测试 scipy.signal
#b, a = butter(4, 0.2, btype='low')
#print(f"Butterworth filter coefficients: b={b}, a={a}")

# 测试 deepseek
#try:
    #model = DeepSeekModel.from_pretrained("path/to/model")
    #print("DeepSeekModel loaded successfully")
#except Exception as e:
    #print(f"Error loading DeepSeekModel: {e}")


class SleepAIAgent:
    def __init__(self, 
             model_path: str = "E:/DeepSeek-V3-0324/",  # 默认模型路径
             hardware_accel=True,
             use_quantization=False):  
        """
        初始化 SleepAIAgent，包括环境调节器、AI 引擎、DeepSeek 模型等组件。
        """
        # 修改环境调节器初始化
        self.env_adjuster = EnvironmentAdjuster({
            'temperature': 21.0,  # 理想温度
            'light_level': 50,    # 理想光照(lux)
            'noise_level': 30     # 理想噪音(dB)
        })

        # 初始化 DeepSeek 模型
        try:
            from deepseek import DeepSeekModel
            self.deepseek_model = DeepSeekModel.from_pretrained(model_path)
            self.deepseek_model.eval()  # 设置为推理模式
            logger.info("DeepSeek 模型加载成功")
        except Exception as e:
            logger.error(f"DeepSeek 模型加载失败: {str(e)}")
            raise RuntimeError("无法加载 DeepSeek 模型，请检查模型路径或文件完整性")

        # 初始化 AI 引擎
        self.engine = DeepSeekMultiModal(
            model="deepseek-sleep-pro-4.0",
            hardware_accel=hardware_accel,
            specialized_knowledge=["sleep_science", "neurobiology"],  # 添加 specialized_knowledge 参数

            model_path=model_path,  # 实际使用参数
            use_quantization=use_quantization  # 实际使用参数
        )

        # 初始化睡眠阶段模型
        self.STAGE_NAMES = ["AWAKE", "NREM1", "NREM2", "NREM3", "REM"]
        self.sleep_stage_model = CNN_SleepModel()  # 需要导入

        # 初始化其他组件
        self.habit_analyzer = HabitAnalyzer("data/user_stats.parquet")
        self.evaluator = InterventionEvaluator()
        self.device_manager = HardwareManager()
        self.user_db = UserDatabase()
        self.feedback_system = FeedbackSystem()

        # 新增干预模块注册
        self.interventions = {
            'music': MusicTherapy(self.device_manager),
            'breathing': BreathingExercise(self.device_manager),
            # 可继续添加其他模块
        }

        logger.info("SleepAIAgent 初始化完成")

    def _bandpass_filter(self, data, lowcut, highcut, fs, order=5):
        """带通滤波器实现"""
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return filtfilt(b, a, data)
    def _select_visual_theme(self, stress_level: float) -> str:
        """根据压力水平选择视觉主题"""
        if stress_level > 70:
            return "calm_ocean"
        elif stress_level > 40:
            return "serene_forest"
        else:
            return "clear_sky"
    def _get_personalized_greeting(self, stress_level: float) -> str:
        """生成个性化问候语"""
        if stress_level > 70:
            return "欢迎开始冥想，让我们一起缓解您的压力。"
        elif stress_level > 40:
            return "欢迎回来，让我们一起放松身心。"
        else:
            return "欢迎开始冥想，保持您的平静状态。"
    async def get_stress_interventions(self, user_id: str) -> List[Dict]:
        """增强版个性化减压方案推荐"""
        # 获取用户数据和实时生物指标
        profile = self.user_db.get_profile(user_id) or {"sensitivity": 0.5}  # 提供默认配置
    
        biometrics = await self.device_manager.get_vital_signs()
        history = self.user_db.get_intervention_history(user_id, days=7)
    
        # 计算动态效果阈值
        baseline_threshold = 0.5
        stress_level = self._calculate_stress_index(biometrics)
        dynamic_threshold = baseline_threshold * (1 + stress_level / 10)  # 压力越大阈值越高
    
        interventions = []
        for name, module in self.interventions.items():
            # 计算干预效果评分(结合历史效果和实时预测)
            effectiveness = (
                0.6 * module.get_effectiveness(profile) +
                0.4 * self._get_historical_effectiveness(history, name)
            )
    
            if effectiveness > dynamic_threshold:
                # 生成带实时调整参数的干预方案
                intervention = await module.apply({
                    **biometrics,
                    'user_sensitivity': profile.get('sensitivity', 0.5),
                    'current_stress': stress_level
                })
                interventions.append(intervention)
    
        return interventions
    def log_intervention(self, user_id: str, intervention: Dict):
        """记录干预执行日志"""
        self.user_db.log_activity(
            user_id,
            activity_type="stress_intervention",
            metadata=intervention
        )

    # 新增辅助方法
        # 在SleepAIAgent类中添加
    def _get_intervention_methods(self) -> Dict:
        """获取多模式减压方法库"""
        return {
            'breathing': {
                '4-7-8': {  # 4秒吸气-7秒屏息-8秒呼气
                    'effectiveness': 0.85,
                    'conditions': lambda bio: 0.3 < bio['stress'] < 0.7
                },
                'box': {  # 4-4-4-4方形呼吸
                    'effectiveness': 0.75,
                    'conditions': lambda bio: bio['hrv'] < 50
                }
            },
            'music': {
                'binaural_beats': {
                    'frequencies': {
                        'theta': (4,7),  # 深度放松
                        'alpha': (8,12)  # 轻度放松
                    },
                    'conditions': lambda bio: bio['eeg']['theta'] > 0.5
                }
            }
        }

    async def select_intervention(self, biometrics: Dict) -> Dict:
        """智能选择最佳减压方式"""
        methods = self._get_intervention_methods()
        suitable = []
        
        # 筛选符合条件的减压方式
        for category in methods:
            for name, params in methods[category].items():
                if params['conditions'](biometrics):
                    suitable.append({
                        'type': category,
                        'name': name,
                        'score': params['effectiveness'] * (1 - biometrics['stress'])
                    })
        
        return max(suitable, key=lambda x: x['score']) if suitable else None
    # 新增用户画像分析
    def _analyze_user_profile(self, user_id: str) -> Dict:
        """深度分析用户特征"""
        history = self.user_db.get_3month_history(user_id)
        return {
            'stress_pattern': self._detect_stress_pattern(history),
            'preferred_modality': self._detect_preferred_modality(history),
            'response_stats': self._calculate_response_stats(history)
        }

    # 在原有推荐算法中整合
    async def generate_recommendations(self, user_id: str) -> List[Dict]:
        profile = self._analyze_user_profile(user_id)
        biometrics = self.device_manager.get_vital_signs()
        
        base = await self.select_intervention(biometrics)
        personalized = self._adjust_for_profile(base, profile)
        
        return self._sort_by_priority(personalized)
    


    def _init_eeg_filter(self):
        """初始化EEG滤波器"""
        value = None

        def eeg_filter(new_val):
            nonlocal value
            value = 0.8 * new_val + (1 - 0.8) * value if value else new_val
            return value

        return eeg_filter

    def _get_processed_eeg_spectrum(self) -> Dict:
        """获取带预处理的EEG频谱数据"""
        raw_eeg = self.device_manager.get_eeg()

        # 1. 带通滤波 (5-30Hz)
        filtered = self._bandpass_filter(
            raw_eeg,
            lowcut=5,
            highcut=30,
            fs=256  # 假设采样率256Hz
        )

        # 2. 频谱分析
        spectrum = np.abs(np.fft.fft(filtered)[:len(filtered) // 2])
        freqs = np.fft.fftfreq(len(filtered), 1 / 256)[:len(filtered) // 2]

        # 3. 特征提取
        return {
            'alpha': spectrum[(freqs >= 8) & (freqs <= 12)].mean(),  # α波(8-12Hz)
            'theta': spectrum[(freqs >= 4) & (freqs <= 7)].mean(),  # θ波(4-7Hz)
            'beta': spectrum[(freqs >= 13) & (freqs <= 30)].mean(),  # β波(13-30Hz)
        }

    def _get_historical_effectiveness(self, history: List, intervention_type: str) -> float:
        """计算某类干预措施的历史平均效果"""
        relevant = [h for h in history if h['type'] == intervention_type]
        if not relevant:
            return 0.7  # 默认值
        return sum(h['effectiveness'] for h in relevant) / len(relevant)

    def _validate_intervention(self, intervention: Dict) -> bool:
        """验证干预方案可行性"""
        required = ['type', 'duration', 'intensity']
        return all(k in intervention for k in required) and intervention['duration'] > 0

    def _predict_impact(self, intervention: Dict, biometrics: Dict) -> float:
        """预测干预效果(0-1)"""
        base = intervention.get('confidence', 0.5)
        # 根据当前压力水平调整预测
        stress_factor = 1 - (biometrics['stress'] / 10)  # 压力越大效果可能越差
        return min(1, base * stress_factor * 1.2)



    def adjust_intervention(self, env_data: Dict):
        adjustments = self.env_adjuster.calculate_adjustment(env_data)
        # 应用补偿到干预方案
        return adjustments


    def check_db_connection(self):
        """检查数据库连接状态"""
        try:
            # 实际检查数据库连接
            return self.user_db.check_connection()  # 假设UserDatabase有这个方法
        except Exception as e:
            logger.error(f"数据库连接检查失败: {str(e)}")
            return False



    async def stress_relief(self, biometrics: Dict) -> Dict:
        """智能减压方案"""
        return await self.engine.predict(
            task="stress_analysis_pro",
            input_data={
                **biometrics,
                "therapy_type": "biofeedback",
                "hardware_data": self.device_manager.get_vital_signs()
            }
        )

    async def meditation_guide(self, user_profile: Dict) -> AsyncGenerator:
        """专业增强版冥想引导系统"""
        # 初始化个性化参数
        user_prefs = user_profile.get('meditation_prefs', {
            'voice_type': 'female_calm',  # 默认温和女声
            'bgm_type': 'nature',         # 默认自然音效
            'guidance_level': 'medium'    # 引导强度
        })
    
        # 根据用户压力水平动态调整
        biometrics = {
            "hrv": self.device_manager.get_hrv(),
            "gsr": self.device_manager.get_gsr()
        }
        stress_level = self._calculate_stress_index(biometrics)
    
        # 生成个性化开场白
        yield self._generate_welcome_message(user_prefs, stress_level)
    
        # 初始化生物反馈平滑滤波器
        feedback_filter = {
            'hrv': self._init_ema_filter(alpha=0.2),
            'gsr': self._init_ema_filter(alpha=0.3),
            'eeg': self._init_eeg_filter()
        }
    
        # 新增反馈历史记录
        feedback_history = {
            'hrv': [],
            'gsr': [],
            'eeg': [],
            'timestamps': []
        }
    
        try:
            async for chunk in self.engine.stream(
                task="meditation_coach_pro",
                params={
                    **user_profile,
                    "realtime_biofeedback": {
                        'hrv': feedback_filter['hrv'](self.device_manager.get_hrv()),
                        'gsr': feedback_filter['gsr'](self.device_manager.get_gsr()),
                        'eeg': self._get_processed_eeg_spectrum()
                    },
                    "adaptive_strategy": self._generate_adaptive_strategy(user_profile)
                },
                timeout=30  # 设置30秒超时
            ):
                # 检查设备连接状态
                if not self.device_manager.is_connected():
                    yield self._get_device_disconnected_fallback()
                    break
    
                # 分析反馈趋势
                feedback_trend = self._analyze_feedback_trend(feedback_history)
    
                # 在适当节点添加科学解释
                if feedback_trend['change_rate'] > 0.5:
                    yield {
                        'type': 'science_tip',
                        'content': "您的心率变异性正在提升，说明身体进入放松状态",
                        'reference': "根据哈佛医学院研究，HRV升高与副交感神经激活相关"
                    }
    
                # 记录实时反馈数据
                current_time = time.time()
                feedback_history['hrv'].append(self.device_manager.get_hrv())
                feedback_history['gsr'].append(self.device_manager.get_gsr())
                feedback_history['eeg'].append(self._get_processed_eeg_spectrum())
                feedback_history['timestamps'].append(current_time)
    
                # 生成实时调节参数
                adjustment = self._calculate_realtime_adjustment(feedback_history)
    
                yield {
                    **self._format_meditation_chunk(
                        chunk,
                        adaptation_level=self._calculate_adaptation_level()
                    ),
                    'realtime_adjustment': adjustment,
                    'feedback_trend': feedback_trend
                }
    
            # 结束引导
            yield {
                'type': 'closing',
                'content': self._generate_closing_message(
                    self._calculate_session_improvement(feedback_history)
                ),
                'action': '慢慢睁开眼睛，感受当下的平静'
            }
        except asyncio.TimeoutError:
            logger.error("冥想引导响应超时")
            yield self._get_timeout_fallback()
        except DeviceDisconnectedError:
            logger.error("生物反馈设备断开连接")
            yield self._get_device_disconnected_fallback()
        except Exception as e:
            logger.error(f"冥想引导异常: {str(e)}")
            yield self._get_error_fallback()


    # 新增辅助方法
    def evaluate_intervention(self, user_id: str, intervention: Dict) -> Dict:
        """评估干预效果"""
        before = self.device_manager.get_vital_signs()
        # 执行干预...
        after = self.device_manager.get_vital_signs()
        
        return {
            'effectiveness': self._calculate_improvement(before, after),
            'feedback': self._get_user_feedback(user_id),
            'suggestions': self._generate_optimization(intervention)
        }

    def _generate_welcome_message(self, prefs: Dict, stress_level: float) -> Dict:
        """生成个性化开场引导"""
        return {
            'type': 'welcome',
            'content': self._get_personalized_greeting(stress_level),
            'voice': prefs['voice_type'],
            'bgm': self._select_bgm(prefs['bgm_type'], stress_level),
            'visual': self._select_visual_theme(stress_level)
        }

    def _select_bgm(self, bgm_type: str, stress_level: float) -> str:
        """智能选择背景音乐"""
        if stress_level > 0.7:
            return 'slow_ocean_waves'  # 高压力使用海浪声
        elif stress_level > 0.4:
            return 'forest_ambience'   # 中等压力使用森林音效
        return 'singing_bowl'         # 低压力使用颂钵音效

    def _calculate_realtime_adjustment(self, feedback_history: Dict) -> Dict:
        """增强版实时调节算法"""
        # 计算压力变化趋势
        stress_trend = np.polyfit(
            range(len(feedback_history['hrv'])),
            feedback_history['hrv'],
            1
        )[0]
        
        return {
            'breathing_rate': self._adjust_breathing_rate(
                feedback_history['hrv'],
                stress_trend
            ),
            'difficulty': self._calculate_optimal_difficulty(stress_trend),
            'feedback_frequency': self._adjust_feedback_frequency(
                feedback_history['gsr']
            )
        }


    def _analyze_feedback_trend(self, feedback_history: Dict) -> Dict:
        """分析反馈数据趋势"""
        if len(feedback_history['hrv']) < 2:
            return {'trend': 'stable', 'change_rate': 0}
        
        hrv_trend = np.polyfit(
            feedback_history['timestamps'],
            feedback_history['hrv'],
            1
        )[0]
        
        return {
            'trend': 'improving' if hrv_trend > 0 else 'declining',
            'change_rate': abs(hrv_trend)
        }


    # 新增辅助方法
    def _init_ema_filter(self, alpha: float):
        """初始化指数移动平均滤波器"""
        value = None
        def ema_filter(new_val):
            nonlocal value
            value = alpha * new_val + (1 - alpha) * value if value else new_val
            return value
        return ema_filter

    def _generate_adaptive_strategy(self, profile: Dict) -> Dict:
        """生成个性化适应策略"""
        return {
            'focus_level': self._calculate_focus_index(),
            'stress_trend': self._get_stress_trend(),
            'user_sensitivity': profile.get('sensitivity', 0.5)
        }



        
    async def holistic_analysis(self, user_data: Dict):
        """全息睡眠分析"""
        return await self.engine.predict(
            task="sleep_holistic",
            input_data={
                **user_data,
                "hardware_signals": self.device_manager.get_latest_data()
            }
        )
    
    async def realtime_intervention(self):
        """优化后的实时干预流"""
        async for state in self.device_manager.stream_state():
            adjusted = self.adjust_intervention(state)
            yield await self.engine.predict(
                task="dynamic_intervention",
                input_data=adjusted
            )




    async def generate_report(self, user_id: str) -> Dict:
        # 基础数据分析
        habits = self.habit_analyzer.analyze_sleep_patterns(user_id)
        env_data = self._get_environment_data()
        adjustments = self.env_adjuster.calculate_adjustment(env_data)
        
        # 新增趋势分析
        weekly_trend = self._analyze_weekly_trend(user_id)
        monthly_trend = self._analyze_monthly_trend(user_id)

        analysis = await self.holistic_analysis(self.user_db.get_profile(user_id))
        evaluation = self.evaluator.evaluate(analysis['before'], analysis['after'])
        
        # 获取历史百分位数用于比较
        last_percentile = self.user_db.get_last_percentile(user_id)
        current_percentile = self.user_db.get_percentile(user_id)
        
        # 新增睡眠质量评分
        sleep_score = self._calculate_sleep_score(
            analysis['sleep_metrics'],
            habits['sleep_regularity']
        )
        
        # 新增睡眠阶段分析
        sleep_stage_analysis = self._analyze_sleep_stages(
            analysis['sleep_metrics']['stage_distribution']
        )
        
        # 新增环境评分
        env_score = self._calculate_environment_score(env_data)
        
        # 生成改进建议
        suggestions = self._generate_enhanced_suggestions(
            analysis,
            habits,
            weekly_trend,
            sleep_stage_analysis
        )

        return {
            **analysis,
            'sleep_score': sleep_score,
            'sleep_stage_analysis': sleep_stage_analysis,
            'environment_score': env_score,
            'comparison': self._format_comparison_data(current_percentile, last_percentile),
            'habit_analysis': habits,
            'environment_adjustments': adjustments,
            'evaluation': evaluation,
            'trend_analysis': {
                'weekly': weekly_trend,
                'monthly': monthly_trend
            },
            'personalized_suggestions': {
                'priority_list': suggestions,
                'weekly_focus': self._get_weekly_focus(suggestions)
            }
        }

    def _calculate_sleep_score(self, metrics: Dict, regularity: float) -> float:
        """计算0-100分的睡眠质量综合评分"""
        return min(100, 
                metrics['deep_sleep'] * 40 + 
                regularity * 30 +
                (100 - metrics['awakenings']) * 30)

    def _analyze_weekly_trend(self, user_id: str) -> Dict:
        """分析用户近7天趋势"""
        return {
            'sleep_quality': self.user_db.get_weekly_metrics(user_id, 'sleep_quality'),
            'stress_level': self.user_db.get_weekly_metrics(user_id, 'stress_level'),
            'progress': self.user_db.get_weekly_progress(user_id)
        }

    def _analyze_monthly_trend(self, user_id: str) -> Dict:
        """分析用户近30天趋势"""
        return {
            'sleep_duration': self.user_db.get_monthly_metrics(user_id, 'sleep_duration'),
            'intervention_effectiveness': self.user_db.get_monthly_metrics(user_id, 'intervention_effectiveness')
        }

    def _analyze_sleep_stages(self, stage_data: Dict) -> Dict:
        """分析各睡眠阶段占比是否理想"""
        return {
            'deep_sleep': {
                'percentage': stage_data['deep_sleep'],
                'assessment': '充足' if stage_data['deep_sleep'] >= 20 else '不足'
            },
            'rem': {
                'percentage': stage_data['rem'],
                'assessment': '充足' if stage_data['rem'] >= 20 else '不足'
            }
        }

    def _calculate_environment_score(self, env_data: Dict) -> float:
        """计算环境因素评分(0-100)"""
        return min(100, 
            (100 - abs(env_data['temperature'] - 21)) * 0.4 +
            (100 - env_data['noise_level']) * 0.3 +
            env_data['air_quality'] * 0.3
        )

    def _generate_enhanced_suggestions(self, analysis: Dict, habits: Dict, trends: Dict, stage_analysis: Dict) -> List[Dict]:
        """生成带优先级的详细建议"""
        suggestions = []
        
        # 根据深度睡眠情况添加建议
        if stage_analysis['deep_sleep']['assessment'] == '不足':
            suggestions.append({
                'type': 'sleep_quality',
                'priority': 1,
                'action': '增加深度睡眠时间',
                'details': '尝试睡前热水澡或轻度拉伸',
                'expected_improvement': '提升15-20%深度睡眠'
            })
        
        # 根据压力水平添加建议
        if trends['stress_level'] > 60:
            suggestions.append({
                'type': 'stress_reduction',
                'priority': 2,
                'action': '每日冥想15分钟',
                'details': '使用APP中的引导冥想',
                'expected_improvement': '降低20-30%压力水平'
            })
        
        return sorted(suggestions, key=lambda x: x['priority'])

    def _get_weekly_focus(self, suggestions: List[Dict]) -> Dict:
        """获取本周重点改善领域"""
        if not suggestions:
            return {'focus': '维持现状', 'reason': '您的睡眠习惯良好'}
        return {
            'focus': suggestions[0]['action'],
            'reason': suggestions[0]['details']
        }

    # 新增辅助方法



    def _generate_personalized_suggestions(self, analysis: Dict, habits: Dict, trends: Dict) -> List[str]:
        """生成个性化建议"""
        suggestions = []
        if trends['weekly']['stress_level']['trend'] > 0.1:
            suggestions.append("建议增加晚间冥想频率")
        if habits['sleep_regularity'] < 0.7:
            suggestions.append("建议固定作息时间")
        return suggestions


# ... 原有代码 ...

    async def advanced_sleep_analysis(self, sleep_data: Dict) -> Dict:
        """多维度睡眠分析"""
        analysis = await self.engine.predict(
            task="sleep_analysis_plus",
            input_data={
                **sleep_data,
                "sleep_stages": self._detect_sleep_stages(sleep_data),
                "environment_factors": self._get_environment_data()
            }
        )
        return {
            **analysis,
            "intervention_plan": self._generate_intervention_plan(analysis)
        }

    def _generate_intervention_plan(self, analysis: Dict) -> List[Dict]:
        """生成智能干预方案"""
        return [
            {
                "type": "sound_wave",
                "intensity": analysis["stress_level"] * 0.8,
                "duration": 30 * 60  # 30分钟
            },
            {
                "type": "light_therapy",
                "color": "amber",
                "schedule": "pre_sleep"
            }
        ]


    def get_current_state(self) -> Dict:
        """获取用户当前综合状态
        返回:
            Dict: 包含心率、压力指数等实时数据
        """
        return {
            "heart_rate": self.device_manager.get_heart_rate(),
            "stress_index": self._calculate_stress_index(),
            "sleep_stage": self._detect_sleep_stages(
                self.device_manager.get_latest_data()
            )["current_stage"],
            "last_update": time.time()
        }

    def _format_recommendation(self, recommendation: Dict) -> Dict:
        """格式化推荐内容为前端可展示的结构
        参数:
            recommendation: 原始推荐数据
        返回:
            格式化后的推荐内容
        """
        return {
            "title": recommendation.get("action_name", "未命名建议"),
            "description": self._translate_action(recommendation["type"]),
            "priority": recommendation.get("priority", 3),
            "duration": f"{recommendation['duration']//60}分钟",
            "icon": self._get_icon_for_type(recommendation["type"])
        }


    def _detect_sleep_stages(self, sleep_data: Dict) -> Dict:
        """基于生物信号数据检测睡眠阶段
        参数:
            sleep_data: 包含EEG、心率等原始数据
        返回:
            {
                "current_stage": "REM|NREM1|NREM2|NREM3|AWAKE",
                "stage_confidence": 0.0-1.0,
                "next_transition": 预估下一阶段转换时间(秒)
            }
        """
        # 使用预训练模型分析EEG数据
        eeg_features = self._extract_eeg_features(sleep_data["eeg"])
        stage_probs = self.sleep_stage_model.predict(eeg_features)
        
        return {
            "current_stage": self.STAGE_NAMES[np.argmax(stage_probs)],
            "stage_confidence": float(np.max(stage_probs)),
            "next_transition": self._predict_transition(stage_probs)
        }


    def _get_environment_data(self) -> Dict:
        """获取卧室环境参数
        返回:
            {
                "temperature": 室温(℃),
                "humidity": 湿度(%),
                "light_level": 光照强度(lux),
                "noise_level": 噪音分贝(dB)
            }
        """
        return {
            "temperature": self.device_manager.get_temperature(),
            "humidity": self.device_manager.get_humidity(),
            "light_level": self.device_manager.get_light_level(),
            "noise_level": self.device_manager.get_noise_level(),
            "air_quality": self.device_manager.get_air_quality_index()
        }


    def _calculate_stress_index(self, biometrics: Dict) -> float:
        """计算压力指数"""
        return StressCalculator.calculate_stress_index(biometrics)

    def _extract_eeg_features(self, raw_eeg):
        """从原始EEG信号提取特征"""
        # 实现信号处理逻辑
        pass
    def _extract_eeg_features(self, raw_eeg):
        """实现EEG特征提取"""
        return {
            'power_spectrum': np.abs(fft(raw_eeg)[:len(raw_eeg)//2]),
            'std_dev': np.std(raw_eeg)
        }
    def _predict_transition(self, stage_probs):
        """预测阶段转换时间"""
        return 90  # 简单实现，实际应基于历史数据



    def _get_interpretation(self, percentile: float) -> str:
        """提供建设性解读"""
        if percentile > 80:
            return "您的睡眠质量优于80%的同龄人"
        elif percentile > 50:
            return "您的睡眠质量处于同龄人中等偏上水平"
        else:
            return "您的睡眠质量有提升空间，我们已为您准备改善方案"

    def _generate_encouragement(self, percentile: float) -> str:
        """生成鼓励性反馈"""
        return "坚持当前作息习惯" if percentile > 60 else "小调整就能带来大改善"

    def _format_comparison_data(self, percentile: float, last_percentile: float) -> Dict:
        """安全格式化比较数据，强调进步而非排名"""
        improvement = percentile - last_percentile if last_percentile else 0
        
        return {
            'display_mode': 'progressive',  # progressive/neutral/competitive
            'progress': {
                'value': improvement,
                'trend': 'up' if improvement >= 0 else 'down',
                'message': self._get_progress_message(improvement)
            },
            'benchmark': {
                'level': self._get_performance_level(percentile),
                'description': self._get_benchmark_description(percentile)
            },
            'suggestions': self._get_improvement_suggestions(percentile),
            'user_preferences': {
                'show_comparison': True,
                'intensity': 'medium'  # low/medium/high
            }
        }

    def _get_progress_message(self, improvement: float) -> str:
        """生成进步导向的反馈"""
        if improvement >= 5:
            return f"太棒了！您的睡眠质量提升了{improvement:.1f}%"
        elif improvement >= 0:
            return f"保持得很好，有{improvement:.1f}%的提升"
        else:
            return "我们注意到有些波动，试试这些改善建议"

    def _get_performance_level(self, percentile: float) -> str:
        """转换为温和的表现等级"""
        bands = [
            (90, "顶尖水平"), 
            (70, "优秀"),
            (40, "良好"),
            (20, "有提升空间"),
            (0, "需要关注")
        ]
        return next(v for k,v in bands if percentile >= k)

    def _get_benchmark_description(self, percentile: float) -> str:
        """生成建设性的基准描述"""
        if percentile > 80:
            return "您的睡眠质量处于人群前20%"
        elif percentile > 50:
            return "您的睡眠质量优于平均水平"
        else:
            return "大多数人在这方面的睡眠质量更好"

    def _get_improvement_suggestions(self, percentile: float) -> List[Dict]:
        """根据表现水平提供具体建议"""
        suggestions = []
        if percentile < 40:
            suggestions.append({
                'type': 'essential',
                'action': '固定作息时间',
                'reason': '能显著改善睡眠质量'
            })
        if percentile < 70:
            suggestions.append({
                'type': 'recommended',
                'action': '睡前1小时减少屏幕使用',
                'reason': '有助于更快入睡'
            })
        return suggestions

    def _calculate_focus_index(self) -> float:
        """基于EEG频谱计算专注度指数"""
        eeg = self.device_manager.get_eeg()
        theta = eeg['power_spectrum'][4:8].mean()  # 4-8Hz
        alpha = eeg['power_spectrum'][8:12].mean() # 8-12Hz
        return alpha / (theta + 1e-6)  # 防止除零
    def generate_stress_profile(self, user_id: str) -> Dict:
        """生成用户压力特征画像"""
        return {
            'stress_patterns': self.user_db.get_stress_patterns(user_id),
            'optimal_interventions': self._find_optimal_interventions(user_id),
            'neuro_response': self._analyze_neuro_response(user_id)
        }

    def _generate_intervention_plan(self, analysis: Dict) -> List[Dict]:
        """科学增强版干预方案"""
        return [
            {
                "type": "binaural_beats",  # 双耳节拍
                "frequency": self._calculate_optimal_frequency(analysis),
                "duration": analysis['stress_duration'] * 0.3
            },
            {
                "type": "biofeedback_game",  # 生物反馈游戏
                "difficulty": analysis['stress_level'] / 10,
                "target_metrics": ["hrv", "gsr"]
            }
        ]
    
    def validate_effectiveness(self, user_id: str) -> Dict:
        """基于临床标准的有效性验证"""
        return {
            'psqi_change': self._calculate_psqi_improvement(user_id),  # 匹兹堡睡眠质量指数
            'hads_change': self._calculate_hads_reduction(user_id),     # 医院焦虑抑郁量表
            'eeg_metrics': self._get_eeg_improvement_metrics(user_id)  # 脑电改善指标
        }

    def _get_processed_eeg_spectrum(self) -> Dict:
        """获取带预处理的EEG频谱数据"""
        raw_eeg = self.device_manager.get_eeg()
        
        # 1. 带通滤波 (5-30Hz)
        filtered = self._bandpass_filter(
            raw_eeg, 
            lowcut=5, 
            highcut=30, 
            fs=256  # 假设采样率256Hz
        )
        
        # 2. 频谱分析
        spectrum = np.abs(np.fft.fft(filtered)[:len(filtered)//2])
        freqs = np.fft.fftfreq(len(filtered), 1/256)[:len(filtered)//2]
        
        # 3. 特征提取
        return {
            'alpha': spectrum[(freqs >= 8) & (freqs <= 12)].mean(),  # α波(8-12Hz)
            'theta': spectrum[(freqs >= 4) & (freqs <= 7)].mean(),    # θ波(4-7Hz)
            'beta': spectrum[(freqs >= 13) & (freqs <= 30)].mean(),    # β波(13-30Hz)
            'quality': self._calculate_signal_quality(raw_eeg)
        }

    def _bandpass_filter(self, data, lowcut, highcut, fs, order=5):
        """带通滤波器实现"""
        nyq = 0.5 * fs
        low = lowcut / nyq
        high = highcut / nyq
        b, a = butter(order, [low, high], btype='band')
        return filtfilt(b, a, data)


    def _calculate_adaptation_level(self) -> float:
        """计算实时冥想适应度(0-1)"""
        # 获取当前生理指标
        hrv = self.device_manager.get_hrv()
        gsr = self.device_manager.get_gsr()
        eeg = self._get_processed_eeg_spectrum()
        
        # 计算各指标得分
        hrv_score = min(1, hrv / 50)  # 假设HRV正常范围0-50
        gsr_score = 1 - min(1, gsr / 10)  # 假设GSR正常范围0-10
        eeg_score = eeg['alpha'] / (eeg['theta'] + 1e-6)  # α/θ波比例
        
        # 加权综合评分
        return 0.4 * hrv_score + 0.3 * gsr_score + 0.3 * eeg_score

    def _get_timeout_fallback(self) -> Dict:
        """超时备用引导内容"""
        return {
            'type': 'fallback',
            'content': "请放松呼吸，专注于此刻的感受...",
            'duration': 60,
            'metadata': {
                'reason': 'timeout',
                'suggestion': '检查网络连接后重试'
            }
        }

    def _get_error_fallback(self) -> Dict:
        """错误备用引导内容""" 
        return {
            'type': 'fallback',
            'content': "让我们进行基础呼吸练习：吸气4秒，屏息4秒，呼气6秒...",
            'duration': 120,
            'metadata': {
                'reason': 'system_error', 
                'suggestion': '稍后重试或联系支持'
            }
        }

    def _calculate_signal_quality(self, raw_eeg: List[float]) -> float:
        """评估EEG信号质量(0-1)"""
        # 1. 检查信号幅度是否在合理范围
        amplitude = np.mean(np.abs(raw_eeg))
        if amplitude < 10 or amplitude > 100:  # 假设合理范围10-100μV
            return 0.2
        
        # 2. 检查信号方差
        variance = np.var(raw_eeg)
        
        # 3. 综合评分
        return min(1, variance / 50)  # 假设方差50为理想值


    def _adjust_breathing_rate(self, last_5_hrv: List[float]) -> float:
        """根据HRV数据动态调节呼吸频率(次/分钟)
        参数:
            last_5_hrv: 最近5次HRV测量值(ms)
        返回:
            调整后的呼吸频率(6-18次/分钟)
        """
        if not last_5_hrv:
            return 12.0  # 默认值
        
        avg_hrv = sum(last_5_hrv) / len(last_5_hrv)
        
        # HRV与呼吸频率的映射关系 (基于临床研究)
        if avg_hrv > 60:    # 高HRV -> 慢呼吸
            return 6.0 + (avg_hrv - 60) * 0.1
        elif avg_hrv > 40:  # 中等HRV -> 中等呼吸
            return 10.0 + (avg_hrv - 40) * 0.1
        else:               # 低HRV -> 快呼吸
            return 14.0 + (avg_hrv - 20) * 0.2

    def _adjust_guidance_intensity(self, last_5_gsr: List[float]) -> float:
        """根据GSR数据调节引导强度(0-1)
        参数:
            last_5_gsr: 最近5次皮肤电反应值(μS)
        返回:
            引导强度系数(0.3-1.0)
        """
        if not last_5_gsr:
            return 0.7  # 默认值
        
        # 计算变化趋势
        trend = np.polyfit(range(len(last_5_gsr)), last_5_gsr, 1)[0]
        
        # 趋势上升(压力增加) -> 增强引导
        if trend > 0.5:
            return min(1.0, 0.7 + trend * 0.2)
        # 趋势下降(放松) -> 减弱引导
        elif trend < -0.3:
            return max(0.3, 0.7 + trend * 0.1)
        return 0.7

    def _adjust_bgm_volume(self, eeg_data: Dict) -> float:
        """根据脑波频谱调节背景音乐音量(0-1)
        参数:
            eeg_data: 包含alpha/theta/beta波强度的字典
        返回:
            音量系数(0.2-0.8)
        """
        # 计算专注度指数 (α/θ比例)
        focus_index = eeg_data['alpha'] / (eeg_data['theta'] + 1e-6)
        
        # 专注度高 -> 降低音量避免干扰
        if focus_index > 2.0:
            return 0.3
        # 专注度低 -> 提高音量辅助集中
        elif focus_index < 1.0:
            return 0.7
        # 中等专注度 -> 适中音量
        return 0.5

    def _evaluate_user_adaptation(self, feedback_history: Dict) -> Dict:
        """综合评估用户适应状态"""
        # 计算关键指标变化
        hrv_change = np.mean(np.diff(feedback_history['hrv'][-10:]))
        gsr_change = np.mean(np.diff(feedback_history['gsr'][-10:]))
        
        # 生成适应度报告
        return {
            'stress_level': self._map_to_percentage(gsr_change, -2, 2),
            'relaxation_speed': self._map_to_percentage(hrv_change, 0, 5),
            'adaptation_score': min(100, 
                self._calculate_adaptation_level() * 100),
            'suggestion': self._generate_adaptation_suggestion(
                hrv_change, 
                gsr_change
            )
        }

    def _map_to_percentage(self, value, min_val, max_val):
        """将值映射到0-100%范围"""
        return max(0, min(100, (value - min_val) / (max_val - min_val) * 100))

    def _get_device_disconnected_fallback(self) -> Dict:
        """设备断开连接的备用方案"""
        return {
            'type': 'fallback',
            'content': '设备连接已断开，请检查生物传感器',
            'duration': 0,  # 立即结束会话
            'metadata': {
                'severity': 'critical',
                'recovery_action': 'reconnect_device'
            }
        }

    def _generate_adaptation_suggestion(self, hrv_change: float, gsr_change: float) -> str:
        """生成适应性建议"""
        if hrv_change > 3 and gsr_change < -1:
            return "您适应得很好，可以尝试更高阶的冥想练习"
        elif hrv_change < 0:
            return "检测到压力反应，建议切换到基础呼吸练习"
        return "保持当前练习节奏"
    
class StressInterventionBase:
    """减压干预模块基类"""
    def __init__(self, device_manager):
        self.device = device_manager
    
    async def apply(self, biometrics: Dict) -> Dict:
        """应用干预措施"""
        raise NotImplementedError
        
    def get_effectiveness(self, user_profile: Dict) -> float:
        """预测干预效果(0-1)"""
        raise NotImplementedError

class FeedbackSystem:
    def __init__(self):
        self.feedback_db = FeedbackDatabase()
        self.adjustment_model = load_model('feedback_adjuster.h5')

    async def process_feedback(self, user_id: str, feedback: Dict):
        """处理用户反馈并优化系统"""
        # 记录反馈
        await self.feedback_db.store(
            user_id,
            feedback['intervention_id'],
            feedback['effectiveness']
        )
        
        # 动态调整参数
        user_history = self.feedback_db.get_user_history(user_id)
        adjustments = self.adjustment_model.predict(user_history)
        self._apply_parameter_adjustments(user_id, adjustments)


# 使用多线程处理生物信号
from concurrent.futures import ThreadPoolExecutor

class RealtimeProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.lock = threading.Lock()

    async def process_stream(self, data):
        """并行处理数据流"""
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                self.executor,
                self._process_eeg,
                data['eeg']
            ),
            loop.run_in_executor(
                self.executor, 
                self._process_hrv,
                data['hrv']
            )
        ]
        return await asyncio.gather(*tasks)

    # 在冥想引导中应用
    async def meditation_guide(self):
        processor = RealtimeProcessor()
        async for data in self.device_manager.stream():
            results = await processor.process_stream(data)
            yield self._format_results(results)


class CNN_SleepModel:
    """占位类，用于模拟 CNN_SleepModel 的行为"""
    def __init__(self):
        print("CNN_SleepModel initialized")