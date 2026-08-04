"""
冥想引导插件 - 基于睡眠和压力分析的个性化冥想指导
提供呼吸练习、放松引导和睡眠改善建议
"""

import random
import time
from plugin_manager import BasePlugin, PluginInfo, PluginType


class MeditationGuidePlugin(BasePlugin):
    """冥想引导插件 - 个性化冥想和放松指导"""
    
    def __init__(self):
        super().__init__()
        self.info = PluginInfo(
            name="冥想引导",
            version="1.0.0",
            plugin_type=PluginType.MEDITATION_METHOD,
            description="基于睡眠和压力分析的个性化冥想指导",
            author="眠小兔冥想实验室"
        )
        
        # 冥想类型库
        self.meditation_types = {
            'breathing': {
                'name': '呼吸练习',
                'description': '专注于呼吸的冥想，适合初学者',
                'duration_options': [5, 10, 15],  # 分钟
                'benefits': ['减轻压力', '提高专注力', '平静心情']
            },
            'body_scan': {
                'name': '身体扫描',
                'description': '从头部到脚趾的身体感知练习',
                'duration_options': [10, 20, 30],
                'benefits': ['放松肌肉', '提高身体感知', '缓解疼痛']
            },
            'sleep_prep': {
                'name': '睡前冥想',
                'description': '帮助入睡的放松练习',
                'duration_options': [10, 15, 20],
                'benefits': ['改善睡眠质量', '减少失眠', '深度放松']
            },
            'stress_relief': {
                'name': '压力缓解',
                'description': '针对高压状态的快速放松',
                'duration_options': [5, 10, 15],
                'benefits': ['快速减压', '情绪稳定', '恢复精力']
            },
            'focus': {
                'name': '专注力训练',
                'description': '提高注意力和工作效率',
                'duration_options': [10, 15, 20],
                'benefits': ['提高专注', '增强记忆力', '减少分心']
            }
        }
        
        # 引导语库
        self.guidance_phrases = {
            'breathing': [
                "轻轻闭上眼睛，感受自然的呼吸",
                "吸气时，感受空气进入鼻腔，充满肺部",
                "呼气时，感受身体的放松和释放",
                "不需要控制呼吸，只是观察它",
                "如果思绪飘走，温柔地带回呼吸"
            ],
            'body_scan': [
                "将注意力带到头顶，感受头部的感觉",
                "慢慢向下，感受面部、颈部的肌肉",
                "注意肩膀是否紧张，允许它们放松",
                "感受胸部的起伏，心脏的跳动",
                "继续向下扫描，直到脚趾"
            ],
            'sleep_prep': [
                "让自己舒服地躺下，准备好入睡",
                "从脚趾开始，感受每个部位的放松",
                "想象自己漂浮在平静的湖面上",
                "让白天的思绪像云朵一样飘走",
                "允许自己完全放松，进入睡眠"
            ]
        }
    
    def analyze_sleep_data(self, sleep_data):
        """分析睡眠数据，确定冥想需求"""
        if not sleep_data:
            return 'breathing'  # 默认呼吸练习
        
        score = sleep_data.get('sleep_score', 75)
        quality = sleep_data.get('sleep_quality', '一般')
        
        if score < 60:
            return 'sleep_prep'  # 睡眠质量差，需要睡前冥想
        elif '压力' in quality or '紧张' in quality:
            return 'stress_relief'  # 压力大，需要减压
        elif score > 85:
            return 'focus'  # 睡眠好，可以专注训练
        else:
            return 'breathing'  # 一般情况，呼吸练习
    
    def analyze_stress_data(self, stress_data):
        """分析压力数据，确定冥想需求"""
        if not stress_data:
            return 'breathing'
        
        stress_level = stress_data.get('stress_level', 0.5)
        
        if stress_level > 0.7:
            return 'stress_relief'  # 高压，需要快速减压
        elif stress_level > 0.5:
            return 'body_scan'  # 中度压力，身体扫描放松
        else:
            return 'breathing'  # 低压力，维持练习
    
    def generate_meditation_plan(self, sleep_data=None, stress_data=None, duration=10):
        """生成个性化冥想计划"""
        # 确定冥想类型
        if sleep_data:
            meditation_type = self.analyze_sleep_data(sleep_data)
        elif stress_data:
            meditation_type = self.analyze_stress_data(stress_data)
        else:
            meditation_type = 'breathing'  # 默认
        
        # 选择最接近的时长
        type_info = self.meditation_types[meditation_type]
        duration_options = type_info['duration_options']
        chosen_duration = min(duration_options, key=lambda x: abs(x - duration))
        
        # 生成引导语序列
        guidance = self.guidance_phrases.get(meditation_type, self.guidance_phrases['breathing'])
        guidance_sequence = random.sample(guidance, min(3, len(guidance)))
        
        # 构建计划
        plan = {
            'meditation_type': meditation_type,
            'type_name': type_info['name'],
            'description': type_info['description'],
            'duration_minutes': chosen_duration,
            'benefits': type_info['benefits'],
            'guidance_sequence': guidance_sequence,
            'personalized_reason': self.get_personalization_reason(sleep_data, stress_data, meditation_type)
        }
        
        return plan
    
    def get_personalization_reason(self, sleep_data, stress_data, meditation_type):
        """获取个性化选择的理由"""
        reasons = []
        
        if sleep_data:
            score = sleep_data.get('sleep_score', 75)
            if score < 60:
                reasons.append(f"睡眠评分较低 ({score}/100)，需要改善睡眠质量")
            elif 'REM' in str(sleep_data):
                reasons.append("REM睡眠阶段需要优化")
        
        if stress_data:
            stress_level = stress_data.get('stress_level', 0.5)
            if stress_level > 0.7:
                reasons.append(f"压力水平较高 ({stress_level:.1%})，需要快速减压")
        
        if not reasons:
            reasons.append("维持日常冥想习惯，提升整体健康")
        
        return "; ".join(reasons)
    
    def generate_breathing_exercise(self, pattern='4-7-8'):
        """生成特定呼吸练习"""
        patterns = {
            '4-7-8': {
                'name': '4-7-8呼吸法',
                'description': '帮助快速放松和入睡的呼吸技巧',
                'steps': [
                    "用鼻子吸气4秒",
                    "屏住呼吸7秒", 
                    "用嘴巴呼气8秒",
                    "重复4次"
                ],
                'benefits': ['快速放松', '帮助入睡', '减轻焦虑']
            },
            'box': {
                'name': '方形呼吸法',
                'description': '平衡神经系统，提高专注力',
                'steps': [
                    "吸气4秒",
                    "屏气4秒",
                    "呼气4秒", 
                    "屏气4秒",
                    "重复5-10次"
                ],
                'benefits': ['平衡情绪', '提高专注', '稳定心率']
            },
            'deep': {
                'name': '深度腹式呼吸',
                'description': '完全放松的深度呼吸',
                'steps': [
                    "手放腹部，感受呼吸",
                    "缓慢吸气，腹部鼓起",
                    "缓慢呼气，腹部收缩",
                    "保持节奏，持续5分钟"
                ],
                'benefits': ['深度放松', '改善呼吸', '缓解紧张']
            }
        }
        
        pattern_info = patterns.get(pattern, patterns['4-7-8'])
        return pattern_info
    
    def create_session_script(self, plan, include_audio_cues=True):
        """创建冥想会话脚本"""
        script = []
        
        # 开场
        script.append({
            'time': '0:00',
            'action': '准备',
            'guidance': f"开始{plan['type_name']}冥想，时长{plan['duration_minutes']}分钟"
        })
        
        script.append({
            'time': '0:30',
            'action': '姿势调整',
            'guidance': "找一个舒服的姿势，可以坐着或躺着，保持脊柱挺直但放松"
        })
        
        # 引导语
        for i, guidance in enumerate(plan['guidance_sequence']):
            minute_mark = 1 + i * 2  # 每2分钟一个引导点
            script.append({
                'time': f'{minute_mark}:00',
                'action': '引导',
                'guidance': guidance
            })
        
        # 呼吸练习（如果适用）
        if plan['meditation_type'] in ['breathing', 'stress_relief']:
            breathing = self.generate_breathing_exercise()
            script.append({
                'time': f"{plan['duration_minutes']-2}:00",
                'action': '呼吸练习',
                'guidance': f"尝试{breathing['name']}: {'; '.join(breathing['steps'][:2])}"
            })
        
        # 结束
        script.append({
            'time': f"{plan['duration_minutes']}:00",
            'action': '结束',
            'guidance': "慢慢睁开眼睛，感受当下的平静。将这份宁静带入接下来的时光。"
        })
        
        return script
    
    def execute(self, data):
        """
        执行冥想引导
        
        参数:
            data: 包含以下键的字典
                - sleep_data: 睡眠分析结果 (可选)
                - stress_data: 压力分析结果 (可选) 
                - duration: 冥想时长分钟数 (默认10)
                - meditation_type: 指定冥想类型 (可选)
                - breathing_pattern: 呼吸模式 (可选)
        
        返回:
            dict: 冥想指导结果
        """
        sleep_data = data.get('sleep_data')
        stress_data = data.get('stress_data')
        duration = data.get('duration', 10)
        meditation_type = data.get('meditation_type')
        breathing_pattern = data.get('breathing_pattern', '4-7-8')
        
        try:
            # 生成冥想计划
            if meditation_type:
                # 使用指定类型
                if meditation_type not in self.meditation_types:
                    return {"error": "不支持的冥想类型", "available_types": list(self.meditation_types.keys())}
                plan = {
                    'meditation_type': meditation_type,
                    'type_name': self.meditation_types[meditation_type]['name'],
                    'description': self.meditation_types[meditation_type]['description'],
                    'duration_minutes': duration,
                    'benefits': self.meditation_types[meditation_type]['benefits'],
                    'guidance_sequence': self.guidance_phrases.get(meditation_type, self.guidance_phrases['breathing'])[:3],
                    'personalized_reason': f"用户指定了{self.meditation_types[meditation_type]['name']}冥想"
                }
            else:
                # 个性化生成
                plan = self.generate_meditation_plan(sleep_data, stress_data, duration)
            
            # 生成会话脚本
            session_script = self.create_session_script(plan)
            
            # 生成呼吸练习（如果需要）
            breathing_exercise = None
            if plan['meditation_type'] in ['breathing', 'stress_relief', 'sleep_prep']:
                breathing_exercise = self.generate_breathing_exercise(breathing_pattern)
            
            # 构建结果
            result = {
                "meditation_plan": plan,
                "session_script": session_script,
                "total_duration_minutes": plan['duration_minutes'],
                "recommended_frequency": self.get_recommended_frequency(sleep_data, stress_data),
                "breathing_exercise": breathing_exercise,
                "personalization_summary": {
                    "based_on_sleep_data": sleep_data is not None,
                    "based_on_stress_data": stress_data is not None,
                    "reason": plan['personalized_reason']
                }
            }
            
            return result
            
        except Exception as e:
            return {
                "error": "冥想指导生成失败",
                "exception": str(e),
                "fallback_plan": {
                    "meditation_type": "breathing",
                    "type_name": "呼吸练习",
                    "duration_minutes": 10,
                    "guidance": "专注于呼吸，吸气4秒，呼气6秒，重复10次"
                }
            }
    
    def get_recommended_frequency(self, sleep_data, stress_data):
        """推荐冥想频率"""
        if stress_data and stress_data.get('stress_level', 0.5) > 0.7:
            return "每天2-3次，每次5-10分钟"
        elif sleep_data and sleep_data.get('sleep_score', 75) < 70:
            return "睡前每天1次，每次10-15分钟"
        else:
            return "每天1次，每次10分钟"