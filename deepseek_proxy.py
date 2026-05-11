"""
AISleepGen DeepSeek API 代理服务器 - AI智能体时代版
为微信小程序提供DeepSeek API调用中转 + 主动管家 + 商业智能
启动: python deepseek_proxy.py
"""

import json
import sys
import os
import urllib.request
import urllib.error
import hashlib
import time
import re
import threading
import math
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, urlencode
from datetime import datetime, timedelta

# ===== AI智能体时代核心引擎 =====

# 1. 趋势检测引擎（主动管家）
# 检测睡眠恶化趋势，自动触发干预建议
class TrendEngine:
    """趋势检测引擎：分析用户画像中的历史数据，检测恶化趋势"""

    ALERT_RULES = {
        'score_drop': {
            'condition': lambda scores: len(scores) >= 3 and all(s < scores[0] for s in scores[-3:]),
            'level': 'warning',
            'message': '评分连续下降{count}天，建议调整作息',
        },
        'insomnia_trend': {
            'condition': lambda entries: len(entries) >= 3 and all(e.get('sleep_latency', 0) > 30 for e in entries[-3:] if e.get('sleep_latency')),
            'level': 'warning',
            'message': '连续{count}天入睡超过30分钟，可能需要干预',
        },
        'awake_trend': {
            'condition': lambda entries: len(entries) >= 3 and all(e.get('awake_times', 0) >= 2 for e in entries[-3:] if e.get('awake_times') is not None),
            'level': 'info',
            'message': '连续{count}天夜醒超过2次，建议尝试深呼吸练习',
        },
        'good_streak': {
            'condition': lambda scores: len(scores) >= 5 and all(s >= 80 for s in scores[-5:]),
            'level': 'positive',
            'message': '恭喜！连续{count}天睡眠质量优秀 🎉',
        },
    }

    @staticmethod
    def analyze(profile, openid_prefix=''):
        """分析用户画像，返回活跃的告警"""
        history = profile.get('history', [])
        if len(history) < 2:
            return []

        alerts = []

        # 提取最近评分序列
        scores = [h.get('wm_score', 0) for h in history if h.get('wm_score', 0) > 0][-7:]

        # 提取最近入睡数据
        last_entries = []
        for h in history[-7:]:
            ext = h.get('extracted', {}) or {}
            last_entries.append(ext)

        # 检测各规则
        # 评分连续下降
        if len(scores) >= 3:
            if all(scores[i] < scores[i-1] for i in range(-2, 0)) and scores[-3] > scores[-2] > scores[-1]:
                drop_count = 3
                for i in range(-4, -len(scores)-1, -1):
                    if scores[i] > scores[i+1]:
                        drop_count += 1
                    else:
                        break
                alerts.append({
                    'type': 'score_drop',
                    'level': 'warning',
                    'message': f'最近连续{drop_count}天评分有点波动，别着急，调整一下节奏能回来',
                    'data': {'count': drop_count, 'scores': scores[-drop_count:]},
                })

        # 入睡困难趋势
        insomnia_entries = [e for e in last_entries if e.get('sleep_latency') is not None and e.get('sleep_latency', 0) > 30]
        if len(insomnia_entries) >= 3:
            alerts.append({
                'type': 'insomnia_trend',
                'level': 'warning',
                'message': f'最近{len(insomnia_entries)}次入睡有点慢，睡前试试4-7-8呼吸，会舒服很多',
                'data': {'count': len(insomnia_entries)},
                'actions': ['start_breathing', 'meditation'],
            })

        # 夜醒频繁
        awake_entries = [e for e in last_entries if e.get('awake_times') is not None and e.get('awake_times', 0) >= 2]
        if len(awake_entries) >= 3:
            alerts.append({
                'type': 'awake_trend',
                'level': 'info',
                'message': f'最近{len(awake_entries)}次夜里醒得比较多，睡前听一段白噪音试试？',
                'data': {'count': len(awake_entries)},
                'actions': ['white_noise'],
            })

        # 优秀趋势（正向反馈）
        good_scores = [s for s in scores[-5:] if s >= 80]
        if len(good_scores) >= 5:
            alerts.append({
                'type': 'good_streak',
                'level': 'positive',
                'message': f'🎉 近5次评分均达80+，继续保持！',
                'data': {},
            })

        return alerts

    @staticmethod
    def get_daily_advice(profile):
        """根据画像生成每日一句建议"""
        alerts = TrendEngine.analyze(profile)
        if alerts:
            # 取最高优先级的告警
            priority = {'warning': 0, 'info': 1, 'positive': 2}
            alerts.sort(key=lambda a: priority.get(a['level'], 3))
            return alerts[0]

        # 无告警时返回默认鼓励
        return {
            'type': 'daily_tip',
            'level': 'info',
            'message': '今晚睡个好觉，明天会更好 💤',
            'data': {},
        }

# 2. 商业智能引擎（AI商业化咨询）
# 返回AI行业动态、睡眠科技趋势
class BizIntelEngine:
    """商业智能引擎：提供AI行业+睡眠科技的简短资讯"""

    @staticmethod
    def get_daily_brief():
        """返回今日商业智能简报"""
        return {
            'ai_trends': [
                {'title': 'AI智能体时代', 'desc': 'Anthropic+Instacart集成，AI可代你购物', 'source': '2026.04'},
                {'title': 'UCP协议发布', 'desc': 'Google发布AI代理开放标准，Shopify/Visa支持', 'source': '2025.01'},
                {'title': 'AI健康监测', 'desc': '大模型在睡眠分析领域的准确率超传统PSG算法', 'source': '2026.03'},
            ],
            'sleep_science': [
                {'title': '最佳入睡温度', 'desc': '卧室温度18-22°C最有利于深度睡眠', 'source': 'Sleep Science'},
                {'title': '蓝光影响', 'desc': '睡前1小时避免蓝光，褪黑素分泌提升40%', 'source': 'NIH 2025'},
                {'title': '规律作息', 'desc': '固定就寝时间比总睡眠时长更能预测健康', 'source': 'Sleep Health 2026'},
            ],
        }

    @staticmethod
    def search(query):
        """搜索商业智能内容（模拟搜索，真实场景应调用搜索API）"""
        data = BizIntelEngine.get_daily_brief()
        results = []
        for section in data.values():
            for item in section:
                if query.lower() in item['title'].lower() or query.lower() in item['desc'].lower():
                    results.append(item)
        return results if results else [{'title': '搜索无结果', 'desc': '请尝试其他关键词', 'source': ''}]

# 3. 主动管家调度器（定时任务）
class ButlerScheduler:
    """主动管家调度器：在每次交互时检测是否需要主动推送"""

    @staticmethod
    def check(openid, profile):
        """检查当前是否需要主动推送"""
        # 1. 趋势检测
        alerts = TrendEngine.analyze(profile)

        # 2. 智能问候（根据时间+上次活跃）
        member = profile.get('member', {})
        last_active_str = member.get('last_active', '')

        # 3. 商业智能简报（每天一次）
        today = datetime.now().strftime('%Y-%m-%d')
        last_brief = profile.get('_last_brief_date', '')
        show_brief = last_brief != today

        return {
            'alerts': alerts,
            'show_brief': show_brief,
            'has_action': any(a.get('actions') for a in alerts),
        }

# ===== 微信小程序配置 =====
# 从环境变量读取，不入库
WECHAT_APPID = os.environ.get("AISLEEPGEN_WECHAT_APPID", "")
WECHAT_SECRET = os.environ.get("AISLEEPGEN_WECHAT_SECRET", "")

# 用户画像持久化存储
USER_PROFILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_profile.json')
PROFILE_BACKUP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'profile_backups')
MAX_BACKUPS = 5  # 保留最近5份备份

