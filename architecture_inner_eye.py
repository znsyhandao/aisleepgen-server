"""
architecture_inner_eye.py — 架构内省引擎 + 极致睡眠评分

在 deepseek_proxy.py 内部运行，每次自学习时顺便做架构健康评估。
不是"架构师AI"，是结构化的架构度量系统。

核心假设：架构不好的时候，可观测的指标会出问题。

极致睡眠评分: 基于压力-睡眠回归模型，告诉用户"在同压力水平下，
你的睡眠比XX%的人好/差"。
"""

import json, os, math, random
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# 架构健康阈值
ARCH_THRESHOLDS = {
    'file_monolith': {  # deepseek_proxy.py 单文件过大
        'warning': 3000,    # 3000行警告
        'critical': 5000,   # 5000行危险
    },
    'response_stall': {  # 用户评分持续下降
        'trend_window': 10,
        'decline_threshold': -0.3,  # 最近10条 vs 之前10条 平均分下降超过30%
    },
    'expert_diversity': {  # 7专家意见差异度
        'min_variance': 0.01,  # 方差低于此说明专家趋同
        'max_variance': 0.20,  # 方差高于此说明专家分歧过大
    },
    'pref_stagnation': {  # 偏好学习停止变化
        'stale_days': 14,  # 14天没有新偏好类别
    },
    'data_growth': {  # 用户数据增长率
        'stall_days': 7,  # 7天用户数量没增长
    },
}


