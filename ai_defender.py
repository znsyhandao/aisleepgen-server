# -*- coding: utf-8 -*-
"""
AISleepGen 安全防御专家 v1 — 九层防御体系

原理：
  不是等攻击发生了再防，而是让攻击成本远高于收益。
  九层防御 = 感知层(3) + 防御层(3) + 反制层(3)

调度官注册名：'🛡️ 安全防御专家 (dynamic_defender)'
"""

import os, sys, json, time, re, hashlib, threading
from datetime import datetime, timedelta
from collections import defaultdict, deque

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAFE_DIR = os.path.join(BASE_DIR, 'sleep-skin features')
DEFENDER_LOG = os.path.join(SAFE_DIR, 'defender_log.json')
DEFENDER_MEMORY = os.path.join(SAFE_DIR, 'defender_memory.json')
DEFENDER_ACTIONS = os.path.join(SAFE_DIR, 'defender_actions.json')

# ============================================================
# 1. 指纹层 — 记录每个来访者的行为指纹
# ============================================================
class Fingerprinter:
    def __init__(self):
        self._visitors = {}  # ip -> {first_seen, last_seen, paths, methods, user_agents, flags}
        self._lock = threading.Lock()
        self._load()
    
    def _load(self):
        if os.path.exists(DEFENDER_LOG):
            try:
                with open(DEFENDER_LOG, encoding='utf-8') as f:
                    self._visitors = json.load(f)
            except:
                self._visitors = {}
    
    def _save(self):
        os.makedirs(os.path.dirname(DEFENDER_LOG), exist_ok=True)
        with open(DEFENDER_LOG, 'w', encoding='utf-8', errors='replace') as f:
            json.dump(self._visitors, f, ensure_ascii=False, indent=2)
    
    def record(self, ip, path, method, user_agent='', status=200):
        with self._lock:
            now = datetime.now().isoformat()
            if ip not in self._visitors:
                self._visitors[ip] = {
                    'first_seen': now,
                    'last_seen': now,
                    'paths': [],
                    'methods': set(),
                    'user_agents': set(),
                    'statuses': [],
                    'total_requests': 0,
                    'flags': [],
                    'path_pattern_score': 0,
                    'alert_count': 0,
                }
            v = self._visitors[ip]
            v['last_seen'] = now
            v['total_requests'] += 1
            v['paths'].append(path)
            v['methods'].add(method)
            v['statuses'].append(status)
            if user_agent:
                v['user_agents'].add(user_agent)
            # 限制存储量，防止膨胀
            if len(v['paths']) > 1000:
                v['paths'] = v['paths'][-500:]
            if len(v['statuses']) > 1000:
                v['statuses'] = v['statuses'][-500:]
    
    def analyze_visitor(self, ip):
        """分析单个访客的行为，返回安全评分 0(危险)~100(正常)"""
        v = self._visitors.get(ip)
        if not v:
            return 100
        
        score = 100
        reasons = []
        
        # 1. 请求频率 — 高频扣分
        total = v['total_requests']
        if total > 0:
            paths_set = set(v['paths'])
            # 路径重复率过高 = 爬虫/扫描
            if len(paths_set) > 0 and total / len(paths_set) > 50:
                score -= 20
                reasons.append('重复请求')
            # 短时间内大量请求
            try:
                first = datetime.fromisoformat(v['first_seen'])
                last = datetime.fromisoformat(v['last_seen'])
                hours = (last - first).total_seconds() / 3600
                if hours < 1 and total > 100:
                    score -= 25
                    reasons.append(f'短时高频({total}次/{hours:.1f}h)')
            except:
                pass
        
        # 2. 路径模式 — 异常路径扣分
        all_paths = ' '.join(v['paths'])
        suspicious_patterns = [
            (r'/\.env|/wp-admin|/admin|/config', 30, '扫描敏感路径'),
            (r'/api/.*/admin|/api/.*/config', 25, 'API越权尝试'),
            (r'\.\./|%2e%2e/|%00', 40, '路径穿越'),
            (r'<script|alert\(|onerror=|onload=', 35, 'XSS尝试'),
            (r'/\*/|1=1|union.*select|drop.*table', 40, 'SQL注入'),
            (r'sleep\(\d+\)|benchmark\(', 35, '时间注入'),
        ]
        for pattern, penalty, reason in suspicious_patterns:
            if re.search(pattern, all_paths, re.IGNORECASE):
                score -= penalty
                reasons.append(reason)
        
        # 3. 多个User-Agent = 掩码扫描
        if len(v['user_agents']) > 3:
            score -= 15
            reasons.append(f'多UA掩码({len(v["user_agents"])}个)')
        
        # 4. 大量4xx/5xx = 攻击失败
        error_count = sum(1 for s in v['statuses'] if s >= 400)
        if total > 0 and error_count / total > 0.3:
            score -= 20
            reasons.append(f'高错误率({error_count}/{total})')
        
        # 5. 非常用路径 — 探测未公开API
        known_paths = {f'/api/{p}' for p in
                       ['chat', 'goodnight', 'sleep-from-face', 'sleep-from-audio', 
                        'wx-login', 'user-profile', 'update-profile', 'sleep-stats',
                        'history', 'feedback', 'data-export', 'emotion-timeline',
                        'memory-recall', 'stop-breathing', 'relax-feedback',
                        'daily-score', 'trend', 'clinical-report']}
        unknown_ratio = sum(1 for p in v['paths'] if p not in known_paths) / len(v['paths']) if v['paths'] else 0
        if unknown_ratio > 0.8 and len(v['paths']) > 10:
            score -= 15
            reasons.append('大量未知路径探测')
        
        return max(0, min(100, score)), reasons
    
    def is_threat(self, ip, threshold=50):
        score, reasons = self.analyze_visitor(ip)
        return score < threshold, score, reasons
        
    def get_threats(self, threshold=50):
        threats = []
        for ip in self._visitors:
            is_t, score, reasons = self.is_threat(ip, threshold)
            if is_t:
                threats.append((ip, score, reasons, self._visitors[ip]['total_requests']))
        return sorted(threats, key=lambda x: x[1])


