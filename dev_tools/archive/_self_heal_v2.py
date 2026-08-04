#!/usr/bin/env python3
"""
SelfHeal v2 — 真正的自愈系统
检测+修复+报警，不光是“我还活着”

集成方式: 在 deepseek_proxy.py 中 import 并启动
"""
import os, sys, json, time, threading, traceback
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(BASE_DIR, "user_profile.json")
PROFILE_BACKUP_DIR = os.path.join(BASE_DIR, "profile_backups")
HEAL_LOG_PATH = os.path.join(BASE_DIR, "heal_actions.json")
ALERT_THRESHOLD = 5  # 连续修复失败 N 次，标记为严重

# 健康指标存储
class HealthMetrics:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_time = time.time()
        self.total_requests = 0
        self.failed_requests = 0
        self.last_repair_time = None
        self.repair_count = 0
        self.consecutive_failures = 0
        self.warnings = []
    
    def record_request(self, ok):
        with self.lock:
            self.total_requests += 1
            if not ok:
                self.failed_requests += 1
                self.consecutive_failures += 1
            else:
                self.consecutive_failures = 0
    
    def error_rate(self):
        with self.lock:
            if self.total_requests == 0:
                return 0.0
            return self.failed_requests / self.total_requests
    
    def uptime(self):
        return time.time() - self.start_time
    
    def add_warning(self, msg):
        with self.lock:
            self.warnings.append({"time": datetime.now().isoformat(), "msg": msg})
            if len(self.warnings) > 100:
                self.warnings = self.warnings[-100:]

METRICS = HealthMetrics()

# ============================================================
# 修复动作
# ============================================================

def _fix_profile_fields(profile):
    """填充缺失字段"""
    default = {
        'meta_params': {
            'intervention_threshold': 0.5,
            'breath_rounds_base': 3,
            'breath_rounds_scale': 0.5,
            'preferred_pattern': '4-7-8',
            'noise_preference': 'ocean',
            'feature_vector': [0.0] * 8,
            'total_interactions': 0,
            'response_rate': 0.0,
            'completion_rate': 0.0,
            'avg_hrv_change': 0.0,
            '_pattern_scores': {},
            'last_meta_update': None,
            'confidence': 0.3,
        },
        'member': {
            'level': 'free',
            'joined_at': datetime.now().strftime('%Y-%m-%d'),
            'last_active': datetime.now().strftime('%Y-%m-%d'),
            'streak_days': 0,
            'total_days': 0,
            'daily_scores': [],
            'active_dates': [],
        },
        'behavior_stats': {
            'total_relax_sessions': 0,
            'total_completed_sessions': 0,
            'total_interrupted_sessions': 0,
            'total_relax_seconds': 0,
            'avg_relax_duration': 0,
            'relax_streak_days': 0,
            'stress_type_distribution': {},
            'last_relax_date': None,
            'common_emotions': [],
            'weekly_counts': [],
        },
        'total_sessions': 0,
        'history': [],
    }
    fixes = []
    for section, fields in default.items():
        if section not in profile:
            profile[section] = fields
            fixes.append(f"添加缺失字段: {section}")
        elif isinstance(fields, dict):
            for k, v in fields.items():
                if k not in profile[section]:
                    profile[section][k] = v
                    fixes.append(f"填充 {section}.{k}")
    return fixes