def measure_system_pulse() -> Dict:
    """采集系统健康的可观测指标（不依赖外部、不阻塞）"""
    pulse = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'metrics': {},
        'alerts': [],
        'recommendations': [],
    }
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. 文件尺寸内省
    proxy_path = os.path.join(base_dir, 'deepseek_proxy.py')
    if os.path.exists(proxy_path):
        with open(proxy_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        line_count = len(lines)
        pulse['metrics']['proxy_lines'] = line_count
        if line_count > ARCH_THRESHOLDS['file_monolith']['critical']:
            pulse['alerts'].append(f'🔴 单文件{line_count}行（临界{ARCH_THRESHOLDS["file_monolith"]["critical"]}行）→ 建议拆分: core_logic.py, handlers.py, self_learn.py')
        elif line_count > ARCH_THRESHOLDS['file_monolith']['warning']:
            pulse['alerts'].append(f'🟡 单文件{line_count}行（警告{ARCH_THRESHOLDS["file_monolith"]["warning"]}行）→ 考虑拆分')
    
    # 2. 用户评分趋势（从calibration读取）
    cal_path = os.path.join(base_dir, 'data', 'calibration.json')
    cal = {}
    if os.path.exists(cal_path):
        with open(cal_path, 'r', encoding='utf-8') as f:
            cal = json.load(f)
        pulse['metrics']['learn_mode'] = cal.get('_learn_mode', 'heuristic')
        pulse['metrics']['avg_rating'] = cal.get('avg_user_rating')
        pulse['metrics']['samples'] = cal.get('samples', 0)
        pulse['metrics']['happy_ratio'] = cal.get('happy_ratio')
        if cal.get('_regression_score') is not None:
            pulse['metrics']['regression_r2'] = cal['_regression_score']
            if cal['_regression_score'] < 0.05 and cal['_regression_score'] >= 0:
                pulse['alerts'].append(f'🟡 回归R²={cal["_regression_score"]:.3f} → 特征工程不足，需增加特征维度')
    
    # 3. 反馈趋势
    fb_path = os.path.join(base_dir, 'data', 'feedback.json')
    if os.path.exists(fb_path):
        with open(fb_path, 'r', encoding='utf-8') as f:
            feedbacks = json.load(f)
        scored_fb = [fb for fb in feedbacks if fb.get('rating', 0) > 0]
        pulse['metrics']['total_feedback'] = len(scored_fb)
        
        if len(scored_fb) >= 20:
            # 比较前后半段评分
            mid = len(scored_fb) // 2
            first_half = sum(fb['rating'] for fb in scored_fb[:mid]) / mid
            second_half = sum(fb['rating'] for fb in scored_fb[mid:]) / (len(scored_fb) - mid)
            pulse['metrics']['rating_trend'] = round(second_half - first_half, 2)
            
            if second_half < first_half * (1 - abs(ARCH_THRESHOLDS['response_stall']['decline_threshold'])):
                pulse['alerts'].append(f'🔴 评分持续下降: {first_half:.1f}→{second_half:.1f} → 建议检查世界模型版本退化')
            elif second_half < first_half * 0.85:
                pulse['alerts'].append(f'🟡 评分轻微下降: {first_half:.1f}→{second_half:.1f} → 关注趋势')
    
    # 4. 专家分化度（从最新profile的experts提取）
    # 跳过——profile读取太贵，不在此处做
    # 改为从calibration的 _last_pref_scan 推断
    pref_scan = cal.get('_last_pref_scan', {})
    if pref_scan:
        sat = pref_scan.get('satisfied_sample', 0)
        dis = pref_scan.get('dissatisfied_sample', 0)
        total_scan = sat + dis
        if total_scan > 0:
            dis_ratio = dis / total_scan
            pulse['metrics']['dissatisfied_ratio'] = round(dis_ratio, 3)
            if dis_ratio > 0.6:
                pulse['alerts'].append(f'🔴 不满意用户占比{dis_ratio:.0%} → 系统性偏差，需回归分析评审')
    
    # 5. 偏好停滞检测
    pref_path = os.path.join(base_dir, 'user_preferences.json')
    if os.path.exists(pref_path):
        with open(pref_path, 'r', encoding='utf-8') as f:
            pref = json.load(f)
        cats = pref.get('categories', {})
        pulse['metrics']['pref_categories'] = len(cats)
        last_update = pref.get('updated_at', '')
        if last_update:
            try:
                last_dt = datetime.strptime(last_update, '%Y-%m-%d %H:%M')
                days_since = (datetime.now() - last_dt).days
                pulse['metrics']['pref_stale_days'] = days_since
                if days_since > ARCH_THRESHOLDS['pref_stagnation']['stale_days']:
                    pulse['alerts'].append(f'🟡 偏好学习{days_since}天未更新 → 建议检查DeepSeek调用是否正常')
            except: pass
    
    # 6. 整体健康评分
    health_score = _compute_health_score(pulse)
    pulse['health_score'] = health_score
    pulse['health_label'] = _health_label(health_score)
    
    # 7. 架构建议（基于综合判断）
    if health_score < 60:
        pulse['recommendations'].append('建议安排架构评审，当前健康度偏低')
    if pulse['metrics'].get('proxy_lines', 0) > 4000:
        pulse['recommendations'].append(f'拆分deepseek_proxy.py: handlers.py(API处理) + self_learn.py(自学习) + inner_eye.py(内省)')
    if 'regression_r2' in pulse['metrics'] and pulse['metrics']['regression_r2'] < 0.1:
        pulse['recommendations'].append('回归R²<0.1: 在feedback保存时补充 sleep_latency, awake_times, pain_flag 字段')
    if pulse['metrics'].get('total_feedback', 0) > 200 and pulse['metrics'].get('regression_r2', 1) < 0.1:
        pulse['recommendations'].append('数据量已>200条但R²低: 考虑改用随机森林或XGBoost')
    
    return pulse


def _compute_health_score(pulse: Dict) -> int:
    """0-100 健康评分"""
    score = 100
    alerts = pulse.get('alerts', [])
    deduction = min(len(alerts) * 15, 60)  # 每个告警扣15分，最多扣60
    score -= deduction
    # 扣分不归零
    return max(10, score)


def _health_label(score: int) -> str:
    if score >= 80:
        return '✅ 健康'
    elif score >= 60:
        return '🟡 需关注'
    else:
        return '🔴 需干预'


def report_to_calibration(pulse: Dict):
    """将架构健康报告写入calibration.json"""
    cal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calibration.json')
    try:
        cal = {}
        if os.path.exists(cal_path):
            with open(cal_path, 'r', encoding='utf-8') as f:
                cal = json.load(f)
        cal['_arch_report'] = {
            'timestamp': pulse['timestamp'],
            'health': pulse['health_score'],
            'label': pulse['health_label'],
            'alerts': pulse['alerts'],
            'recommendations': pulse['recommendations'][:3],  # 最多3条
            'metrics': pulse['metrics'],
        }
        # 极致评分基准快照
        cal['_extreme_benchmarks'] = {
            str(k): v for k, v in _PRESSURE_BENCHMARKS.items()
        }
        with open(cal_path, 'w', encoding='utf-8') as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)
    except:
        pass


