"""
世界模型 v3.1 — 差异化深化
专注 DeepSeek 不可能做到的事情
基于 v2.1 的6专家会诊扩展
"""

import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ============================================================
# 模块1：场景分类器 — 识别用户当前处在什么阶段
# DeepSeek 不会主动做这个，它只是被动响应
# ============================================================

SCENE_PATTERNS = {
    'first_visit': {
        'triggers': ['第一次', '新用户', '初次', '刚来', '开始用'],
        'keywords': [],
        'desc': '新用户首次使用',
        'action': '做完整首评建立基线'
    },
    'daily_checkin': {
        'triggers': ['昨晚', '昨天', '凌晨', '睡了'],
        'keywords': ['昨晚', '昨天', '睡了', '醒', '入睡'],
        'desc': '日常睡眠打卡',
        'action': '提取数据加入趋势'
    },
    'problem_consult': {
        'triggers': ['怎么办', '为什么', '怎么', '改善', '解决'],
        'keywords': ['失眠', '睡不着', '早醒', '多梦', '打鼾'],
        'desc': '具体问题咨询',
        'action': '深度分析+具体方案'
    },
    'report_request': {
        'triggers': ['报告', '评估', '分析', '总结'],
        'keywords': ['报告', '评估'],
        'desc': '请求生成报告',
        'action': '调用报告生成'
    },
    'correction': {
        'triggers': ['记错', '不是', '不对', '纠正', '其实', '说错了'],
        'keywords': [],
        'desc': '用户纠正之前的记录',
        'action': '标记修正+更新画像'
    },
    'emotional_support': {
        'triggers': ['压力', '焦虑', '烦躁', '担心', '害怕', '累', '崩溃'],
        'keywords': ['压力', '焦虑', '烦躁', '崩溃', '好累'],
        'desc': '情绪宣泄/减压需求',
        'action': '先共情减压再分析'
    },
}

def classify_scene(user_message: str) -> Dict:
    """分类用户当前场景"""
    for scene, config in SCENE_PATTERNS.items():
        # 触发器匹配（优先）
        for t in config['triggers']:
            if t in user_message:
                return {
                    'scene': scene,
                    'confidence': 0.8,
                    'action': config['action'],
                    'desc': config['desc']
                }
        # 关键词匹配
        for k in config['keywords']:
            if k in user_message:
                # 避免首次匹配的关键词被后续覆盖
                if scene not in ['first_visit']:
                    return {
                        'scene': scene,
                        'confidence': 0.6,
                        'action': config['action'],
                        'desc': config['desc']
                    }
    
    return {'scene': 'general', 'confidence': 0.3, 'action': 'general_reply', 'desc': '普通对话'}


# ============================================================
# 模块2：个人化策略记忆 — 记住用户的偏好/习惯
# DeepSeek 每次对话都是独立的，记不住用户的个人策略
# ============================================================


# ============================================================
# 模块2：偏好学习系统 — 真正的个性化
# DeepSeek做不到：跨对话学习用户偏好，自动调整策略
# ============================================================