def fix_profile_corruption():
    """数据自修复：检查并修复 user_profile.json"""
    fixes = []
    try:
        if not os.path.exists(PROFILE_PATH):
            fixes.append("profile 文件不存在（首次运行无需修复）")
            return fixes
        
        # 备份当前文件
        os.makedirs(PROFILE_BACKUP_DIR, exist_ok=True)
        backup_name = f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        backup_path = os.path.join(PROFILE_BACKUP_DIR, backup_name)
        
        # 读文件
        with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
            raw = f.read()
        
        # 验证 JSON 完整性
        try:
            all_profiles = json.loads(raw)
        except json.JSONDecodeError as e:
            # 文件损坏！尝试修复
            fixes.append(f"JSON 解析错误: {e}")
            # 尝试从备份恢复
            backups = sorted(os.listdir(PROFILE_BACKUP_DIR), reverse=True)
            restored = False
            for bk in backups[:5]:
                bk_path = os.path.join(PROFILE_BACKUP_DIR, bk)
                try:
                    with open(bk_path, 'r', encoding='utf-8') as f:
                        json.loads(f.read())
                    # 这是个有效的备份
                    import shutil
                    shutil.copy2(bk_path, PROFILE_PATH)
                    fixes.append(f"从备份恢复: {bk}")
                    restored = True
                    break
                except:
                    continue
            if not restored:
                # 备份后再修复
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(raw)
                # 用默认 profile 重建
                all_profiles = {"default": _get_default_profile()}
                fixes.append(f"文件损坏，重建默认文件（已备份到 {backup_name}）")
        
        if not isinstance(all_profiles, dict):
            fixes.append("数据非 dict 格式，重建")
            all_profiles = {}
        
        # 检查每个用户的字段完整性
        for oid, profile in list(all_profiles.items()):
            user_fixes = _fix_profile_fields(profile)
            if user_fixes:
                fixes.extend([f"[{oid[:12]}...] {f}" for f in user_fixes])
        
        # 写回（自动修复后）
        with open(PROFILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(all_profiles, f, ensure_ascii=False, indent=2)
        
        if not fixes:
            fixes.append("数据文件正常")
        
    except Exception as e:
        fixes.append(f"修复过程出错: {e}")
    
    return fixes

def _get_default_profile():
    """镜像 deepseek_proxy.py 中的默认画像"""
    return {
        'history': [], 'latest': {}, 'total_sessions': 0,
        'stress_log': [], 'relax_log': [],
        'behavior_stats': {
            'total_relax_sessions': 0, 'total_completed_sessions': 0,
            'total_interrupted_sessions': 0, 'total_relax_seconds': 0,
            'avg_relax_duration': 0, 'relax_streak_days': 0,
            'stress_type_distribution': {}, 'last_relax_date': None,
            'common_emotions': [], 'weekly_counts': [],
        },
        'member': {
            'level': 'free', 'joined_at': datetime.now().strftime('%Y-%m-%d'),
            'last_active': datetime.now().strftime('%Y-%m-%d'),
            'streak_days': 0, 'total_days': 0, 'daily_scores': [],
            'active_dates': [],
        },
        'user_info': {'nickname': '睡眠探索者', 'avatar_url': '', 'gender': 0, 'age_range': ''},
        'meta_params': {
            'intervention_threshold': 0.5, 'breath_rounds_base': 3,
            'breath_rounds_scale': 0.5, 'preferred_pattern': '4-7-8',
            'noise_preference': 'ocean', 'feature_vector': [0.0] * 8,
            'total_interactions': 0, 'response_rate': 0.0,
            'completion_rate': 0.0, 'avg_hrv_change': 0.0,
            '_pattern_scores': {}, 'last_meta_update': None, 'confidence': 0.3,
        },
    }

def clean_expired_data():
    """清理过期数据"""
    fixes = []
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 删除 90 天前的备份
        if os.path.exists(PROFILE_BACKUP_DIR):
            cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y%m%d')
            for f in os.listdir(PROFILE_BACKUP_DIR):
                if f < cutoff:
                    os.remove(os.path.join(PROFILE_BACKUP_DIR, f))
                    fixes.append(f"清理过期备份: {f}")
        
        # 压缩 user_profile.json（保留最近 90 天的历史，删除更早的）
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
                all_profiles = json.load(f)
            
            for oid, profile in all_profiles.items():
                if 'history' in profile and len(profile['history']) > 90:
                    profile['history'] = profile['history'][-90:]
                    fixes.append(f"[{oid[:12]}...] 压缩历史到 90 条")
            
            with open(PROFILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(all_profiles, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        fixes.append(f"清理出错: {e}")
    
    return fixes

# ============================================================
# 自愈调度器
# ============================================================

def _run_heal_cycle():
    """单次自愈检查+修复"""
    all_fixes = []
    all_issues = []
    
    # 1. 数据自修复
    data_fixes = fix_profile_corruption()
    all_fixes.extend(data_fixes)
    
    # 2. 清理过期数据 (每天一次)
    hour = datetime.now().hour
    if hour == 3:  # 凌晨 3 点
        clean_fixes = clean_expired_data()
        all_fixes.extend(clean_fixes)
    
    # 3. 检查请求积压
    consecutive = METRICS.consecutive_failures
    if consecutive >= 5:
        all_issues.append(f"连续 {consecutive} 次请求失败")
    if METRICS.error_rate() > 0.3 and METRICS.total_requests > 10:
        all_issues.append(f"错误率 {METRICS.error_rate()*100:.0f}%")
    
    # 4. 检查 API key
    api_ok = True  # 由外部传入
    
    return all_fixes, all_issues

def heal_scheduler():
    """自愈循环（后台线程）"""
    while True:
        try:
            fixes, issues = _run_heal_cycle()
            
            # 记录修复动作
            if fixes or issues:
                heal_log = []
                if os.path.exists(HEAL_LOG_PATH):
                    try:
                        with open(HEAL_LOG_PATH, 'r', encoding='utf-8') as f:
                            heal_log = json.load(f)
                    except:
                        heal_log = []
                
                entry = {
                    "time": datetime.now().isoformat(),
                    "fixes": fixes,
                    "issues": issues,
                }
                heal_log.append(entry)
                if len(heal_log) > 200:
                    heal_log = heal_log[-200:]
                
                with open(HEAL_LOG_PATH, 'w', encoding='utf-8') as f:
                    json.dump(heal_log, f, ensure_ascii=False, indent=2)
                
                if fixes:
                    print(f'[SelfHeal] 已修复: {"; ".join(fixes[:3])}{"..." if len(fixes) > 3 else ""}')
                if issues:
                    print(f'[SelfHeal] ❌ 告警: {"; ".join(issues)}')
            else:
                print(f'[SelfHeal] 自检正常')
                
        except Exception as e:
            print(f'[SelfHeal] 自愈循环异常: {e}')
        
        time.sleep(600)  # 10分钟

def start_self_heal():
    """启动自愈系统"""
    print('[SelfHeal] v2 自愈系统启动（每10分钟自检+修复）')
    t = threading.Thread(target=heal_scheduler, daemon=True)
    t.start()
    return t

# ============================================================
# API 集成装饰器（统计请求健康）
# ============================================================

def monitor_request(handler_func):
    """装饰 HTTP 请求处理函数，统计成功/失败"""
    def wrapper(*args, **kwargs):
        try:
            result = handler_func(*args, **kwargs)
            METRICS.record_request(True)
            return result
        except Exception as e:
            METRICS.record_request(False)
            raise
    return wrapper

# 快速测试入口
if __name__ == "__main__":
    print("=== SelfHeal v2 测试 ===")
    fixes, issues = _run_heal_cycle()
    print(f"修复: {fixes}")
    print(f"问题: {issues}")
    print(f"健康指标: 运行 {METRICS.uptime()/60:.0f}min, "
          f"请求 {METRICS.total_requests}, 错误率 {METRICS.error_rate():.1%}")
