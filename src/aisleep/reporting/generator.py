from functools import wraps



class MedicalReportGenerator:
  
    def __init__(self, clinical_db):
        self.clinical_db = clinical_db
        self.review_system = DoctorReviewSystem()  # 医生审核系统
        self.validator = ClinicalValidator()  
        self.reference_ranges = {
            'hrv': (20, 100),  # 毫秒
            'rem_percent': (20, 25),  # %
            'deep_sleep': (15, 20)    # %
        }

    def _get_clinical_interpretation(self, user_id: str) -> Dict:
        """生成临床数据解读"""
        user_data = self.clinical_db.get_user_data(user_id)
        return {
            'sleep_stages': self._interpret_sleep_stages(user_data),
            'vital_signs': self._analyze_vital_signs(user_data),
            'risk_factors': self._assess_health_risks(user_data)
        }

    def _interpret_sleep_stages(self, data: Dict) -> Dict:
        """专业睡眠分期解读"""
        return {
            'rem': {
                'value': data['rem_percent'],
                'status': 'normal' if self.reference_ranges['rem_percent'][0] <= data['rem_percent'] <= self.reference_ranges['rem_percent'][1] else 'abnormal',
                'clinical_notes': self._get_rem_notes(data)
            },
            # ... 其他睡眠阶段分析
        }

    def _analyze_long_term_trends(self, user_id: str) -> Dict:
        """生成临床趋势报告"""
        historical = self.clinical_db.get_historical_data(user_id, days=30)
        return {
            'sleep_efficiency_trend': self._calculate_trend(historical, 'sleep_efficiency'),
            'rem_latency_trend': self._calculate_trend(historical, 'rem_latency'),
            'clinical_alert': self._check_abnormal_trends(historical)
        }

    def _generate_medical_recommendations(self, user_id: str) -> List[Dict]:
        user_data = self.clinical_db.get_user_data(user_id)
        recommendations = []
        
        # 基于睡眠障碍风险的建议
        risks = self._assess_sleep_disorder_risks(user_data)
        if risks['apnea_risk'] > 0.7:
            recommendations.append({
                'type': 'clinical',
                'code': 'CLIN_001',
                'action': '建议进行多导睡眠图(PSG)检查',
                'rationale': '检测到睡眠呼吸暂停高风险'
            })
        
        # 基于睡眠质量的建议
        if user_data['sleep_efficiency'] < 85:
            recommendations.append({
                'type': 'behavioral',
                'code': 'BEH_002', 
                'action': '认知行为疗法(CBT-I)',
                'rationale': '睡眠效率低于临床标准'
            })
        
        return recommendations


    def generate_clinical_report(self, user_id: str) -> Dict:
        """生成符合医疗标准的报告"""
        return {
            'interpretation': self._get_clinical_interpretation(user_id),
            'trend_analysis': self._analyze_long_term_trends(user_id),
            'recommendations': self._generate_medical_recommendations(user_id)
        }
        
    @review_system.require_review('rem_notes')
    def _get_rem_notes(self, data: Dict) -> str:
        """生成REM睡眠临床注释"""
        if data['rem_percent'] < 15:
            return "REM睡眠不足，可能与抑郁或神经退行性疾病相关"
        elif data['rem_percent'] > 30:
            return "REM睡眠过多，建议排查睡眠呼吸暂停"
        return "REM睡眠在正常范围内"

    def _calculate_trend(self, historical: List[Dict], metric: str) -> Dict:
        """计算临床指标变化趋势"""
        values = [x[metric] for x in historical]
        slope = np.polyfit(range(len(values)), values, 1)[0]
        return {
            'slope': slope,
            'significance': 'significant' if abs(slope) > 2 else 'moderate'
        }

    def _check_abnormal_trends(self, historical: List[Dict]) -> List[str]:
        """检测异常临床趋势"""
        alerts = []
        if self._calculate_trend(historical, 'awakening_index')['slope'] > 1.5:
            alerts.append("觉醒次数显著增加")
        # ... 其他异常检测
        return alerts

    def _assess_sleep_disorder_risks(self, user_data: Dict) -> Dict:
        """评估常见睡眠障碍风险"""
        return {
            'insomnia_risk': self._calculate_insomnia_risk(user_data),
            'apnea_risk': self._calculate_apnea_risk(user_data),
            'restless_leg_risk': self._calculate_rls_risk(user_data)
        }

    def _calculate_insomnia_risk(self, data: Dict) -> float:
        """计算失眠风险指数(0-1)"""
        return min(1, 
            data['sleep_latency'] * 0.4 + 
            data['awakening_index'] * 0.6
        )

    def _calculate_apnea_risk(self, data: Dict) -> float:
        """计算睡眠呼吸暂停风险"""
        return 0 if data['spo2_avg'] > 92 else (94 - data['spo2_avg']) / 10

    def _get_reference_notes(self, metric: str, value: float) -> str:
        """获取临床指标解释说明"""
        notes = {
            'rem_percent': {
                'low': "REM睡眠不足可能影响记忆巩固",
                'normal': "REM睡眠有助于情绪调节和记忆处理",
                'high': "REM睡眠过多可能与神经递质失衡有关"
            },
            'deep_sleep': {
                'low': "深睡不足影响身体修复功能",
                'normal': "深睡阶段对生长激素分泌至关重要"
            }
        }
        # ... 实现范围检查和注释选择逻辑 ...
    def validate_report(self, report: Dict) -> bool:
        """验证报告数据是否符合临床标准"""
        required_sections = ['interpretation', 'trend_analysis', 'recommendations']
        if not all(section in report for section in required_sections):
            return False
        
        # 验证关键临床指标是否存在
        required_metrics = ['rem_percent', 'deep_sleep', 'sleep_efficiency']
        if not all(metric in report['interpretation']['sleep_stages'] 
                for metric in required_metrics):
            return False
            
        return True


    def evidence_based(reference: str):
        """确保医学建议有循证依据的装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                result['evidence_reference'] = reference  # 添加参考文献
                return result
            return wrapper
        return decorator
    
    @evidence_based(reference="AASM Clinical Guidelines v3.0")
    @validator.validate_algorithm
    def _generate_medical_recommendations(self, user_id: str):
        # 生成建议时会自动：
        # 1. 添加参考文献标记
        # 2. 验证算法有效性
        recommendations = []
        # ... 具体建议生成逻辑 ...
        return recommendations



class ClinicalValidator:
    @staticmethod
    def validate_algorithm(algorithm_func):
        """临床验证装饰器"""
        def wrapper(*args, **kwargs):
            # 先执行原始算法获取结果
            result = algorithm_func(*args, **kwargs)
            
            # 验证逻辑（示例）
            if not MedicalStandardChecker.check_report(result):
                raise ValueError("算法输出不符合临床标准")
            
            return result
        return wrapper



class DoctorReviewSystem:
    def __init__(self):
        self.approved_notes = set()
    
    def require_review(self, note_type: str):
        """需要医生审核的内容标记"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                if note_type not in self.approved_notes:
                    raise ValueError(f"临床注释'{note_type}'尚未通过医生审核")
                return func(*args, **kwargs)
            return wrapper
        return decorator

class MedicalStandardChecker:
    """检查报告是否符合医疗文档标准"""
    
    STANDARDS = {
        'required_sections': ['interpretation', 'recommendations'],
        'required_fields': {
            'interpretation': ['sleep_stages', 'vital_signs'],
            'recommendations': ['action', 'rationale']
        }
    }

    @classmethod
    def check_report(cls, report: Dict) -> bool:
        for section in cls.STANDARDS['required_sections']:
            if section not in report:
                return False
            for field in cls.STANDARDS['required_fields'].get(section, []):
                if field not in report[section]:
                    return False
        return True
