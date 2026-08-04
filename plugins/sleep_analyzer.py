"""
睡眠分析插件 - 分析EDF睡眠数据
基于MNE-Python的睡眠阶段分析
"""

import numpy as np
from plugin_manager import BasePlugin, PluginInfo, PluginType

try:
    import mne
    MNE_AVAILABLE = True
except ImportError:
    MNE_AVAILABLE = False
    print("[WARN] MNE-Python未安装，睡眠分析功能受限")


class SleepAnalyzerPlugin(BasePlugin):
    """睡眠分析插件 - 分析EDF格式的睡眠数据"""
    
    def __init__(self):
        super().__init__()
        self.info = PluginInfo(
            name="睡眠分析",
            version="1.0.0",
            plugin_type=PluginType.DATA_ANALYSIS,
            description="EDF睡眠数据分析，包括睡眠阶段、质量和建议",
            author="眠小兔睡眠实验室"
        )
        
        # 睡眠阶段映射
        self.stage_mapping = {
            'Sleep stage W': '清醒',
            'Sleep stage 1': 'N1期',
            'Sleep stage 2': 'N2期',
            'Sleep stage 3': 'N3期',
            'Sleep stage 4': 'N4期',
            'Sleep stage R': 'REM期',
            'Sleep stage ?': '未评分'
        }
    
    def validate_edf_file(self, edf_path):
        """验证EDF文件"""
        import os
        
        if not os.path.exists(edf_path):
            return False, f"文件不存在: {edf_path}"
        
        if not edf_path.lower().endswith('.edf'):
            return False, "文件格式错误，需要EDF格式"
        
        if os.path.getsize(edf_path) < 1024:  # 小于1KB
            return False, "文件大小异常"
        
        return True, "文件验证通过"
    
    def analyze_sleep_structure(self, annotations):
        """分析睡眠结构"""
        if not annotations or len(annotations) == 0:
            return None
        
        stage_counts = {}
        stage_durations = {}
        total_duration = 0
        
        for desc, onset, duration in zip(annotations.description, annotations.onset, annotations.duration):
            stage_name = str(desc)
            stage_counts[stage_name] = stage_counts.get(stage_name, 0) + 1
            stage_durations[stage_name] = stage_durations.get(stage_name, 0) + duration
            total_duration += duration
        
        if total_duration == 0:
            return None
        
        # 计算百分比
        stage_percentages = {}
        for stage, duration in stage_durations.items():
            stage_percentages[stage] = duration / total_duration * 100
        
        return {
            "stage_counts": stage_counts,
            "stage_durations": stage_durations,
            "stage_percentages": stage_percentages,
            "total_duration_hours": total_duration / 3600,
            "total_segments": len(annotations)
        }
    
    def calculate_sleep_score(self, sleep_structure):
        """计算睡眠评分 (0-100)"""
        if not sleep_structure:
            return 65.0  # 默认中等分数
        
        percentages = sleep_structure["stage_percentages"]
        
        score = 70.0  # 基础分数
        
        # 1. REM期评分 (20-25%为理想)
        rem_percent = percentages.get('Sleep stage R', 0)
        if 20 <= rem_percent <= 25:
            score += 10
        elif 15 <= rem_percent < 20 or 25 < rem_percent <= 30:
            score += 5
        elif rem_percent < 10:
            score -= 10
        
        # 2. 深睡眠评分 (N3+N4期，15-25%为理想)
        deep_sleep = percentages.get('Sleep stage 3', 0) + percentages.get('Sleep stage 4', 0)
        if 15 <= deep_sleep <= 25:
            score += 10
        elif 10 <= deep_sleep < 15 or 25 < deep_sleep <= 30:
            score += 5
        elif deep_sleep < 5:
            score -= 10
        
        # 3. 清醒期评分 (<10%为理想)
        wake_percent = percentages.get('Sleep stage W', 0)
        if wake_percent < 10:
            score += 10
        elif wake_percent < 20:
            score += 5
        elif wake_percent > 30:
            score -= 15
        
        # 4. 睡眠效率评分
        total_sleep = 100 - wake_percent
        sleep_efficiency = total_sleep / 100
        
        if sleep_efficiency > 0.85:
            score += 10
        elif sleep_efficiency > 0.75:
            score += 5
        elif sleep_efficiency < 0.60:
            score -= 10
        
        # 确保分数在0-100之间
        return max(0, min(100, score))
    
    def get_sleep_recommendations(self, sleep_structure, sleep_score):
        """根据睡眠分析结果提供建议"""
        recommendations = []
        
        if not sleep_structure:
            recommendations.append("睡眠数据不足，建议收集完整夜间睡眠数据")
            return recommendations
        
        percentages = sleep_structure["stage_percentages"]
        
        # 1. REM期建议
        rem_percent = percentages.get('Sleep stage R', 0)
        if rem_percent < 15:
            recommendations.append("REM睡眠不足，建议保证7-8小时睡眠时间")
        elif rem_percent > 30:
            recommendations.append("REM睡眠过多，可能睡眠质量不佳")
        
        # 2. 深睡眠建议
        deep_sleep = percentages.get('Sleep stage 3', 0) + percentages.get('Sleep stage 4', 0)
        if deep_sleep < 10:
            recommendations.append("深睡眠不足，建议睡前避免咖啡因和电子设备")
        
        # 3. 清醒期建议
        wake_percent = percentages.get('Sleep stage W', 0)
        if wake_percent > 20:
            recommendations.append("夜间清醒时间过多，建议保持安静黑暗的睡眠环境")
        
        # 4. 基于总分建议
        if sleep_score >= 85:
            recommendations.append("睡眠质量优秀，继续保持良好作息习惯")
        elif sleep_score >= 70:
            recommendations.append("睡眠质量良好，注意保持规律作息")
        elif sleep_score >= 60:
            recommendations.append("睡眠质量一般，建议改善睡眠习惯")
        else:
            recommendations.append("睡眠质量需要关注，建议咨询睡眠专家")
        
        # 5. 通用建议
        recommendations.append("固定作息时间，每天同一时间睡觉和起床")
        recommendations.append("睡前1小时避免使用电子设备")
        recommendations.append("保持卧室黑暗、安静、凉爽")
        
        return recommendations[:5]  # 返回前5条建议
    
    def execute(self, data):
        """
        执行睡眠分析
        
        参数:
            data: 包含以下键的字典
                - edf_path: EDF文件路径 (必需)
                - hypnogram_path: 睡眠分期标注文件路径 (可选)
                - analysis_mode: 分析模式 ('basic'|'detailed') (可选)
        
        返回:
            dict: 睡眠分析结果
        """
        edf_path = data.get('edf_path')
        hypnogram_path = data.get('hypnogram_path')
        analysis_mode = data.get('analysis_mode', 'basic')
        
        # 验证输入
        if not edf_path:
            return {"error": "未提供EDF文件路径", "required": "edf_path"}
        
        # 验证文件
        valid, message = self.validate_edf_file(edf_path)
        if not valid:
            return {"error": "文件验证失败", "message": message}
        
        # 检查MNE是否可用
        if not MNE_AVAILABLE:
            return {
                "error": "依赖库未安装",
                "message": "需要安装MNE-Python: pip install mne",
                "simulated_result": self.get_simulated_result()
            }
        
        try:
            # 1. 读取PSG数据（抑制警告）
            import warnings
            warnings.filterwarnings('ignore', message='Highpass cutoff frequency')
            
            print(f"[SLEEP] 读取EDF文件: {edf_path}")
            raw = mne.io.read_raw_edf(edf_path, preload=False, verbose=False)
            
            # 2. 读取睡眠分期标注
            annotations = None
            if hypnogram_path:
                try:
                    annotations = mne.read_annotations(hypnogram_path)
                    print(f"[SLEEP] 读取睡眠分期标注: {len(annotations)}个时段")
                except Exception as e:
                    print(f"[WARN] 读取标注文件失败: {e}")
                    annotations = None
            
            # 3. 分析睡眠结构
            sleep_structure = self.analyze_sleep_structure(annotations)
            
            # 4. 计算睡眠评分
            sleep_score = self.calculate_sleep_score(sleep_structure)
            
            # 5. 获取建议
            recommendations = self.get_sleep_recommendations(sleep_structure, sleep_score)
            
            # 6. 构建结果
            result = {
                "sleep_score": float(sleep_score),
                "sleep_quality": self.get_quality_label(sleep_score),
                "recommendations": recommendations,
                "data_summary": {
                    "edf_file": edf_path,
                    "recording_duration_hours": raw.times[-1] / 3600 if hasattr(raw, 'times') else 0,
                    "channels": len(raw.ch_names) if hasattr(raw, 'ch_names') else 0,
                    "sampling_rate": raw.info['sfreq'] if hasattr(raw.info, 'sfreq') else 0,
                    "has_hypnogram": annotations is not None,
                    "hypnogram_segments": len(annotations) if annotations else 0
                }
            }
            
            # 7. 添加详细分析结果（如果可用）
            if sleep_structure and analysis_mode == 'detailed':
                result["detailed_analysis"] = {
                    "sleep_structure": sleep_structure,
                    "stage_distribution": self.format_stage_distribution(sleep_structure)
                }
            
            return result
            
        except Exception as e:
            return {
                "error": "睡眠分析过程中出现错误",
                "exception": str(e),
                "suggestion": "请检查EDF文件格式是否正确，或提供睡眠分期标注文件"
            }
    
    def get_simulated_result(self):
        """当MNE不可用时返回模拟结果"""
        return {
            "sleep_score": 75.0,
            "sleep_quality": "模拟分析 - 良好",
            "recommendations": [
                "安装MNE-Python以获得准确分析: pip install mne",
                "保持规律作息时间",
                "睡前避免咖啡因和电子设备"
            ],
            "data_summary": {
                "note": "模拟结果 - 需要安装MNE-Python",
                "simulation": True
            }
        }
    
    def get_quality_label(self, score):
        """根据分数返回质量标签"""
        if score >= 85:
            return "优秀"
        elif score >= 70:
            return "良好"
        elif score >= 60:
            return "一般"
        else:
            return "需要改善"
    
    def format_stage_distribution(self, sleep_structure):
        """格式化睡眠阶段分布"""
        if not sleep_structure:
            return {}
        
        formatted = {}
        percentages = sleep_structure["stage_percentages"]
        
        for stage_code, percentage in percentages.items():
            stage_name = self.stage_mapping.get(stage_code, stage_code)
            formatted[stage_name] = {
                "percentage": float(percentage),
                "duration_hours": sleep_structure["stage_durations"].get(stage_code, 0) / 3600,
                "segments": sleep_structure["stage_counts"].get(stage_code, 0)
            }
        
        return formatted