if __name__ == '__main__':
    pulse = measure_system_pulse()
    print(f'健康评分: {pulse["health_score"]}/100 ({pulse["health_label"]})')
    for a in pulse['alerts']:
        print(f'  {a}')
    for r in pulse['recommendations']:
        print(f'  💡 {r}')
    print(f'\n指标:')
    for k, v in pulse['metrics'].items():
        print(f'  {k}: {v}')


# ===== 🌟 极致睡眠评分模块 =====
# 基于群体数据的压力分层睡眠百分位计算

# 压力5级各睡眠时长分布的参考基准（分钟，群体数据模拟）
# 数据来源：NSF 2022 + 模拟校准
_PRESSURE_BENCHMARKS = {
    1: {'mean': 465, 'std': 45, 'label': '轻松'},    # 低压力平均7h45m
    2: {'mean': 450, 'std': 50, 'label': '微压'},
    3: {'mean': 420, 'std': 55, 'label': '适中'},
    4: {'mean': 390, 'std': 60, 'label': '高压'},
    5: {'mean': 360, 'std': 65, 'label': '极压'},
}
_PRESSURE_LATENCY_BENCHMARKS = {
    1: {'mean': 15, 'std': 8, 'label': '轻松入睡'},
    2: {'mean': 20, 'std': 10, 'label': '微延迟'},
    3: {'mean': 30, 'std': 15, 'label': '中度延迟'},
    4: {'mean': 45, 'std': 20, 'label': '难入睡'},
    5: {'mean': 60, 'std': 25, 'label': '严重失眠'},
}


def compute_sleep_percentile(user_data: Dict) -> Optional[Dict]:
    """
    计算用户的睡眠在同压力水平下的百分位排名
    
    Args:
        user_data: 包含 sleep_latency, total_duration, stress_level 的字典
    
    Returns:
        {
            'duration_percentile': 0-100,  // 睡眠时长比XX%的人好
            'latency_percentile': 0-100,   // 入睡速度比XX%的人好  
            'composite_score': 0-100,      // 综合评分
            'grade': 'S/A/B/C/D'           // 评级
        }
    """
    stress = user_data.get('stress_level', 3)
    duration = user_data.get('total_duration', 420)
    latency = user_data.get('sleep_latency', 30)
    
    # 标准化为1-5级
    stress = max(1, min(5, int(stress)))
    
    bench_dur = _PRESSURE_BENCHMARKS.get(stress, _PRESSURE_BENCHMARKS[3])
    bench_lat = _PRESSURE_LATENCY_BENCHMARKS.get(stress, _PRESSURE_LATENCY_BENCHMARKS[3])
    
    # 模拟正态分布百分位（简化的z-score → 百分位映射）
    def _z_to_percentile(z):
        """标准正态CDF近似"""
        return max(1, min(99, round(50 + z * 21.06)))
    
    # 时长：越长越好
    dur_z = (duration - bench_dur['mean']) / bench_dur['std']
    dur_pct = _z_to_percentile(dur_z)
    
    # 入睡潜伏期：越短越好
    lat_z = (bench_lat['mean'] - latency) / bench_lat['std']
    lat_pct = _z_to_percentile(lat_z)
    
    # 综合评分（加权）
    composite = round(dur_pct * 0.5 + lat_pct * 0.5)
    
    # 评级
    if composite >= 90:
        grade = 'S'
    elif composite >= 75:
        grade = 'A'
    elif composite >= 55:
        grade = 'B'
    elif composite >= 30:
        grade = 'C'
    else:
        grade = 'D'
    
    return {
        'duration_percentile': dur_pct,
        'latency_percentile': lat_pct,
        'composite_score': composite,
        'grade': grade,
        'benchmark_group': f'压力{stress}级人群',
    }


def make_extreme_bedtime_context(user_data: Dict) -> str:
    """
    生成供DeepSeek注入的极致睡眠上下文
    
    示例输出:
    "【极致评分】你的睡眠在同压力水平(3级)下超过65%的用户(B级)"
    """
    result = compute_sleep_percentile(user_data)
    if not result:
        return ''
    
    grade_icons = {'S': '🏆', 'A': '🌟', 'B': '✅', 'C': '📈', 'D': '💪'}
    icon = grade_icons.get(result['grade'], '❓')
    
    return (
        f"【极致评分】睡眠在{result['benchmark_group']}中超过{result['composite_score']}%的用户"
        f"({icon}{result['grade']}级, "
        f"时长优于{result['duration_percentile']}%, "
        f"入睡优于{result['latency_percentile']}%)"
    )