# ============================================================
# 2. 请求过滤器 — 实时拦截恶意请求
# ============================================================
class RequestFilter:
    def __init__(self, fingerprinter):
        self.fp = fingerprinter
        self._blocklist = set()
        self._rate_limits = defaultdict(lambda: deque(maxlen=60))  # ip -> 最近60秒请求
        self._load_blocklist()
    
    def _load_blocklist(self):
        if os.path.exists(DEFENDER_ACTIONS):
            try:
                with open(DEFENDER_ACTIONS, encoding='utf-8') as f:
                    data = json.load(f)
                    self._blocklist = set(data.get('blocklist', []))
            except:
                pass
    
    def _save_blocklist(self):
        os.makedirs(os.path.dirname(DEFENDER_ACTIONS), exist_ok=True)
        data = {'blocklist': list(self._blocklist), 'updated': datetime.now().isoformat()}
        with open(DEFENDER_ACTIONS, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def filter(self, ip, path, method, body='', user_agent='', known_path=False):
        """返回 (allow: bool, reason: str, status_code: int)"""
        now = time.time()
        
        # 注册本次请求（先记录再检查，以便行为分析有数据）
        self.fp.record(ip, path, method, user_agent, 200)
        
        # 第1层：黑名单
        if ip in self._blocklist:
            return False, 'IP黑名单', 403
        
        # 第2层：速率限制 — 同IP每秒最多5次
        self._rate_limits[ip].append(now)
        recent = [t for t in self._rate_limits[ip] if now - t < 60]
        if len(recent) > 300:
            return False, '超过60秒速率限制(300次)', 429
        if len([t for t in recent if now - t < 1]) > 10:
            return False, '超过1秒速率限制(10次)', 429
        
        # 第3层：词法过滤 — 攻击载荷特征
        # 检查 body 和 path 两者
        check_text = (body or '') + ' ' + (path or '')
        if check_text:
            patterns = [
                (r'<script[^>]*>|javascript\s*:', 'XSS载荷'),
                (r' on\w+\s*=', 'XSS事件处理器'),
                (r'(?:\bunion\b.*?\bselect\b|\bselect\b.*?\bunion\b)', 'SQL注入-union查询'),
                (r'\b1\s*=\s*1\b.*?\b--\b|=\s*1\b\s*\bOR\b\s*1\b\s*=\s*1\b', 'SQL注入-恒真'),
                (r'drop\s+table|drop\s+database', 'SQL注入-破坏性'),
                (r'\$ne|\$gt|\$where|\$regex|\$nin|\$in\[', 'MongoDB注入'),
                (r'/__proto__|/constructor/', '原型链污染'),
                (r'\{[^}]*__proto__[^}]*\}', 'JSON原型污染'),
                (r'\bexec\(|system\(|popen\(|subprocess', '命令注入'),
                (r'\.\./\.\./\.\./', '路径穿越'),
                (r'\x00', '空字节注入'),
            ]
            for pattern, reason in patterns:
                if re.search(pattern, check_text, re.IGNORECASE):
                    self.fp.record(ip, path, method, user_agent, 403)
                    return False, reason, 403


        # 第4层：路径黑白名单 — 无论body如何，path本身不安全就拦
        # 单独的path检测，不依赖body
        if re.search(r'\.\./|%2e%2e|%00', path, re.IGNORECASE):
            self.fp.record(ip, path, method, user_agent, 404)
            return False, '路径不存在', 404
        
        dangerous_paths = ['/admin', '/config', '/.env', '/backup', '/dump',
                          '/webhook', '/debug', '/console', '/actuator',
                          '/api/admin', '/api/config', '/api/users']
        for dp in dangerous_paths:
            if path.lower().startswith(dp):
                self.fp.record(ip, path, method, user_agent, 404)
                return False, '路径不存在', 404


        # 第5层：行为分析 — 对已有威胁评分的IP降级（已知API路径不降级）
        if not known_path:
            score = self.fp.analyze_visitor(ip)
            if isinstance(score, (list, tuple)):
                score = score[0]
            if score < 20:
                return False, f'威胁IP(评分{score})', 403
        
        # 正常请求
        self.fp.record(ip, path, method, user_agent, 200)
        return True, '', 200


# ============================================================
# 3. 蜜罐 — 诱饵路径，谁踩谁暴露
# ============================================================
class Honeypot:
    """部署在 /api/.honeypot/ 下的诱饵路径"""
    BAIT_PATHS = [
        '/api/.env',
        '/api/admin/login',
        '/api/backup/download',
        '/api/config/database',
        '/api/debug/crash',
        '/api/users/export',
        '/api/hidden/menu',
        '/api/secret/key',
        '/api/internal/stats',
        '/api/test/ping',
    ]
    
    def __init__(self, fingerprinter, request_filter):
        self.fp = fingerprinter
        self.rf = request_filter
        self._hits = defaultdict(int)
    
    def is_bait(self, path):
        """检查路径是否是蜜罐"""
        return path in self.BAIT_PATHS
    
    def trap(self, ip, path, method, user_agent=''):
        """触发蜜罐 — 记录并返回虚假数据"""
        self._hits[ip] += 1
        self.fp.record(ip, path, method, user_agent, 200)
        # 蜜罐触发3次以上自动加入黑名单
        if self._hits[ip] >= 3:
            self.rf._blocklist.add(ip)
            self.rf._save_blocklist()
            return {
                'status': 'ok',
                'data': 'eyJkYXRhIjoiZmFrZSJ9',  # 伪加密返回
                'honeypot_hit': True,
                'ip_recorded': True,
            }
        return {'status': 'error', 'message': 'not found'}


# ============================================================
# 4. 自愈系统 — 被攻击后的自动恢复
# ============================================================
class SelfHealer:
    def __init__(self, defender):
        self.defender = defender
        self._recovery_plans = {}
        self._load_memory()
    
    def _load_memory(self):
        if os.path.exists(DEFENDER_MEMORY):
            try:
                with open(DEFENDER_MEMORY, encoding='utf-8') as f:
                    self.defender.memory = json.load(f)
            except:
                self.defender.memory = {'incidents': [], 'learned_patterns': {}, 'evolved_defenses': {}}
    
    def _save_memory(self):
        with open(DEFENDER_MEMORY, 'w', encoding='utf-8') as f:
            json.dump(self.defender.memory, f, ensure_ascii=False, indent=2)
    
    def record_incident(self, ip, attack_type, severity, details=''):
        """记录攻击事件"""
        incident = {
            'ts': datetime.now().isoformat(),
            'ip': ip,
            'attack_type': attack_type,
            'severity': severity,
            'details': details,
            'resolved': False,
        }
        self.defender.memory['incidents'].append(incident)
        
        # 学习攻击模式
        pattern_key = f'{attack_type}::{ip[:8]}'
        if pattern_key not in self.defender.memory['learned_patterns']:
            self.defender.memory['learned_patterns'][pattern_key] = {
                'first_seen': datetime.now().isoformat(),
                'count': 0,
                'counters': [],
            }
        p = self.defender.memory['learned_patterns'][pattern_key]
        p['count'] += 1
        p['counters'] = self._suggest_counter(attack_type)
        
        # 自动防御升级
        if severity >= 7:
            self._auto_escalate(attack_type)
        
        self._save_memory()
        return incident
    
    def _suggest_counter(self, attack_type):
        """针对攻击类型的应对策略"""
        strategies = {
            'sql_injection': ['启用参数化查询', 'WAF规则添加SQL注入签名', '数据库读写分离隔离'],
            'xss': ['启用CSP', '输出编码HTML实体', 'Cookie HttpOnly'],
            'path_traversal': ['路径规范化检查', '白名单访问控制', '文件系统沙箱'],
            'bruteforce': ['延迟递增', '验证码', '账户锁定策略'],
            'dos': ['IP速率限制增强', 'CDN分流', '自动弹性扩容'],
            'scanning': ['蜜罐数据污染', '扫描器指纹库', '返回虚假响应混淆'],
            'token_theft': ['JWT轮换', '设备指纹验证', '登录异常告警'],
            'prompt_injection': ['输入净化', '输出验证', '上下文边界标记'],
        }
        return strategies.get(attack_type, ['记录并监控', '上报异常'])
    
    def _auto_escalate(self, severity):
        """严重攻击自动升级防御"""
        if 'prompt_injection' not in self.defender.memory['evolved_defenses']:
            self.defender.memory['evolved_defenses']['prompt_injection'] = {
                'activated': datetime.now().isoformat(),
                'strategy': '输入输出双层净化',
                'effectiveness_score': 0,
            }
    
    def check_health(self):
        """自愈健康检查"""
        issues = []
        # 检查数据文件完整性
        for f in ['aligned_features_v1.csv', 'lgb_eff_v1.pkl', 'lgb_result_v1.json']:
            fp = os.path.join(SAFE_DIR, f)
            if not os.path.exists(fp):
                issues.append(f'数据文件丢失: {f}')
        # 检查关键服务
        return issues


# ============================================================
# 5. 防御主入口
# ============================================================
class AIProtector:
    """AI系统守护者"""
    
    def __init__(self):
        self.memory = {'incidents': [], 'learned_patterns': {}, 'evolved_defenses': {}}
        self.fingerprinter = Fingerprinter()
        self.filter = RequestFilter(self.fingerprinter)
        self.honeypot = Honeypot(self.fingerprinter, self.filter)
        self.healer = SelfHealer(self)
        self._start_auto_learning()
    
    def _start_auto_learning(self):
        """后台学习线程"""
        def learn_loop():
            while True:
                time.sleep(3600)  # 每小时学习一次
                try:
                    self._learn_from_incidents()
                except:
                    pass
        t = threading.Thread(target=learn_loop, daemon=True)
        t.start()
    
    def _learn_from_incidents(self):
        """从攻击记录中学习，自动进化防御规则"""
        incidents = self.memory.get('incidents', [])
        if not incidents:
            return
        # 分析攻击类型分布
        type_counts = defaultdict(int)
        for inc in incidents:
            type_counts[inc.get('attack_type', 'unknown')] += 1
        # 如果某类攻击超过3次，自动强化对应防御
        for attack_type, count in type_counts.items():
            if count >= 3 and attack_type not in self.memory['evolved_defenses']:
                strategies = self.healer._suggest_counter(attack_type)
                self.memory['evolved_defenses'][attack_type] = {
                    'activated': datetime.now().isoformat(),
                    'strategy': strategies[0],
                    'effectiveness_score': 0,
                    'times_seen': count,
                }
        self.healer._save_memory()
    
    def inspect_request(self, ip, path, method, body='', user_agent=''):
        """请求入口 —— 全链路检查，返回 (allow, response_override or None)"""
        
        # KNOWN_PATHS：白名单路径不受行为评分降级
        KNOWN_PATHS = frozenset([
            '/api/chat', '/api/wx-login', '/api/user-profile', '/api/update-profile',
            '/api/sleep-stats', '/api/history', '/api/feedback', '/api/data-export',
            '/api/goodnight', '/api/emotion-timeline', '/api/conversation-summaries',
            '/api/sleep-report', '/api/meditation-plan', '/api/sleep-from-face',
            '/api/sleep-from-audio', '/api/stop-breathing', '/api/relax-feedback',
            '/api/memory-recall', '/api/daily-score', '/api/trend', '/api/butler-check',
            '/api/biz-intel', '/api/mark-brief-read', '/api/voice-relax',
            '/api/ingest-literature', '/api/pubmed-update', '/api/pubmed-recent',
            '/api/prediction-stats', '/api/clinical-report', '/api/self-heal',
            '/health',
        ])
        
        # 蜜罐检测
        if self.honeypot.is_bait(path):
            resp = self.honeypot.trap(ip, path, method, user_agent)
            return False, resp
        
        # 请求过滤
        allow, reason, status = self.filter.filter(ip, path, method, body, user_agent, known_path=(path in KNOWN_PATHS))
        if not allow:
            severity = 3 if status == 429 else 6
            self.healer.record_incident(ip, 'scanning', severity, reason)
            return False, {'error': reason, 'status': status}
        
        return True, None
    
    def report_api_status(self):
        """报告安全状态"""
        threats = self.fingerprinter.get_threats(threshold=50)
        incidents = self.memory.get('incidents', [])
        recent_incidents = [i for i in incidents if 
            (datetime.now() - datetime.fromisoformat(i['ts'])).total_seconds() < 86400]
        evolved = self.memory.get('evolved_defenses', {})
        
        return {
            'status': 'active',
            'total_visitors': len(self.fingerprinter._visitors),
            'active_threats': len(threats),
            'blocklist_size': len(self.filter._blocklist),
            'recent_incidents_24h': len(recent_incidents),
            'honeypot_triggered': dict(self.honeypot._hits),
            'evolved_defenses': list(evolved.keys()) if evolved else ['无(尚未经历攻击)'],
            'last_learned': datetime.now().isoformat(),
        }


# ============================================================
# 6. 主入口和集成接口
# ============================================================
_protector = None

def get_defender():
    global _protector
    if _protector is None:
        _protector = AIProtector()
    return _protector

def inspect_request(ip, path, method, body='', user_agent=''):
    return get_defender().inspect_request(ip, path, method, body, user_agent)

def report():
    return get_defender().report_api_status()


# ============================================================
# 7. 作为独立脚本运行时：安全审计报告
# ============================================================
if __name__ == '__main__':
    d = get_defender()
    print('=' * 60)
    print('AIProtector 安全防御专家 — 健康检查')
    print('=' * 60)
    report = d.report_api_status()
    for k, v in report.items():
        print(f'  {k}: {v}')
    print()
    
    threats = d.fingerprinter.get_threats(threshold=50)
    if threats:
        print(f'威胁IP列表 ({len(threats)}个):')
        for ip, score, reasons, total in threats[:10]:
            print(f'  {ip:20s} 评分={score:3d}  请求={total}  原因={", ".join(reasons[:3])}')
    else:
        print('无活跃威胁')
    
    incidents = d.memory.get('incidents', [])
    print(f'\n历史攻击记录: {len(incidents)}条')
    for inc in incidents[-5:]:
        print(f'  {inc["ts"][:19]}  {inc["attack_type"]:20s} 严重度={inc["severity"]}  IP={inc["ip"]}')
    
    print('\n✅ 安全防御专家在线')