class PreferenceLearning:
    """偏好学习系统 — 跟踪什么策略有效、用户偏好什么方式"""
    
    # 干预策略分类
    STRATEGY_CATEGORIES = {
        'relaxation': ['冥想', '正念', '呼吸', '放松', '白噪音', '轻音乐', '渐进式肌肉放松'],
        'routine': ['固定作息', '定时', '规律', '生物钟', '固定时间'],
        'environment': ['卧室', '温度', '光线', '噪音', '遮光', '床垫', '枕头'],
        'diet': ['咖啡', '茶', '晚餐', '宵夜', '饮食', '喝酒', '酒', '奶茶', '咖啡因', '褪黑素'],
        'exercise': ['运动', '跑步', '散步', '瑜伽', '健身', '锻炼', '太极', '拉伸'],
        'cognitive': ['认知', '想法', '担忧', '焦虑', 'CBT', '认知行为', '日记'],
        'sleep_hygiene': ['睡', '就寝', '起床', '午睡', '补觉', '熬夜'],
        'medication': ['药', '安眠', '处方', '医生', '就医', '诊断'],
    }
    
    def __init__(self):
        self.preferences = {
            'preferred_categories': [],       # 用户偏好哪些方式
            'rejected_categories': [],        # 用户不喜欢哪些方式
            'known_methods': {},              # {方法名: 尝试次数}
            'effective_methods': {},          # {方法名: 有效次数}
            'ineffective_methods': {},        # {方法名: 无效次数}
            'user_said': [],                  # 用户对每种策略的原话
            'last_updated': '',
        }
    
    def learn_from_history(self, profile_history: List[Dict]) -> Dict:
        """从对话历史中学习用户偏好"""
        pref = dict(self.preferences)
        pref['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        category_count = {}
        category_reject = {}
        method_effect = {}
        
        for entry in profile_history:
            user_said = entry.get('user_said', '')
            content = str(user_said)
            entry_type = entry.get('type', 'normal')
            
            # 检测方法试过
            for cat, keywords in self.STRATEGY_CATEGORIES.items():
                for kw in keywords:
                    if kw in content:
                        # 试过这个方法
                        method_key = f'{cat}:{kw}'
                        if method_key not in method_effect:
                            method_effect[method_key] = {'tried': 0, 'effective': 0, 'ineffective': 0}
                        method_effect[method_key]['tried'] += 1
                        
                        if cat not in category_count:
                            category_count[cat] = 0
                        category_count[cat] += 1
            
            # 检测纠正/拒绝信号
            reject_signals = ['没用', '不行', '没效果', '不喜欢', '不想', '不要', '试过', '不好', '坚持不了']
            for signal in reject_signals:
                if signal in content:
                    for cat, keywords in self.STRATEGY_CATEGORIES.items():
                        for kw in keywords:
                            if kw in content:
                                if cat not in category_reject:
                                    category_reject[cat] = 0
                                category_reject[cat] += 1
            
            # 检测"有效"信号
            effective_signals = ['好了', '有效', '改善了', '好多了', '不错', '有改善', '有用']
            for signal in effective_signals:
                if signal in content:
                    # 找到关联的方法
                    for cat, keywords in self.STRATEGY_CATEGORIES.items():
                        for kw in keywords:
                            if kw in pref.get('last_context', ''):
                                method_key = f'{cat}:{kw}'
                                if method_key in method_effect:
                                    method_effect[method_key]['effective'] += 1
            
            # 保存用户原话
            pref['user_said'].append({
                'content': content[:80],
                'type': entry_type,
                'date': entry.get('date', '')
            })
        
        # 汇总偏好
        for cat in self.STRATEGY_CATEGORIES:
            tried = category_count.get(cat, 0)
            rejected = category_reject.get(cat, 0)
            
            if rejected >= 2:
                pref['rejected_categories'].append(cat)
            elif tried >= 1:
                pref['preferred_categories'].append(cat)
        
        # 汇总方法效果
        pref['known_methods'] = {k: v['tried'] for k, v in method_effect.items()}
        pref['effective_methods'] = {k: v['effective'] for k, v in method_effect.items() if v['effective'] > 0}
        pref['ineffective_methods'] = {k: v['ineffective'] for k, v in method_effect.items() if v['ineffective'] > 0}
        
        return pref
    
    def build_context(self, preferences: Dict) -> str:
        """构建偏好上下文注入prompt"""
        if not preferences or not preferences.get('known_methods'):
            return ''
        
        lines = []
        lines.append('【用户偏好分析】')
        
        # 已拒绝的策略
        if preferences.get('rejected_categories'):
            cat_names = {'relaxation': '放松类', 'routine': '作息类', 'environment': '环境类',
                        'diet': '饮食类', 'exercise': '运动类', 'cognitive': '认知类',
                        'sleep_hygiene': '睡眠卫生类', 'medication': '药物类'}
            rejected = [cat_names.get(c, c) for c in preferences['rejected_categories']]
            lines.append(f'  用户已表示无效/不喜欢的策略方向: {", ".join(rejected)}')
            lines.append(f'  建议: 下次不要再推荐这些方向')
        
        # 有效策略
        if preferences.get('effective_methods'):
            effective = list(preferences['effective_methods'].keys())[:3]
            lines.append(f'  曾被报告有效的具体方法: {", ".join(effective)}')
            lines.append(f'  建议: 可以进一步追问效果')
        
        # 已尝试方法统计
        tried = preferences.get('known_methods', {})
        if tried:
            top = sorted(tried.items(), key=lambda x: -x[1])[:5]
            lines.append(f'  用户尝试最多的策略:')
            for method, count in top:
                lines.append(f'    - {method} (提到{count}次)')
        
        # 整体建议
        if preferences.get('rejected_categories'):
            lines.append('  警告: 不要推荐已被用户否定过的方法')
        
        return '\n'.join(lines) + '\n'
def vertical_comparison(profile: Dict) -> Dict:
    """纵向对比 — 今天 vs 昨天 vs 上周"""
    from datetime import datetime, timedelta
    
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    last_week = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    history = profile.get('history', [])
    
    # 找指定日期的记录
    today_entry = None
    yesterday_entry = None
    week_entries = []
    
    for e in history:
        d = e.get('date', '')
        if d == today:
            today_entry = e
        elif d == yesterday:
            yesterday_entry = e
        elif d >= last_week:
            week_entries.append(e)
    
    if not today_entry and not yesterday_entry:
        return {}
    
    def _get_score(e):
        return e.get('wm_score', 0) or 0
    
    comparison = {
        'today_score': _get_score(today_entry) if today_entry else None,
        'yesterday_score': _get_score(yesterday_entry) if yesterday_entry else None,
        'week_avg': None,
        'trend': 'stable'
    }
    
    if week_entries:
        week_scores = [_get_score(e) for e in week_entries if _get_score(e) > 0]
        if week_scores:
            comparison['week_avg'] = round(sum(week_scores) / len(week_scores), 1)
    
    # 趋势判断
    scores = []
    dates = []
    for e in history:
        sc = _get_score(e)
        if sc > 0:
            scores.append(sc)
            dates.append(e.get('date', ''))
    
    if len(scores) >= 3:
        # 简单线性趋势
        import math
        n = len(scores)
        x_avg = (n - 1) / 2
        y_avg = sum(scores) / n
        num = sum((i - x_avg) * (s - y_avg) for i, s in enumerate(scores))
        den = sum((i - x_avg) ** 2 for i in range(n))
        slope = num / den if den > 0 else 0
        
        if slope > 2: comparison['trend'] = 'improving'
        elif slope < -2: comparison['trend'] = 'declining'
        else: comparison['trend'] = 'stable'
    
    return comparison


if __name__ == '__main__':
    # 测试场景分类
    tests = [
        "昨晚11点睡6点醒，中间醒了一次",
        "我最近压力好大，睡不着怎么办",
        "怎么才能快速入睡",
        "给我做一次睡眠评估",
        "你记错了，我上次说的是腰疼",
        "感觉好累不想动",
    ]
    for t in tests:
        result = classify_scene(t)
        print(f"  {t[:20]:20s} -> {result['scene']:15s} conf={result['confidence']}")
    
    print("\n")
    s = StrategyMemory()
    dialog = [{'content': '我平时不喝咖啡', 'date': 'today'}, {'content': '晚上会去跑步', 'date': 'today'}]
    strategies = s.extract_strategies(dialog)
    print(s.build_context(strategies))


# ============================================================
# 模块5：生理恢复深度分析 — DeepSeek 做不到的部分
# 基于睡眠时长和结构的生理恢复量化
# ============================================================

class PhysiologicalRecovery:
    """生理恢复分析 — 这是纯大模型做不到的量化维度"""
    
    GLYMPHATIC_BASE_RATE = 0.6
    N3_CYCLE_LENGTH = 90
    N3_CLEARANCE_MULTIPLIER = 2.5
    
    def analyze_recovery(self, data):
        """生理恢复量化分析"""
        total_dur = data.get('total_duration', 450)
        sleep_latency = data.get('sleep_latency', 15)
        awake_times = data.get('awake_times', 0)
        wake_dur = data.get('awake_duration', 0)
        wake_str = data.get('wake_time', '')
        pain = data.get('pain')
        
        result = {}
        result['glymphatic'] = self._calc_glymphatic(total_dur, awake_times, wake_dur)
        result['growth_hormone'] = self._calc_growth_hormone(total_dur, sleep_latency, awake_times)
        result['cortisol'] = self._calc_cortisol_response(wake_str)
        
        recovery_score = (
            result['glymphatic']['score'] * 0.4 +
            result['growth_hormone']['score'] * 0.35 +
            result['cortisol']['score'] * 0.25
        )
        result['overall_recovery'] = round(max(0, min(100, recovery_score)), 1)
        result['pain_impact'] = self._calc_pain_impact(pain, total_dur)
        
        return result
    
    def _calc_glymphatic(self, total_dur, awake_times, wake_dur):
        effective_sleep = max(0, total_dur - wake_dur)
        n3_cycles = effective_sleep / self.N3_CYCLE_LENGTH
        base_clearance = self.GLYMPHATIC_BASE_RATE
        
        if effective_sleep >= 420:
            base_clearance *= 1.3
        elif effective_sleep >= 360:
            base_clearance *= 1.1
        elif effective_sleep < 300:
            base_clearance *= 0.5
        
        if awake_times >= 3:
            base_clearance *= (1 - 0.12 * awake_times)
        elif awake_times >= 2:
            base_clearance *= 0.88
        
        if n3_cycles < 3:
            base_clearance *= max(0.3, n3_cycles / 4)
        
        clearance_pct = max(0, min(100, base_clearance * 100))
        
        findings = []
        if clearance_pct < 40:
            findings.append(f"估算糖蛋白清除效率仅{clearance_pct:.0f}%, 基于睡眠时长和中断次数")
        elif clearance_pct < 65:
            findings.append(f"估算糖蛋白清除效率{clearance_pct:.0f}%, 低于理想值")
        else:
            findings.append(f"估算糖蛋白清除效率{clearance_pct:.0f}%, 属正常范围")
        
        return {'score': max(0, clearance_pct), 'efficiency': round(base_clearance, 2), 'n3_cycles': round(n3_cycles, 1), 'findings': findings}
    
    def _calc_growth_hormone(self, total_dur, sleep_latency, awake_times):
        potential_pulses = total_dur / 90.0
        first_pulse_loss = max(0, sleep_latency - 15) / 90.0
        effective_pulses = max(0, potential_pulses - first_pulse_loss)
        
        if awake_times > 2:
            effective_pulses *= (1 - 0.1 * awake_times)
        
        gh_score = min(100, effective_pulses / 5 * 100)
        
        findings = []
        if gh_score < 40:
            findings.append(f"估算生长激素分泌评分{gh_score:.0f}%, 基于睡眠参数")
        elif gh_score < 65:
            findings.append(f"估算生长激素分泌评分{gh_score:.0f}%, 中等水平")
        else:
            findings.append(f"估算生长激素分泌评分{gh_score:.0f}%, 修复功能正常")
        
        return {'score': max(0, gh_score), 'pulses': round(effective_pulses, 1), 'findings': findings}
    
    def _calc_cortisol_response(self, wake_str):
        if not wake_str:
            return {'score': 70, 'findings': ['起床时间未知, 皮质醇节律估算受限'], 'deviation': 0}
        try:
            wake_hour = int(wake_str.split(':')[0])
            wake_min = int(wake_str.split(':')[1])
            wake_decimal = wake_hour + wake_min / 60
        except:
            return {'score': 70, 'findings': ['起床时间无效, 皮质醇节律无法估算'], 'deviation': 0}
        
        deviation = abs(wake_decimal - 6.5)
        
        if deviation <= 0.5:
            cortisol_score = 90
            findings = ["估算皮质醇觉醒反应正常, 起床时间在6:00-7:00窗口"]
        elif deviation <= 1.5:
            cortisol_score = max(50, 90 - deviation * 20)
            findings = [f"估算起床时间偏差{deviation:.1f}h, 皮质醇节律轻度偏移"]
        else:
            cortisol_score = max(20, 90 - deviation * 25)
            findings = [f"估算起床时间偏差{deviation:.1f}h, 皮质醇节律明显偏移"]
        
        return {'score': cortisol_score, 'deviation': round(deviation, 2), 'findings': findings}
    
    def _calc_pain_impact(self, pain, total_dur):
        if not pain:
            return {'level': 'none', 'impact': 0, 'description': '无疼痛影响'}
        return {'level': 'medium', 'impact': 15, 'description': f'疼痛可能影响恢复质量, 建议关注'}


# ============================================================
# 模块6：就医决策支持 — DeepSeek 不会主动做决策树
# ============================================================

class MedicalReferral:
    """就医建议决策树"""
    
    def assess(self, data, profile):
        history = profile.get('history', [])
        total_dur = data.get('total_duration', 450)
        sleep_latency = data.get('sleep_latency', 15)
        awake_times = data.get('awake_times', 0)
        snore = data.get('snore_related', False)
        feels = data.get('feeling', 'ok')
        pain = data.get('pain')
        
        reasons = []
        urgency = 'routine'
        
        chronic_count = sum(1 for e in history[-7:] if (e.get('wm_score', 100) or 0) < 60) if history else 0
        if chronic_count >= 5:
            reasons.append("近7天中5天以上睡眠评分低于60, 符合慢性失眠频率标准")
            urgency = 'soon'
        
        if sleep_latency > 60:
            reasons.append(f"入睡潜伏期{sleep_latency}分钟, 严重入睡困难")
            if chronic_count >= 3:
                urgency = 'soon'
        
        if snore and awake_times >= 3:
            reasons.append("打鼾+频繁夜醒, OSA风险较高, 建议多导睡眠监测")
            urgency = 'soon'
        
        if feels == 'very_tired' and chronic_count >= 3:
            reasons.append("持续睡眠不足+日间功能严重受损")
            urgency = 'soon'
        
        if feels in ('very_tired', 'tired') and pain and total_dur < 300:
            reasons.append("睡眠问题+疼痛+疲劳叠加, 建议综合评估")
            urgency = 'urgent'
        
        return {
            'needs_referral': len(reasons) > 0,
            'urgency': urgency,
            'reasons': reasons,
            'recommendation': {
                'routine': '建议维持当前习惯, 定期监测',
                'soon': '建议近期就医, 进行专业睡眠评估',
                'urgent': '建议尽快就医, 排除器质性疾病'
            }.get(urgency, '')
        }