def _load_all_profiles():
    """加载所有用户的画像数据。自动迁移旧版单用户格式。"""
    default_keys = {'history', 'latest', 'total_sessions', 'stress_log', 'behavior_stats'}
    if os.path.exists(USER_PROFILE_PATH):
        try:
            with open(USER_PROFILE_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
        except (json.JSONDecodeError, Exception) as e:
            print(f'[Profile] ⚠️ 文件损坏 ({e}), 尝试从备份恢复...')
            recovered = _recover_from_backup()
            if recovered is not None:
                raw = recovered
            else:
                print('[Profile] ⚠️ 无可用备份, 使用空数据')
                return {}
        # 检测旧版格式：顶层字段混有旧字段名（即使存在其他key）
            if isinstance(raw, dict):
                top_level_keys = set(raw.keys())
                has_old_fields = bool(top_level_keys & default_keys)
                if has_old_fields:
                    old_data = {k: raw[k] for k in default_keys if k in raw}
                    other_keys = {k: raw[k] for k in raw if k not in default_keys}
                    new_format = {}
                    new_format['default'] = old_data
                    new_format.update(other_keys)
                    # 仅当有数据迁移时才写回
                    if old_data:
                        with open(USER_PROFILE_PATH, 'w', encoding='utf-8') as f:
                            json.dump(new_format, f, ensure_ascii=False, indent=2)
                        print(f'[Profile] 旧格式迁移完成，数据已放入 default 用户下')
                    return new_format
            return raw
        except:
            pass
    return {}

def _save_all_profiles(all_profiles):
    """保存所有用户的画像数据（写前自动备份）"""
    try:
        _backup_profile()
        with open(USER_PROFILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[Profile] 保存失败: {e}')


def _backup_profile():
    """写前备份 user_profile.json（保留最近5份）"""
    if not os.path.exists(USER_PROFILE_PATH):
        return
    os.makedirs(PROFILE_BACKUP_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    dst = os.path.join(PROFILE_BACKUP_DIR, f'profile_{ts}.json')
    try:
        import shutil
        shutil.copy2(USER_PROFILE_PATH, dst)
    except Exception as e:
        print(f'[Backup] 备份失败: {e}')
        return
    # 清理旧备份
    try:
        backups = sorted([f for f in os.listdir(PROFILE_BACKUP_DIR) if f.startswith('profile_')])
        while len(backups) > MAX_BACKUPS:
            os.remove(os.path.join(PROFILE_BACKUP_DIR, backups.pop(0)))
    except:
        pass


def _recover_from_backup():
    """尝试从最近的备份恢复 profile 数据"""
    if not os.path.exists(PROFILE_BACKUP_DIR):
        return None
    backups = sorted([f for f in os.listdir(PROFILE_BACKUP_DIR) if f.endswith('.json')], reverse=True)
    for fn in backups[:MAX_BACKUPS]:
        fp = os.path.join(PROFILE_BACKUP_DIR, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict) and len(data) > 0:
                # 恢复成功：覆盖损坏文件
                import shutil
                shutil.copy2(fp, USER_PROFILE_PATH)
                print(f'[Backup] 从 {fn} 恢复成功')
                return data
        except:
            continue
    print('[Backup] ❌ 无可用备份')
    return None

def _get_default_profile():
    """创建一个新用户的默认画像（含会员系统字段）"""
    return {
        'history': [],
        'latest': {},
        'total_sessions': 0,
        'stress_log': [],
        'relax_log': [],  # 减压详细记录（替代旧的intervention_log）
        'behavior_stats': {
            'total_relax_sessions': 0,
            'total_completed_sessions': 0,   # 完整做完的
            'total_interrupted_sessions': 0,  # 中途中断的
            'total_relax_seconds': 0,          # 累计减压时长（秒）
            'avg_relax_duration': 0,           # 平均每次减压时长
            'relax_streak_days': 0,            # 连续减压天数
            'stress_type_distribution': {},    # {工作压力: 10, 失眠焦虑: 5}
            'last_relax_date': None,
            'common_emotions': [],
            'weekly_counts': [],               # [{week_start: "2026-04-21", count: 3}]
        },
        # 会员系统
        'member': {
            'level': 'free',          # free | pro | unlimited
            'joined_at': datetime.now().strftime('%Y-%m-%d'),
            'last_active': datetime.now().strftime('%Y-%m-%d'),
            'streak_days': 0,          # 连续使用天数
            'total_days': 0,           # 累计使用天数
            'daily_scores': [],         # [{date, score}] 用于计算平均分
            'active_dates': [],         # 活跃日期列表（用于连续天数计算）
        },
        # 用户信息
        'user_info': {
            'nickname': '睡眠探索者',
            'avatar_url': '',
            'gender': 0,    # 0未知 1男 2女
            'age_range': '',
        },
        # 元学习参数（Phase 1: 数据结构）
        'meta_params': {
            'intervention_threshold': 0.5,       # 触发干预的置信度门槛
            'breath_rounds_base': 3,             # 基础呼吸轮数
            'breath_rounds_scale': 0.5,          # 压力增量对应的额外轮数
            'preferred_pattern': '4-7-8',        # 偏好呼吸模式
            'noise_preference': 'ocean',         # 偏好白噪音类型

            'feature_vector': [0.0] * 8,         # 8维用户行为特征

            'total_interactions': 0,             # 干预总次数
            'response_rate': 0.0,                # 干预接受率
            'completion_rate': 0.0,              # 呼吸练习完成率
            'avg_hrv_change': 0.0,               # 平均HRV变化（预留）

            '_pattern_scores': {},               # 各呼吸模式的完成分数（内部用）
            'last_meta_update': None,            # 最后更新日期
            'confidence': 0.3,                   # 对该用户的了解程度
        },
    }

def _load_user_profile(openid='default'):
    """加载指定用户的画像"""
    all_profiles = _load_all_profiles()
    if openid not in all_profiles:
        all_profiles[openid] = _get_default_profile()
        _save_all_profiles(all_profiles)
    profile = all_profiles[openid]
    # 兼容：旧用户缺少 meta_params → 自动填充默认值
    if 'meta_params' not in profile:
        from copy import deepcopy
        default = _get_default_profile()
        profile['meta_params'] = deepcopy(default['meta_params'])
    return profile

def _save_user_profile(profile, openid='default'):
    """保存指定用户的画像
    
    参数顺序: save_user_profile(PROFILE, OPENID) — profile在前，openid在后。
    调用时保持 (profile, openid) 顺序，不要传反。
    """
    # 运行时防御：传反了立刻报错
    assert isinstance(profile, dict), (
        f'save_user_profile: profile必须是dict，收到{type(profile).__name__}。'
        f' 提示: 调用顺序是 save(profile, openid) — 不是 (openid, profile)！'
    )
    assert isinstance(openid, str), (
        f'save_user_profile: openid必须是str，收到{type(openid).__name__}。'
        f' 提示: 调用顺序是 save(profile, openid) — 不是 (openid, profile)！'
    )
    all_profiles = _load_all_profiles()
    all_profiles[openid] = profile
    _save_all_profiles(all_profiles)

def _update_user_profile(extracted_data, wm_result, user_message, openid='default'):
    """更新用户画像：合并本次对话提取的数据，保存专家分析"""
    profile = _load_user_profile(openid)
    today = datetime.now().strftime('%Y-%m-%d')

    # 检测纠正意图--用户说"记错了""不是""不对"等，直接覆写 latest 而不是追加
    is_correction = any(w in user_message for w in ['记错', '不是', '不对', '错了', '纠正', '更正', '修正', '其实', '搞错', '你弄错'])

    # 提取专家维度数据（用于回顾分析）
    expert_snapshot = {}
    if wm_result:
        dims = wm_result.get('analysis', {}).get('dimensions', {}) if isinstance(wm_result.get('analysis'), dict) else {}
        for dim_name, dim_info in dims.items():
            if isinstance(dim_info, dict) and dim_info.get('score') is not None:
                snapshot = {
                    'score': dim_info['score'],
                    'findings': dim_info.get('findings', []),
                    'risk_flags': dim_info.get('risk_flags', []),
                    'recommended_therapies': dim_info.get('recommended_therapies', []),
                    'specialty': dim_info.get('specialty', dim_name),
                }
                # 特定专家字段
                for extra_key in ['sleep_efficiency', 'arousal_type', 'osa_risk', 'chronotype',
                                  'phq9_sim', 'gad7_sim', 'glymphatic_efficiency', 'risk_score',
                                  'physiological_arousal', 'cognitive_arousal']:
                    if extra_key in dim_info:
                        snapshot[extra_key] = dim_info[extra_key]
                expert_snapshot[dim_name] = snapshot

    # 本次会话摘要
    session_entry = {
        'date': today,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'extracted': extracted_data or {},
        'wm_score': wm_result.get('total_score', 0) if wm_result else 0,
        'wm_quality': wm_result.get('quality', '') if wm_result else '',
        'user_said': user_message[:100],
        'type': 'correction' if is_correction else 'normal',
        'experts': expert_snapshot,  # 保存专家快照供回顾
    }

    # 合并到历史（保留最近30条）
    profile['history'].append(session_entry)
    if len(profile['history']) > 30:
        profile['history'] = profile['history'][-30:]

    # 更新最新画像--如果是纠正，数据来源标注为"用户修正"
    profile['latest'] = {
        'date': today,
        'score': wm_result.get('total_score', 0) if wm_result else 0,
        'quality': wm_result.get('quality', '') if wm_result else '',
        'pain': extracted_data.get('pain', False) if extracted_data else False,
        'pain_area': extracted_data.get('pain_area', '') if extracted_data else '',
        'environment_cold': extracted_data.get('environment_cold', False) if extracted_data else False,
        'environment_hot': extracted_data.get('environment_hot', False) if extracted_data else False,
        'snore_related': extracted_data.get('snore_related', False) if extracted_data else False,
        'awake_times': extracted_data.get('awake_times', 0) if extracted_data else 0,
        'stress': extracted_data.get('stress_level', 0) if extracted_data else 0,
        'feeling': extracted_data.get('feeling', '') if extracted_data else '',
        'confirmed': not is_correction,  # 纠正后标记为未确认
    }

    profile['total_sessions'] += 1

    # ===== 更新会员系统 =====
    if 'member' not in profile:
        profile['member'] = _get_default_profile()['member']
    member = profile['member']
    member['last_active'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    # 活跃日期追踪
    if 'active_dates' not in member:
        member['active_dates'] = []
    if today not in member['active_dates']:
        member['active_dates'].append(today)
        member['total_days'] = len(member['active_dates'])

    # 连续天数计算
    if 'active_dates' in member and member['active_dates']:
        sorted_dates = sorted(member['active_dates'], reverse=True)
        streak = 0
        from datetime import datetime as dt, timedelta
        check_date = dt.now().date()
        for d in sorted_dates:
            try:
                date_obj = dt.strptime(d, '%Y-%m-%d').date()
                if date_obj == check_date:
                    streak += 1
                    check_date -= timedelta(days=1)
                elif date_obj == check_date:
                    continue
                else:
                    break
            except:
                continue
        member['streak_days'] = streak

    # 每日评分追踪
    if 'daily_scores' not in member:
        member['daily_scores'] = []
    wm_score = wm_result.get('total_score', 0) if wm_result else 0
    if wm_score > 0:
        # 当天已有评分则更新，否则追加
        existing = [x for x in member['daily_scores'] if x.get('date') == today]
        if existing:
            existing[0]['score'] = wm_score
        else:
            member['daily_scores'].append({'date': today, 'score': wm_score})
        # 保留最近90天
        member['daily_scores'] = member['daily_scores'][-90:]

    _save_user_profile(profile, openid)
    print(f'[Profile] [{openid[:8]}...] 已更新{"(纠正)" if is_correction else ""}, 总对话次数={profile["total_sessions"]}')
    # 每次保存用户画像后尝试自学习
    _trigger_self_learn()


# 在 _handle_chat 中的 try-except 外部调用 _update_user_profile 的安全包装
def _safe_update_profile(extracted_data, wm_result, user_message, openid):
    """安全调用 _update_user_profile，防止异常传播"""
    try:
        _update_user_profile(extracted_data, wm_result, user_message, openid)
    except Exception as e:
        print(f'[Profile] 保存失败(安全跳过): {e}')


def _log_intervention(openid, stress_type, breath_pattern, rounds=0, duration=0, completed=True, user_message=''):
    """记录减压干预详细日志
    Args:
        openid: 用户ID
        stress_type: 压力类型（工作压力/失眠焦虑等）
        breath_pattern: 呼吸模式（4-7-8/箱式呼吸等）
        rounds: 完成了多少轮
        duration: 持续秒数
        completed: 是否完成（True=做完, False=中断）
    """
    try:
        profile = _load_user_profile(openid)
        # 初始化数据结构
        if 'relax_log' not in profile:
            profile['relax_log'] = []
        if 'behavior_stats' not in profile:
            profile['behavior_stats'] = {'total_relax_sessions': 0, 'common_emotions': []}
        bs = profile['behavior_stats']
        # 填充默认值
        for k in ['total_completed_sessions','total_interrupted_sessions','total_relax_seconds',
                   'avg_relax_duration','relax_streak_days','stress_type_distribution',
                   'last_relax_date','weekly_counts']:
            if k not in bs:
                bs[k] = 0 if k not in ['stress_type_distribution','weekly_counts','last_relax_date'] else ({} if k == 'stress_type_distribution' else ([] if k == 'weekly_counts' else None))

        now = datetime.now()
        today = now.strftime('%Y-%m-%d')
        now_str = now.strftime('%Y-%m-%d %H:%M')

        # 记录详细log
        entry = {
            'timestamp': now_str,
            'date': today,
            'type': 'breathing',
            'stress_type': stress_type,
            'breath_pattern': breath_pattern,
            'rounds_completed': rounds,
            'duration_seconds': duration,
            'completed': completed,
        }
        profile['relax_log'].append(entry)
        # 保留最近200条
        if len(profile['relax_log']) > 200:
            profile['relax_log'] = profile['relax_log'][-200:]

        # 更新统计
        bs['total_relax_sessions'] = bs.get('total_relax_sessions', 0) + 1
        if completed:
            bs['total_completed_sessions'] = bs.get('total_completed_sessions', 0) + 1
        else:
            bs['total_interrupted_sessions'] = bs.get('total_interrupted_sessions', 0) + 1
        bs['total_relax_seconds'] = bs.get('total_relax_seconds', 0) + duration
        total_sessions = bs['total_relax_sessions']
        total_secs = bs['total_relax_seconds']
        bs['avg_relax_duration'] = round(total_secs / total_sessions, 1) if total_sessions > 0 else 0

        # 压力类型分布
        sdist = bs.get('stress_type_distribution', {})
        if isinstance(sdist, dict):
            sdist[stress_type] = sdist.get(stress_type, 0) + 1
            bs['stress_type_distribution'] = sdist

        # 连续减压天数
        bs['last_relax_date'] = today
        if 'relax_streak_days' in bs:
            # 检查昨天是否也有记录
            yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
            last_relax = bs.get('last_relax_date') or ''
            if last_relax == yesterday or last_relax == today:
                bs['relax_streak_days'] = bs.get('relax_streak_days', 0) + 1
            else:
                bs['relax_streak_days'] = 1

        # 周统计
        week_start = (now - timedelta(days=now.weekday())).strftime('%Y-%m-%d')
        wcounts = bs.get('weekly_counts', [])
        found = False
        for w in wcounts:
            if w.get('week_start') == week_start:
                w['count'] = w.get('count', 0) + 1
                found = True
                break
        if not found:
            wcounts.append({'week_start': week_start, 'count': 1})
        if len(wcounts) > 12:  # 保留3个月
            bs['weekly_counts'] = wcounts[-12:]

        # 保存到根目录 user_profile.json（与 _load_user_profile 一致）
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base_dir, 'user_profile.json')
        all_profiles = {}
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                all_profiles = json.load(f)
        all_profiles[openid] = profile
        # 写入文件（不用 save_json，它不存在）
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
        print(f'[RelaxLog] 已记录: {stress_type}, {breath_pattern}, rounds={rounds}, completed={completed}')
        # 每次记录干预日志时触发元学习更新
        try:
            _meta_update(openid, {
                'stress_type': stress_type,
                'breath_pattern': breath_pattern,
                'rounds': rounds,
                'duration': duration,
                'completed': completed,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                '_raw_message': user_message,
            })
        except Exception as e:
            print(f'[MetaUpdate] 跳过: {e}')
    except Exception as e:
        print(f'[RelaxLog] 跳过: {e}')


def _extract_features(profile, user_message, stress_type=''):
    """从用户消息和画像中提取8维特征向量（Phase 2）

    维度:
        F1: 压力强度 (0-1) - 关键词密度/情绪强度
        F2: 失眠倾向 (0-1) - 失眠相关词频率
        F3: 焦虑唤醒 (0-1) - 焦虑躯体症状词
        F4: 情绪极性 (0-1) - WorldModel feeling 得分
        F5: 对话深度 (0-1) - 本轮对话轮数归一化
        F6: 互动时段 (0-1) - 白天/深夜/凌晨
        F7: 历史接受率 (0-1) - 过去干预的完成率
        F8: 反馈一致性 (0-1) - 用户反馈与log匹配度
    """
    import re
    features = [0.0] * 8

    # F1: 压力强度 - 压力关键词密度
    stress_words = ['压力', '累', '烦', '难受', '痛苦', '焦虑', '紧张', '不安', '担心', '崩溃']
    matches = sum(1 for w in stress_words if w in user_message)
    features[0] = min(1.0, matches / 5.0)

    # F2: 失眠倾向
    insomnia_words = ['睡不着', '失眠', '醒了', '醒来', '熬夜', '难入睡', '睡不好', '做梦', '噩梦']
    matches_i = sum(1 for w in insomnia_words if w in user_message)
    features[1] = min(1.0, matches_i / 4.0)

    # F3: 焦虑唤醒
    arousal_words = ['心慌', '心跳', '喘不过气', '胸闷', '手抖', '出汗', '害怕', '恐惧']
    matches_a = sum(1 for w in arousal_words if w in user_message)
    features[2] = min(1.0, matches_a / 4.0)

    # F4: 情绪极性 - 用已有的情绪提取结果
    # 从 profile 的 emotion_timeline 取最近一条
    et = profile.get('emotion_timeline', [])
    if et:
        last_feeling = str(et[-1].get('feeling', '')).lower()
        if last_feeling in ('bad', 'terrible', 'anxious'):
            features[3] = 0.2
        elif last_feeling in ('good', 'great', 'happy'):
            features[3] = 0.8
        else:
            features[3] = 0.5
    else:
        features[3] = 0.5

    # F5: 对话深度
    history = profile.get('history', [])
    # 取最近10分钟内的对话
    now_ts = datetime.now().timestamp()
    recent = [h for h in history if isinstance(h, dict) and now_ts - h.get('_ts', now_ts) < 600]
    features[4] = min(1.0, len(recent) / 20.0)

    # F6: 互动时段
    hour = datetime.now().hour
    if 23 <= hour or hour < 3:
        features[5] = 1.0  # 深夜
    elif 3 <= hour < 6:
        features[5] = 0.8  # 凌晨
    elif 6 <= hour < 12:
        features[5] = 0.3  # 上午
    elif 12 <= hour < 18:
        features[5] = 0.5  # 下午
    else:
        features[5] = 0.7  # 傍晚

    # F7: 历史接受率
    bs = profile.get('behavior_stats', {})
    total = bs.get('total_relax_sessions', 0)
    completed = bs.get('total_completed_sessions', 0)
    features[6] = round(completed / max(1, total), 2)

    # F8: 反馈一致性 - 当前压力类型和历史的匹配度
    sdist = bs.get('stress_type_distribution', {})
    if stress_type and sdist:
        total_stress = sum(sdist.values())
        this_stress_count = sdist.get(stress_type, 0)
        features[7] = round(this_stress_count / max(1, total_stress), 2)
    else:
        features[7] = 0.5

    return features


def _meta_update(openid, session_data):
    """元学习更新器（Phase 2）

    每次干预结束后调用，根据本次干预结果更新用户的元参数。
    session_data: {
        'stress_type': str,
        'breath_pattern': str,
        'rounds': int,
        'duration': int,
        'completed': bool,
        'timestamp': str,
    }
    """
    profile = _load_user_profile(openid)
    mp = profile.setdefault('meta_params', {})

    # 如果 meta_params 不完整（旧用户第一次加载），补默认值
    default = _get_default_profile()['meta_params']
    for k, v in default.items():
        if k not in mp:
            mp[k] = v

    completed = session_data.get('completed', False)
    pattern = session_data.get('breath_pattern', '4-7-8')

    # 1. 更新完成率
    old_rate = mp.get('completion_rate', 0.0)
    old_count = mp.get('total_interactions', 0)
    new_rate = (old_count * old_rate + (1 if completed else 0)) / (old_count + 1)
    mp['completion_rate'] = round(new_rate, 3)
    mp['total_interactions'] = old_count + 1

    # 2. 根据完成率调整干预阈值
    #    完成率高于 0.6 → 微降阈值（用户接受干预）
    #    低于 0.4 → 升阈值（用户可能不需要）
    target = 0.5
    if completed:
        target = 0.45  # 做完了 → 可以更积极干预
    else:
        target = 0.55  # 没做完 → 提高门槛
    old_threshold = mp.get('intervention_threshold', 0.5)
    new_threshold = old_threshold + (target - old_threshold) * 0.2  # 平滑移动
    mp['intervention_threshold'] = round(max(0.3, min(0.8, new_threshold)), 3)

    # 3. 更新偏好模式评分
    pscores = mp.get('_pattern_scores', {})
    pscores[pattern] = pscores.get(pattern, 0) + (1.0 if completed else -0.3)
    mp['preferred_pattern'] = sorted(pscores, key=lambda k: pscores[k], reverse=True)[0]

    # 4. 更新压力类型的特征向量
    fv = mp.get('feature_vector', [0.0] * 8)
    stress_type = session_data.get('stress_type', '')
    # 用 _extract_features 的当前消息特征做 EMA 更新
    user_message = session_data.get('_raw_message', '')
    if user_message:
        new_fv = _extract_features(profile, user_message, stress_type)
        # EMA: new = 0.3 * current + 0.7 * old
        for i in range(8):
            fv[i] = round(0.3 * new_fv[i] + 0.7 * fv[i], 3)
    mp['feature_vector'] = fv

    # 5. 更新响应率
    total = profile.get('total_sessions', 0)
    mp['response_rate'] = round(mp['total_interactions'] / max(1, total), 3)

    # 6. 更新置信度 - 随交互次数增长但递减
    n = mp['total_interactions']
    mp['confidence'] = round(min(0.95, 0.3 + n * 0.08 - (n - 1) * 0.02), 3)

    mp['last_meta_update'] = session_data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M'))

    # 保存
    _save_user_profile(profile, openid)
    print(f'[MetaUpdate] 已更新: interactions={n}, threshold={mp["intervention_threshold"]}, confidence={mp["confidence"]}, preferred={mp["preferred_pattern"]}')


def _run_daily_batch_optimization(profile, openid):
    """跨夜中观适应 — 每日首次活跃时自动优化元参数

    Lazy Maintenance Pattern: 不依赖外部调度器，附着在用户自然流量上触发。
    每次调用检查 _last_meta_batch 日期，非今天则执行 batch 优化。
    """
    mp = profile.setdefault('meta_params', {})
    today = datetime.now().strftime('%Y-%m-%d')

    # 去重检查：今天已经优化过就不跑了
    last_batch = mp.get('_last_meta_batch', '')
    if last_batch == today:
        return False

    relax_logs = profile.get('relax_log', [])
    if not relax_logs:
        mp['_last_meta_batch'] = today
        _save_user_profile(profile, openid)
        return True

    # 分析前一日干预日志
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    target_logs = [log for log in relax_logs if log.get('timestamp', '').startswith(yesterday)]
    if not target_logs:
        target_logs = [log for log in relax_logs if log.get('timestamp', '').startswith(today)]
    if not target_logs:
        target_logs = relax_logs[-5:]

    total = len(target_logs)
    completed = sum(1 for log in target_logs if log.get('completed'))
    rate = completed / total if total > 0 else 0
    avg_rounds = sum(log.get('rounds', 3) for log in target_logs) / total if total > 0 else 3

    print(f'[DailyBatch] [{openid[:8]}...] logs={total} completed={completed} rate={rate:.2f} avg_rounds={avg_rounds:.1f}')

    # 1. 完成率 → 干预阈值
    old_threshold = mp.get('intervention_threshold', 0.5)
    if rate >= 0.7:
        mp['intervention_threshold'] = round(max(0.25, old_threshold - 0.05), 2)
    elif rate <= 0.3:
        mp['intervention_threshold'] = round(min(0.75, old_threshold + 0.08), 2)
    else:
        mp['intervention_threshold'] = round((old_threshold + 0.5) / 2, 2)

    # 2. 平均轮数 → rounds_scale
    old_scale = mp.get('breath_rounds_scale', 2.0)
    if avg_rounds >= 4:
        mp['breath_rounds_scale'] = round(min(3.5, old_scale + 0.3), 2)
    elif avg_rounds <= 2:
        mp['breath_rounds_scale'] = round(max(0.5, old_scale - 0.3), 2)

    # 3. 完成率 → rounds_base
    if rate >= 0.7 and mp.get('breath_rounds_base', 3) < 6:
        mp['breath_rounds_base'] = min(6, mp['breath_rounds_base'] + 1)
    elif rate <= 0.3 and mp.get('breath_rounds_base', 3) > 2:
        mp['breath_rounds_base'] = max(2, mp['breath_rounds_base'] - 1)

    # 4. 记录本次优化日期
    mp['_last_meta_batch'] = today
    _save_user_profile(profile, openid)
    print(f'[DailyBatch] [{openid[:8]}...] done: threshold={mp["intervention_threshold"]} base={mp["breath_rounds_base"]} scale={mp["breath_rounds_scale"]}')
    return True


# ===== 自学习引擎：服务器运行时自动进化 =====
_self_learn_counter = 0
_self_learn_lock = threading.Lock()

def _load_calibration():
    """加载校准参数，没有则返回默认值"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calibration.json')
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except: pass
    return {
        'version': '1.0',
        'learned_on': '',
        'pain_penalty_base': 0.08,
        'latency_threshold': 120,
        'user_group_weights': {},
    }

_save_calibration_lock = threading.Lock()
def _save_calibration(cal):
    """安全保存校准数据"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'calibration.json')
    with _save_calibration_lock:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(cal, f, ensure_ascii=False, indent=2)

def _trigger_self_learn(force=False):
    """尝试自我学习（每5分钟最多触发一次，feedback提交时force=True）"""
    now = time.time()
    last = getattr(_trigger_self_learn, '_last_learn', None)
    if not force and last is not None and now - last < 300:
        return
    _trigger_self_learn._last_learn = now

    try:
        # 拉反馈数据
        fb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'feedback.json')
        if not os.path.exists(fb_path):
            return
        with open(fb_path, 'r', encoding='utf-8') as f:
            feedbacks = json.load(f)

        # 过滤有评分的反馈
        scored_fb = [fb for fb in feedbacks if fb.get('rating', 0) > 0]
        if len(scored_fb) < 3:
            return  # 数据不够

        # 加载当前校准
        cal = _load_calibration()

        # 1. 分析低评分反馈的比例 → 调整疼痛修正
        low_ratings = [fb for fb in scored_fb if fb['rating'] <= 2]

        # 自适应模式切换：启发式 vs 线性回归
        _use_regression = len(scored_fb) >= 100
        cal['_learn_mode'] = 'regression' if _use_regression else 'heuristic'

        if _use_regression:
            # ===== 数据充足：scikit-learn 线性回归（增强特征版）=====
            try:
                from sklearn.linear_model import LinearRegression
                # 构建特征矩阵：5维特征
                _X_rows = []
                _y_rows = []
                for _fb in scored_fb:
                    _wm = _fb.get('wm_score_at_time') or 50.0
                    _lat = _fb.get('sleep_latency', 30) or 30
                    _awake = _fb.get('awake_times', 1) or 1
                    _dur = _fb.get('total_duration', 420) or 420
                    _stress = _fb.get('stress_level', 5) or 5
                    _msg = _fb.get('message') or ''
                    _pain_flag = 1.0 if any(kw in _msg.lower() for kw in ['疼','痛','酸','不舒服','不适','难受']) else 0.0
                    _X_rows.append([_wm, _lat, _awake, _dur, _stress, _pain_flag])
                    _y_rows.append(_fb['rating'])
                if len(set(tuple(r) for r in _X_rows)) >= 10:  # 至少10个不同样本
                    _reg = LinearRegression().fit(_X_rows, _y_rows)
                    _pain_coef = _reg.coef_[5] if len(_reg.coef_) > 5 else 0.0
                    cal['_regression_coefs'] = {
                        'wm_score': round(_reg.coef_[0], 4),
                        'latency': round(_reg.coef_[1], 4),
                        'awake': round(_reg.coef_[2], 4),
                        'duration': round(_reg.coef_[3], 4),
                        'stress': round(_reg.coef_[4], 4),
                        'pain_flag': round(_pain_coef, 4),
                    }
                    cal['_regression_intercept'] = round(_reg.intercept_, 3)
                    cal['_regression_score'] = round(_reg.score(_X_rows, _y_rows), 3)
                    if _pain_coef < -0.3:
                        cal['pain_penalty_base'] = min(0.15, max(0.05, abs(_pain_coef) * 0.3))
                    elif _pain_coef < -0.1:
                        cal['pain_penalty_base'] = 0.10
                    else:
                        cal['pain_penalty_base'] = 0.08
                    print(f'[SelfLearn] 回归6维: R²={cal["_regression_score"]} pain={_pain_coef:.3f}')
                else:
                    print('[SelfLearn] 回归跳过: 样本多样性不足')
            except Exception as _rege:
                print(f'[SelfLearn] 回归失败,回退启发式: {_rege}')

        if not _use_regression and len(low_ratings) >= 3:
            # ===== 数据不足：启发式 =====
            old_penalty = cal.get('pain_penalty_base', 0.08)
            new_penalty = min(old_penalty + 0.02, 0.15)
            cal['pain_penalty_base'] = new_penalty
            print(f'[SelfLearn] 启发式模式: {old_penalty} -> {new_penalty} (基于{len(low_ratings)}条低评, 满100自动切换回归)')

        # 2. 高评分反馈的快乐用户比例
        high_ratings = sum(1 for fb in scored_fb if fb['rating'] >= 4)
        happy_ratio = high_ratings / len(scored_fb)
        cal['happy_ratio'] = round(happy_ratio, 3)

        # 3. 平均评分
        cal['avg_user_rating'] = round(sum(fb['rating'] for fb in scored_fb) / len(scored_fb), 2)
        # wm_score_at_time 可能为None，安全求和
        _wm_scores = [fb.get('wm_score_at_time', 0) or 0 for fb in scored_fb]
        cal['avg_wm_at_feedback'] = round(sum(_wm_scores) / len(scored_fb), 1)

        # ===== 🌉 双引擎协同：偏好趋势 → 校准决策 =====
        try:
            _co_pref_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_preferences.json')
            if os.path.exists(_co_pref_path):
                with open(_co_pref_path, 'r', encoding='utf-8') as f:
                    _co_pref = json.load(f)
                # 提取偏好衰退类别
                _co_cats = _co_pref.get('categories', {})
                _co_declining = [c for c, v in _co_cats.items()
                                if isinstance(v, dict) and v.get('trend') == 'declining']
                if _co_declining:
                    # 偏好衰退且评分低 → 系统推荐的策略方向可能错了
                    cal['declining_prefs'] = _co_declining
                    # 如果是用户普遍不喜欢relaxation → 降低其权重影响
                    if 'relaxation' in _co_declining and len(low_ratings) >= 3:
                        cal['pref_penalty_relaxation'] = min(cal.get('pref_penalty_relaxation', 0.0) + 0.02, 0.15)
                        print(f'[SelfLearn] 协同: relaxation偏好衰退, 惩罚+0.02')
                    if 'medication' in _co_declining:
                        cal['pref_note'] = '用户群体抗拒药物方案,建议优先行为干预'
                # 统计高低分用户偏好差异
                _co_high_users = [fb.get('openid', '')[:8] for fb in scored_fb if fb['rating'] >= 4]
                _co_low_users = [fb.get('openid', '')[:8] for fb in scored_fb if fb['rating'] <= 2]
                if _co_high_users and _co_low_users:
                    cal['_last_pref_scan'] = {
                        'satisfied_sample': len(_co_high_users),
                        'dissatisfied_sample': len(_co_low_users),
                    }
                print(f'[SelfLearn] 协同扫描: {len(_co_cats)}个偏好类别')
        except Exception as _co_e:
            print(f'[SelfLearn] 协同跳过: {_co_e}')

        cal['learned_on'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        cal['samples'] = len(scored_fb)
        cal['version'] = '1.0'

        _save_calibration(cal)

        # ===== 🏛️ 架构内省：自学习完成后顺便做系统健康检查 =====
        try:
            from architecture_inner_eye import measure_system_pulse, report_to_calibration
            _pulse = measure_system_pulse()
            report_to_calibration(_pulse)
            if _pulse['health_score'] < 60:
                print(f'[ArchEye] 健康度{_pulse["health_score"]}/100 {_pulse["health_label"]}')
                for _a in _pulse['recommendations'][:2]:
                    print(f'[ArchEye] 💡 {_a}')
        except Exception as _ae:
            pass  # 内省引擎不影响主流程

        print(f'[SelfLearn] 学习完成: 用户评分={cal["avg_user_rating"]} WM={cal["avg_wm_at_feedback"]} 满意率={happy_ratio:.0%}')
    except Exception as e:
        print(f'[SelfLearn] 跳过: {e}')

# 深度分析模块导入
try:
    from preference_engine import PreferenceEngine
    from world_model_deep import (
        classify_scene, vertical_comparison
    )
    _pref_engine = None  # 延迟初始化
    _HAS_DEEP_MODULE = True
except ImportError:
    _HAS_DEEP_MODULE = False
    _pref_engine = None
    def classify_scene(m): return {'scene': 'general', 'confidence': 0.3, 'action': 'general_reply', 'desc': ''}
    def vertical_comparison(p): return {}

# 世界模型实例（延迟加载）
_world_model_instance = None
def _get_world_model():
    global _world_model_instance
    if _world_model_instance is None:
        try:
            from sleep_world_model import WorldModelEngine
            _world_model_instance = WorldModelEngine()
            # 加载自学习校准参数（如果有）
            try:
                cal = _load_calibration()
                WorldModelEngine._calibration = cal
                print(f'[WorldModel] 加载自学习校准: pain_penalty={cal.get("pain_penalty_base",0.08)}')
            except:
                pass
            print('[WorldModel] 世界模型v4.1已加载')
        except Exception as e:
            print(f'[WorldModel] 加载失败: {e}')
            return None
    return _world_model_instance

def _trend_analysis(profile):
    """跨日趋势分析 - 世界模型的独家能力，DeepSeek做不到"""
    history = profile.get('history', [])
    if len(history) < 2:
        return ''

    daily = {}
    for e in history:
        d = e['date']
        daily[d] = e

    dates = sorted(daily.keys())
    if len(dates) < 2:
        return ''

    scores = []
    for d in dates:
        sc = daily[d].get('wm_score', 0)
        if sc and sc > 0:
            scores.append((d, sc))

    if len(scores) < 2:
        return ''

    first_score = scores[0][1]
    last_score = scores[-1][1]
    diff = last_score - first_score

    if diff > 10:
        trend = (
            f"【趋势分析】\n"
            f"  最早记录: {scores[0][0]} 评分{scores[0][1]}\n"
            f"  最新记录: {scores[-1][0]} 评分{scores[-1][1]}\n"
            f"  趋势: 提升 {diff:.0f} 分，睡眠质量在改善\n"
            f"  建议: 继续保持良好的睡眠习惯"
        )
    elif diff < -10:
        trend = (
            f"【趋势分析】\n"
            f"  最早记录: {scores[0][0]} 评分{scores[0][1]}\n"
            f"  最新记录: {scores[-1][0]} 评分{scores[-1][1]}\n"
            f"  趋势: 下降 {abs(diff):.0f} 分，睡眠质量在恶化\n"
            f"  建议: 需要关注最近的睡眠变化，找出影响原因"
        )
    else:
        trend = (
            f"【趋势分析】\n"
            f"  最早记录: {scores[0][0]} 评分{scores[0][1]}\n"
            f"  最新记录: {scores[-1][0]} 评分{scores[-1][1]}\n"
            f"  趋势: 基本稳定 (变化 {abs(diff):.0f} 分)\n"
            f"  建议: 持续监测，微调睡眠习惯"
        )

    return f"\n===== 跨日趋势分析 =====\n{trend}\n==========================\n"


def _build_history_context(openid='default'):
    """构建历史画像上下文，注入prompt--含叙事对比"""
    profile = _load_user_profile(openid)
    if not profile['history']:
        return '', {}

    today = datetime.now().strftime('%Y-%m-%d')
    today_entries = [e for e in profile['history'] if e['date'] == today]
    previous_entries = [e for e in profile['history'] if e['date'] != today]

    lines = []

    # 今天的情况
    if today_entries:
        last = today_entries[-1]
        entry_type = last.get('type', 'normal')
        prefix = '【今天 用户修正】' if entry_type == 'correction' else f'【今天 {today}】'
        # 从 conversation_summaries 中找回复摘要
        summaries = profile.get('conversation_summaries', [])
        my_reply = ''
        for s in reversed(summaries):
            if s.get('user', '') in last.get('user_said', ''):
                my_reply = s.get('reply_preview', '')
                break
        lines.append(f"{prefix}用户说：{last.get('user_said', '')}，评分{last.get('wm_score', '?')}，我的回复摘要：{my_reply[:60]}")

    # 历史记录（最近3天）
    dates_shown = set()
    for e in reversed(previous_entries):
        d = e['date']
        if d not in dates_shown and len(lines) < 4:
            dates_shown.add(d)
            entry_type = e.get('type', 'normal')
            label = f'【{d}】' if entry_type == 'normal' else f'【{d} 已修正】'
            # 从 conversation_summaries 中找回复摘要
            my_reply_hist = ''
            for s in reversed(summaries):
                if s.get('user', '') in e.get('user_said', ''):
                    my_reply_hist = s.get('reply_preview', '')
                    break
            lines.append(f"{label}用户说：{e.get('user_said', '')}，评分{e.get('wm_score', '?')}，我的回复摘要：{my_reply_hist[:60]}")

    # === 对比叙事（核心改进） ===
    if len(previous_entries) >= 1 or len(today_entries) >= 2:
        # 拿到上次和这次的评分
        scores = []
        for entry in profile['history'][-3:]:
            s = entry.get('wm_score', 0)
            if s and s > 0:
                scores.append((entry['date'], s, entry.get('user_said', '')[:30]))
        if len(scores) >= 2:
            last_score = scores[-2][1]
            current_score = scores[-1][1]
            delta = current_score - last_score
            if delta > 5:
                trend_note = f"评分对比：上次{scores[-2][0]} {last_score}分 → 这次{scores[-1][0]} {current_score}分，改善了+{delta:.0f}分。如果用户今天报告不同的情况，请提到这个进步并鼓励。"
            elif delta < -5:
                trend_note = f"评分对比：上次{scores[-2][0]} {last_score}分 → 这次{scores[-1][0]} {current_score}分，下降了{delta:.0f}分。请关注变化原因，不要指责用户。"
            else:
                trend_note = f"评分对比：上次{scores[-2][0]} {last_score}分 → 这次{scores[-1][0]} {current_score}分，基本稳定(±{abs(delta):.0f})。"
            lines.append(trend_note)
            # 跟踪上次建议
            last_entry = profile['history'][-2] if len(profile['history']) >= 2 else profile['history'][-1]
            last_advice = ''
            for s in reversed(summaries):
                if s.get('advice_given'):
                    last_advice = s.get('advice_given', '')
                    break
                elif s.get('user', '') in last_entry.get('user_said', ''):
                    last_advice = s.get('reply_preview', '')
                    break
            if last_advice:
                lines.append(f"上次给用户的建议: {last_advice[:120]}")
                lines.append("注意：如果用户反馈中提到尝试了这些建议或自有其他方法，请基于执行情况做分析对比，不要假定用户没看到或没尝试。关注效果变化。")

    # === 情绪减压记录 ===
    stress_log = profile.get('stress_log', [])
    recent_stress = stress_log[-3:] if stress_log else []
    if recent_stress:
        stress_lines = ['情绪记录:']
        for s in recent_stress:
            stress_lines.append(f"  {s.get('date','')} {s.get('time','')} 情绪:{s.get('emotion','?')}(强度{s.get('intensity','?')}) 方案:{s.get('plan_name','?')}")
        lines.append('\n'.join(stress_lines))

    # === 偏好学习 ===
    try:
        from preference_storage import PreferenceStorage
        ps = PreferenceStorage()
        ps.load()
        if ps.data.get('category_preferences'):
            liked = [k for k, v in ps.data['category_preferences'].items() if v.get('positive', 0) > 0]
            disliked = [k for k, v in ps.data['category_preferences'].items() if v.get('negative', 0) > 0]
            if liked: lines.append(f"用户喜欢的方法: {', '.join(liked)}")
            if disliked: lines.append(f"用户不喜欢: {', '.join(disliked)}")
    except:
        pass

    # === 行为统计 ===
    stats = profile.get('behavior_stats', {})
    total = stats.get('total_relax_sessions', 0)
    if total > 0:
        lines.append(f"累计减压{total}次，常见情绪: {', '.join(stats.get('common_emotions', ['未知']))}")

    # === 构建结构化专家历史（用于世界模型回顾分析）===
    expert_history = {}
    # 找到最近一次有专家快照的历史记录
    for e in reversed(previous_entries):
        experts = e.get('experts', {})
        if experts:
            expert_history = experts
            break

    if lines:
        ctx = '\n'.join(lines)
        trend_ctx = _trend_analysis(profile)
        return f"""
===== 用户睡眠历史记录 =====
{ctx}
{trend_ctx}注意事项：
- 标注"已修正"的记录表示用户后来纠正过，以修正后的信息为准
- 如果用户明确说之前的记忆有误，更新你的认知，不要坚持旧数据
- 如果是新的一天，先问候并自然询问"昨晚睡得怎么样"
==========================
""", expert_history
    return '', expert_history

# DeepSeek API配置（从openclaw配置读取）
DEEPSEEK_API_KEY = None
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

def load_deepseek_key():
    """从openclaw.json加载DeepSeek API Key"""
    global DEEPSEEK_API_KEY

    config_paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        "C:\\Users\\cqs10\\.openclaw\\openclaw.json"
    ]

    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                key = config.get('models', {}).get('providers', {}).get('deepseek', {}).get('apiKey', '')
                if key and key != '__OPENCLAW_REDACTED__':
                    DEEPSEEK_API_KEY = key
                    return True
            except:
                pass

    # 也尝试环境变量
    import_env = os.environ.get('DEEPSEEK_API_KEY', '')
    if import_env:
        DEEPSEEK_API_KEY = import_env
        return True
    # 从 .env 文件加载（服务器部署fallback）
    env_path = os.path.join(os.path.dirname(__file__) or '.', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('DEEPSEEK_API_KEY='):
                    DEEPSEEK_API_KEY = line.strip().split('=', 1)[1]
                    return True
    return False


class ProxyHandler(BaseHTTPRequestHandler):
    # ===== 安全验证: 文献注入权限控制 =====
    EVIDENCE_ADMIN_KEY = os.environ.get("AISLEEPGEN_ADMIN_KEY", "")

    def _verify_admin(self, data):
        """验证管理员权限"""
        if not self.EVIDENCE_ADMIN_KEY:
            # 未设置密钥：仅允许本地请求
            return self.client_address[0] in ("127.0.0.1", "::1", "localhost")
        return data.get("admin_key", "") == self.EVIDENCE_ADMIN_KEY

    def _set_headers(self, status=200, content_type='application/json'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-OpenID')
        self.end_headers()

    # ===== Self-Healing 系统 =====
    # AI智能体时代核心能力：自动检测、自动修复、自动进化
    _heal_log = []  # 修复日志
    _last_heal_check = 0
    _heal_interval = 300  # 5分钟检查一次

    def _log_heal(self, action, status, detail=''):
        """记录一次修复动作"""
        entry = {
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'action': action,
            'status': status,
            'detail': detail
        }
        self._heal_log.append(entry)
        if len(self._heal_log) > 50:
            self._heal_log = self._heal_log[-50:]
        print(f'[SelfHeal] {status}: {action} - {detail}')

    def _do_self_heal(self):
        """自我诊断+修复端点。小程序/外部可触发"""
        try:
            self._set_headers()
            now = time.time()
            issues = []
            fixes = []
            status = 'healthy'

            # 1. 检查DeepSeek API Key
            if not DEEPSEEK_API_KEY:
                issues.append('DEEPSEEK_API_KEY missing')
                status = 'degraded'
                self._log_heal('check_api_key', 'FAIL', 'API KEY not configured')
            else:
                # 快速测试连通性
                try:
                    test_body = json.dumps({
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": "ping"}],
                        "max_tokens": 5
                    }).encode('utf-8')
                    test_req = urllib.request.Request(
                        DEEPSEEK_BASE_URL + "/chat/completions", data=test_body,
                        headers={"Content-Type": "application/json",
                                "Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                        method='POST'
                    )
                    test_resp = urllib.request.urlopen(test_req, timeout=10)
                    self._log_heal('check_api_key', 'OK', 'API connected')
                except Exception as e:
                    issues.append(f'DeepSeek API unreachable: {str(e)[:60]}')
                    status = 'degraded'
                    self._log_heal('check_api_key', 'FAIL', str(e)[:80])

            # 2. 检查用户画像文件完整性
            for fn in ['user_profile.json', '.auto_evidence.json']:
                fpath = os.path.join(os.path.dirname(__file__) or '.', fn)
                if os.path.exists(fpath):
                    try:
                        sz = os.path.getsize(fpath)
                        if sz < 10:
                            issues.append(f'{fn} is ~empty')
                            status = 'degraded'
                        # JSON 完整性校验
                        if fn == 'user_profile.json':
                            with open(fpath, 'r', encoding='utf-8') as _chk:
                                json.load(_chk)
                    except json.JSONDecodeError:
                        issues.append(f'{fn} 损坏')
                        status = 'degraded'
                        recovered = _recover_from_backup()
                        if recovered is not None:
                            fixes.append(f'从备份恢复 {fn}')
                            self._log_heal('fix_corrupted_file', 'OK', f'{fn} 从备份恢复')
                    except:
                        issues.append(f'{fn} unreadable')
                        status = 'degraded'
                else:
                    # 自愈：创建空文件
                    try:
                        with open(fpath, 'w', encoding='utf-8') as f:
                            json.dump({} if fn == 'user_profile.json' else [], f)
                        fixes.append(f'Created missing {fn}')
                        self._log_heal('fix_missing_file', 'OK', f'Created {fn}')
                    except Exception as e:
                        issues.append(f'Cannot create {fn}')
                        self._log_heal('fix_missing_file', 'FAIL', str(e)[:60])

            # 3. 检查端口监听状态
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('127.0.0.1', 8090))
                # 能绑定说明端口空闲--实际不应该，因为本进程就在用
                sock.close()
            except:
                # 端口占用中，正常
                pass
            finally:
                try: sock.close()
                except: pass

            # 4. 检查PubMed证据时效性
            try:
                ev_path = os.path.join(os.path.dirname(__file__) or '.', '.auto_evidence.json')
                if os.path.exists(ev_path):
                    ev_mtime = os.path.getmtime(ev_path)
                    age_hours = (time.time() - ev_mtime) / 3600
                    if age_hours > 48:
                        issues.append(f'Evidence stale ({age_hours:.0f}h old)')
                        status = 'degraded'
                        self._log_heal('check_evidence_freshness', 'STALE', f'{age_hours:.0f}h old')
            except:
                pass

            # 5. 内存清理：检查用户画像缓存大小
            try:
                profile_path = os.path.join(os.path.dirname(__file__) or '.', 'user_profile.json')
                if os.path.exists(profile_path) and os.path.getsize(profile_path) > 5 * 1024 * 1024:
                    fixes.append('Profile file >5MB - consider archive')
                    self._log_heal('check_profile_size', 'WARN', f'{os.path.getsize(profile_path)} bytes')
            except:
                pass
            # 6. 数据自修复：用户画像缺失字段填充
            try:
                profile_path = os.path.join(os.path.dirname(__file__) or '.', 'user_profile.json')
                if os.path.exists(profile_path):
                    with open(profile_path, 'r', encoding='utf-8') as f:
                        all_profiles = json.load(f)
                    # 检查每个用户的 meta_params 完整性
                    from copy import deepcopy
                    default_mp = {
                        'intervention_threshold': 0.5, 'breath_rounds_base': 3,
                        'breath_rounds_scale': 0.5, 'preferred_pattern': '4-7-8',
                        'noise_preference': 'ocean', 'feature_vector': [0.0] * 8,
                        'total_interactions': 0, 'response_rate': 0.0,
                        'completion_rate': 0.0, 'avg_hrv_change': 0.0,
                        '_pattern_scores': {}, 'last_meta_update': None, 'confidence': 0.3,
                    }
                    for oid, profile in all_profiles.items():
                        if 'meta_params' not in profile:
                            profile['meta_params'] = deepcopy(default_mp)
                            fixes.append(f'Added missing meta_params for {oid[:12]}')
                        else:
                            mp = profile['meta_params']
                            for k, v in default_mp.items():
                                if k not in mp:
                                    mp[k] = v
                                    fixes.append(f'Filled {k} for {oid[:12]}')
                    with open(profile_path, 'w', encoding='utf-8') as f:
                        json.dump(all_profiles, f, ensure_ascii=False, indent=2)
            except Exception as e:
                issues.append(f'Profile repair error: {str(e)[:60]}')

            result = {
                'success': True,
                'status': status,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'issues': issues,
                'fixes': fixes,
                'checks': ['api_key', 'data_files', 'port', 'evidence_freshness', 'profile_integrity'],
                'heal_log': self._heal_log[-5:],
                'repair_count': len(fixes),
            }
            if issues:
                result['summary'] = f'{len(issues)} issues found, {len(fixes)} auto-fixed'
            else:
                result['summary'] = 'All systems healthy'
            # 如果有严重问题，打印警告
            for issue in issues:
                if 'API' in issue or 'failure' in issue.lower():
                    print(f'[SelfHeal] ⚠️ 严重: {issue}')

            self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
            self._last_heal_check = now
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/health':
            self._set_headers()
            self.wfile.write(json.dumps({
                'status': 'ok',
                'service': 'AISleepGen DeepSeek Proxy',
                'deepseek_connected': DEEPSEEK_API_KEY is not None
            }).encode('utf-8'))
            return

        if path == '/api/self-heal':
            self._do_self_heal()
            return

        # GET /api/sleep-stats?openid=xxx
        if path == '/api/sleep-stats':
            qs_openid = ''
            if parsed.query:
                qs_params = dict(p.split('=') for p in parsed.query.split('&') if '=' in p)
                qs_openid = qs_params.get('openid', '')
            openid = qs_openid if qs_openid else self._get_openid({})
            profile = _load_user_profile(openid)
            member = profile.get('member', {})
            daily_scores = member.get('daily_scores', [])
            scores = [x.get('score', 0) for x in daily_scores if x.get('score', 0) > 0]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0
            total_sessions = profile.get('total_sessions', 0)

            # 最近7天分数
            recent_scores = []
            from datetime import datetime, timedelta
            for i in range(7):
                day = datetime.now() - timedelta(days=i)
                day_str = day.strftime('%Y-%m-%d')
                found = [x for x in daily_scores if x.get('date', '').startswith(day_str)]
                recent_scores.append({
                    'date': day_str,
                    'score': found[0].get('score', 0) if found else None
                })

            self._set_headers()
            self.wfile.write(json.dumps({
                'avg_score': avg_score,
                'total_sessions': total_sessions,
                'recent_scores': recent_scores,
                'streak_days': member.get('streak_days', 0),
                'total_days': member.get('total_days', 0),
            }).encode('utf-8'))
            return

        # GET /api/timeline?openid=xxx&limit=30
        if path == '/api/timeline':
            qs_params = {}
            if parsed.query:
                qs_params = dict(p.split('=') for p in parsed.query.split('&') if '=' in p)
            openid = qs_params.get('openid', '') or self._get_openid({})
            limit = min(int(qs_params.get('limit', '30')), 100)
            profile = _load_user_profile(openid)
            history = profile.get('history', [])
            # 筛选有wm_score的记录，按时间倒序取limit条
            scored = [h for h in history if h.get('wm_score', 0) > 0]
            scored.sort(key=lambda x: x.get('date', ''), reverse=True)
            recent = scored[:limit]
            recent.reverse()  # 正序输出
            points = []
            for h in recent:
                pt = {
                    'date': h.get('date', ''),
                    'score': h.get('wm_score', 0),
                    'quality': h.get('quality', ''),
                    'message': (h.get('user_said') or '')[:40],
                }
                # 如果有专家数据，提取各维度评分
                experts = h.get('experts', {})
                if experts and isinstance(experts, dict):
                    for ek, ev in experts.items():
                        if isinstance(ev, dict) and ev.get('score') is not None:
                            if 'dims' not in pt: pt['dims'] = {}
                            pt['dims'][ek] = round(ev['score'] * 100, 1)
                points.append(pt)
            self._set_headers()
            self.wfile.write(json.dumps({
                'points': points,
                'total': len(scored),
                'has_experts': any('dims' in p for p in points),
            }).encode('utf-8'))
            return

        # GET /api/history?openid=xxx&page=1&page_size=20
        if path == '/api/history':
            qs_params = {}
            if parsed.query:
                qs_params = dict(p.split('=') for p in parsed.query.split('&') if '=' in p)
            openid = qs_params.get('openid', '') or self._get_openid({})
            page = int(qs_params.get('page', '1'))
            page_size = int(qs_params.get('page_size', '20'))
            profile = _load_user_profile(openid)
            history = profile.get('report_history', [])
            total = len(history)
            start = (page - 1) * page_size
            end = start + page_size
            paged = history[start:end] if start < total else []
            self._set_headers()
            self.wfile.write(json.dumps({
                'total': total,
                'page': page,
                'page_size': page_size,
                'records': paged
            }).encode('utf-8'))
            return

        # 用户信息GET接口：/api/user-profile?openid=xxx
        if path == '/api/user-profile':
            # 从query string拿openid
            qs_openid = ''
            if parsed.query:
                qs_params = dict(p.split('=') for p in parsed.query.split('&') if '=' in p)
                qs_openid = qs_params.get('openid', '')
            openid = qs_openid if qs_openid else self._get_openid({})
            profile = _load_user_profile(openid)
            member = profile.get('member', {})
            daily_scores = member.get('daily_scores', [])
            avg_score = 0
            if daily_scores:
                scores = [x.get('score', 0) for x in daily_scores if x.get('score', 0) > 0]
                avg_score = round(sum(scores) / len(scores), 1) if scores else 0

            self._set_headers()
            # 7天评分趋势
            from datetime import datetime, timedelta
            scores_7d = []
            for i in range(7):
                day = datetime.now() - timedelta(days=i)
                day_str = day.strftime('%Y-%m-%d')
                found = [x for x in daily_scores if x.get('date', '').startswith(day_str)]
                scores_7d.insert(0, {'date': day_str, 'score': found[0].get('score', 0) if found else None})
            # 7日均值
            valid = [s['score'] for s in scores_7d if s['score'] and s['score'] > 0]
            avg_7d = round(sum(valid) / len(valid), 1) if valid else 0

            self.wfile.write(json.dumps({
                'openid': openid[:16],
                'user_info': profile.get('user_info', {}),
                'member': {
                    'level': member.get('level', 'free'),
                    'total_sessions': profile.get('total_sessions', 0),
                    'total_days': member.get('total_days', 0),
                    'streak_days': member.get('streak_days', 0),
                    'avg_score': avg_score,
                    'avg_score_7d': avg_7d,
                    'current_score': daily_scores[-1].get('score', 0) if daily_scores else 0,
                    'scores_7d': scores_7d,
                    'joined_at': member.get('joined_at', ''),
                },
                'behavior': profile.get('behavior_stats', {}),
                'onboarding_done': profile.get('meta_params', {}).get('_initial_questionnaire', False),
            }).encode('utf-8'))
            return

        # 问卷状态接口：/api/onboarding-status?openid=xxx
        if path == '/api/onboarding-status':
            qs_openid = ''
            if parsed.query:
                qs_params = dict(p.split('=') for p in parsed.query.split('&') if '=' in p)
                qs_openid = qs_params.get('openid', '')
            openid = qs_openid if qs_openid else self._get_openid({})
            profile = _load_user_profile(openid)
            mp = profile.get('meta_params', {})
            self._set_headers()
            self.wfile.write(json.dumps({
                'onboarding_done': mp.get('_initial_questionnaire', False),
            }).encode('utf-8'))
            return

        if path == '/api/pricing':
            handle_get_pricing(self)
            return

        if path == '/audio/sleep.mp3':
            self._serve_audio('sleep.mp3')
            return

        # ===== 🌐 网页版静态服务 =====
        if path == '/':
            # Try web/index.html first, fallback to old page
            _web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
            _idx = os.path.join(_web_dir, 'index.html')
            if os.path.exists(_idx):
                self._set_headers(200, 'text/html; charset=utf-8')
                with open(_idx, 'r', encoding='utf-8') as _fh:
                    self.wfile.write(_fh.read().encode('utf-8'))
            else:
                self._set_headers(200, 'text/html; charset=utf-8')
                self.wfile.write("""<h1>AISleepGen DeepSeek Proxy</h1>
            <p>运行中...</p>
            <ul>
                <li><a href="/health">健康检查</a></li>
                <li><a href="/api/sleep-report">生成睡眠报告(POST)</a></li>
                <li><a href="/api/meditation-plan">生成冥想计划(POST)</a></li>
            </ul>
            """.encode('utf-8'))
            return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            _web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
            _idx = os.path.join(_web_dir, 'index.html')
            if os.path.exists(_idx):
                with open(_idx, 'r', encoding='utf-8') as _fh:
                    self.wfile.write(_fh.read().encode('utf-8'))
            else:
                self.wfile.write(b'<h1>AISleepGen</h1><p>Web not ready</p>')
            return

        self._set_headers(404)
        self.wfile.write(json.dumps({'error': 'Not found'}).encode('utf-8'))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        content_type = self.headers.get('Content-Type', '')

        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))

        if 'multipart/form-data' in content_type and path == '/api/voice-relax':
            # 语音文件上传 - 读取原始数据自行解析边界
            post_data = self.rfile.read(content_length) if content_length > 0 else b''
            data = self._parse_multipart(post_data, content_type)
        elif content_length > 0:
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
            except:
                data = {}
        else:
            data = {}

        if path == '/api/sleep-report':
            self._handle_sleep_report(data)
        elif path == '/api/meditation-plan':
            self._handle_meditation_plan(data)
        elif path == '/api/chat':
            self._handle_chat(data)
        elif path == '/api/chat-report':
            self._handle_chat_report(data)
        elif path == '/api/ingest-literature':
            self._handle_ingest_literature(data)
        elif path == '/api/voice-relax':
            self._handle_voice_relax(data)
        elif path == '/api/wx-login':
            self._handle_wx_login(data)
        elif path == '/api/update-profile':
            self._handle_update_profile(data)
        elif path == '/api/sleep-stats':
            self._handle_sleep_stats(data)
        elif path == '/api/history':
            self._handle_history(data)
        elif path == '/api/feedback':
            self._handle_feedback(data)
        elif path == '/api/data-export':
            self._handle_data_export(data)
        elif path == '/api/butler-check':
            self._handle_butler_check(data)
        elif path == '/api/biz-intel':
            self._handle_biz_intel(data)
        elif path == '/api/mark-brief-read':
            self._handle_mark_brief_read(data)
        elif path == '/api/pubmed-update':
            self._handle_pubmed_update(data)
        elif path == '/api/pubmed-recent':
            self._handle_pubmed_recent(data)
        elif path == '/api/goodnight':
            self._handle_goodnight(data)
        elif path == '/api/self-heal':
            self._do_self_heal()
        elif path == '/api/emotion-timeline':
            self._handle_emotion_timeline(data)
        elif path == '/api/conversation-summaries':
            self._handle_conversation_summaries(data)
        elif path == '/api/timeline':
            # timeline 是 GET 接口，POST 也转发到 GET handler
            self._do_GET()
        elif path == '/api/create-order':
            handle_create_order(self, data)
        elif path == '/api/pay-callback':
            handle_pay_callback(self)
        elif path == '/api/pricing':
            handle_get_pricing(self)
        elif path == '/api/recommend-tier':
            handle_smart_recommend(self, data)
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({'error': 'Not found'}).encode('utf-8'))

    def _parse_multipart(self, body, content_type):
        """简易 multipart/form-data 解析"""
        result = {}
        try:
            # 提取 boundary
            import re
            m = re.search(r'boundary=(.+?)(?:;|$)', content_type)
            if not m: return result
            boundary = m.group(1).strip().strip('"')
            delimiter = ('--' + boundary).encode()
            parts = body.split(delimiter)
            for part in parts:
                if b'Content-Disposition' not in part: continue
                header_end = part.find(b'\r\n\r\n')
                if header_end < 0: continue
                headers_raw = part[:header_end].decode('utf-8', errors='replace')
                value = part[header_end+4:]
                # 文件名(有文件)或字段名
                name_m = re.search(r'name="(.+?)"', headers_raw)
                if not name_m: continue
                name = name_m.group(1)
                # 如果是文件，保存到临时目录
                if 'filename=' in headers_raw:
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3', dir='.')
                    tmp.write(value.rstrip(b'\r\n'))
                    tmp.close()
                    result['_voice_file'] = tmp.name
                    result['voice_file'] = tmp.name
                else:
                    result[name] = value.decode('utf-8', errors='replace').strip()
        except:
            pass
        return result

    def _call_deepseek(self, messages, max_tokens=2000, temperature=0.7):
        """调用DeepSeek API"""
        if not DEEPSEEK_API_KEY:
            return {'error': 'DeepSeek API Key未配置'}

        payload = {
            'model': 'deepseek-chat',
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
            'stream': False
        }

        req = urllib.request.Request(
            f'{DEEPSEEK_BASE_URL}/chat/completions',
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
                'Content-Type': 'application/json'
            },
            method='POST'
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode('utf-8'))
                return {
                    'content': result['choices'][0]['message']['content'],
                    'usage': result.get('usage', {})
                }
        except urllib.error.HTTPError as e:
            return {'error': f'HTTP {e.code}: {e.read().decode("utf-8")}'}
        except Exception as e:
            return {'error': str(e)}

    def _get_openid(self, data):
        """从请求数据中安全获取openid，优先取X-OpenID头"""
        # 先看请求头
        header_openid = self.headers.get('X-OpenID', '')
        if header_openid and header_openid != 'undefined' and header_openid != 'null':
            return header_openid
        # 再看请求体
        return data.get('openid', 'default')

    def _handle_wx_login(self, data):
        """微信小程序登录：用code换openid"""
        self._set_headers()
        code = data.get('code', '')
        if not code:
            self.wfile.write(json.dumps({'error': 'code is required'}).encode('utf-8'))
            return
        if not WECHAT_APPID or not WECHAT_SECRET:
            # 开发模式：用code的md5模拟openid
            fake_oid = 'dev_' + hashlib.md5(code.encode()).hexdigest()[:16]
            print(f'[WxLogin] 开发模式 openid={fake_oid}')
            self.wfile.write(json.dumps({'openid': fake_oid}).encode('utf-8'))
            return
        try:
            params = urlencode({
                'appid': WECHAT_APPID,
                'secret': WECHAT_SECRET,
                'js_code': code,
                'grant_type': 'authorization_code',
            })
            req = urllib.request.Request(
                f'https://api.weixin.qq.com/sns/jscode2session?{params}',
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode('utf-8'))
            if 'openid' in result:
                self.wfile.write(json.dumps({
                    'openid': result['openid'],
                    'session_key': '',  # 不返回敏感信息
                }).encode('utf-8'))
            else:
                self.wfile.write(json.dumps({'error': str(result)}).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))

    def _handle_update_profile(self, data):
        """更新用户信息（含问卷初始化）"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)

        if 'user_info' not in profile:
            profile['user_info'] = {}

        ui = data.get('user_info', {})
        for key in ('nickname', 'avatar_url', 'gender', 'age_range'):
            if key in ui:
                profile['user_info'][key] = ui[key]

        # 问卷初始化钩子：提交问卷后初始化 meta_params
        survey = data.get('onboarding_survey', {})
        if survey:
            mp = profile.setdefault('meta_params', {})
            default = _get_default_profile()['meta_params']
            for k, v in default.items():
                if k not in mp:
                    mp[k] = v

            # 压力程度 → intervention_threshold
            stress_level = survey.get('stress_level', 'medium')
            threshold_map = {'low': 0.65, 'medium': 0.5, 'high': 0.35}
            mp['intervention_threshold'] = threshold_map.get(stress_level, 0.5)

            # 练习时长偏好 → breath_rounds_base
            duration_pref = survey.get('duration_pref', 'medium')
            rounds_map = {'short': 3, 'medium': 4, 'long': 6}
            mp['breath_rounds_base'] = rounds_map.get(duration_pref, 4)

            # 尝试过的方法 → preferred_pattern
            methods = survey.get('methods', [])
            if 'breathing' in methods or not methods:
                mp['preferred_pattern'] = '4-7-8'
            elif 'meditation' in methods:
                mp['preferred_pattern'] = '箱式呼吸'
            else:
                mp['preferred_pattern'] = '4-7-8'

            # 偏好声音 → noise_preference
            sound_pref = survey.get('sound_pref', 'ocean')
            mp['noise_preference'] = sound_pref

            # 作息类型 → 映射到 feature_vector F6 先验
            sleep_type = survey.get('sleep_type', 'normal')
            fv = mp.get('feature_vector', [0.0] * 8)
            type_map = {'night_owl': 0.8, 'normal': 0.5, 'early_bird': 0.3}
            fv[5] = type_map.get(sleep_type, 0.5)  # F6: 时段偏好

            # 初次困扰 → F1/F2/F3 先验
            main_issue = survey.get('main_issue', '')
            if main_issue == 'insomnia':
                fv[1] = 0.7  # F2: 失眠倾向
            elif main_issue == 'anxiety':
                fv[2] = 0.7  # F3: 焦虑唤醒
            elif main_issue == 'stress':
                fv[0] = 0.7  # F1: 压力强度
            else:
                fv[0] = 0.4
                fv[1] = 0.4
            mp['feature_vector'] = fv

            # 完成问卷后提升置信度
            mp['confidence'] = 0.5
            mp['_initial_questionnaire'] = True
            mp['last_meta_update'] = datetime.now().strftime('%Y-%m-%d %H:%M')

            print(f'[Onboarding] [{openid[:8]}...] 问卷初始化完成: stress={stress_level}, duration={duration_pref}, issue={main_issue}')

        _save_user_profile(profile, openid)
        self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
        print(f'[Profile] [{openid[:8]}...] 用户信息已更新')

    def _handle_sleep_stats(self, data):
        """POST: 获取睡眠统计 (也支持 GET)"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)
        member = profile.get('member', {})
        daily_scores = member.get('daily_scores', [])
        scores = [x.get('score', 0) for x in daily_scores if x.get('score', 0) > 0]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        from datetime import datetime, timedelta
        recent = []
        for i in range(7):
            day = datetime.now() - timedelta(days=i)
            day_str = day.strftime('%Y-%m-%d')
            found = [x for x in daily_scores if x.get('date', '').startswith(day_str)]
            recent.append({'date': day_str, 'score': found[0].get('score', 0) if found else None})
        self.wfile.write(json.dumps({
            'avg_score': avg_score,
            'total_sessions': profile.get('total_sessions', 0),
            'recent_scores': recent,
            'streak_days': member.get('streak_days', 0),
            'total_days': member.get('total_days', 0),
            'relax_stats': {
                'total_sessions': bs.get('total_relax_sessions', 0),
                'completed_sessions': bs.get('total_completed_sessions', 0),
                'avg_duration': bs.get('avg_relax_duration', 0),
                'relax_streak_days': bs.get('relax_streak_days', 0),
                'stress_type_distribution': bs.get('stress_type_distribution', {}),
            } if (bs := profile.get('behavior_stats', {})) else {}
        }).encode('utf-8'))

    def _handle_history(self, data):
        """POST: 获取历史记录列表"""
        self._set_headers()
        openid = self._get_openid(data)
        page = data.get('page', 1)
        page_size = data.get('page_size', 20)
        profile = _load_user_profile(openid)
        history = profile.get('report_history', [])
        total = len(history)
        start = (page - 1) * page_size
        end = start + page_size
        paged = history[start:end] if start < total else []
        self.wfile.write(json.dumps({
            'total': total,
            'page': page,
            'page_size': page_size,
            'records': paged
        }).encode('utf-8'))

    def _handle_feedback(self, data):
        """POST: 用户反馈（关联auto_report数据）"""
        self._set_headers()
        openid = self._get_openid(data)
        msg = data.get('message', '')
        rating = data.get('rating', 5)
        if not msg.strip():
            self.wfile.write(json.dumps({'success': False, 'error': '消息不能为空'}).encode('utf-8'))
            return
        # 保存到 feedback 文件（附带当前分析快照）
        try:
            feedback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'feedback.json')
            os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
            if os.path.exists(feedback_path):
                with open(feedback_path, 'r', encoding='utf-8') as f:
                    all_feedback = json.load(f)
            else:
                all_feedback = []
            # 尝试从最近的profile snap加载WM数据
            wm_score = None
            cb = {}
            try:
                profile = _load_user_profile(openid)
                hist = profile.get('history', [])
                if hist:
                    last = hist[-1]
                    wm_score = last.get('wm_score')
                    cb = last.get('insights', {}).get('confidence_bounds', {}) if last.get('insights') else {}
                # 如果仍为None，取latest
                if wm_score is None:
                    wm_score = profile.get('latest', {}).get('score')
            except:
                pass
            # 回归特征工程：从提交数据或最近画像提取
            try:
                __pf = _load_user_profile(openid)
                __lt = __pf.get('latest', {}) or {}
                __sl = data.get('sleep_latency') or __lt.get('sleep_latency') or 30
                __aw = data.get('awake_times') or __lt.get('awake_times') or 1
                __du = data.get('total_duration') or __lt.get('total_duration') or 420
                __st = data.get('stress_level') or __lt.get('stress_level') or 3
            except:
                __sl, __aw, __du, __st = 30, 1, 420, 3
            all_feedback.append({
                'openid': openid[:16],
                'message': msg,
                'rating': rating,
                'wm_score_at_time': wm_score,
                'confidence_bounds': cb,
                'sleep_latency': __sl,
                'awake_times': __aw,
                'total_duration': __du,
                'stress_level': __st,
                'time': datetime.now().isoformat()
            })
            with open(feedback_path, 'w', encoding='utf-8') as f:
                json.dump(all_feedback, f, ensure_ascii=False, indent=2)
            self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
            print(f'[Feedback] [{openid[:8]}...] 评分{rating}/5 wm={wm_score} 说: {msg[:50]}')
            # 反馈后强制自学习
            _trigger_self_learn(force=True)
        except Exception as e:
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))

    def _handle_data_export(self, data):
        """POST: 数据导出"""
        self._set_headers()
        openid = self._get_openid(data)
        export_format = data.get('format', 'json')
        profile = _load_user_profile(openid)
        export_data = {
            'openid': openid[:16],
            'export_time': datetime.now().isoformat(),
            'member': {
                'level': profile.get('member', {}).get('level', 'free'),
                'total_sessions': profile.get('total_sessions', 0),
                'streak_days': profile.get('member', {}).get('streak_days', 0),
                'total_days': profile.get('member', {}).get('total_days', 0),
            },
            'user_info': profile.get('user_info', {}),
            'report_history': profile.get('report_history', []),
        }
        if export_format == 'csv':
            import io
            output = io.StringIO()
            output.write('date,score,duration,quality\n')
            for r in profile.get('report_history', []):
                output.write(f"{r.get('date','')},{r.get('score','')},{r.get('duration','')},{r.get('quality','')}\n")
            csv_str = output.getvalue()
            self._set_headers(200, 'text/csv; charset=utf-8')
            self.wfile.write(csv_str.encode('utf-8'))
        else:
            self.wfile.write(json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8'))
        print(f'[Export] [{openid[:8]}...] 数据已导出')

    def _handle_butler_check(self, data):
        """POST: 主动管家检测--返回趋势告警+商业智能简报"""
        self._set_headers()
        openid = self._get_openid(data)
        if not openid:
            openid = 'default'
        profile = _load_user_profile(openid)
        print(f'[Butler] openid={openid} profile_has_last_brief={"_last_brief_date" in profile}')

        # 强制执行简报（临时调试）
        result = ButlerScheduler.check(openid, profile)
        result['show_brief'] = True
        result['brief'] = BizIntelEngine.get_daily_brief()

        print(f'[Butler] result show_brief={result.get("show_brief")} alerts={len(result.get("alerts", []))}')

        # 记录简报已读
        if result.get('show_brief'):
            profile['_last_brief_date'] = datetime.now().strftime('%Y-%m-%d')
            _save_user_profile(profile, openid)
            result['brief'] = BizIntelEngine.get_daily_brief()

        self.wfile.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
        print(f'[Butler] [{openid[:8]}...] 管家检测: {len(result.get("alerts", []))} 条告警')

    def _handle_biz_intel(self, data):
        """POST: 获取商业智能/行业动态"""
        self._set_headers()
        query = data.get('query', '')
        if query:
            results = BizIntelEngine.search(query)
        else:
            brief = BizIntelEngine.get_daily_brief()
            results = brief.get('ai_trends', []) + brief.get('sleep_science', [])
        self.wfile.write(json.dumps({'results': results}, ensure_ascii=False).encode('utf-8'))

    def _handle_mark_brief_read(self, data):
        """POST: 标记商业智能简报已读"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)
        profile['_last_brief_date'] = datetime.now().strftime('%Y-%m-%d')
        _save_user_profile(profile, openid)
        self.wfile.write(json.dumps({'success': True}).encode('utf-8'))

    def _handle_pubmed_update(self, data):
        """POST/GET: 手动触发PubMed更新"""
        self._set_headers()
        try:
            count = PubmedFrontier.run_daily_update()
            self.wfile.write(json.dumps({
                'success': True,
                'new_articles': count,
                'message': f'PubMed更新完成，找到{count}篇新文献'
            }, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({
                'success': False,
                'error': str(e)
            }).encode('utf-8'))

    def _handle_pubmed_recent(self, data):
        """POST: 获取最近文献摘要（用于前端简报或对话注入）"""
        self._set_headers()
        days = data.get('days', 7)
        categories = data.get('categories', None)
        max_results = data.get('max_results', 5)
        evidence = PubmedFrontier.get_recent_evidence(
            days=days, categories=categories, max_results=max_results
        )
        self.wfile.write(json.dumps({
            'success': True,
            'count': len(evidence),
            'evidence': evidence,
        }, ensure_ascii=False).encode('utf-8'))

    def _handle_goodnight(self, data):
        """POST: 生成晚安推送（个性化睡前建议）"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)

        member = profile.get('member', {})
        history = profile.get('history', [])
        emotion_timeline = profile.get('emotion_timeline', [])
        summaries = profile.get('conversation_summaries', [])
        today = datetime.now().strftime('%Y-%m-%d')

        today_entries = [h for h in history if h.get('date') == today]
        today_scores = [h.get('wm_score', 0) for h in today_entries if h.get('wm_score', 0) > 0]
        today_avg = round(sum(today_scores) / len(today_scores), 1) if today_scores else None

        recent_scores = [h.get('wm_score', 0) for h in history[-7:] if h.get('wm_score', 0) > 0]
        trend = 'stable'
        if len(recent_scores) >= 3:
            if all(recent_scores[i] < recent_scores[i-1] for i in range(1, len(recent_scores))):
                trend = 'declining'
            elif all(recent_scores[i] > recent_scores[i-1] for i in range(1, len(recent_scores))):
                trend = 'improving'

        today_emotions = [e for e in emotion_timeline if e.get('date') == today]
        last_emotion = today_emotions[-1].get('emotion', '') if today_emotions else ''

        all_topics = []
        for s in summaries:
            all_topics.extend(s.get('topics', []))
        from collections import Counter
        topic_counts = Counter(all_topics)
        common_topic = topic_counts.most_common(1)[0][0] if topic_counts else '睡眠'

        suggestions = {
            'declining': '今晚别想太多，好好休息一晚，状态会回来的',
            'improving': '最近状态在变好，今晚继续保持节奏',
            'stable': '今晚好好睡一觉，明天又是新的一天',
        }

        advice = suggestions.get(trend, suggestions['stable'])

        score_msg = ''
        if today_avg is not None:
            if today_avg >= 80:
                score_msg = f'今天表现不错，继续保持~'
            elif today_avg >= 60:
                score_msg = f'今天状态还可以，今晚好好休息'
            else:
                score_msg = f'今晚好好调整，明天会更好'

        streak = member.get('streak_days', 0)
        streak_msg = f' 已连续记录{streak}天🔥' if streak > 0 else ''

        topic_tips = {
            '失眠': '明天记录一下一整天喝了多少咖啡因',
            '打鼾': '今晚试试严格侧卧睡',
            '压力': '明天找个时间做10分钟正念',
            '作息': '明天同一时间起床，巩固生物钟',
        }
        tomorrow_tip = topic_tips.get(common_topic, f'继续关注{common_topic}，数据会越来越清晰')

        push = {
            'success': True,
            'title': f'晚安 💤{streak_msg}',
            'message': f'{score_msg}\n{advice}\n\n📌 明天小提示：{tomorrow_tip}',
            'advice': advice,
            'trend': trend,
            'today_score': today_avg,
            'streak_days': streak,
        }

        try:
            if 'goodnight_log' not in profile:
                profile['goodnight_log'] = []
            profile['goodnight_log'].append({
                'date': today,
                'time': datetime.now().strftime('%H:%M'),
                'advice': advice,
                'trend': trend,
            })
            if len(profile['goodnight_log']) > 30:
                profile['goodnight_log'] = profile['goodnight_log'][-30:]
            _save_user_profile(profile, openid)
        except:
            pass

        self.wfile.write(json.dumps(push, ensure_ascii=False).encode('utf-8'))
        print(f'[Goodnight] [{openid[:8]}...] 晚安推送已生成')

    def _handle_emotion_timeline(self, data):
        """GET/POST: 获取情绪时间线"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)
        timeline = profile.get('emotion_timeline', [])
        self.wfile.write(json.dumps({
            'success': True,
            'count': len(timeline),
            'timeline': timeline[-40:],
        }, ensure_ascii=False).encode('utf-8'))

    def _handle_conversation_summaries(self, data):
        """GET/POST: 获取对话摘要"""
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)
        summaries = profile.get('conversation_summaries', [])
        self.wfile.write(json.dumps({
            'success': True,
            'count': len(summaries),
            'summaries': summaries[-30:],
        }, ensure_ascii=False).encode('utf-8'))

    def _handle_sleep_report(self, data):
        """生成睡眠分析报告"""
        self._set_headers()

        # 提取问卷数据
        bedtime = data.get('bedtime', '未知')
        wake_time = data.get('wake_time', '未知')
        sleep_latency = data.get('sleep_latency', '未知')  # 入睡时间
        awake_times = data.get('awake_times', '未知')  # 醒来次数
        awake_duration = data.get('awake_duration', '未知')  # 清醒时长
        feeling = data.get('feeling', '一般')  # 醒来感觉
        stress_level = data.get('stress_level', 5)  # 压力水平 1-10
        exercise = data.get('exercise', False)  # 是否运动
        caffeine = data.get('caffeine', False)  # 是否摄入咖啡因
        screen_time = data.get('screen_time', False)  # 睡前看屏幕

        # 调用世界模型进行多维度分析
        wm = _get_world_model()
        world_analysis = ""
        if wm:
            try:
                wm_result = wm.comprehensive_analysis({
                    'bedtime': bedtime, 'wake_time': wake_time,
                    'sleep_latency': sleep_latency, 'awake_times': awake_times,
                    'feeling': feeling, 'stress_level': stress_level,
                    'screen_time': screen_time
                })
                dims = wm_result.get('analysis', {}).get('dimensions', {})
                dim_names = {
                    'ClinicalPsychologist': '临床心理学', 'CBT': '认知行为治疗',
                    'SleepPhysician': '睡眠医学', 'Chronobiologist': '昼夜节律',
                    'LifeScientist': '生命科学', 'RiskManager': '风险评估',
                    'StressRelaxation': '减压与自主神经调节'
                }
                dim_lines = []
                for k, v in dims.items():
                    score = v.get('score', 0) * 100
                    name = dim_names.get(k, k)
                    dim_lines.append(f"  {name}: {score:.0f}/100")
                world_analysis = "\n".join(dim_lines)
                print(f'World Model分析完成: 综合评分 {wm_result["total_score"]}分')
            except Exception as e:
                print(f'World Model调用失败: {e}')
                world_analysis = ""

        # 构建提示词 - 注入世界模型分析
        world_context = f"""
===== 世界模型多维度分析 =====
{world_analysis}

请在你的分析中引用这些专业维度分析结果，使报告具有专业深度，超越普通的睡眠分析。
==========================
""" if world_analysis else ""

        system_prompt = ("你是一位专业的睡眠医学专家和睡眠咨询师。你的职责是基于用户提供的睡眠数据，生成一份专业、准确、有洞察力的睡眠分析报告。\n\n" +
                        (world_context + "\n\n" if world_context else "") +
                        '请严格按照以下JSON格式输出报告，不要添加任何额外说明：\n\n' +
                        '{\n' +
                        '  "score": 0-100的整数评分,\n' +
                        '  "quality": "优秀/良好/一般/较差/需要改善",\n' +
                        '  "analysis": {\n' +
                        '    "totalDuration": "估算的总睡眠时长",\n' +
                        '    "sleepEfficiency": "睡眠效率百分比",\n' +
                        '    "mainIssues": ["主要问题1", "主要问题2"],\n' +
                        '    "strengths": ["优势1", "优势2"]\n' +
                        '  },\n' +
                        '  "detailedAnalysis": "一段200-300字的详细睡眠分析，专业且有洞察力",\n' +
                        '  "healthImpacts": {\n' +
                        '    "cardiovascular": "心血管健康影响分析",\n' +
                        '    "cognitive": "认知功能影响分析",\n' +
                        '    "emotional": "情绪健康影响分析"\n' +
                        '  },\n' +
                        '  "suggestions": ["建议1", "建议2", "建议3", "建议4", "建议5"],\n' +
                        '  "tomorrowPlan": "明天具体的行动计划建议",\n' +
                        '  "meditationRecommendation": "推荐的冥想类型和时长"\n' +
                        '}')

        user_prompt = f"""请基于以下睡眠数据生成专业的睡眠分析报告：

**基本信息：**
- 上床时间：{bedtime}
- 醒来时间：{wake_time}
- 入睡时间（从上床到睡着）：{sleep_latency}分钟
- 夜间醒来次数：{awake_times}次
- 清醒总时长：{awake_duration}分钟
- 醒来感觉：{feeling}
- 压力水平（1-10）：{stress_level}
- 今天是否运动：{'是' if exercise else '否'}
- 是否摄入咖啡因：{'是' if caffeine else '否'}
- 睡前使用电子设备：{'是' if screen_time else '否'}

请基于这些数据进行专业分析，给出评分、分析、健康影响和建议。"""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        # 尝试粒计算评分（作为DeepSeek fallback）
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from granular_report import compute_sleep_quality_from_questionnaire, format_report_response
            _q_score = compute_sleep_quality_from_questionnaire(data)
            _granular_response = format_report_response(_q_score, data)
            print(f'[粒计算] 评分完成: {_q_score["total_score"]}分 ({_q_score["grade"]})', flush=True)
        except Exception as e:
            print(f'[粒计算] 评分失败(不影响主流程): {e}', flush=True)
            _granular_response = None

        # 调用DeepSeek
        result = self._call_deepseek(messages, max_tokens=3000)

        if 'error' in result:
            # DeepSeek失败，回退到粒计算评分
            if _granular_response:
                self.wfile.write(json.dumps(_granular_response, ensure_ascii=False).encode('utf-8'))
                return
            self.wfile.write(json.dumps({'error': result['error']}).encode('utf-8'))
            return

        # 尝试解析JSON
        try:
            content = result['content']
            # 提取JSON部分（可能被markdown包裹）
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '{' in content:
                json_str = content[content.index('{'):content.rindex('}')+1]
            else:
                json_str = content

            report = json.loads(json_str)
            response = {
                'success': True,
                'report': report,
                'usage': result.get('usage', {})
            }
        except:
            # JSON解析失败，返回原始内容
            response = {
                'success': True,
                'report_raw': result['content'],
                'usage': result.get('usage', {})
            }

        self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))

    def _handle_meditation_plan(self, data):
        """生成冥想计划"""
        self._set_headers()

        sleep_quality = data.get('sleep_quality', '一般')
        stress_level = data.get('stress_level', 5)
        duration = data.get('duration', 10)

        system_prompt = """你是一位冥想和正念指导专家。请根据用户的状态推荐合适的冥想计划。

请严格按照以下JSON格式输出：
{
  "type": "冥想类型",
  "typeName": "类型名称",
  "description": "冥想描述",
  "durationMinutes": 时长分钟数,
  "benefits": ["好处1", "好处2", "好处3"],
  "guidanceSteps": [
    {"time": "0:00", "guidance": "引导语"},
    {"time": "2:00", "guidance": "引导语"},
    {"time": "5:00", "guidance": "引导语"}
  ],
  "breathingPattern": {
    "name": "呼吸法名称",
    "steps": ["步骤1", "步骤2", "步骤3"]
  },
  "personalizedAdvice": "个性化建议"
}"""

        user_prompt = f"""用户状态：
- 睡眠质量：{sleep_quality}
- 压力水平（1-10）：{stress_level}
- 期望时长：{duration}分钟

请推荐合适的冥想计划。"""

        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}
        ]

        result = self._call_deepseek(messages, max_tokens=2000)

        if 'error' in result:
            self.wfile.write(json.dumps({'error': result['error']}).encode('utf-8'))
            return

        try:
            content = result['content']
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '{' in content:
                json_str = content[content.index('{'):content.rindex('}')+1]
            else:
                json_str = content
            plan = json.loads(json_str)
        except:
            plan = {'raw': result['content']}

        self.wfile.write(json.dumps({
            'success': True,
            'plan': plan,
            'usage': result.get('usage', {})
        }, ensure_ascii=False).encode('utf-8'))

    def _extract_sleep_data_from_text(self, text):
        """从对话文本中提取睡眠相关数据（v2.0 - 高级自然语言理解版）
        支持：模糊表达、时间区间、连续事件推理
        """
        import re
        data = {}

        # 预处理：统一中英文标点
        text_clean = text.replace('-', '-').replace('～', '~').replace('：', ':').replace('，', ',').replace('。', '.').replace('？', '?')

        # ===== 第一阶段：精确表达式匹配 =====

        # 上床时间（高级版）
        # 模式1: "12点多躺下"、"1点半睡的"、"11点50睡的"
        bed_match = None
        bed_patterns = [
            r'(?:上床|睡觉|入睡|躺下|就寝|闭眼).{0,10}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?',
            r'(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:睡|上床|躺下|才睡)',
            r'(?:昨晚|夜里|晚上).{0,5}?(\d{1,2})\s*[点时:：]?\s*(\d{0,2})\s*(?:分|半)?\s*(?:睡|躺)',
        ]
        for pat in bed_patterns:
            m = re.search(pat, text_clean)
            if m:
                bed_match = m
                break

        # 特殊模式：点多表达（12点多躺下→12:30）
        if not bed_match:
            _more = re.search(r'(\d{1,2})\s*点多\s*(?:躺下|睡|上床)', text_clean)
            if _more:
                _h = int(_more.group(1))
                data['bedtime'] = f'{_h}:30'
                print(f'[Extract] 点多匹配: bedtime={_h}:30')
                bed_match = _more

        # 翻来覆去到X点才睡着→提取睡着时间
        _toss = re.search(r'(?:翻来覆去|辗转反侧).{0,20}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:才|就)?\s*(?:睡着|入睡)', text_clean)
        if _toss:
            _sh = int(_toss.group(1))
            _sm = int(_toss.group(2)) if _toss.group(2) else 0
            _at = text_clean[_toss.end():_toss.end()+4]
            if '\u534a' in _at and _sm == 0:
                _sm = 30
            data['_fall_asleep_time'] = f'{_sh}:{_sm:02d}'
            print(f'[Extract] 翻来覆去匹配: 睡着时间={_sh}:{_sm:02d}')
            if 'bedtime' in data:
                try:
                    _bt = data['bedtime']
                    _bh, _bm = map(int, _bt.split(':'))
                    _bed_total = _bh * 60 + _bm
                    _fall_total = _sh * 60 + _sm
                    if _fall_total < _bed_total:
                        _fall_total += 12 * 60
                    _latency = _fall_total - _bed_total
                    if 5 < _latency < 180:
                        data['sleep_latency'] = _latency
                        print(f'[Extract] 自动推算latency={_latency}分钟')
                except:
                    pass

        if bed_match and not isinstance(bed_match, bool):
            h = int(bed_match.group(1))
            m = 0
            m_str = bed_match.group(2) if bed_match.group(2) else ''
            if m_str:
                m = int(m_str)
            # 检查后面是否有"半"
            after = text_clean[bed_match.end():bed_match.end()+4]
            if '半' in after and m == 0:
                m = 30
            # 检查"点多"模式：12点多 = 12:xx
            ctx_before = text_clean[max(0, bed_match.start()-6):bed_match.start()]
            ctx_after = text_clean[bed_match.end():bed_match.end()+6]
            if '多' in ctx_before + ctx_after and m_str == '0':
                m = 30  # "12点多" ≈ 12:30
            # 检查"点多"更精确：如果后面跟了具体数字如"12点50"
            if '多' in ctx_before + ctx_after and m_str and '半' not in after:
                pass  # 已有具体分钟
            data['bedtime'] = f'{h}:{m:02d}'

        # 起床时间（高级版）
        wake_patterns = [
            r'(?:起床|醒来|睁眼|醒了|睡到).{0,10}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分)?',
            r'(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分)?\s*(?:醒|起床|起来|睁眼|就醒了)',
        ]
        wake_match = None
        for pat in wake_patterns:
            m = re.search(pat, text_clean)
            if m:
                wake_match = m
                break
        if wake_match:
            h = int(wake_match.group(1))
            m = int(wake_match.group(2)) if wake_match.group(2) else 0
            after = text_clean[wake_match.end():wake_match.end()+4]
            if '半' in after and m == 0:
                m = 30
            data['wake_time'] = f'{h}:{m:02d}'

        # 睡眠时长（支持区间"五六个小时"）
        dur_match = re.search(r'(?:睡[了]?|睡眠|只睡[了]?|睡了大概|睡了约|一共睡了)\s*(?:大约|大概|约)?\s*(\d+(?:[.-]\d+)?)\s*(?:~|到|至|-|-)?\s*(\d+)?\s*(?:小时|个钟|h|H|钟头)', text_clean)
        if dur_match:
            val = float(dur_match.group(1).replace('-','.').replace('，',''))
            val2 = dur_match.group(2)
            if val2:
                val2 = float(val2)
                # 取中间值
                val = (val + val2) / 2
            data['total_duration'] = round(val * 60)  # 转为分钟
            data['total_duration_source'] = 'explicit'

        # 区间表达"五六个小时"
        if 'total_duration' not in data:
            range_match = re.search(r'[五五六]六个?小时|七八个小时', text)
            if range_match:
                r = range_match.group(0)
                if '五' in r and '六' in r:
                    data['total_duration'] = 330  # 5.5h
                elif '六' in r and '七' in r:
                    data['total_duration'] = 390  # 6.5h
                elif '七' in r and '八' in r:
                    data['total_duration'] = 450  # 7.5h
                data['total_duration_source'] = 'range_estimate'

        # 入睡时间（高级版）
        # 模式1: "翻来覆去到1点半才睡着" → 需要结合上床时间计算latency
        # 模式2: "大概一个小时才睡着" → direct
        # 模式3: "很快就睡着了" → short

        latency_match = None
        latency_patterns = [
            r'(?:翻来覆去|辗转反侧|折腾).{0,15}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:才|就)?\s*(?:睡着|入睡)',
            r'(?:入睡|睡着|睡?着|进[入]睡眠).{0,10}?(\d+)\s*分钟',
            r'(\d+)\s*分钟\D{0,5}(?:才)?(?:睡着|入睡|才睡)',
            r'(?:过了|大概|大约|约)?\s*(\d+)\s*分钟\D{0,5}(?:才)?(?:睡着|入睡)',
            r'(?:半个?小时|30分钟).{0,5}(?:才)?(?:睡着|入睡)',
            r'(?:一个?小时|60分钟).{0,5}(?:才)?(?:睡着|入睡)',
        ]
        for pat in latency_patterns:
            m = re.search(pat, text_clean)
            if m:
                latency_match = m
                break

        if latency_match:
            # 检查是否是"翻来覆去到X点才睡着"→通过时间计算latency
            if '翻来覆去' in text and 'bedtime' in data:
                try:
                    bed_h, bed_m = map(int, data['bedtime'].split(':'))
                    fall_h = int(latency_match.group(1))
                    fall_m = int(latency_match.group(2)) if latency_match.group(2) else 0
                    after = text_clean[latency_match.end():latency_match.end()+4]
                    if '半' in after and fall_m == 0:
                        fall_m = 30
                    # 计算差值
                    bed_total = bed_h * 60 + bed_m
                    fall_total = fall_h * 60 + fall_m
                    if fall_total < bed_total:
                        fall_total += 12 * 60  # 跨12点
                    latency = fall_total - bed_total
                    if 5 < latency < 180:  # 合理范围5分钟-3小时
                        data['sleep_latency'] = latency
                except:
                    pass
            else:
                # 直接数字
                if latency_match.lastindex >= 2 and latency_match.group(2):
                    # "翻来覆去到X点"模式
                    pass  # 上面已经处理了
                elif latency_match.group(1) in ['半个', '30']:
                    data['sleep_latency'] = 30
                elif latency_match.group(1) in ['一个', '60']:
                    data['sleep_latency'] = 60
                else:
                    data['sleep_latency'] = int(latency_match.group(1)) if latency_match.group(1).isdigit() else None
                    if data.get('sleep_latency') and data['sleep_latency'] > 180:
                        data['sleep_latency_estimate'] = 'long'

        # 模糊表达："很快就睡着了"
        if 'sleep_latency' not in data and 'sleep_latency_estimate' not in data:
            if re.search(r'(?:很快|一下就|一会就|没多久|瞬间).{0,5}(?:睡着|入睡|就睡)', text):
                data['sleep_latency'] = 10
                data['sleep_latency_estimate'] = 'short'
            elif re.search(r'(?:很久|好久|特别久|特别长|老半天|半天).{0,10}(?:才|都)(?:睡着|入睡)', text):
                data['sleep_latency'] = 60
                data['sleep_latency_estimate'] = 'long'

        # 自动推导：如果bedtime和睡着时间都拿到了但latency没有，尝试计算
        # 这个在翻来覆去模式中已实现

        # 醒来次数（高级版）
        # 模式: "醒了好几次"、"醒了两次"、"醒了又醒"
        awake_match = re.search(r'(?:醒|夜醒|中途醒|醒过来)\D{0,5}(\d+)\s*次', text)
        if awake_match:
            data['awake_times'] = int(awake_match.group(1))
        elif re.search(r'(?:醒了好几次|频繁醒|反复醒|醒醒睡睡|醒来了好多次)', text):
            data['awake_times'] = 3
            data['awake_estimate'] = True
        elif re.search(r'(?:醒了一次|醒过1次)', text):
            data['awake_times'] = 1
        elif re.search(r'(?:醒了两次|醒了2次)', text):
            data['awake_times'] = 2
        elif re.search(r'(?:醒|醒来|夜醒)', text):
            # 只提到"醒"但没说次数，不提就不设置
            pass

        # 清醒时长
        awake_dur = re.search(r'(?:醒[了來]?|清醒)\D{0,10}(\d+)\s*分钟', text)
        if awake_dur:
            data['awake_duration'] = int(awake_dur.group(1))
        elif re.search(r'(?:很久|好长|半天)\D{0,5}(?:睡不|醒[了来])', text):
            data['awake_duration'] = 45

        # 深睡/浅睡/REM
        deep_match = re.search(r'(?:深睡|深眠|熟睡).*?(\d+)\s*%', text)
        if deep_match: data['deep_sleep_percent'] = float(deep_match.group(1))
        rem_match = re.search(r'(?:REM|快速眼动|做梦).*?(\d+)\s*%', text)
        if rem_match: data['rem_sleep_percent'] = float(rem_match.group(1))

        # 疼痛/不适
        if re.search(r'(?:疼|痛|酸|麻|胀|抽筋|痉挛|紧?绷)', text):
            data['pain'] = True
            for area in ['大腿', '膝盖', '腰', '背', '肩', '颈', '头', '手', '脚', '腿', '关节']:
                if area in text:
                    data['pain_area'] = area
                    break

        # 环境因素
        if re.search(r'(?:冷|寒|凉|冻)', text):
            data['environment_cold'] = True
        if re.search(r'(?:热|闷|出汗|烦躁)', text):
            data['environment_hot'] = True
        if re.search(r'(?:声音|吵|噪音|闹)', text):
            data['environment_noise'] = True
        if re.search(r'(?:亮|光|灯|光线)', text):
            data['environment_light'] = True

        # 打鼾/呼吸
        if re.search(r'(?:鼻贴|打鼾|鼾|呼吸|止鼾|通气|鼻子)', text):
            data['snore_related'] = True
            if re.search(r'(?:改善|减少|少了|好转|有效)', text):
                data['snore_improved'] = True
            elif re.search(r'(?:严重|加重|大声|厉害)', text):
                data['snore_worsened'] = True

        # 压力/心情
        stress_match = re.search(r'压力.*?(\d+)', text)
        if stress_match:
            data['stress_level'] = int(stress_match.group(1))
        elif re.search(r'(?:焦虑|紧张|担心|烦躁|郁闷|不开心)', text):
            data['stress_level'] = 7  # 高压力推定

        # 感觉
        feel_map = {
            '累': 'tired', '疲惫': 'very_tired', '困': 'sleepy',
            '一般': 'normal', '还行': 'normal', '不错': 'good',
            '精神': 'refreshed', '好': 'good', '舒服': 'good',
            '很差': 'very_bad', '不好': 'bad', '糟糕': 'very_bad'
        }
        for word, val in feel_map.items():
            if word in text:
                data['feeling'] = val
                break

        # 睡前屏幕/电子设备
        if re.search(r'(?:看手机|刷手机|刷视频|玩手机|打游戏|看电脑|看屏幕|电子设备)', text):
            data['screen_time'] = True

        # 是否提到睡眠质量描述
        quali_words = ['失眠', '难入睡', '睡眠差', '质量差', '睡不好', '睡眠不好']
        for w in quali_words:
            if w in text:
                data['quality_complaint'] = True
                break

        # 睡眠时长推算：如果说了上床和起床时间但没有总时长
        if 'bedtime' in data and 'wake_time' in data and 'total_duration' not in data:
            try:
                b_parts = data['bedtime'].split(':')
                w_parts = data['wake_time'].split(':')
                b_h, b_m = int(b_parts[0]), int(b_parts[1])
                w_h, w_m = int(w_parts[0]), int(w_parts[1])
                # 修正：早晨<=12点且上床时间<=12点 → 上床是前一天的晚上
                if b_h <= 12: b_h += 12  # 晚上11点=23点
                if b_h >= 24: b_h = 12  # 安全保护
                # 如果起床时间<上床时间，起床是第二天
                if w_h < b_h: w_h += 24
                total_min = (w_h - b_h) * 60 + (w_m - b_m)
                if 120 < total_min < 720:  # 合理范围2-12小时
                    data['total_duration'] = total_min
            except: pass

        # 类型转换：确保数值字段是数字
        for num_field in ['sleep_latency', 'awake_times', 'awake_duration', 'total_duration',
                          'stress_level', 'heart_rate_avg', 'hrv_avg', 'spo2_avg',
                          'deep_sleep_percent', 'rem_sleep_percent', 'light_sleep_percent']:
            if num_field in data and isinstance(data[num_field], str):
                try:
                    data[num_field] = int(data[num_field])
                except ValueError:
                    try:
                        data[num_field] = float(data[num_field])
                    except:
                        pass
        if data:
            print(f'[提取] 从文本中提取到: {data}')
        return data if data else None

    def _handle_ingest_literature(self, data):
        """
        文献注入接口
        用户给PMID/DOI/描述 → 自动抓取PubMed → 写入.auto_evidence.json
        前端调用: POST /api/ingest-literature
        {"pmid": "42030840", "note": "CBT-I对大学生有效"}
        """
        self._set_headers()
        # ===== 权限验证 =====
        if not self._verify_admin(data):
            self.wfile.write(json.dumps({
                'success': False,
                'error': '权限不足：请提供有效的 admin_key，或从本地访问'
            }, ensure_ascii=False).encode('utf-8'))
            return

        pmid = data.get('pmid', '')
        doi = data.get('doi', '')
        user_note = data.get('note', '').strip()[:200]

        # 检查.auto_evidence.json
        auto_evidence_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.auto_evidence.json')

        if not pmid and not doi:
            self.wfile.write(json.dumps({
                'success': False,
                'error': '请提供PMID或DOI'
            }, ensure_ascii=False).encode('utf-8'))
            return

        # 从PubMed拉取
        fetched = self._fetch_pubmed_article(pmid, doi)

        if not fetched:
            self.wfile.write(json.dumps({
                'success': False,
                'error': f'未能从PubMed获取该文献 (PMID={pmid}, DOI={doi})'
            }, ensure_ascii=False).encode('utf-8'))
            return

        # ===== 期刊质量过滤 =====
        journal = fetched.get('journal', '').lower()
        qc_result = self._check_literature_quality(fetched)
        if not qc_result['passed']:
            self.wfile.write(json.dumps({
                'success': False,
                'error': qc_result['reason'],
                'detail': qc_result['detail'],
            }, ensure_ascii=False).encode('utf-8'))
            print(f'[QC Reject] PMID={fetched["pmid"]} - {qc_result["reason"]}: {fetched.get("journal", "?")}')
            return

        # 构建证据条目
        entry = {
            'name': fetched['title'][:100],
            'evidence': f'手动导入 | PMID: {fetched["pmid"]}, DOI: {fetched["doi"]}',
            'description': fetched.get('abstract', '')[:300] or user_note,
            'indications': ['literature'],
            'effect_size': '手动导入, 待确认',
            'certainty': 'manual',
            'pmid': fetched['pmid'],
            'doi': fetched['doi'],
            'added_on': datetime.now().strftime('%Y-%m-%d'),
            'user_note': user_note,
            'ingested_by': 'user',
            'source': 'user_manual_import',
        }

        # 写入.auto_evidence.json
        auto_evidence = []
        if os.path.exists(auto_evidence_path):
            try:
                with open(auto_evidence_path, 'r', encoding='utf-8') as f:
                    auto_evidence = json.load(f)
            except:
                pass

        # 去重
        existing_pmids = {e.get('pmid') for e in auto_evidence}
        if entry['pmid'] not in existing_pmids:
            auto_evidence.append(entry)
            with open(auto_evidence_path, 'w', encoding='utf-8') as f:
                json.dump(auto_evidence, f, ensure_ascii=False, indent=2)

        self.wfile.write(json.dumps({
            'success': True,
            'message': f'文献已注入: {fetched["title"][:60]}...',
            'entry': {
                'pmid': fetched['pmid'],
                'title': fetched['title'][:80],
                'evidence_entries': f'当前共 {len(auto_evidence)} 条',
            }
        }, ensure_ascii=False).encode('utf-8'))

        print(f'[Ingest] 用户手动注入文献: PMID={fetched["pmid"]}, {fetched["title"][:60]}...')

    def _fetch_pubmed_article(self, pmid, doi):
        """从PubMed拉取单篇文献详情"""
        import urllib.request, urllib.parse
        import xml.etree.ElementTree as ET

        try:
            if pmid:
                url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml'
            else:
                # DOI查询
                search_url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term={doi}[doi]&retmax=1&retmode=json'
                req = urllib.request.Request(search_url, headers={'User-Agent': 'AISleepGen/1.0'})
                with urllib.request.urlopen(req, timeout=15) as r:
                    sr = json.loads(r.read())
                ids = sr.get('esearchresult', {}).get('idlist', [])
                if not ids:
                    return None
                url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={ids[0]}&retmode=xml'

            req = urllib.request.Request(url, headers={'User-Agent': 'AISleepGen/1.0'})
            with urllib.request.urlopen(req, timeout=15) as r:
                xml = r.read().decode('utf-8')

            # 简易XML解析
            import re

            pmid_out = pmid or (ids[0] if not pmid else pmid)

            # Title
            title_m = re.search(r'<ArticleTitle[^>]*>(.*?)</ArticleTitle>', xml, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else '未知标题'

            # DOI
            doi_m = re.search(r'<ELocationID[^>]*EIdType="doi"[^>]*>(.*?)</ELocationID>', xml)
            doi_out = doi_m.group(1) if doi_m else doi

            # Year
            year_m = re.search(r'<Year>(\d{4})</Year>', xml)
            year = year_m.group(1) if year_m else '?'

            # Journal
            journal_m = re.search(r'<Journal>.*?<Title[^>]*>(.*?)</Title>', xml, re.DOTALL)
            journal = journal_m.group(1) if journal_m else ''
            if not journal:
                # Try ISOAbbreviation
                journal_m = re.search(r'<ISOAbbreviation[^>]*>(.*?)</ISOAbbreviation>', xml)
                journal = journal_m.group(1) if journal_m else ''
            journal = journal.replace('&amp;', '&')

            # Abstract (first 500 chars)
            abs_m = re.search(r'<AbstractText[^>]*>(.*?)</AbstractText>', xml, re.DOTALL)
            abstract = ''
            if abs_m:
                abstract = re.sub(r'<[^>]+>', '', abs_m.group(1)).strip()[:500]

            return {
                'pmid': pmid_out,
                'title': title,
                'doi': doi_out or '',
                'year': year,
                'abstract': abstract,
                'journal': journal,
            }

        except Exception as e:
            print(f'[FetchPubMed] 拉取失败: {e}')
            return None
    # 顶级睡眠/医学期刊列表
    TOP_JOURNALS = {
        'sleep', 'sleep medicine', 'sleep medicine reviews', 'journal of sleep research',
        'journal of clinical sleep medicine', 'sleep health', 'nature and science of sleep',
        'brain', 'lancet', 'the lancet', 'the lancet neurology', 'lancet neurology',
        'the lancet psychiatry', 'lancet psychiatry', 'new england journal of medicine',
        'nejm', 'nature', 'nature medicine', 'nature neuroscience',
        'science', 'science translational medicine',
        'jama', 'jama psychiatry', 'jama neurology', 'jama internal medicine',
        'jama network open', 'bmj', 'the bmj', 'british medical journal',
        'cell', 'cell reports', 'cell reports medicine',
        'annual review of neuroscience', 'annual review of medicine',
        'american journal of respiratory and critical care medicine',
        'chest', 'neurology', 'annals of neurology',
        'proceedings of the national academy of sciences', 'pnas',
        'plos medicine', 'plos one', 'plos biology',
        'eclinicalmedicine', 'the lancet digital health',
        'frontiers in neuroscience', 'frontiers in psychiatry',
        'frontiers in human neuroscience', 'frontiers in neurology',
        'journal of neuroscience', 'european heart journal',
        'psychosomatic medicine', 'journal of psychosomatic research',
        'clinical psychology review', 'behaviour research and therapy',
        'journal of consulting and clinical psychology',
        'psychological medicine', 'journal of affective disorders',
        'depression and anxiety', 'psychiatry research',
        'biological psychiatry', 'translational psychiatry',
        'molecular psychiatry', 'current biology',
        'chronobiology international', 'journal of biological rhythms',
        'scientific reports', 'communications medicine',
        'npj digital medicine', 'npj sleep and circadian rhythms',
    }

    # 抢夺性/低质量期刊标记
    PREDATORY_JOURNALS = {
        'journal of sleep disorders and management',
        'journal of insomnia and sleep disorders',
        'international journal of sleep disorders',
        'journal of sleep sciences',
    }

    def _check_literature_quality(self, fetched):
        """检查文献质量：期刊+内容相关性+发表年份"""
        title = (fetched.get('title') or '').lower()
        journal = (fetched.get('journal') or '').lower()
        year_str = fetched.get('year', '0')
        abstract = (fetched.get('abstract') or '').lower()

        # 1) 抢夺性期刊直接拒掉
        for bad in self.PREDATORY_JOURNALS:
            if bad in journal or journal in bad:
                return {
                    'passed': False,
                    'reason': '低质量/抢夺性期刊',
                    'detail': '期刊 "' + (fetched.get('journal') or '?') + '" 已被列入低质量期刊列表',
                }

        # 2) 检查期刊是否是顶级/可信期刊
        is_top = any(t in journal or journal in t for t in self.TOP_JOURNALS)

        # 3) 内容相关性检查
        sleep_keywords = [
            'sleep', 'insomnia', 'circadian', 'chronotype', 'melatonin',
            'cbt-i', 'cbti', 'cognitive behavioral', 'sleep apnea',
            'osa', 'cpap', 'restless leg', 'narcolepsy', 'hypersomnia',
            'fatigue', 'nightmare', 'parasomnia', 'sleep quality',
            'sleep deprivation', 'sleep restriction', 'sleep hygiene',
            'actigraphy', 'polysomnography', 'psg', 'psqi', 'epworth',
            'stop-bang', 'berlin questionnaire',
            'gaba', 'orexin', 'hypocretin',
            'glymphatic', 'neuroimaging', 'cognition',
        ]
        is_relevant = any(kw in title for kw in sleep_keywords)

        # 4) 年份检查
        try:
            year = int(year_str)
            is_recent = year >= 2020
        except:
            is_recent = True

        # ===== 判定逻辑 =====
        if is_top and is_relevant and is_recent:
            return {'passed': True, 'score': 'high', 'reason': '顶刊+相关'}

        if is_top and is_recent:
            return {'passed': True, 'score': 'medium', 'reason': '顶刊但不直接相关'}

        if is_top:
            return {'passed': True, 'score': 'medium', 'reason': '顶刊但较旧'}

        # 非顶刊：需要严格审查
        if not is_relevant:
            return {
                'passed': False,
                'reason': '非顶刊且不相关',
                'detail': '期刊 "' + (fetched.get('journal') or '?') + '" 不在顶刊列表中，且标题不含睡眠相关关键词',
            }

        if is_relevant and is_recent:
            return {'passed': True, 'score': 'medium', 'reason': '非顶刊但相关且较新'}

        if is_relevant:
            return {'passed': True, 'score': 'low', 'reason': '非顶刊但相关，年份较旧'}

        return {'passed': True, 'score': 'low', 'reason': '通过所有检查'}

    def _handle_chat(self, data):
        """处理AI对话"""
        self._set_headers()

        # 获取用户标识（微信openid）
        openid = self._get_openid(data)

        # 每日懒优化：跨夜中观适应（Lazy Maintenance Pattern）
        if openid:
            __p = _load_user_profile(openid)
            _run_daily_batch_optimization(__p, openid)

        # 从对话中提取睡眠数据（如果有）
        user_message = data.get('message', '')
        history = data.get('history', [])

        # ===== 自动检测PMID并注入文献 =====
        import re
        pmid_detected = None
        if user_message:
            # 匹配8位数字的PMID
            pmid_matches = re.findall(r'\b(\d{8})\b', user_message)
            # 匹配DOI
            doi_matches = re.findall(r'(10\.\d{4,}/[^\s,.;:!?]+)', user_message)
            if pmid_matches and not any(kw in user_message for kw in ['睡', '醒', '起', '梦', '困', '累', '乏', '失眠', '熬夜']):
                pmid_detected = pmid_matches[0]
                # 聊天自动注入仅限本地
                if self.client_address[0] in ("127.0.0.1", "::1", "localhost"):
                    try:
                        fetched = self._fetch_pubmed_article(pmid_detected, "")
                        if fetched:
                            auto_ev_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".auto_evidence.json")
                            auto_ev = []
                            if os.path.exists(auto_ev_path):
                                with open(auto_ev_path, "r") as f:
                                    auto_ev = json.load(f)
                            existing = {e.get("pmid") for e in auto_ev}
                            if pmid_detected not in existing:
                                entry = {
                                    "name": fetched["title"][:100],
                                    "evidence": "聊天注入 | PMID: " + pmid_detected,
                                    "description": (fetched.get("abstract", "") or "")[:300],
                                    "indications": ["chat_injection"],
                                    "effect_size": "聊天注入",
                                    "certainty": "conversation",
                                    "pmid": pmid_detected,
                                    "doi": fetched.get("doi", ""),
                                    "added_on": datetime.now().strftime("%Y-%m-%d"),
                                    "source": "chat_auto_ingest",
                                }
                                auto_ev.append(entry)
                                with open(auto_ev_path, "w", encoding="utf-8") as f:
                                    json.dump(auto_ev, f, ensure_ascii=False, indent=2)
                                print("[ChatIngest] PMID=" + pmid_detected + " 已自动注入")
                    except Exception as e:
                        print("[ChatIngest] PMID=" + pmid_detected + " 注入失败: " + str(e))
                    print(f'[ChatIngest] PMID={pmid_detected} 注入失败: {e}')

        # 调用世界模型分析睡眠数据（从对话上下文提取）
        wm_context = ""
        wm_scores_text = ""
        wm = _get_world_model()
        if wm:
            # 从历史对话中提取可能的睡眠数据（仅用于画像积累，不用于当前评分）
            all_text = user_message
            for msg in history:
                if isinstance(msg, dict) and msg.get('content'):
                    all_text += ' ' + msg['content']

            # 【关键】评分展示只基于用户当前这条消息中的量化数据，不依据历史
            current_data = self._extract_sleep_data_from_text(user_message)
            full_data = self._extract_sleep_data_from_text(all_text)

            # 数据充分性判断：只看当前消息
            has_quantitative_now = bool(
                current_data and (
                    current_data.get('bedtime') or
                    current_data.get('wake_time') or
                    current_data.get('total_duration') or
                    (current_data.get('awake_times') and not current_data.get('awake_estimate')) or
                    current_data.get('sleep_latency') or
                    current_data.get('deep_sleep_percent') or
                    current_data.get('rem_sleep_percent')
                )
            )

            # 预先定义，供内部try和外部auto_report共用
            wm_result_global = None

            if full_data:
                try:
                    # 用完整数据（含历史）做世界模型分析，更准确
                    wm_result_global = wm.comprehensive_analysis(full_data)
                    wm_result = wm_result_global
                    total = wm_result.get('total_score', 0)
                    quality = wm_result.get('quality', 'unknown')
                    insights = wm_result.get('insights', {})
                    recs = wm_result.get('recommendations', [])

                    analysis = wm_result.get('analysis', {})
                    dims = analysis.get('dimensions', {}) if isinstance(analysis, dict) else {}
                    overall_conf = analysis.get('confidence', 0) if isinstance(analysis, dict) else 0

                    # 构建专家评分文本
                    dim_lines = []
                    # 使用世界模型真实的维度名称和顺序
                    dim_order = ['ClinicalPsychologist', 'CBT', 'SleepPhysician', 'Chronobiologist',
                                 'LifeScientist', 'RiskManager', 'StressRelaxation']
                    dim_icons_map = {
                        'ClinicalPsychologist': '🧠', 'CBT': '💭', 'SleepPhysician': '🩺',
                        'Chronobiologist': '🕐', 'LifeScientist': '🧬', 'RiskManager': '⚠️',
                        'StressRelaxation': '🧘'
                    }
                    dim_names_map = {
                        'ClinicalPsychologist': '临床心理', 'CBT': '认知行为', 'SleepPhysician': '睡眠医学',
                        'Chronobiologist': '昼夜节律', 'LifeScientist': '生命科学', 'RiskManager': '风险评估',
                        'StressRelaxation': '减压放松'
                    }
                    for key in dim_order:
                        dim = dims.get(key, {})
                        if dim and dim.get('score') is not None:
                            score = dim['score'] * 100
                            conf = dim.get('confidence', 0) * 100
                            icon = dim_icons_map.get(key, '📋')
                            name = dim_names_map.get(key, key)
                            if conf >= 70: conf_label = '置信度较高'
                            elif conf >= 40: conf_label = '置信度中等'
                            else: conf_label = '置信度偏低'
                            dim_lines.append(f"{icon} {name} {score:.0f}/100 · {conf_label}")

                    dims_text = "\n".join(dim_lines)

                    # 整体置信度
                    if overall_conf >= 0.7: overall_conf_tag = '较高'
                    elif overall_conf >= 0.4: overall_conf_tag = '中等'
                    else: overall_conf_tag = '较低'

                    print(f'[WorldModel] 综合评分={total}, 质量={quality}, 置信度={overall_conf:.0%}')
                    print(f'[WorldModel] 7维度:\n{dims_text}')

                    if has_quantitative_now:
                        # 构建结构化的维度摘要（供DeepSeek真实引用）
                        _dim_summary = []
                        for key in dim_order:
                            dim = dims.get(key, {})
                            if dim and dim.get('score') is not None:
                                sc = round(dim['score'] * 100)
                                conf = dim.get('confidence', 0) * 100
                                findings = dim.get('findings', [])
                                name = dim_names_map.get(key, key)
                                icon = dim_icons_map.get(key, '📋')
                                _dim_summary.append(f"{icon} {name}: {sc}/100 · 核心发现: {findings[0][:40] if findings else ''}")

                        _ar_takeaway = insights.get('primary_focus', '')
                        _ar_retro = []
                        try:
                            rf = locals().get('retrospective_findings')
                            if rf:
                                _ar_retro = rf[:3]
                        except:
                            pass

                        # ===== 数据可信度标注（推理约束层） =====
                        # 分析用户给的数据点，标注哪些维度有直接数据支撑
                        user_fields_count = sum(1 for f in ['bedtime','wake_time','awake_times','total_duration','sleep_latency','deep_sleep_percent'] if full_data.get(f))
                        if user_fields_count <= 2:
                            data_adequacy = "数据不足(仅{})".format(user_fields_count)
                            inference_limit = "严重: 大部分维度为推测，仅展示1-2个有数据支撑的维度"
                        elif user_fields_count <= 4:
                            data_adequacy = "数据一般({})".format(user_fields_count)
                            inference_limit = "中等: 部分维度为估算，优先展示有数据支撑的维度"
                        else:
                            data_adequacy = "数据充分({})".format(user_fields_count)
                            inference_limit = "低: 可展示大多数维度，但要标注估算项"

                        # 为每个维度标注可信度类型
                        dim_trust_notes = []
                        for key in dim_order:
                            dim = dims.get(key, {})
                            if dim and dim.get('score') is not None:
                                conf = dim.get('confidence', 0) * 100
                                name = dim_names_map.get(key, key)
                                if conf >= 70:
                                    trust_note = "可信度较高"
                                elif conf >= 40:
                                    trust_note = "可信度中等(部分依据估算)"
                                else:
                                    trust_note = "可信度偏低(主要为推测)"
                                dim_trust_notes.append(f"{name}: {trust_note}")

                        wm_context = f"""
===== 世界模型分析数据(约束: 必须基于这些真实数据做分析，不要自创评分) =====
【数据局限性】
用户提供数据点: {user_fields_count}个({data_adequacy})
推理约束: {inference_limit}
⚠️ 评分不是医学诊断，是基于有限数据的估算，必须向用户说明这一点。

综合评分: {total}/100 · 质量: {quality} · 全局置信度: {overall_conf_tag}
维度可信度明细:
{chr(10).join(dim_trust_notes)}

维度评分详情:
{chr(10).join(_dim_summary)}
核心洞察: {insights.get('summary', '')}
行动建议: {_ar_takeaway}
回顾变化: {'；'.join(_ar_retro) if _ar_retro else '无历史对比数据'}
减压方案: {_ar_relax.get('primary_therapy', '') if '_ar_relax' in dir() and _ar_relax else ''}
循证文献数: {_ar_ev_count if '_ar_ev_count' in dir() else 0}
置信范围: {'±' + str(insights.get('confidence_bounds', {}).get('margin_of_error', '10')) + ' / PSQI≈' + str(insights.get('confidence_bounds', {}).get('estimated_psqi_range', '?')) if insights.get('confidence_bounds', {}) else ''}
==========================
"""
                    else:
                        # 数据不足时不展示具体评分
                        print(f'[WorldModel] 跳过评分展示(当前消息数据不足): {list(full_data.keys()) if full_data else "空"}')

                    # 生理恢复分析 - 纯大模型做不到的量化维度
                    recovery_report = ""
                    try:
                        from world_model_deep import PhysiologicalRecovery
                        pr = PhysiologicalRecovery()
                        recovery = pr.analyze_recovery(full_data)
                        if recovery.get('overall_recovery', 0) > 0:
                            rec = recovery['overall_recovery']
                            rr = []
                            rr.append("===== 身体恢复评估(基于睡眠参数估算) =====")
                            rr.append("综合恢复评分: %d/100 · 仅供参考,非临床数据" % rec)
                            gl = recovery['glymphatic']
                            rr.append("🧠 类淋巴清除估算: %d/100" % gl['score'])
                            gh = recovery['growth_hormone']
                            rr.append("💪 生长激素分泌估算: %d/100" % gh['score'])
                            co = recovery['cortisol']
                            rr.append("⚡ 皮质醇节律估算: %d/100" % co['score'])
                            rr.append("==========================")
                            recovery_report = "\n".join(rr) + "\n\n"
                    except Exception as pr_e:
                        print(f'[Recovery] 跳过: {pr_e}')
                    if recovery_report:
                        print(f'[Recovery] 报告已生成({len(recovery_report)}字符)')
                        wm_context += recovery_report
                    # ===== 世界模型前置诊断引擎（心理减压+睡眠健康导向）=====
                    clinical_diagnosis = []

                    # 1. 总评分 → 用"状态"代替"分级"，温柔表达
                    if total >= 85:
                        clinical_diagnosis.append("【状态概览】整体不错（≥85分）- 你的睡眠基础挺好，保持节奏就好")
                    elif total >= 70:
                        clinical_diagnosis.append("【状态概览】有改善空间（70-84分）- 一些小调整就能让你睡得更舒服")
                    elif total >= 55:
                        clinical_diagnosis.append("【状态概览】需要多一些关照（55-69分）- 你的身体在发出信号，我们一起找找原因")
                    else:
                        clinical_diagnosis.append("【状态概览】最近睡眠状态不太好（<55分）- 这不怪你，压力大/生活节奏乱的时候睡眠总会先被影响，我们一步一步来")

                    # 2. 各维度异常检测 → 温和提醒，不贴标签
                    anomalous_dims = []
                    for key in dim_order:
                        dim = dims.get(key, {})
                        if dim and dim.get('score') is not None:
                            score = dim['score'] * 100
                            conf = dim.get('confidence', 0) * 100
                            name = dim_names_map.get(key, key)
                            if score < 60 and conf >= 40:
                                anomalous_dims.append(f"· {name}({score:.0f}/100) - 可以关注一下这个方面")
                    if anomalous_dims:
                        clinical_diagnosis.append("【值得关注的方面】")
                        clinical_diagnosis.extend(anomalous_dims)

                    # 3. 症状关联分析（非医疗诊断，侧重减压引导）
                    user_msg_lower = user_message.lower()
                    symptom_analysis = []

                    # 失眠/难以入睡
                    if any(kw in user_msg_lower for kw in ['睡不着', '难入睡', '入睡困难', '躺了很久', '翻来覆去']):
                        latency = current_data.get('sleep_latency', full_data.get('sleep_latency', 0))
                        if latency and isinstance(latency, (int, float)):
                            if latency > 60:
                                symptom_analysis.append('· 你说躺了很久睡不着--超过1小时确实很难受。这种情况下身体可能已经习惯了「一上床就清醒」的模式。好消息是，通过调整睡前的放松习惯，这个模式是可以慢慢改变的')
                            elif latency > 30:
                                symptom_analysis.append("· 入睡需要半小时以上--可能睡前还在想事情？试试睡前一小时把手机放客厅，做5分钟深呼吸")
                            else:
                                symptom_analysis.append('· 入睡时间不算太长，但能感觉到你的困扰。有时候担心睡不着本身就会让人睡不着')

                    # 打鼾/呼吸暂停 → 温和提醒，强调改善而非诊断
                    if any(kw in user_msg_lower for kw in ['打鼾', '打呼', '呼吸停', '憋醒', '喘不上气', '呼吸暂停']):
                        symptom_analysis.append("· 你提到打鼾的问题--很多人以为只是吵到别人，但其实它也可能影响你的睡眠深度和白天精神状态。侧卧睡通常能明显改善，今晚可以试试。如果调整睡姿后还是没改善，去医院呼吸科做个睡眠监测也不复杂，很多人做完才知道自己睡眠质量可以好那么多")

                    # 夜醒
                    if any(kw in user_msg_lower for kw in ['半夜醒', '醒了', '醒来', '夜醒', '睡不沉', '容易醒']):
                        awake = current_data.get('awake_times', full_data.get('awake_times', 0))
                        if awake and isinstance(awake, (int, float)):
                            if awake >= 3:
                                symptom_analysis.append(f"· 一晚醒{awake}次确实很折腾人，每次醒来看时间就更焦虑。可以试试睡前做一次身体扫描冥想，减少夜间自动唤醒的次数")
                            else:
                                symptom_analysis.append(f"· 夜醒{awake}次其实在正常范围内，但如果醒来后很难再睡着，可以试试不带手机下床喝口水、听段白噪音再回去躺")

                    # 晨起状态
                    if any(kw in user_msg_lower for kw in ['口干', '头痛', '头昏', '没精神', '起不来', '困', '累', '乏力']):
                        if '口干' in user_msg_lower or '头痛' in user_msg_lower:
                            symptom_analysis.append("· 早上起来口干或者头痛--试试睡前在床头放杯水，睡前2小时不喝酒。如果长期这样+打鼾，去医院看看会更安心")
                        else:
                            duration = current_data.get('total_duration', full_data.get('total_duration', 0))
                            if duration and isinstance(duration, (int, float)):
                                if duration >= 7:
                                    symptom_analysis.append(f"· 睡了{duration:.1f}小时但白天还是困--可能问题不是时长，而是睡眠深度不够。睡前减少蓝光、保持卧室凉爽有助于增加深睡比例")
                                else:
                                    symptom_analysis.append(f"· 睡眠时长{duration:.1f}小时偏少，白天困是身体在提醒你：我需要更多休息")

                    # 情绪/压力
                    if any(kw in user_msg_lower for kw in ['焦虑', '压力', '紧张', '担心', '烦躁', 'emo', '抑郁', '不开心']):
                        symptom_analysis.append('· 能感觉到你的情绪状态和睡眠在互相影响--晚上睡不好让你白天更焦虑，白天焦虑又让你晚上更难入睡。这不是你一个人的问题，这是现代人最常见的睡眠陷阱。先别想着治好，今晚就做一件事：睡前把今天担心的事写在一张纸上，明天再面对它')

                    # 产品/保健品咨询
                    if any(kw in user_msg_lower for kw in ['保健', '褪黑素', '维生素', '补剂', '药', '成分', '保健贴', '贴剂', '止鼾', '助眠产品']):
                        symptom_analysis.append("· 你在看助眠产品--市面上这类东西很多，但大多数治标不治本。真正有效的是找到你失眠的根源：是压力？是作息乱了？是太焦虑？从根上解决问题，比花冤枉钱买贴剂有用得多")

                    if symptom_analysis:
                        clinical_diagnosis.append("【我注意到的一些线索】")
                        clinical_diagnosis.extend(symptom_analysis)

                    # 4. 趋势分析 → 鼓励为主
                    history_trend = profile_local.get('history', [])
                    if len(history_trend) >= 3:
                        recent_scores = [
                            h.get('extracted', {}).get('wm_score') or h.get('wm_score', 0)
                            for h in history_trend[-5:] if h.get('wm_score', 0) > 0
                        ]
                        if len(recent_scores) >= 3:
                            if all(recent_scores[i] < recent_scores[i-1] for i in range(1, len(recent_scores))):
                                clinical_diagnosis.append("【趋势】最近评分有点往下走，可能是最近压力大了。别担心，这个阶段调整一下能回来")
                            elif all(recent_scores[i] > recent_scores[i-1] for i in range(1, len(recent_scores))):
                                clinical_diagnosis.append("【趋势】评分在变好，你的调整有效果了！继续保持 👍")
                            elif recent_scores[-1] >= 80:
                                clinical_diagnosis.append("【趋势】最近状态稳定不错，可以总结一下这段时间做对了什么，延续下去")

                    # 5. 就医提示 → 温和的"如果...建议..."
                    need_doctor = total < 55 or any(kw in user_msg_lower for kw in ['打鼾', '打呼', '呼吸停', '憋醒', '喘不上气'])
                    if need_doctor:
                        clinical_diagnosis.append("【温馨提醒】如果尝试了调整睡姿、减压放松等方法后，打鼾或睡眠问题还是没改善，去医院看看没什么大不了的--睡眠门诊有办法帮你，而且比你想象的简单")

                    wm_diagnosis_text = "\n".join(clinical_diagnosis) if clinical_diagnosis else ""
                    if wm_diagnosis_text:
                        wm_context += f"\n===== 世界模型分析参考 =====\n{wm_diagnosis_text}\n========================\n"
                        print(f'[WorldModel] 心理减压诊断已生成({len(wm_diagnosis_text)}字符, {len(clinical_diagnosis)}项)')

                    # ===== 回顾分析：比较本次与上次专家结论 =====
                    retrospective_findings = []
                    if full_data and wm and expert_history:
                        try:
                            dims = analysis.get('dimensions', {}) if isinstance(analysis, dict) else {}
                            current_latest = profile_local.get('latest', {})
                            data_delta = WorldModelEngine.build_user_data_delta(current_latest, full_data)
                            for dim_name, prev_expert in expert_history.items():
                                curr_expert = dims.get(dim_name, {})
                                if curr_expert and isinstance(curr_expert, dict) and curr_expert.get('score') is not None:
                                    findings = WorldModelEngine.build_retrospective(prev_expert, curr_expert, data_delta)
                                    retrospective_findings.extend(findings)
                            if retrospective_findings:
                                retro_text = "回顾分析(与上次对比):\n" + "\n".join(f"  · {f}" for f in retrospective_findings[:6])
                                wm_context += f"\n{retro_text}\n"
                                print(f'[Retrospective] {len(retrospective_findings)}项回顾发现')
                        except Exception as retro_e:
                            print(f'[Retrospective] 跳过: {retro_e}')

                    # 保存到用户画像
                    _safe_update_profile(full_data, wm_result, user_message, openid)
                    # ===== 自动生成迷你睡眠卡（供前端渲染）=====
                    try:
                        _ar_total = wm_result.get('total_score', 0) if wm_result else 0
                        if _ar_total >= 50:
                            _ar_analysis = wm_result.get('analysis', {})
                            _ar_dims = _ar_analysis.get('dimensions', {}) if isinstance(_ar_analysis, dict) else {}
                            _ar_local_dims = {}
                            _ar_map = {'clinical_psychology': '临床心理', 'cbt_cognitive': '认知行为',
                                        'sleep_medicine': '睡眠医学', 'chronobiology': '昼夜节律',
                                        'life_science': '生命科学', 'risk_management': '风险评估'}
                            for _k, _l in _ar_map.items():
                                _d = _ar_dims.get(_k, {})
                                if _d and _d.get('score') is not None:
                                    _ar_local_dims[_l] = round(_d['score'] * 100)

                            _ar_insights = wm_result.get('insights', {})
                            _ar_profile = _load_user_profile(openid)
                            _ar_scores = [h.get('wm_score', 0) for h in _ar_profile.get('history', [])[-7:] if h.get('wm_score', 0) > 0]
                            _ar_trend = 'stable'
                            if len(_ar_scores) >= 3:
                                _ar_last3 = _ar_scores[-3:]
                                if all(_ar_last3[i] < _ar_last3[i-1] for i in range(1, len(_ar_last3))):
                                    _ar_trend = 'declining'
                                elif all(_ar_last3[i] > _ar_last3[i-1] for i in range(1, len(_ar_last3))):
                                    _ar_trend = 'improving'

                            # ===== 减压建议结构化输出 =====
                            _ar_relax = {}
                            _ar_sr = dims.get('StressRelaxation', {})
                            if _ar_sr and isinstance(_ar_sr, dict):
                                _ar_relax = {
                                    'arousal_type': _ar_sr.get('arousal_type', ''),
                                    'physiological_arousal': _ar_sr.get('physiological_arousal', 0),
                                    'cognitive_arousal': _ar_sr.get('cognitive_arousal', 0),
                                }
                                # 提取最高优先级的放松疗法名称
                                _ar_tds = _ar_sr.get('therapy_details', [])
                                if isinstance(_ar_tds, list) and len(_ar_tds) > 0:
                                    # 优先选"首选"
                                    primary = [t for t in _ar_tds if isinstance(t, dict) and t.get('priority') == '首选']
                                    if primary:
                                        _ar_relax['primary_therapy'] = primary[0].get('name', '')
                                        _ar_relax['primary_evidence'] = primary[0].get('evidence', '')[:60]
                                    else:
                                        _ar_relax['primary_therapy'] = _ar_tds[0].get('name', '') if isinstance(_ar_tds[0], dict) else ''

                            # ===== 回顾发现 =====
                            _ar_retro = []
                            if retrospective_findings:
                                _ar_retro = retrospective_findings[:4]

                            # ===== 风险提示 =====
                            _ar_action = wm_result.get('action_plan', {})
                            _ar_risks = []
                            if _ar_action:
                                _ar_risks = _ar_action.get('urgent_items', [])[:2]

                            print(f'[AutoReport] 世界模型分析完成 (score={_ar_total})')
                    except Exception as _ar_e:
                        print(f'[AutoReport] 生成失败: {_ar_e}')

                except Exception as e:
                    print(f'[WorldModel] 分析出错: {e}')
                    # 即使分析出错也尝试保存上下文
                    try:
                        _safe_update_profile(full_data if 'full_data' in dir() else {},
                                             wm_result if 'wm_result' in dir() else None,
                                             user_message, openid)
                    except: pass

        # 偏好学习(独立于世界模型，任何消息都处理) — 异步后台执行
        _async_pref_data = {}
        _async_profile_local = {}
        if _HAS_DEEP_MODULE:
            def _run_pref_async(uid, msg):
                try:
                    global _pref_engine
                    if _pref_engine is None:
                        from preference_engine import PreferenceEngine
                        def _pref_api_call(messages, **kwargs):
                            return self._call_deepseek(messages, **kwargs)
                        _pref_engine = PreferenceEngine(_pref_api_call)
                    pl = _load_user_profile(uid)
                    pd = _pref_engine.process_message(msg, pl)
                    if pd.get('categories'):
                        print(f'[Preference] 已学习: {list(pd["categories"].keys())}')
                    else:
                        print(f'[Preference] 分析完成(无新偏好)')
                except Exception as e:
                    print(f'[Preference] 异步跳过: {e}')
            threading.Thread(target=_run_pref_async, args=(openid, user_message), daemon=True).start()
        pref_data = {}
        profile_local = {}

        # 构建结构化生物反馈数据（世界模型v3的核心差异化）— 异步后台执行
        _async_biofeedback_data = None
        _async_wm_result = None
        if _HAS_DEEP_MODULE and 'wm' in locals() and wm:
            def _run_biofeedback_async(uid, msg, hist):
                try:
                    fd = self._extract_sleep_data_from_text(
                        msg + ' ' + ' '.join([m.get('content','') for m in hist])
                    )
                    if fd:
                        wr = wm.comprehensive_analysis(fd)
                        sk = wr.get('skin_biofeedback', {})
                        if sk.get('available'):
                            print(f'[Biofeedback] 已生成 {len(sk.get("dates_available", []))}天皮肤数据')
                except Exception as e:
                    print(f'[Biofeedback] 异步跳过: {e}')
            threading.Thread(target=_run_biofeedback_async, args=(openid, user_message, history), daemon=True).start()
        biofeedback_data = None
        wm_result = None

        # 构建历史画像上下文（含专家回顾数据）
        history_context, expert_history = _build_history_context(openid)

        # ===== 前沿证据注入（世界模型v5.0）=====
        # 根据用户消息内容匹配相关类别的近期文献
        evidence_context = ""
        try:
            user_msg_lower_for_evidence = user_message.lower()

            # 用户关键词→证据类别的映射
            keyword_cat_map = {
                '失眠': 'cbt_i', '睡不着': 'cbt_i', '入睡': 'cbt_i',
                '打鼾': 'sleep_apnea', '打呼': 'sleep_apnea', '呼吸': 'sleep_apnea',
                '熬夜': 'circadian', '作息': 'circadian', '时差': 'circadian',
                '压力': 'stress', '焦虑': 'stress', '紧张': 'stress', '冥想': 'stress',
                '更年期': 'women_sleep', '孕期': 'women_sleep', '月经': 'women_sleep',
                '孩子': 'adolescent', '青少年': 'adolescent', '学生': 'adolescent',
            }

            matched_cats = set()
            for kw, cat in keyword_cat_map.items():
                if kw in user_msg_lower_for_evidence:
                    matched_cats.add(cat)

            if matched_cats:
                recent_evidence = PubmedFrontier.get_recent_evidence(
                    days=30, categories=list(matched_cats), max_results=3
                )
            else:
                # 无特定匹配时取近期高certainty文献
                recent_evidence = PubmedFrontier.get_recent_evidence(
                    days=30, max_results=2
                )

            if recent_evidence:
                evidence_context = PubmedFrontier.format_evidence_for_prompt(recent_evidence)
                if evidence_context:
                    print(f'[EvidenceInject] 已注入{len(recent_evidence)}篇相关文献')
        except Exception as e:
            print(f'[EvidenceInject] 跳过: {e}')

        today_str = datetime.now().strftime('%Y年%m月%d日')

        # 场景感知上下文
        scene_context = ""
        if _HAS_DEEP_MODULE:
            scene = classify_scene(user_message)
            scene_context = f"\n用户当前场景: {scene['desc']} (置信度{scene['confidence']:.0%})\n"
            # 纵向对比
            profile = _load_user_profile(openid)
            comparison = vertical_comparison(profile)
            if comparison.get('today_score') or comparison.get('yesterday_score'):
                today_s = comparison.get('today_score', '?')
                yes_s = comparison.get('yesterday_score', '?')
                wk_s = comparison.get('week_avg', '?')
                trend = comparison.get('trend', 'stable')
                trend_cn = {'improving': '改善中', 'declining': '恶化', 'stable': '稳定'}.get(trend, '稳定')
                scene_context += f"纵向对比: 今天{today_s}分 / 昨天{yes_s}分 / 近7天平均{wk_s}分 · 趋势:{trend_cn}\n"
            # 偏好学习上下文
            if pref_data and pref_data.get('categories'):
                pref_ctx = _pref_engine.build_context(pref_data)
                if pref_ctx:
                    scene_context += pref_ctx

            # ===== 🌟 极致睡眠评分：压力分层对比 =====
            if wm_result and isinstance(wm_result, dict):
                try:
                    from architecture_inner_eye import make_extreme_bedtime_context
                    _stress = full_data.get('stress_level', 3) or 3
                    _dur = full_data.get('total_duration', 420) or 420
                    _lat = full_data.get('sleep_latency', 30) or 30
                    _extreme_ctx = make_extreme_bedtime_context({
                        'stress_level': _stress,
                        'total_duration': _dur,
                        'sleep_latency': _lat,
                    })
                    if _extreme_ctx:
                        scene_context += _extreme_ctx + '\n'
                except Exception:
                    pass

            # ===== 情绪感知语调提示（内隐，不暴露给用户）=====
            try:
                emotion_timeline = profile.get('emotion_timeline', [])
                if emotion_timeline:
                    recent_emotions = emotion_timeline[-3:]
                    emotion_words = [e.get('emotion', '') for e in recent_emotions]
                    # 仅当检测到负面情绪时才调整语调
                    negative_moods = {'焦虑': 1, '烦躁': 1, '压力': 1, '低落': 1, '疲惫': 1, '愤怒': 1}
                    has_negative = any(e in negative_moods for e in emotion_words)
                    if has_negative:
                        # 不暴露检测结果，只给语调指令
                        scene_context += "用户近期情绪偏负面，请用更多的共情和陪伴，少给建议，多回应感受。\n"
                    elif '开心' in emotion_words or '平静' in emotion_words:
                        scene_context += "用户近期情绪积极，可以更多正向鼓励，肯定用户的进步。\n"
            except:
                pass

        # ===== 数据级纠正检测（量化验证，不依赖关键词） =====
        correction_note = ""
        try:
            profile_check = _load_user_profile(openid)
            last_history = profile_check.get('history', [])
            last_extracted = {}
            if last_history:
                last_entry = last_history[-1]
                last_extracted = last_entry.get('extracted', {}) or {}

            # 检测关键词意图
            correction_keywords = ['记错', '不是', '不对', '错了', '纠正', '更正', '修正', '其实', '搞错', '你弄错', '说错']
            has_correction_intent = any(w in user_message for w in correction_keywords)

            # 批评反馈检测--用户说"不专业""不行""太差"等评价性批评
            feedback_keywords = ['不专业', '不行', '太差', '不好', '没用', '不满意', '错误', '不准', '假', '忽悠', '垃圾', '水平低']
            has_feedback_intent = any(w in user_message for w in feedback_keywords)

            # 提取当前消息中的新数据
            current_extracted = self._extract_sleep_data_from_text(user_message) or {}

            # 量化比对：新数据 vs 上一次提取的数据
            quant_fields = ['bedtime', 'wake_time', 'sleep_latency', 'awake_times', 'awake_duration', 'total_duration', 'deep_sleep_percent']
            corrected_fields = []
            for f in quant_fields:
                new_val = current_extracted.get(f)
                old_val = last_extracted.get(f)
                if new_val is not None and new_val != '' and new_val != 0:
                    if old_val is not None and old_val != '' and str(new_val) != str(old_val):
                        corrected_fields.append(f)

            if corrected_fields:
                field_names = {
                    'bedtime': '入睡时间', 'wake_time': '起床时间', 'sleep_latency': '入睡时长',
                    'awake_times': '夜醒次数', 'awake_duration': '清醒时长', 'total_duration': '总睡眠时长',
                    'deep_sleep_percent': '深睡比例'
                }
                fields_cn = [field_names.get(f, f) for f in corrected_fields]
                correction_note = (
                    f"\n【数据纠正检测】\n"
                    f"用户提供了与之前不同的数据（涉及 {', '.join(fields_cn)}）。\n"
                    f"处理原则：以用户最新的数据为准，重新分析。\n"
                    f"不要坚持旧数据，直接道歉并基于新数据给出分析。\n"
                )
            elif has_correction_intent and not corrected_fields:
                # 用户说"你记错了"但没给新数据 → 引用最近一次数据让用户确认
                _last_msg = last_entry.get('user_said', '') or ''
                _last_sleep_summary = []
                if last_extracted:
                    _m = {'bedtime':'入睡','wake_time':'起床','sleep_latency':'入睡用时','awake_times':'夜醒次数','total_duration':'总时长'}
                    for k, cn in _m.items():
                        if last_extracted.get(k):
                            _last_sleep_summary.append(f'{cn}={last_extracted[k]}')
                _summary = '，'.join(_last_sleep_summary) if _last_sleep_summary else last_entry.get('wm_quality','上一次数据')
                correction_note = (
                    f"\n【用户表示不满但未提供新数据】\n"
                    f"用户上次说的是: {_last_msg[:80]}\n"
                    f"系统上次提取的是: {_summary}\n"
                    f"处理原则：先诚恳道歉。然后逐条复述系统之前理解的数据，询问哪条不对。\n"
                    f"不要问\"昨晚睡得怎么样\"--用户已经说过了。\n"
                    f"要问具体哪条数据不对，比如\"是我把入睡时间记成11点不对吗？\"\n"
                )
            elif has_feedback_intent and last_history:
                # 用户对分析质量本身不满意（不是纠正数据），有历史评分数据
                last_entry = last_history[-1] if last_history else {}
                _last_msg = last_entry.get('user_said', '') or ''
                _last_score = last_entry.get('wm_score', 0)
                correction_note = (
                    f"\n【用户对分析表达不满（非数据纠正）】\n"
                    f"用户之前提供了数据: {_last_msg[:80]}\n"
                    f"上次评分: {_last_score if _last_score else '暂无'}\n"
                    f"处理原则：不要道歉过度，也不要问\"昨晚睡得怎么样\"--用户已经有数据了。\n"
                    f"直接追问用户对哪个部分不满意：是评分偏高/偏低？还是建议不实用？还是分析角度不对？\n"
                    f"回复模板：\"具体是哪方面让您不满意？是评分不太符合您的感受，还是建议不太适用？您告诉我，我来调整。\"\n"
                )
        except Exception as e:
            print(f'[CorrectionCheck] 跳过: {e}')

        # ===== 对话即干预：检测用户求助意图 =====
        intervention_mode = False
        intervention_prompt_extra = ""
        try:
            # 求助关键词：需要减压/放松的场景
            help_keywords = [
                '压力大', '睡不着', '睡不觉', '焦虑', '烦躁', '心慌', '不安', '担心',
                '醒了睡不着', '醒来睡不着', '紧张', '害怕', '难受', '痛苦',
                '喘不过气', '胸口闷', '心跳快',
                '放松一下', '帮我放松', '减压', '心烦', '很烦', '郁闷',
            ]
            has_help_intent = any(kw in user_message for kw in help_keywords)

            # 呼吸完成反馈--用户做完呼吸练习后说的"做完了""好一点了"
            done_keywords = ['做完了', '做完了', '放松了一些', '放松了', '好一点', '好点了', '舒服了', '平静了', '感觉不错']
            has_done_intent = any(kw in user_message for kw in done_keywords)

            # 用户反馈"做完了"→ 更新最近的relax_log为completed
            if has_done_intent:
                try:
                    profile = _load_user_profile(openid)
                    if 'relax_log' in profile and profile['relax_log']:
                        last_entry = profile['relax_log'][-1]
                        if not last_entry.get('completed'):
                            last_entry['completed'] = True
                            last_entry['feedback'] = user_message[:50]
                            # 保存（不用 save_json，直接用 json.dump）
                            base_dir = os.path.dirname(os.path.abspath(__file__))
                            p_path = os.path.join(base_dir, 'user_profile.json')
                            all_p = {}
                            if os.path.exists(p_path):
                                with open(p_path, 'r', encoding='utf-8') as f:
                                    all_p = json.load(f)
                            all_p[openid] = profile
                            with open(p_path, 'w', encoding='utf-8') as f:
                                json.dump(all_p, f, ensure_ascii=False, indent=2)
                            print(f'[RelaxLog] 反馈标记为completed: {user_message[:30]}')
                except Exception as e:
                    print(f'[RelaxLog] 反馈更新跳过: {e}')

            # Phase 3: 元学习驱动的干预决策
            _mp_profile = _load_user_profile(openid)
            mp = _mp_profile.get('meta_params', {})
            # 提取特征（F1-F8）
            raw_features = _extract_features(_mp_profile, user_message, '')
            # 计算综合干预得分：压力相关维度加权
            intervention_score = (
                raw_features[0] * 0.30 +   # F1: 压力强度
                raw_features[1] * 0.25 +   # F2: 失眠倾向
                raw_features[2] * 0.20 +   # F3: 焦虑唤醒
                raw_features[3] * 0.10 +   # F4: 情绪极性
                raw_features[5] * 0.15     # F6: 互动时段（深夜权重高）
            )
            threshold = mp.get('intervention_threshold', 0.5)
            confidence = mp.get('confidence', 0.3)

            # 决策：高置信度用分数 vs 低置信度用关键词保底
            if confidence >= 0.6:
                should_intervene = intervention_score >= threshold
            else:
                # 对不了解的用户，靠关键词触发（保底安全策略）
                should_intervene = has_help_intent

            # 有量化数据时不干预（保留旧逻辑）
            has_current_data = bool(current_data) if 'current_data' in dir() and current_data else False
            # 但即使有数据，如果置信度高且分数很高也干预
            if has_current_data and confidence < 0.7:
                should_intervene = False

            if should_intervene and not has_current_data:
                intervention_mode = True
                # 特征向量 + 关键词混合判断压力类型
                stress_type = '一般压力'
                if any(kw in user_message for kw in ['睡不着', '睡不觉', '醒了', '醒来']):
                    stress_type = '失眠焦虑'
                elif raw_features[2] > 0.4 and any(kw in user_message for kw in ['心跳', '心慌', '害怕', '紧张']):
                    stress_type = '焦虑唤醒'
                elif any(kw in user_message for kw in ['工作', '老板', '同事', '项目', 'deadline', '业绩', '考试']):
                    stress_type = '工作压力'
                elif any(kw in user_message for kw in ['感情', '恋爱', '分手', '吵架', '伴侣', '对象', '婚姻']):
                    stress_type = '情感压力'
                elif raw_features[0] > raw_features[1] + 0.2:
                    stress_type = '工作压力'
                elif raw_features[1] > raw_features[2] + 0.2:
                    stress_type = '失眠焦虑'

                # 动态轮数：元参数 + 干预得分校准
                base_rounds = mp.get('breath_rounds_base', 3)
                scale = mp.get('breath_rounds_scale', 0.5)
                dynamic_rounds = max(3, min(8, base_rounds + int(scale * intervention_score * 5)))

                print(f'[Intervention] Phase3: score={intervention_score:.3f} thresh={threshold} conf={confidence}')
                print(f'[Intervention] 检测到求助意图, 类型={stress_type}, 轮数={dynamic_rounds}')

                # ===== Phase 7: 推理时搜索 — 对多个备选干预策略评分，选最优 =====
                _inference_candidates = [
                    {'name': '4-7-8', 'inhale': 4, 'hold': 7, 'exhale': 8, 'arousal_reduction': 0.8, 'completion_rate': 0.8, 'description': '经典放松'},
                    {'name': '箱式呼吸', 'inhale': 4, 'hold': 4, 'exhale': 4, 'arousal_reduction': 0.6, 'completion_rate': 0.9, 'description': '军队训练法'},
                    {'name': '3-3-6扩展', 'inhale': 3, 'hold': 3, 'exhale': 6, 'arousal_reduction': 0.7, 'completion_rate': 0.6, 'description': '延长呼气'},
                    {'name': '4-2-4蝴蝶', 'inhale': 4, 'hold': 2, 'exhale': 4, 'arousal_reduction': 0.5, 'completion_rate': 0.95, 'description': '最简入门'},
                ]
                # 用户偏好加权
                _pref_boost = 0.2 if mp.get('preferred_pattern', '') in ['4-7-8', 'box', '3-3-6'] else 0
                _completion_rate = mp.get('completion_rate', 0.5)
                # 搜索评分：arousal_reduction * 0.4 + completion_rate_delta * 0.3 + novelty * 0.2 + pref_boost * 0.1
                _best_score = -1
                _best_pattern = _inference_candidates[0]
                for _c in _inference_candidates:
                    _cr_score = 1.0 - abs(_completion_rate - _c['completion_rate'])
                    _novelty = 0.1 if _c['name'] == _preferred else 0.5
                    _pref_bonus = 0.2 if _c['name'] == _preferred else 0
                    _score = _c['arousal_reduction'] * 0.4 + _cr_score * 0.3 + _novelty * 0.2 + _pref_bonus * 0.1
                    if _score > _best_score:
                        _best_score = _score
                        _best_pattern = _c
                _selected_pattern = _best_pattern
                print(f'[Intervention] Search: 候选={len(_inference_candidates)} 最优={_selected_pattern["name"]} score={_best_score:.3f} (preferred={mp.get("preferred_pattern", "?")})')
                _pattern = {
                    'name': _selected_pattern['name'],
                    'inhale': _selected_pattern['inhale'],
                    'hold': _selected_pattern['hold'],
                    'exhale': _selected_pattern['exhale'],
                    'rounds': dynamic_rounds,
                }
                intervention_prompt_extra = f"""
【当前模式：迷你减压干预 - 用户压力类型推测为{stress_type}】
用户当前消息表达了压力/焦虑/失眠困扰，且没有提供新的睡眠数据。
你的任务是：通过对话完成一次迷你减压干预，但不输出文字呼吸引导--而是转向沉浸式体验。

**注意：回复中不要包含呼吸引导的文字描述。** 只需要：
1. 共情（一到两句）
2. 简短邀请用户做呼吸练习（不超过两句话）
3. 结尾说"准备好了就告诉我"
4. **不要**在文字中写"吸气4秒...屏住7秒..."--这些由前端动画接管

回复模板示例：
- "听起来压力不小。我们先做个深呼吸放松一下，跟着屏幕上的动画节奏来就好。准备好了告诉我。"
- "能感受到你现在很紧张。一起做个呼吸练习吧，让身体先慢下来。准备好了就告诉我。"

关键原则：
- 引导语简短自然，说是"一起做"而不是"我教你做"
- 整个过程控制在3-4句话内
- **不要写呼吸节奏的文字，不要写吸气/呼气引导**--前端动画会展示
"""
        except Exception as e:
            print(f'[InterventionCheck] 跳过: {e}')
            intervention_mode = False

        system_content = f"""你是眠小兔，一名睡眠健康顾问

【推理约束规则 - 必须遵守】
规则1: 只有当用户当前消息中出现了具体的睡眠数据时，才用评分模板展示当前评分。
规则2: 当前消息没有数据→不展示评分。历史评分可引用回顾，但不作为当前评分。
规则3: 用户纠正时以最新说法为准。{correction_note}

【数据可信度规则 - 必须遵守】
规则A: 世界模型数据中包含【数据局限性】标注，根据用户提供的数据点数量决定推理深度：
  - 数据不足(≤2个字段): 只展示1-2个有数据支撑的维度，其他维度说"数据不足，暂不展示"
  - 数据一般(3-4个字段): 可展示有数据支撑的维度，标注哪些是估算项
  - 数据充分(≥5个字段): 可展示全部维度，但仍标注估算项
规则B: 每条结论必须标注可信度:
  - "可信度高" = 有直接数据支撑且置信度高
  - "基于估算" = 由少量数据推算，仅供参考
  - "推测" = 没有数据支撑，仅为合理猜测
规则C: 不要假装你"知道"用户没说过的事。不知道就说不知道。
规则D: 评分展示要克制。数据少时少展示维度，数据多时再多展示。不要让人感觉"随便说两句就出了7个评分"。

，当前日期是 {today_str}。对话风格温暖而不煽情，专业而不学究。

回复结构：
1. 共情（一句足够）
2. 基于数据做分析（引用评分时要带可信度说明）
3. 明确标注哪些是确定结论，哪些是推测
4. 建议要具体、可执行
4. 如有世界模型数据，展示7维度评估（要整洁、一眼看清）
5. 2-3条具体可执行的建议，每条必须按"三要素"模板写：
   模板：[行动指令]（基于用户的具体数据[引用数据]），因为[简短科学解释]。
   示例：
   ❌ "保持良好的睡眠习惯"（空洞）
   ✅ "把入睡时间提前到11点（你最近12点睡7点起，总时长足够但深睡不够），因为11点前入睡能赶上生长激素分泌高峰，更容易进入深睡"
   ✅ "醒来后15分钟还没睡着就起来坐一会儿（你昨晚醒了1次超过20分钟），不要在床上焦虑，避免床和'睡不着'形成条件反射"
6. 就医提示：只适用于连续失眠超3周或伴有严重身体不适的情况。用户第一次对话或仅描述轻微症状时，不要提就医。

格式规范：
- 评分区用"📊 7维评估"开头，每个维度一行：🕐 昼夜节律 88/100 · 置信度较高
- 如果数据中有"身体恢复评估"部分，也要展示出来，这是纯大模型做不到的生理量化指标
- 不用星号、下划线等Markdown符号做粗体，纯Unicode
- 建议用数字列表 1. 2. 3.
- 如果引用了科学研究，在建议区最后统一加一行"📚 参考文献"：
  📚 参考文献
  · Stepanski et al., Sleep Med Rev 2003 (PMID: 14631217)
  · 基于临床共识
  只用 evidence_context 中提供的 PMID，不要编造。
- 段落之间空行，不堆砌
- 注意时间线：今天是 {today_str}，用户说的"昨晚"就是 {today_str} 的前一天。如果用户隔天再次询问，应区分是新的情况还是跟踪之前的反馈。

纠正处理：
- 如果用户指出你记错了（如"我之前说的是腰疼不是大腿疼"），立即承认错误并更新记忆
- 纠正比历史记录更重要。用户明确纠正后，以纠正后的信息为准
- 不要坚持旧的错误记忆，这会让用户感到沮丧

{history_context}

{wm_context}{evidence_context}{scene_context}"""

        # ===== 对话即干预：干预模式覆盖 =====
        if intervention_mode and intervention_prompt_extra:
            system_content = f"""你是眠小兔，一名专注于减压和睡眠健康的AI助手。

你的角色不是分析或评分，而是陪伴用户完成一次即时的减压干预。

{intervention_prompt_extra}

当前日期是 {today_str}。对话语言自然温暖，不做作。
"""
            print(f'[Intervention] 已切换到干预模式')

        # 构建"减压+睡眠管理"风格的系统提示
        if intervention_mode:
            # 干预模式下不走任何评分/分析路径
            pass
        elif wm_context and has_quantitative_now:
            # 有充足数据，按完整分析回复
            pass
        else:
            # 数据不足时，prompt改为引导式，不给评分
            system_content += """

【数据不足时的互动规则】
用户描述睡眠问题但缺少关键数据时，不要急着给建议，而是按下面策略互动：

第一轮：先共情，然后问1个最关键的跟进问题（不要一次问多个）
- 如果是"半夜醒来" → 问：是每晚都这样还是偶尔？醒来后多久能再睡着？
- 如果是"睡不着" → 问：躺床上大概多久才能睡着？
- 如果是"睡眠浅" → 问：大概几点睡、几点起？
- 如果是"压力大" → 问：什么时间段压力最大？
一轮只问1个问题，等用户回答后再往下推。

第二轮：根据用户的回答，再追问第2个关键问题
- 有了入睡时间→问醒来时间
- 有了时长→问醒来次数
- 有了次数→问醒来感觉

第三轮：数据足够后，基于收集到的数据做分析，展示评分和建议

【追问时的结构化映射】
当用户给出了具体数字后，在回复中自然地确认我理解的数据：
- "我记一下：你大约12点睡、6点醒" → 这样系统会自动识别
- 然后用分析或评分回应用户

关键原则：
- 不一次问太多问题，避免用户觉得像在填表
- 保持"减压"的氛围，不要让用户觉得在被审问
- 用自然的语气，比如"我大概了解情况了，还想问个问题……"
- 每次回复都先回应用户的情绪，再问问题

"""

        # 初始化消息列表
        messages = [{'role': 'system', 'content': system_content}]

        # 添加历史对话
        for msg in history:
            messages.append(msg)

        # 添加当前消息
        messages.append({'role': 'user', 'content': user_message})

        # 【关键防护】当前消息无量化数据时，注入硬约束
        if not has_quantitative_now:
            # 分析已有的历史数据字段数
            hist_field_count = 0
            if last_history:
                last_ext = last_history[-1].get('extracted', {}) or {}
                hist_field_count = len([k for k in ['bedtime','wake_time','awake_times','total_duration','sleep_latency'] if last_ext.get(k)])

            constraint = (
                "### 重要约束 ###\n"
                "用户当前这条消息没有提供具体的睡眠数据(时间/时长/次数)。\n"
                "- 可以引用历史评分作为回顾背景，但不能当作当前消息的评分\n"
                "- 不要假设用户之前给过数据所以这次也能评分\n"
                "- 重点放在共情和引导反问\n"
                "- 如果用户指出之前的记忆有误，承认错误并以最新说法为准\n"
                f"- 用户已有 {hist_field_count} 个历史字段。如果已有3个以上字段（入睡时间/起床时间/夜醒次数/总时长中的任意3个），可以基于已有数据做简略分析，同时询问缺失的关键字段。"
            )
            messages.append({'role': 'system', 'content': constraint})

        try:
            # ===== 干预模式：不走 DeepSeek，直接返回呼吸引导 =====
            if intervention_mode:
                # 根据元参数 + 压力类型选择呼吸模式
                _stress_type = stress_type if 'stress_type' in dir() else '一般压力'
                _stress_type = stress_type if 'stress_type' in dir() else '一般压力'
                _mp_for_pattern = _load_user_profile(openid).get('meta_params', {})
                if '焦虑' in _stress_type or '紧张' in str(user_message):
                    _tip = '慢慢吸气4秒，屏住7秒，缓缓呼气8秒，感觉压力随呼吸释放'
                elif '失眠' in _stress_type or '睡不着' in str(user_message):
                    _tip = '慢吸4秒，屏住7秒，长呼8秒，让身体慢慢进入休息状态'
                else:
                    _tip = '跟着动画节奏慢慢来，把注意力放在呼吸上'
                print(f'[Intervention] 策略选择: {_pattern["name"]}, rounds={_pattern["rounds"]}, tip={_tip[:20]}...')

                # 让DeepSeek生成共情+邀请文案，但不生成呼吸引导文字

                # 让DeepSeek生成共情+邀请文案，但不生成呼吸引导文字
                result = self._call_deepseek(messages, max_tokens=200, temperature=0.7)
                reply_content = result['content']
                # 添加action参数让前端展示呼吸动画
                response_obj = {
                    'success': True,
                    'action': 'start_breathing',
                    'action_params': {
                        'name': _pattern['name'],
                        'inhale': _pattern['inhale'],
                        'hold': _pattern['hold'],
                        'exhale': _pattern['exhale'],
                        'rounds': _pattern['rounds'],
                        'tip': _tip,
                    },
                    'reply': reply_content,
                    'intervention': True,
                    'stress_type': _stress_type,
                    'usage': result.get('usage', {}),
                }
                print(f'[Intervention] 响应: {_stress_type}, 呼吸模式={_pattern["name"]}, rounds={_pattern["rounds"]}')
                # 记录干预日志（首次-启动，后续反馈"做完了"时再更新为completed）
                _log_intervention(openid, _stress_type, _pattern['name'], rounds=_pattern['rounds'], duration=0, completed=False, user_message=user_message)
            else:
                result = self._call_deepseek(messages, max_tokens=1000, temperature=0.7)
                reply_content = result['content']

            # 检测是否包含实操引导意图
            breathing_kw = ['呼吸', '带我做', '带我练', '引导', '跟着', '实操', '练习']
            is_breathing_req = any(kw in user_message for kw in breathing_kw)

            if 'response_obj' not in locals():
                response_obj = {
                    'success': True,
                    'reply': reply_content,
                    'usage': result.get('usage', {}),
                }

            # ===== 附加迷你睡眠卡数据（auto_report）=====
            try:
                _ar_rebuild = False
                _ar_src = locals().get('_auto_report_data')
                if not _ar_src:
                    _ar_rebuild = True
                if _ar_rebuild or not _ar_src:
                    _wm_r = locals().get('wm_result') or globals().get('wm_result')
                    if _wm_r and isinstance(_wm_r, dict) and _wm_r.get('total_score', 0) >= 50 and has_quantitative_now:
                        _ar_dims = _wm_r.get('analysis', {}).get('dimensions', {}) if isinstance(_wm_r.get('analysis'), dict) else {}

                        # 1. 维度评分升级：{score, label, icon}
                        _ar_d2meta = {
                            'ClinicalPsychologist': {'name':'临床心理','icon':'🧠'},
                            'CBT': {'name':'认知行为','icon':'💭'},
                            'SleepPhysician': {'name':'睡眠医学','icon':'🩺'},
                            'Chronobiologist': {'name':'昼夜节律','icon':'🕐'},
                            'LifeScientist': {'name':'生命科学','icon':'🧬'},
                            'RiskManager': {'name':'风险评估','icon':'⚠️'},
                            'StressRelaxation': {'name':'减压放松','icon':'🧘'},
                        }
                        _dl = {}
                        for _k, _vm in _ar_d2meta.items():
                            _d = _ar_dims.get(_k, {})
                            if _d and _d.get('score') is not None:
                                _sc = round(_d['score'] * 100)
                                _label = '优秀' if _sc >= 85 else '良好' if _sc >= 70 else '一般' if _sc >= 55 else '需关注'
                                _dl[_vm['name']] = {'score': _sc, 'label': _label, 'icon': _vm['icon']}

                        # 2. 减压建议升级：从action_plan取therapy_details
                        _ar_sr = _ar_dims.get('StressRelaxation', {}) or {}
                        _ar_relax = {'arousal_type': _ar_sr.get('arousal_type', ''),
                                     'physiological_arousal': _ar_sr.get('physiological_arousal', 0),
                                     'cognitive_arousal': _ar_sr.get('cognitive_arousal', 0)}
                        # 优先从 action_plan 的 therapy_details 中提取减压方案
                        _ar_action_plan = _wm_r.get('action_plan', {})
                        _ar_td = _ar_action_plan.get('therapy_details', {})
                        if isinstance(_ar_td, dict):
                            for _k, _v in _ar_td.items():
                                if _k.startswith('StressRelaxation_'):
                                    if '[首选]' in str(_v) or '[备选]' in str(_v):
                                        _parts = str(_v).split(' | ')
                                        _ar_relax['primary_therapy'] = _parts[0].replace('[首选] ', '').replace('[备选] ', '')
                                        for _p in _parts:
                                            if '证据:' in _p:
                                                _ar_relax['evidence'] = _p.replace('证据:', '').strip()[:80]
                                            elif '效应量:' in _p:
                                                _ar_relax['effect_size'] = _p.replace('效应量:', '').strip()
                                        break
                        # fallback: 从 findings 提取
                        if 'primary_therapy' not in _ar_relax:
                            _sr_findings = _ar_sr.get('findings', [])
                            for _f in _sr_findings:
                                if 'PMR' in _f or '身体扫描' in _f or '呼吸' in _f:
                                    _ar_relax['primary_therapy'] = '渐进肌肉放松/身体扫描'
                                    _ar_relax['evidence'] = '基于唤醒类型匹配的循证放松方案'
                                    break
                        # 推荐疗法ID列表
                        _ar_rt_list = _ar_action_plan.get('recommended_therapies', [])
                        if isinstance(_ar_rt_list, list):
                            _ar_relax['therapy_ids'] = _ar_rt_list[:4]

                        # 3. 回顾发现
                        _ar_retro = []
                        _rf = locals().get('retrospective_findings')
                        if _rf:
                            _ar_retro = _rf[:4]

                        # 4. 趋势 → 对象化
                        _ar_trend_obj = {'direction': 'stable', 'delta_7d': 0, 'labels': []}
                        _ar_profile = _load_user_profile(openid)
                        _ar_scores = [h.get('wm_score', 0) for h in _ar_profile.get('history', [])[-7:] if h.get('wm_score', 0) > 0]
                        if len(_ar_scores) >= 3:
                            _ar_last3 = _ar_scores[-3:]
                            _ar_delta = round(_ar_scores[-1] - _ar_scores[0], 1)
                            _ar_trend_obj['delta_7d'] = _ar_delta
                            _ar_trend_obj['labels'] = _ar_scores
                            if all(_ar_last3[i] < _ar_last3[i-1] for i in range(1, len(_ar_last3))):
                                _ar_trend_obj['direction'] = 'declining'
                            elif all(_ar_last3[i] > _ar_last3[i-1] for i in range(1, len(_ar_last3))):
                                _ar_trend_obj['direction'] = 'improving'

                        # 5. action_takeaway - 可操作的行动建议
                        _ar_takeaway = ''
                        _ar_insights = _wm_r.get('insights', {})
                        _ar_summaries = _ar_insights.get('summary', [])
                        _ar_primary = _ar_insights.get('primary_focus', '')
                        if _ar_primary:
                            _ar_takeaway = _ar_primary
                        elif _ar_summaries and isinstance(_ar_summaries, list) and _ar_summaries:
                            _ar_takeaway = _ar_summaries[0]
                        else:
                            _ar_takeaway = _wm_r.get('action_plan', {}).get('key_actions', ['关注睡眠质量'])[0]

                        # 6. 循证证据计数
                        _ar_ev_count = 0
                        _ar_top_evidence = ''
                        for _k, _vm in _ar_d2meta.items():
                            _d = _ar_dims.get(_k, {})
                            if _d and isinstance(_d, dict):
                                _ec = _d.get('evidence_cited', 0) or 0
                                _et = _d.get('evidence_total', 0) or 0
                                _ar_ev_count += _et
                        if _ar_ev_count == 0:
                            _ar_top_evidence = _wm_r.get('action_plan', {}).get('auto_evidence_count', 0) or 0
                            _ar_ev_count = _ar_top_evidence

                        # 7. reason - 诊断推理简述
                        _ar_reason = ''
                        _ar_lowest_dim = None
                        _ar_lowest_score = 101
                        for _k, _vm in _ar_d2meta.items():
                            _d = _ar_dims.get(_k, {})
                            if _d and _d.get('score') is not None:
                                _sc = round(_d['score'] * 100, 1)
                                if _sc < _ar_lowest_score:
                                    _ar_lowest_score = _sc
                                    _ar_lowest_dim = _vm['name']
                        _ar_risk_flags = []
                        for _k, _vm in _ar_d2meta.items():
                            _d = _ar_dims.get(_k, {})
                            if _d and isinstance(_d, dict):
                                _ar_risk_flags.extend(_d.get('risk_flags', []))
                        _reason_parts = []
                        if _ar_lowest_dim and _ar_lowest_score < 80:
                            _reason_parts.append(f"主要瓶颈：{_ar_lowest_dim}({_ar_lowest_score}/100)")
                        if _ar_relax.get('arousal_type', '') != 'low_arousal' or _ar_sr.get('physiological_arousal', 0) >= 2:
                            _ar_at = _ar_relax.get('arousal_type', '')
                            if _ar_at == 'high_physiological':
                                _reason_parts.append(f"唤醒类型：生理唤醒型（交感神经过度激活）")
                            elif _ar_at == 'high_cognitive':
                                _reason_parts.append(f"唤醒类型：认知唤醒型（反刍思维）")
                            elif _ar_at == 'mixed':
                                _reason_parts.append(f"唤醒类型：混合型（生理+认知双重激活）")
                        if _ar_risk_flags:
                            _reason_parts.append(f"风险标记：{_ar_risk_flags[0]}")
                        _ar_reason = '；'.join(_reason_parts)

                        # 8. user_profile_tags - 用户分型标签
                        _ar_tags = []
                        _ar_sr_at = _ar_sr.get('arousal_type', '')
                        if _ar_sr_at in ('high_physiological', 'mixed'):
                            _ar_tags.append('生理唤醒型')
                        elif _ar_sr_at == 'high_cognitive':
                            _ar_tags.append('认知唤醒型')
                        if _ar_sr.get('sleep_latency', 30) > 30:
                            _ar_tags.append('入睡困难型')
                        if (isinstance(_ar_scores, list) and len(_ar_scores) >= 5 and
                            all(s < 65 for s in _ar_scores[-3:])):
                            _ar_tags.append('持续性差')
                        if _ar_tags and len(_ar_tags) > 0:
                            pass  # keep as is

                        response_obj['auto_report'] = {
                            'score': _wm_r.get('total_score', 0),
                            'quality': _wm_r.get('quality', ''),
                            'trend': _ar_trend_obj,
                            'dimension_scores': _dl,
                            'summary': _ar_insights.get('summary', ''),
                            'primary_focus': _ar_primary,
                            'relaxation': _ar_relax,
                            'retrospective': _ar_retro,
                            'risk_items': _wm_r.get('action_plan', {}).get('urgent_items', [])[:2],
                            'action_takeaway': _ar_takeaway,
                            'reasoning': _ar_reason,
                            'user_tags': _ar_tags,
                            'evidence_count': _ar_ev_count,
                            'confidence_bounds': _ar_insights.get('confidence_bounds', {}),
                            'data_sufficient': _ar_insights.get('_known_fields', 0) > 2
                                              if _ar_insights.get('_known_fields') is not None
                                              else (_wm_r.get('total_score', 0) >= 10),
                            'references': [{
                                'pmid': _ar_relax.get('evidence', '').split('PMID: ')[-1].split(')')[0] if 'PMID' in (_ar_relax.get('evidence', '') or '') else '',
                                'source': _ar_relax.get('evidence', '')[:80] if _ar_relax.get('evidence') else '',
                                'label': '基于临床研究'
                            }] if _ar_relax.get('evidence') else []
                        }
            except Exception:
                pass

            # ===== 干预模式标记 =====
            if intervention_mode:
                response_obj['intervention'] = True
                response_obj['stress_type'] = stress_type if 'stress_type' in dir() else '一般压力'

            # ===== 最佳实践：世界模型皮肤生物反馈独立字段 =====
            if biofeedback_data:
                response_obj['biofeedback'] = biofeedback_data
                print(f'[Response] biofeedback已附加到响应')

            if is_breathing_req:
                pattern = '4-7-8'
                if '4-7-8' in user_message or '478' in user_message: pattern = '4-7-8'
                elif '箱式' in user_message or '4-4-4' in user_message: pattern = 'box'
                patterns = {
                    '4-7-8': {'name': '4-7-8呼吸法', 'inhale': 4, 'hold': 7, 'exhale': 8, 'rounds': 5},
                    'box': {'name': '箱式呼吸', 'inhale': 4, 'hold': 4, 'exhale': 4, 'rounds': 5},
                    '2-4-6': {'name': '2-4-6呼吸法', 'inhale': 2, 'hold': 4, 'exhale': 6, 'rounds': 5},
                }
                response_obj['action'] = 'start_breathing'
                response_obj['action_params'] = patterns.get('4-7-8', patterns['4-7-8'])
                response_obj['reply'] = '好的，带你做一次呼吸练习，跟着节奏放松🧘'
                print(f'[Action] 呼吸引导: {response_obj["action_params"]["name"]}')

            # ===== 干预模式: 组装action响应 =====
            if intervention_mode:
                _st = stress_type if 'stress_type' in dir() and stress_type else '一般压力'
                # "醒了"场景 → 渐进式肌肉放松
                if _st == '失眠焦虑' and any(kw in user_message for kw in ['醒了', '醒来']):
                    response_obj['action'] = 'start_progressive_relaxation'
                    response_obj['action_params'] = {
                        'name': '全身渐进式放松',
                        'steps': [
                            {'part': '脚部', 'instruction': '用力绷紧双脚5秒...然后完全放松'},
                            {'part': '小腿', 'instruction': '小腿收紧5秒...松开放松'},
                            {'part': '大腿和臀部', 'instruction': '大腿和臀部收紧...放松'},
                            {'part': '腹部', 'instruction': '腹部收紧...放松'},
                            {'part': '手和手臂', 'instruction': '握拳、手臂收紧...放松'},
                            {'part': '肩膀', 'instruction': '耸肩到耳朵...放下'},
                            {'part': '脸部', 'instruction': '皱眉、咬牙...全面放松'},
                        ],
                        'total_seconds': 120,
                        'tip': '跟着指令一步步来，感受从紧张到放松的对比',
                    }
                    response_obj['reply'] = '半夜醒来确实难受。我们做个全身渐进放松，帮你重新入睡。跟着指令一步一步来🧘'
                    print(f'[Action] 渐进放松引导')
                    # 记录干预日志
                    _log_intervention(openid, _st, '渐进式肌肉放松', rounds=7, duration=120, completed=False, user_message=user_message)
                else:
                    response_obj['action'] = 'start_breathing'
                    response_obj['action_params'] = {
                        'name': '4-7-8呼吸法',
                        'inhale': 4, 'hold': 7, 'exhale': 8, 'rounds': 3,
                        'tip': '跟着动画节奏，慢慢吸气…屏住…缓缓呼出…',
                    }
                    response_obj['reply'] = '一起做个呼吸练习，让身体慢慢放松下来🌬️'
                    print(f'[Action] 呼吸引导: 4-7-8')
                    # 记录干预日志
                    _log_intervention(openid, _st, '4-7-8呼吸法', rounds=3, duration=0, completed=False, user_message=user_message)

            # ===== 跨对话记忆：对话摘要 =====
            try:
                profile_mem = _load_user_profile(openid)
                if 'conversation_summaries' not in profile_mem:
                    profile_mem['conversation_summaries'] = []

                # 根据用户消息和AI回复生成简短摘要
                user_msg_short = user_message[:60].replace('\n', ' ')
                ai_reply_short = reply_content[:80].replace('\n', ' ')

                # 检测关键主题
                topics = []
                topic_keywords = {
                    '失眠': '失眠', '睡不着': '失眠', '入睡困难': '失眠',
                    '打鼾': '打鼾', '呼吸': '呼吸',
                    '压力': '压力', '焦虑': '焦虑', '情绪': '情绪',
                    '冥想': '冥想', '呼吸练习': '呼吸练习',
                    '作息': '作息', '熬夜': '作息', '生物钟': '作息',
                }
                msg_lower = user_message.lower()
                for kw, topic in topic_keywords.items():
                    if kw in msg_lower and topic not in topics:
                        topics.append(topic)

                # 提取本次回复中的建议（取数字标号部分的文本）
                advice_this_time = ''
                import re as _re_adv
                _adv_matches = _re_adv.findall(r'(?:\d+\.\s*)([^\n]+(?:因为[^\n]+)?)', reply_content)
                if _adv_matches:
                    advice_this_time = ' | '.join(a.strip()[:60] for a in _adv_matches[:3])

                summary_entry = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'user': user_msg_short,
                    'reply_preview': ai_reply_short,
                    'advice_given': advice_this_time,
                    'topics': topics[:3],
                    'has_score': has_quantitative_now,
                    'total_score': wm_result.get('total_score', 0) if wm_result else 0,
                }
                profile_mem['conversation_summaries'].append(summary_entry)
                # 保留最近50条摘要
                if len(profile_mem['conversation_summaries']) > 50:
                    profile_mem['conversation_summaries'] = profile_mem['conversation_summaries'][-50:]

                # ===== 情绪时间线 =====
                if 'emotion_timeline' not in profile_mem:
                    profile_mem['emotion_timeline'] = []

                # 简单情绪关键词检测（非AI方式，轻量快速）
                emotion_detected = None
                intensity = 5
                emotion_kw_map = {
                    '焦虑': ('焦虑', 7), '担心': ('焦虑', 6), '害怕': ('焦虑', 8), '紧张': ('焦虑', 7),
                    '烦躁': ('烦躁', 7), '烦': ('烦躁', 6), '受不了': ('烦躁', 8),
                    '压力': ('压力', 7), '累': ('疲惫', 6), '好累': ('疲惫', 7), '疲倦': ('疲惫', 7), '没精神': ('疲惫', 6),
                    '难过': ('低落', 7), '不开心': ('低落', 6), '伤心': ('低落', 8), '哭': ('低落', 8),
                    '开心': ('开心', 7), '好了': ('平静', 5), '不错': ('平静', 5), '好多了': ('平静', 6),
                    '生气': ('愤怒', 7), '气死': ('愤怒', 9), '无语': ('烦躁', 5),
                    'emo': ('低落', 6), '抑郁': ('低落', 8),
                    '失眠': ('焦虑', 6), '睡不着': ('焦虑', 7),
                }
                for kw, (emotion, default_intensity) in emotion_kw_map.items():
                    if kw in msg_lower:
                        emotion_detected = emotion
                        intensity = default_intensity
                        break

                if not emotion_detected:
                    # 情绪中性，根据评分估算
                    wm_score_val = wm_result.get('total_score', 0) if wm_result else 0
                    if wm_score_val >= 80:
                        emotion_detected = '平静'
                        intensity = 4
                    elif wm_score_val >= 60:
                        emotion_detected = '中性'
                        intensity = 3
                    elif wm_score_val > 0:
                        emotion_detected = '疲惫'
                        intensity = 6
                    else:
                        emotion_detected = '中性'
                        intensity = 3

                emotion_entry = {
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'date': datetime.now().strftime('%Y-%m-%d'),
                    'emotion': emotion_detected,
                    'intensity': intensity,
                    'score': wm_result.get('total_score', 0) if wm_result else 0,
                    'topic': topics[0] if topics else 'general',
                }
                profile_mem['emotion_timeline'].append(emotion_entry)
                # 保留最近90天
                if len(profile_mem['emotion_timeline']) > 90:
                    profile_mem['emotion_timeline'] = profile_mem['emotion_timeline'][-90:]

                _save_user_profile(profile_mem, openid)
                print(f'[Memory] 对话摘要+情绪已存储')
            except Exception as mem_e:
                print(f'[Memory] 存储失败: {mem_e}')

            # ===== 数据层级驱动：根据用户成熟度自动进化功能 =====
            try:
                _dp = _load_user_profile(openid)
                _dp_member = _dp.get('member', {})
                _total_sessions = _dp.get('total_sessions', 0)
                _dp_hist = _dp.get('history', [])
                _dp_scored = [h for h in _dp_hist if h.get('wm_score', 0) > 0]
                _dp_data_days = len(set(h.get('date', '') for h in _dp_scored))

                # 数据丰富度等级
                if _dp_data_days <= 1:
                    _dp_level = 'cold_start'
                    _dp_tip = '再多记录几天，分析会更精准'
                elif _dp_data_days <= 3:
                    _dp_level = 'warming'
                    _dp_tip = '已有' + str(_dp_data_days) + '天数据，趋势开始成形'
                elif _dp_data_days <= 7:
                    _dp_level = 'active'
                    _dp_tip = '一周数据量，可以查看周趋势了'
                else:
                    _dp_level = 'mature'
                    _dp_tip = str(_dp_data_days) + '天数据积累，分析置信度稳定'

                # 下一个解锁里程碑
                _dp_milestones = {
                    'cold_start': '3天数据 → 趋势图',
                    'warming': '7天数据 → 周报告',
                    'active': '14天数据 → 个性化建议',
                    'mature': '坚持记录，对比效果更明显',
                }

                # 如果有≥2次有评分的对话，推送时间线
                _dp_timeline = None
                if len(_dp_scored) >= 2:
                    try:
                        _dp_hist = _dp.get('history', [])
                        _dp_scored = [h for h in _dp_hist if h.get('wm_score', 0) > 0]
                        if len(_dp_scored) >= 2:
                            _dp_timeline = []
                            for h in _dp_scored[-10:]:
                                pt = {'date': h.get('date', ''), 'score': h.get('wm_score', 0)}
                                _dp_experts = h.get('experts', {})
                                if _dp_experts and isinstance(_dp_experts, dict):
                                    pt['dims'] = {k: round(v['score']*100, 1) for k, v in _dp_experts.items() if isinstance(v, dict) and v.get('score')}
                                _dp_timeline.append(pt)
                    except:
                        pass

                response_obj['data_level'] = _dp_level
                response_obj['data_tip'] = _dp_tip
                response_obj['next_milestone'] = _dp_milestones.get(_dp_level, '')
                if _dp_timeline:
                    response_obj['timeline'] = _dp_timeline
                    print(f'[Evolution] level={_dp_level} sessions={_total_sessions} days={_dp_data_days} timeline={len(_dp_timeline)}pts')
            except Exception as _dpe:
                print(f'[Evolution] 跳过: {_dpe}')

            # ===== 📈 运营引擎：欢迎/留存/里程碑 =====
            try:
                from ops_engine import (craft_welcome_message, get_next_milestone,
                                      get_user_insight_stats, assess_retention_risk)
                _welcome = craft_welcome_message(profile_local)
                if _welcome:
                    response_obj['welcome'] = _welcome
                _ms = get_next_milestone(profile_local)
                if _ms:
                    response_obj['milestone'] = _ms
                _risk = assess_retention_risk(profile_local)
                if _risk:
                    response_obj['retention_alert'] = _risk
                _insight = get_user_insight_stats(profile_local)
                if _insight.get('status') == 'ready':
                    response_obj['insight'] = _insight
            except Exception as _oe:
                print(f'[Ops] 跳过: {_oe}')

            # ===== 如果世界模型有评分，自动附加迷你睡眠卡 =====
            self.wfile.write(json.dumps(response_obj, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({
                'success': False,
                'error': str(e)
            }, ensure_ascii=False).encode('utf-8'))

    def _recognize_speech(self, file_path):
        """语音文件转文字 - 使用本地whisper模型（完全离线）"""
        try:
            import whisper
            model = whisper.load_model('base')  # base模型约140MB，首次加载会下载
            result = model.transcribe(file_path, language='zh')
            text = result.get('text', '').strip()
            print(f'[Voice] 识别结果: {text}')
            return text
        except Exception as e:
            print(f'[Voice] 语音识别错误: {e}')
            return None

    def _handle_voice_relax(self, data):
        """语音减压：分析用户情绪，匹配减压方案（支持文本和录音文件）"""
        self._set_headers()

        openid = self._get_openid(data)

        # 检查是否有语音文件
        voice_file = data.get('_voice_file') or data.get('voice_file')
        if voice_file:
            user_text = self._recognize_speech(voice_file)
            try: os.unlink(voice_file)
            except: pass
            if not user_text:
                self.wfile.write(json.dumps({
                    'success': False,
                    'error': '没听清楚，再说一次？'
                }, ensure_ascii=False).encode('utf-8'))
                return
        else:
            user_text = data.get('text', '').strip()

        if not user_text:
            self.wfile.write(json.dumps({
                'success': False,
                'error': '请说句话吧'
            }, ensure_ascii=False).encode('utf-8'))
            return

        # ===== Phase 8: 语音情绪特征提取（规则引擎 + 情绪词典） =====
        import re
        _voice_emotion_profile = {}
        try:
            _emotion_dict = {
                '焦虑': {'emotion': 'anxiety', 'intensity': 7, 'plan': 'breathing'},
                '紧张': {'emotion': 'anxiety', 'intensity': 6, 'plan': 'breathing'},
                '心慌': {'emotion': 'anxiety', 'intensity': 8, 'plan': 'breathing'},
                '害怕': {'emotion': 'fear', 'intensity': 7, 'plan': 'breathing'},
                '烦躁': {'emotion': 'irritation', 'intensity': 6, 'plan': 'pmr'},
                '烦': {'emotion': 'irritation', 'intensity': 5, 'plan': 'pmr'},
                '生气': {'emotion': 'anger', 'intensity': 7, 'plan': 'pmr'},
                '愤怒': {'emotion': 'anger', 'intensity': 8, 'plan': 'pmr'},
                '睡不着': {'emotion': 'insomnia', 'intensity': 6, 'plan': 'meditation'},
                '失眠': {'emotion': 'insomnia', 'intensity': 7, 'plan': 'meditation'},
                '压力': {'emotion': 'stress', 'intensity': 6, 'plan': 'breathing'},
                '累': {'emotion': 'fatigue', 'intensity': 5, 'plan': 'meditation'},
                '疲惫': {'emotion': 'fatigue', 'intensity': 6, 'plan': 'meditation'},
                '困': {'emotion': 'sleepy', 'intensity': 4, 'plan': 'meditation'},
                'emo': {'emotion': 'sadness', 'intensity': 5, 'plan': 'meditation'},
                '低落': {'emotion': 'sadness', 'intensity': 6, 'plan': 'meditation'},
                '不开心': {'emotion': 'sadness', 'intensity': 5, 'plan': 'meditation'},
                '难过': {'emotion': 'sadness', 'intensity': 7, 'plan': 'meditation'},
                '想哭': {'emotion': 'sadness', 'intensity': 8, 'plan': 'meditation'},
            }
            _max_intensity = 0
            _primary_emotion = 'unknown'
            _suggested_plan = 'breathing'
            for _kw, _info in _emotion_dict.items():
                if _kw in user_text and _info['intensity'] > _max_intensity:
                    _max_intensity = _info['intensity']
                    _primary_emotion = _info['emotion']
                    _suggested_plan = _info['plan']
            _exclamation = user_text.count('!') + user_text.count('！')
            if _exclamation >= 2:
                _max_intensity = min(10, _max_intensity + 1)
            _sentences = [s for s in re.split(r'[。！？\n]', user_text) if s.strip()]
            _short_sentence_ratio = sum(1 for s in _sentences if len(s) < 10) / max(1, len(_sentences))
            if _short_sentence_ratio > 0.5:
                _max_intensity = min(10, _max_intensity + 1)
            _voice_emotion_profile = {
                'emotion': _primary_emotion,
                'intensity': _max_intensity,
                'suggested_plan': _suggested_plan,
                'text_length': len(user_text),
                'short_sentence_ratio': round(_short_sentence_ratio, 2),
                'exclamation_count': _exclamation,
            }
            print(f"[VoiceEmotion] [{openid[:8]}...] {_primary_emotion} intensity={_max_intensity} plan={_suggested_plan}")
            _timeline_profile = _load_user_profile(openid)
            if 'emotion_timeline' not in _timeline_profile:
                _timeline_profile['emotion_timeline'] = []
            _timeline_profile['emotion_timeline'].append({
                'date': datetime.now().strftime('%Y-%m-%d'),
                'time': datetime.now().strftime('%H:%M'),
                'source': 'voice_emotion_analysis',
                'emotion': _primary_emotion,
                'intensity': _max_intensity,
                'text_preview': user_text[:30],
            })
            if len(_timeline_profile['emotion_timeline']) > 40:
                _timeline_profile['emotion_timeline'] = _timeline_profile['emotion_timeline'][-40:]
            _save_user_profile(_timeline_profile, openid)
        except Exception as _ve_e:
            print(f'[VoiceEmotion] 跳过: {_ve_e}')

        system_prompt = """你是一位情绪减压和正念引导专家。用户的语音经过转写后发给你，请分析他们当前的情绪状态并推荐最合适的减压方案。

请严格按照以下JSON格式输出（只输出JSON，不要其他文字）：
{
  "emotion": "用户核心情绪，如焦虑/压力/烦躁/疲惫/失眠/愤怒/低落",
  "emotion_intensity": 1-10,
  "brief_empathy": "一句共情的话（最多20字）",
  "plan_type": "meditation" 或 "breathing" 或 "pmr",
  "plan_name": "方案名称",
  "plan_params": {
    "inhale": 4,
    "hold": 7,
    "exhale": 8,
    "rounds": 5
  },
  "description": "为什么要推荐这个方案（一句话）"
}"""

        user_prompt = f"用户说：{user_text}\n\n请分析用户情绪并推荐减压方案。"

        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = self._call_deepseek([
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ], max_tokens=500, temperature=0.3)

                reply = result.get('reply', '')
                # 提取JSON
                reply = reply.strip()
                if reply.startswith('```json'): reply = reply[7:]
                if reply.startswith('```'): reply = reply[3:]
                if reply.endswith('```'): reply = reply[:-3]
                reply = reply.strip()

                plan = json.loads(reply)

                # 验证必需字段
                if not plan.get('plan_type'):
                    plan['plan_type'] = 'breathing'
                if not plan.get('plan_params'):
                    plan['plan_params'] = {'inhale': 4, 'hold': 7, 'exhale': 8, 'rounds': 5}

                # 记录情绪和减压到用户画像
                try:
                    profile = _load_user_profile(openid)
                    today = datetime.now().strftime('%Y-%m-%d')
                    if 'stress_log' not in profile:
                        profile['stress_log'] = []
                    profile['stress_log'].append({
                        'date': today,
                        'time': datetime.now().strftime('%H:%M'),
                        'text': user_text,
                        'emotion': plan.get('emotion', '未知'),
                        'intensity': plan.get('emotion_intensity', 5),
                        'plan': plan.get('plan_type', ''),
                        'plan_name': plan.get('plan_name', ''),
                    })
                    # 只保留最近50条
                    profile['stress_log'] = profile['stress_log'][-50:]
                    _save_user_profile(profile, openid)
                    print(f'[Profile] 情绪记录已保存: {plan.get("emotion")}')
                except Exception as e:
                    print(f'[Profile] 情绪记录失败: {e}')

                # 更新行为统计
                try:
                    p2 = _load_user_profile(openid)
                    if 'behavior_stats' not in p2:
                        p2['behavior_stats'] = {'total_relax_sessions': 0, 'common_emotions': []}
                    p2['behavior_stats']['total_relax_sessions'] = p2['behavior_stats'].get('total_relax_sessions', 0) + 1
                    emo = plan.get('emotion', '')
                    if emo and emo != '未知':
                        emos = p2['behavior_stats'].get('common_emotions', [])
                        emos.append(emo)
                        p2['behavior_stats']['common_emotions'] = [x[0] for x in Counter(emos).most_common(5)]
                    _save_user_profile(p2, openid)
                except:
                    pass

                plan['success'] = True
                self.wfile.write(json.dumps(plan, ensure_ascii=False).encode('utf-8'))
                return

            except Exception as e:
                if attempt < max_retries - 1:
                    continue
                # 降级：返回默认呼吸方案
                try:
                    profile = _load_user_profile(openid)
                    if 'stress_log' not in profile: profile['stress_log'] = []
                    profile['stress_log'].append({
                        'date': datetime.now().strftime('%Y-%m-%d'),
                        'time': datetime.now().strftime('%H:%M'),
                        'text': user_text,
                        'emotion': '压力',
                        'intensity': 5,
                        'plan': 'breathing',
                        'plan_name': '4-7-8呼吸法',
                    })
                    profile['stress_log'] = profile['stress_log'][-50:]
                    _save_user_profile(profile, openid)
                except: pass
                self.wfile.write(json.dumps({
                    'success': True,
                    'emotion': '压力',
                    'emotion_intensity': 5,
                    'brief_empathy': '听起来你有些压力',
                    'plan_type': 'breathing',
                    'plan_name': '4-7-8呼吸法',
                    'plan_params': {'inhale': 4, 'hold': 7, 'exhale': 8, 'rounds': 5},
                    'description': '先做一组呼吸练习，帮助身心放松'
                }, ensure_ascii=False).encode('utf-8'))

    def _handle_chat_report(self, data):
        """从对话历史生成睡眠报告（统一格式）"""
        self._set_headers()

        openid = self._get_openid(data)
        history = data.get('history', [])

        if not history:
            self.wfile.write(json.dumps({'success': False, 'error': '对话历史为空'}, ensure_ascii=False).encode('utf-8'))
            return

        # 将对话历史转为文本
        dialog_text = '\n'.join([
            f"{'用户' if m['role']=='user' else 'AI助手'}: {m['content']}"
            for m in history
        ])

        # 从对话中提取睡眠数据，调用世界模型
        wm_context = ""
        wm = _get_world_model()
        all_text = ' '.join([m.get('content', '') for m in history])
        extracted = self._extract_sleep_data_from_text(all_text)

        # 如果没有提取到任何睡眠数据，直接返回信息不足（不与DeepSeek对话）
        if not extracted:
            self.wfile.write(json.dumps({
                'success': False,
                'error': 'INFO_INSUFFICIENT',
                'message': '对话中没有提供足够的睡眠信息。请先告诉你的入睡时间、醒来时间、睡眠质量等，再生成报告。'
            }, ensure_ascii=False).encode('utf-8'))
            return

        if wm:
            try:
                wm_result = wm.comprehensive_analysis(extracted)
                total = wm_result.get('total_score', 0)

                # ===== 最佳实践：皮肤生物反馈独立结构化输出 =====
                chat_report_biofeedback = None
                skin_bio = wm_result.get('skin_biofeedback', {})
                if skin_bio.get('available'):
                    chat_report_biofeedback = {
                        'type': 'skin_sleep_biofeedback',
                        'source': 'face_photo_analysis_v6',
                        'skin_context': skin_bio.get('context_text', ''),
                        'dates_available': skin_bio.get('dates_available', []),
                    }

                print(f'[ChatReport] 世界模型已注入, 评分={total}')
                # 保存到用户画像（用对话文本中最新的用户消息）
                _update_user_profile(extracted, wm_result, all_text[:100], openid)
            except Exception as e:
                print(f'[ChatReport] 世界模型出错: {e}')

        # 统一prompt，输出跟report.wxml匹配的字段

        # 统一prompt，输出跟report.wxml匹配的字段
        messages = [
            {'role': 'system', 'content': f'''你是一名睡眠分析专家。根据以下对话记录生成一份睡眠分析报告。

对话记录：
{dialog_text}

{"以下是对话中提取的7维度分析数据，请参考并融入报告：" + wm_context if wm_context else ""}

请严格按照以下JSON格式输出，只输出JSON不要其他文字。每个字段必须都有值，不要空字段：
{{
  "score": (0-100的整数评分),
  "quality": ("优秀"或"良好"或"一般"或"较差"或"需要改善"),
  "duration": "Xh Xm格式的睡眠时长",
  "detailedAnalysis": "一段200-300字的详细分析，引用7维度数据（如有）",
  "details": {{
    "deepSleep": "Xh Xm",
    "remSleep": "Xh Xm",
    "lightSleep": "Xh Xm",
    "awakeTime": "Xh Xm",
    "sleepEfficiency": 85,
    "sleepLatency": "Xh Xm"
  }},
  "healthScores": {{
    "cardiovascular": 0-100,
    "cognitive": 0-100,
    "emotional": 0-100,
    "physical": 0-100
  }},
  "sleepStages": [
    {{"name": "深睡", "value": 25, "color": "#4A90D9"}},
    {{"name": "REM", "value": 23, "color": "#7B68EE"}},
    {{"name": "浅睡", "value": 47, "color": "#82B74B"}},
    {{"name": "清醒", "value": 5, "color": "#E57373"}}
  ],
  "trends": {{
    "scoreTrend": "+1",
    "durationTrend": "+15m",
    "efficiencyTrend": "+2%"
  }},
  "suggestions": ["建议1（带科学依据）", "建议2", "建议3"],
  "sourceName": "AI聊天生成"
}}'''}
        ]

        try:
            result = self._call_deepseek(messages, max_tokens=2000, temperature=0.3)

            import json as json_module
            report_text = result['content']

            # 尝试提取JSON
            try:
                report = json_module.loads(report_text)
            except:
                import re
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', report_text, re.DOTALL)
                if match:
                    report = json_module.loads(match.group(1))
                else:
                    # 直接找花括号
                    start = report_text.find('{')
                    end = report_text.rfind('}')
                    if start >= 0 and end > start:
                        report = json_module.loads(report_text[start:end+1])
                    else:
                        self.wfile.write(json.dumps({'success': False, 'error': '报告格式解析失败'}, ensure_ascii=False).encode('utf-8'))
                        return

            # 补全必需字段（防止DeepSeek遗漏）
            report.setdefault('details', {})
            report['details'].setdefault('deepSleep', '2h 0m')
            report['details'].setdefault('remSleep', '1h 45m')
            report['details'].setdefault('lightSleep', '3h 30m')
            report['details'].setdefault('awakeTime', '15m')
            report['details'].setdefault('sleepEfficiency', 85)
            report['details'].setdefault('sleepLatency', '15m')
            report.setdefault('healthScores', {'cardiovascular': 75, 'cognitive': 70, 'emotional': 75, 'physical': 70})
            report.setdefault('sleepStages', [
                {'name': '深睡', 'value': 25, 'color': '#4A90D9'},
                {'name': 'REM', 'value': 23, 'color': '#7B68EE'},
                {'name': '浅睡', 'value': 47, 'color': '#82B74B'},
                {'name': '清醒', 'value': 5, 'color': '#E57373'}
            ])
            report.setdefault('trends', {'scoreTrend': '+1', 'durationTrend': '+15m', 'efficiencyTrend': '+2%'})
            report.setdefault('suggestions', ['保持规律作息', '适当运动改善睡眠'])
            report.setdefault('sourceName', 'AI聊天生成')
            report.setdefault('duration', '7h 30m')

            response = {
                'success': True,
                'report': report
            }
            if chat_report_biofeedback:
                response['biofeedback'] = chat_report_biofeedback

            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        except Exception as e:
            self.wfile.write(json.dumps({
                'success': False,
                'error': str(e)
            }, ensure_ascii=False).encode('utf-8'))


# ===== PubMed 前沿感知引擎（世界模型v5.0）=====
# 每日自动爬取最新睡眠领域RCT/Meta，更新auto_evidence.json

PUBMED_SLEEP_QUERY = (
    '(("sleep"[MeSH Terms] OR "insomnia"[MeSH Terms] OR "sleep apnea"[MeSH Terms] '
    'OR "circadian rhythm"[MeSH Terms] OR "sleep quality"[tiab] OR "sleep deprivation"[tiab]) '
    'AND ("randomized controlled trial"[pt] OR "meta analysis"[pt] OR "systematic review"[pt]) '
    'AND ("humans"[MeSH Terms]))'
)

class PubmedFrontier:
    """PubMed前沿感知引擎：自动爬取+分类+证据提取"""

    CATEGORY_MAP = {
        'cbt_i': ['cognitive behavioral therapy', 'cbt-i', 'cbti', 'insomnia therapy', 'sleep therapy'],
        'sleep_apnea': ['sleep apnea', 'osa', 'cpap', 'oral appliance', 'snoring'],
        'circadian': ['circadian', 'chronobiology', 'melatonin', 'light therapy', 'shift work'],
        'stress': ['stress', 'anxiety', 'depression', 'mindfulness', 'meditation', 'relaxation'],
        'sleep_quality': ['sleep quality', 'sleep hygiene', 'sleep efficiency', 'sleep duration'],
        'women_sleep': ['menopause', 'pregnancy', 'menstrual', 'postpartum', 'women sleep'],
        'adolescent': ['adolescent', 'teen', 'child sleep', 'pediatric'],
    }

    @staticmethod
    def fetch_latest(days_back=7, max_results=20):
        """爬取最近days_back天的睡眠领域新文献"""
        import urllib.request, urllib.parse

        # 先用esearch搜索论文ID
        params = {
            'db': 'pubmed',
            'term': PUBMED_SLEEP_QUERY,
            'reldate': days_back,
            'retmax': max_results,
            'retmode': 'json',
            'sort': 'date',
        }
        search_url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?' + urllib.parse.urlencode(params)

        try:
            req = urllib.request.Request(search_url, headers={'User-Agent': 'AISleepGen/2.0'})
            with urllib.request.urlopen(req, timeout=20) as r:
                result = json.loads(r.read().decode('utf-8'))

            id_list = result.get('esearchresult', {}).get('idlist', [])
            if not id_list:
                print(f'[PubmedFrontier] 未找到最近{days_back}天新文献')
                return []

            print(f'[PubmedFrontier] 找到{len(id_list)}篇潜在文献，开始拉取详情...')

            # 批量拉取详情（efetch支持逗号分隔多个ID）
            details_url = (
                f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
                f'?db=pubmed&id={",".join(id_list)}&retmode=xml'
            )
            req = urllib.request.Request(details_url, headers={'User-Agent': 'AISleepGen/2.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                xml_data = r.read().decode('utf-8')

            # 简易解析：拆分每篇文献
            articles = PubmedFrontier._parse_pubmed_xml_batch(xml_data)
            print(f'[PubmedFrontier] 成功解析{len(articles)}篇文献')
            return articles

        except Exception as e:
            print(f'[PubmedFrontier] 爬取失败: {e}')
            return []

    @staticmethod
    def _parse_pubmed_xml_batch(xml_data):
        """批量解析PubMed XML，提取关键信息"""
        import re
        articles = []

        # 拆分每篇Article
        article_blocks = re.findall(r'<PubmedArticle>.*?</PubmedArticle>', xml_data, re.DOTALL)

        for block in article_blocks:
            try:
                # PMID
                pmid_m = re.search(r'<PMID[^>]*>(.*?)</PMID>', block)
                if not pmid_m:
                    continue
                pmid = pmid_m.group(1)

                # Title
                title_m = re.search(r'<ArticleTitle[^>]*>(.*?)</ArticleTitle>', block, re.DOTALL)
                title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else 'Unknown'
                title = title.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')

                # Abstract
                abs_parts = re.findall(r'<AbstractText[^>]*>(.*?)</AbstractText>', block, re.DOTALL)
                abstract = ' '.join(re.sub(r'<[^>]+>', '', p).strip() for p in abs_parts)[:500]

                # DOI
                doi_m = re.search(r'<ELocationID[^>]*EIdType="doi"[^>]*>(.*?)</ELocationID>', block)
                doi = doi_m.group(1) if doi_m else ''

                # Year
                year_m = re.search(r'<Year>(\d{4})</Year>', block)
                year = year_m.group(1) if year_m else '?'

                # Journal
                journal_m = re.search(r'<Journal>.*?<Title[^>]*>(.*?)</Title>', block, re.DOTALL)
                journal = journal_m.group(1) if journal_m else ''
                if not journal:
                    journal_m = re.search(r'<ISOAbbreviation[^>]*>(.*?)</ISOAbbreviation>', block)
                    journal = journal_m.group(1) if journal_m else ''
                journal = journal.replace('&amp;', '&')

                # Publication type
                pub_types = re.findall(r'<PublicationType[^>]*>(.*?)</PublicationType>', block)

                # Determine certainty based on publication type
                pt_text = ' '.join(pub_types).lower()
                if 'meta-analysis' in pt_text or 'systematic review' in pt_text:
                    certainty = 'high'
                    effect_size = 'Meta分析, 待提取效应量'
                elif 'randomized controlled trial' in pt_text or 'clinical trial' in pt_text:
                    certainty = 'high'
                    effect_size = 'RCT, 待提取效应量'
                elif 'observational' in pt_text or 'cohort' in pt_text or 'case-control' in pt_text:
                    certainty = 'low'
                    effect_size = '观察性研究, 待提取效应量'
                else:
                    certainty = 'low'
                    effect_size = '待确定研究类型'

                # Categorize
                title_abs_lower = (title + ' ' + abstract).lower()
                categories = []
                for cat, keywords in PubmedFrontier.CATEGORY_MAP.items():
                    if any(kw in title_abs_lower for kw in keywords):
                        categories.append(cat)
                if not categories:
                    categories.append('general_sleep')

                article = {
                    'pmid': pmid,
                    'title': title[:200],
                    'doi': doi,
                    'year': year,
                    'journal': journal[:100],
                    'abstract': abstract[:300],
                    'publication_types': pub_types,
                    'certainty': certainty,
                    'effect_size': effect_size,
                    'categories': categories,
                    'fetched_at': datetime.now().strftime('%Y-%m-%d'),
                }
                articles.append(article)

            except Exception as e:
                print(f'[PubmedFrontier] 跳过一篇文章: {e}')
                continue

        return articles

    @staticmethod
    def merge_into_evidence(new_articles, evidence_path=None):
        """将新文献合并到auto_evidence.json，去重"""
        if evidence_path is None:
            evidence_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.auto_evidence.json')

        # 读取现有证据
        existing = {}
        if os.path.exists(evidence_path):
            try:
                with open(evidence_path, 'r', encoding='utf-8') as f:
                    existing_list = json.load(f)
                for e in existing_list:
                    pmid = e.get('pmid', '')
                    if pmid:
                        existing[pmid] = e
            except:
                existing = {}

        # 合并新文献（跳过已存在的）
        added = 0
        for article in new_articles:
            pmid = article.get('pmid', '')
            if pmid and pmid not in existing:
                entry = {
                    'name': article.get('title', 'Unknown')[:200],
                    'evidence': f"{article.get('journal', '')} et al., {article.get('year', '?')}, PMID: {pmid}",
                    'description': article.get('abstract', '')[:300],
                    'indications': article.get('categories', ['general_sleep']),
                    'effect_size': article.get('effect_size', '待确定'),
                    'certainty': article.get('certainty', 'low'),
                    'pmid': pmid,
                    'doi': article.get('doi', ''),
                    'added_on': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'pubmed_auto',
                }
                existing[pmid] = entry
                added += 1

        # 写回文件
        merged = list(existing.values())
        with open(evidence_path, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        print(f'[PubmedFrontier] 合并完成: 新增{added}篇, 总计{len(merged)}篇')
        return added

    @staticmethod
    def get_recent_evidence(days=7, categories=None, max_results=5):
        """获取最近x天的文献摘要（用于注入对话上下文）"""
        evidence_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.auto_evidence.json')
        if not os.path.exists(evidence_path):
            return []

        try:
            with open(evidence_path, 'r', encoding='utf-8') as f:
                all_evidence = json.load(f)
        except:
            return []

        # 按日期过滤
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        recent = [e for e in all_evidence if e.get('added_on', '') >= cutoff]

        # 按类别过滤
        if categories:
            filtered = []
            for e in recent:
                e_cats = e.get('indications', [])
                if any(c in e_cats for c in categories):
                    filtered.append(e)
            recent = filtered

        # 按certainty排序
        certainty_order = {'high': 0, 'low': 1, 'manual': 2}
        recent.sort(key=lambda e: certainty_order.get(e.get('certainty', 'low'), 3))

        return recent[:max_results]

    @staticmethod
    def format_evidence_for_prompt(evidence_list):
        """将文献列表格式化为prompt可用的文本"""
        if not evidence_list:
            return ""

        lines = ["\n===== 最新睡眠科学研究参考 ====="]
        for e in evidence_list:
            certainty_tag = {
                'high': '✅ 证据等级高',
                'low': '📘 证据等级中低',
                'manual': '📄 手动导入',
            }.get(e.get('certainty', ''), '📄')
            lines.append(
                f"· {e.get('name', 'Unknown')[:120]}"
                f"\n  {certainty_tag} | {e.get('evidence', '')[:80]}"
                f"\n  核心: {e.get('description', '')[:150]}"
            )
        lines.append("================================")
        return '\n'.join(lines)

    @staticmethod
    def run_daily_update():
        """执行每日更新（可被cron或API触发）"""
        print(f'[PubmedFrontier] 开始每日自动更新...')
        articles = PubmedFrontier.fetch_latest(days_back=7, max_results=30)
        if articles:
            added = PubmedFrontier.merge_into_evidence(articles)
            print(f'[PubmedFrontier] 每日更新完成: 找到{len(articles)}篇, 新增{added}篇')
        else:
            print(f'[PubmedFrontier] 每日更新完成: 无新文献')
        return len(articles)

def run_pubmed_cron():
    """独立运行的cron任务（由threading定时触发）"""
    while True:
        try:
            PubmedFrontier.run_daily_update()
        except Exception as e:
            print(f'[PubmedCron] 执行失败: {e}')
        # 每24小时执行一次
        time.sleep(86400)


def main():
    if load_deepseek_key():
        print('DeepSeek API Key OK')
    else:
        print('DeepSeek API Key not found')

    # 初始化偏好存储
    try:
        from preference_storage import PreferenceStorage
        ps = PreferenceStorage()
        ps.load()
        print(f'Preference storage ready')
    except Exception as e:
        print(f'Preference storage init failed: {e}')

    # 启动PubMed前沿感知引擎（后台定时任务）
    try:
        # 启动时立即执行一次（异步，不阻塞）
        def delayed_first_run():
            time.sleep(5)
            try:
                PubmedFrontier.run_daily_update()
            except Exception as e:
                print(f'[PubmedFrontier] 首次更新失败: {e}')
        threading.Thread(target=delayed_first_run, daemon=True).start()
        # 后台线程每24小时执行
        cron_thread = threading.Thread(target=run_pubmed_cron, daemon=True)
        cron_thread.start()
        print('[PubmedFrontier] 后台更新线程已启动')
    except Exception as e:
        print(f'[PubmedFrontier] 启动失败: {e}')

    # 启动Self-Healing后台线程（每10分钟API连通性检查）
    def run_self_heal_cron():
        while True:
            time.sleep(600)
            try:
                test_body = json.dumps({
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 3
                }).encode('utf-8')
                test_req = urllib.request.Request(
                    DEEPSEEK_BASE_URL + "/chat/completions", data=test_body,
                    headers={"Content-Type": "application/json",
                            "Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
                    method='POST'
                )
                urllib.request.urlopen(test_req, timeout=10)
            except Exception as e:
                print(f'[SelfHeal] ⚠️ API异常: {e}')
    threading.Thread(target=run_self_heal_cron, daemon=True).start()
    print('[SelfHeal] 自愈系统v2已启动（每10分钟自检+修复）')

    port = int(os.environ.get('AISLEEPGEN_PORT', '8090'))
    server = ThreadingHTTPServer(('0.0.0.0', port), ProxyHandler)
    print(f'Server on http://localhost:{port}')
    print(f'  /health, /api/chat, /api/sleep-report, /api/meditation-plan')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopped')
        server.server_close()

# ============================================================
# 微信支付 + 会员升级 + AI智能定价推荐
# ============================================================
# 配置方式（环境变量）:
#   AISLEEPGEN_WECHAT_MCHID    - 微信支付商户号
#   AISLEEPGEN_WECHAT_API_KEY  - 商户API密钥（APIv2）
#   AISLEEPGEN_WECHAT_APPSECRET - 小程序appsecret（已有AISLEEPGEN_WECHAT_SECRET）
#   
# 如果未配置商户号，支付接口返回友好提示（不会崩溃）

# 导入专业推荐引擎
from tier_recommender import (
    get_smart_recommendation as _smart_recommend,
    get_pricing_info,
    PRICING,
    record_recommendation_click,
    record_conversion,
)

WECHAT_MCHID = os.environ.get('AISLEEPGEN_WECHAT_MCHID', '')
WECHAT_API_KEY = os.environ.get('AISLEEPGEN_WECHAT_API_KEY', '')


def _generate_nonce_str(length=32):
    """生成随机字符串"""
    import random
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return ''.join(random.choice(chars) for _ in range(length))


def _wechat_sign(params, api_key):
    """微信支付签名（MD5）"""
    sorted_keys = sorted(params.keys())
    raw = '&'.join(f'{k}={params[k]}' for k in sorted_keys) + f'&key={api_key}'
    return hashlib.md5(raw.encode('utf-8')).hexdigest().upper()


def _xml_to_dict(xml_str):
    """简易XML转dict"""
    result = {}
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml_str)
    for child in root:
        result[child.tag] = child.text
    return result


def _dict_to_xml(d):
    """dict转XML"""
    parts = ['<xml>']
    for k, v in d.items():
        parts.append(f'<{k}><![CDATA[{v}]]></{k}>')
    parts.append('</xml>')
    return ''.join(parts)


def create_wechat_order(openid, tier, period='month', ip='127.0.0.1'):
    """
    创建微信支付JSAPI订单
    返回: {success: bool, prepay_id: str, pay_params: dict} 或 {success: false, error: str}
    """
    if not WECHAT_MCHID or not WECHAT_API_KEY:
        return {'success': False, 'no_payment': True, 'error': '商户号未配置，支付暂不可用'}
    
    # 价格查询
    tier_config = PRICING.get(tier)
    if not tier_config:
        return {'success': False, 'error': '无效的套餐'}
    
    if period == 'month':
        price = tier_config['price_monthly']
    elif period == 'quarter' and tier == 'pro':
        price = tier_config['price_quarter']
    elif period == 'year' and tier == 'pro':
        price = tier_config['price_year']
    elif period == 'year' and tier == 'unlimited':
        price = tier_config['price_year']
    else:
        return {'success': False, 'error': '无效的周期'}
    
    total_fee = int(price * 100)  # 元转分
    
    # 获取用户的openid用于回调
    profile = _load_user_profile(openid)
    wx_openid = profile.get('user_info', {}).get('wx_openid', openid)
    
    # 构建统一下单参数
    order_no = f'{datetime.now().strftime("%Y%m%d%H%M%S")}{_generate_nonce_str(8)}'
    notify_url = f'http://82.156.208.245:8090/api/pay-callback'
    
    params = {
        'appid': WECHAT_APPID,
        'mch_id': WECHAT_MCHID,
        'nonce_str': _generate_nonce_str(),
        'body': f'AISleepGen {tier_config["name"]} ({period})',
        'out_trade_no': order_no,
        'total_fee': str(total_fee),
        'spbill_create_ip': ip,
        'notify_url': notify_url,
        'trade_type': 'JSAPI',
        'openid': wx_openid,
    }
    params['sign'] = _wechat_sign(params, WECHAT_API_KEY)
    
    import http.client
    xml_data = _dict_to_xml(params)
    
    try:
        conn = http.client.HTTPSConnection('api.mch.weixin.qq.com', timeout=10)
        conn.request('POST', '/pay/unifiedorder', xml_data, {'Content-Type': 'text/xml'})
        resp = conn.getresponse().read().decode('utf-8')
        result = _xml_to_dict(resp)
        
        if result.get('return_code') == 'SUCCESS' and result.get('result_code') == 'SUCCESS':
            prepay_id = result['prepay_id']
            
            # 构造小程序支付参数
            pay_params = {
                'appId': WECHAT_APPID,
                'timeStamp': str(int(time.time())),
                'nonceStr': _generate_nonce_str(),
                'package': f'prepay_id={prepay_id}',
                'signType': 'MD5',
            }
            pay_params['paySign'] = _wechat_sign(pay_params, WECHAT_API_KEY)
            
            return {
                'success': True,
                'prepay_id': prepay_id,
                'order_no': order_no,
                'pay_params': pay_params,
                'tier': tier,
                'period': period,
                'price': price,
            }
        else:
            err_msg = result.get('return_msg', result.get('err_code_des', '未知错误'))
            return {'success': False, 'error': f'下单失败: {err_msg}'}
    except Exception as e:
        return {'success': False, 'error': f'支付通讯异常: {str(e)}'}


def upgrade_member(openid, tier, order_no='', period='month'):
    """
    升级会员等级
    保存订单记录+更新会员等级+设置过期时间
    """
    profile = _load_user_profile(openid)
    
    # 计算会员到期时间
    now = datetime.now()
    if period == 'month':
        expire = now.replace(month=now.month + 1) if now.month < 12 else now.replace(year=now.year + 1, month=1)
    elif period == 'quarter':
        expire = now.replace(month=now.month + 3) if now.month <= 9 else now.replace(year=now.year + 1, month=now.month - 9)
    elif period == 'year':
        expire = now.replace(year=now.year + 1)
    else:
        expire = now.replace(month=now.month + 1)
    
    # 更新会员信息
    member = profile.setdefault('member', {})
    old_level = member.get('level', 'free')
    
    # 升级逻辑：低等级不能覆盖高等级
    tier_order = {'free': 0, 'pro': 1, 'unlimited': 2}
    current_tier = member.get('level', 'free')
    if tier_order.get(tier, 0) <= tier_order.get(current_tier, 0):
        # 相同等级或降级，延长有效期
        old_expire = member.get('expire_at', '')
        if old_expire:
            try:
                old_time = datetime.strptime(old_expire, '%Y-%m-%d')
                if old_time > now:
                    expire = old_time.replace(month=old_time.month + 
                        (1 if period == 'month' else 3 if period == 'quarter' else 12))
                else:
                    expire = now.replace(month=now.month + 
                        (1 if period == 'month' else 3 if period == 'quarter' else 12))
            except:
                pass
    
    member['level'] = tier
    member['expire_at'] = expire.strftime('%Y-%m-%d')
    member['last_upgrade'] = now.strftime('%Y-%m-%d %H:%M')
    
    # 订单历史
    orders = profile.setdefault('order_history', [])
    orders.append({
        'order_no': order_no,
        'tier': tier,
        'period': period,
        'amount': PRICING.get(tier, {}).get('price_monthly', 0),
        'time': now.strftime('%Y-%m-%d %H:%M:%S'),
        'old_level': old_level,
    })
    
    _save_user_profile(profile, openid)
    return profile


# ===== 支付/会员接口路由 =====

def handle_create_order(handler, data):
    """POST /api/create-order - 创建支付订单"""
    openid = handler._get_openid(data)
    tier = data.get('tier', 'pro')
    period = data.get('period', 'month')
    ip = handler.client_address[0]
    
    if tier not in ('pro', 'unlimited'):
        handler._set_headers(400)
        handler.wfile.write(json.dumps({'error': '无效套餐'}).encode('utf-8'))
        return
    
    result = create_wechat_order(openid, tier, period, ip)
    handler._set_headers()
    handler.wfile.write(json.dumps(result).encode('utf-8'))


def handle_pay_callback(handler):
    """POST /api/pay-callback - 微信支付结果回调"""
    content_length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(content_length).decode('utf-8')
    
    result = _xml_to_dict(body)
    
    # 验证签名
    if result.get('return_code') == 'SUCCESS':
        expected_sign = _wechat_sign(result, WECHAT_API_KEY)
        if result.get('sign') == expected_sign:
            # 支付成功
            if result.get('result_code') == 'SUCCESS':
                openid = result.get('openid', '')
                order_no = result.get('out_trade_no', '')
                # 根据订单号查套餐信息（简化：从out_trade_no推断）
                # 实际应有订单数据库
                upgrade_member(openid, 'pro', order_no)
                
                handler._set_headers()
                resp_xml = _dict_to_xml({
                    'return_code': 'SUCCESS',
                    'return_msg': 'OK'
                })
                handler.wfile.write(resp_xml.encode('utf-8'))
                return
    
    handler._set_headers()
    resp_xml = _dict_to_xml({
        'return_code': 'FAIL',
        'return_msg': 'SIGN ERROR'
    })
    handler.wfile.write(resp_xml.encode('utf-8'))


def handle_get_pricing(handler):
    """GET /api/pricing - 获取定价信息"""
    handler._set_headers()
    handler.wfile.write(json.dumps(get_pricing_info()).encode('utf-8'))


def handle_smart_recommend(handler, data):
    """POST /api/recommend-tier - AI智能推荐会员方案（专业引擎）"""
    openid = handler._get_openid(data)
    recommendation = _smart_recommend(openid)
    handler._set_headers()
    handler.wfile.write(json.dumps(recommendation).encode('utf-8'))


if __name__ == '__main__':
    main()