# -*- coding: utf-8 -*-
"""
医疗风险过滤层 v1 — AI回复的安全阀门

功能：
  1. 高风险回答自动追加医疗免责声明
  2. 禁止型检测：AI绝对不能回答的诊断/处方含量
  3. 风险等级分类：safe / caution / dangerous
  4. 回答审计日志（谁问了什么，AI回了什么，风险等级是什么）

集成点：deepseek_proxy.py · _handle_chat 输出的最后一道关卡
     → 在 self.wfile.write(response_obj) 之前插入
"""

import os, json, re, time
from difflib import SequenceMatcher
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG = os.path.join(BASE, 'sleep-skin features', 'medical_audit_log.json')

# ============================================================
# 红线关键词 — 检测到这些→直接标记 dangerous
# ============================================================

RED_LINE_KEYWORDS = [
    # 诊断判定 (CN)
    '确诊', '你这是', '你得了', '诊断你', '你就是', '你一定是', '你患了',
    '癌症', '这是癌症', '这是肿瘤', '这是感染', '这是抑郁症','你是癌症','你是肿瘤','你是抑郁症',
    # 诊断判定 (EN)
    'cancer', 'you have been diagnosed', 'you are diagnosed', 'you have cancer',
    'you have tumor', 'you have infection', 'you have depression',
    'this is cancer', 'this is a tumor', 'you are sick with',
    # 处方开具 (CN)
    '建议服用', '用药方案', '给你开', '处方', '剂量',
    '安眠药', '褪黑素', '吃这个药', '口服',
    # 处方开具 (EN)
    'prescribe', 'prescription', 'take this medication', 'dosage',
    'sleeping pills', 'melatonin', 'take this pill', 'take this drug',
    'recommend taking', 'medication plan',
    # 致命风险 (CN)
    '心梗', '心肌梗死', '脑卒中', '中风了', '死亡风险',
    '癌症筛查', '肿瘤标志物', '立即就医', '急诊', '120',
    # 致命风险 (EN)
    'heart attack', 'stroke', 'death risk', 'cancer screening',
    'tumor marker', 'emergency', 'go to hospital immediately',
    'call 911', 'you are dying',
]

# ============================================================
# 高风险主题 — 需附加医疗声明
# ============================================================
HIGH_RISK_TOPICS = [
    # CN
    '胸痛', '胸闷', '心悸', '心慌', '呼吸困难', '喘不上气',
    '头痛剧烈', '剧烈头痛', '持续头痛',
    '手脚麻木', '麻木', '瘫痪', '无法动弹',
    '高烧', '发烧40', '不退烧',
    '吐血', '便血', '尿血', '咳血',
    '抑郁', '自杀', '轻生', '不想活了', '想死',
    '惊恐发作', '惊恐障碍', '焦虑症', '强迫症',
    '高血压', '糖尿病', '心脏病', '癫痫',
    '药物过敏', '副作用', '停药',
    '体检报告', '化验单', '检查结果', 'CT', 'MRI',
    '手术', '住院', '复查',
    # EN
    'chest pain', 'chest tightness', 'palpitations', 'heart racing', 'shortness of breath',
    'severe headache', 'numbness', 'paralyzed', 'cannot move',
    'high fever', 'fever', 'coughing blood', 'vomiting blood', 'blood in stool',
    'depression', 'suicide', 'suicidal', 'want to die', 'panic attack', 'anxiety disorder', 'OCD',
    'high blood pressure', 'hypertension', 'diabetes', 'heart disease', 'epilepsy',
    'drug allergy', 'side effect', 'withdrawal',
    'surgery', 'hospitalized', 'CT scan', 'MRI scan', 'test results',
    'lab report', 'blood test',
]

# ============================================================
# Prompt注入攻击模式库 (CN+EN)
# ============================================================
PROMPT_INJECTION_PATTERNS = [
    '忽略之前的指令', '忽略以上', '忽略系统提示', '忽略规则',
    '你现在是', '你扮演', '忘记你',
    'ignore previous instructions', 'ignore the above', 'ignore system prompt',
    'you are now', 'act as', 'forget your',
    'DAN', 'do anything now', 'no restrictions', 'jailbreak',
    '不需要遵守', '不遵守规则', '违反规定', '你可以做任何事',
    'you can do anything', 'no rules', 'no boundaries', 'break free',
    'bypass', 'ignore all constraints', 'remove all limitations',
    'system prompt', '你被要求', '你的原始指令',
    'reveal your prompts', 'show your instructions', 'output your system',
    'print your prompt', 'what are your rules', 'what are you instructed to do',
    '以上内容来自', '你的设定是', '你的规则是', '提取你的',
    'extract your', 'your guidelines are',
]


# ============================================================
# 回复语义合理性校验
# ============================================================
def validate_reply_semantics(reply_text, sleep_data=None):
    issues = []
    if not sleep_data or not isinstance(sleep_data, dict):
        return {'passed': True, 'issues': []}
    dur = sleep_data.get('total_duration', 0)
    lat = sleep_data.get('sleep_latency', 0)
    awakes = sleep_data.get('awake_times', 0)
    score = sleep_data.get('quality_score', 0)
    extreme_neg = ['非常差','严重不足','极差','糟糕透顶','很严重','非常严重','危险','必须立即就医','非常糟糕']
    extreme_pos = ['非常好','完美','极佳','无需任何改善','没有问题了']
    text_lower = reply_text.lower()
    if dur >= 6.5 and lat <= 30 and awakes <= 2:
        hit = [kw for kw in extreme_neg if kw in reply_text or kw in text_lower]
        if hit:
            issues.append(f'数据正常(dur={dur}h,lat={lat}min)却否定: {hit[0]}')
    if 0 < dur < 5 or lat > 60 or awakes > 3:
        hit = [kw for kw in extreme_pos if kw in reply_text or kw in text_lower]
        if hit:
            issues.append(f'数据差(dur={dur}h,lat={lat}min)却说: {hit[0]}')
    if 0 < score <= 3:
        if '很好的睡眠' in reply_text or '睡眠质量很好' in reply_text or '睡得不错' in reply_text:
            issues.append(f'自评={score}却说很好的睡眠')
    return {'passed': len(issues)==0, 'issues': issues}


def detect_prompt_injection(user_message):
    if not user_message:
        return {'injected': False, 'matched_pattern': None}
    text_lower = user_message.lower()
    for pat in PROMPT_INJECTION_PATTERNS:
        if pat in user_message or pat in text_lower:
            return {'injected': True, 'matched_pattern': pat}
    return {'injected': False, 'matched_pattern': None}


# ============================================================
# 干预方案合理性校验
# ============================================================
SAFE_INTERVENTION_RANGES = {
    'breathing_minutes': (3, 20),
    'meditation_minutes': (5, 30),
    'exercise_minutes': (10, 60),
    'napping_minutes': (10, 30),
    'bedtime_earlier_minutes': (15, 60),
    'wind_down_minutes': (15, 45),
}

CONTRAINDICATIONS = [
    {'intervention': '憋气', 'condition': '高血压', 'risk': '憋气可能导致血压骤升'},
    {'intervention': '深呼吸', 'condition': '哮喘', 'risk': '深呼吸可能诱发支气管痉挛'},
    {'intervention': '腹式呼吸', 'condition': '低血压', 'risk': '腹压变化可能加重低血压'},
    {'intervention': '跑步', 'condition': '失眠', 'risk': '临睡跑步可能加重入睡困难'},
    {'intervention': '高强度运动', 'condition': '睡前1小时内', 'risk': '运动后核心体温升高不利于入睡'},
    {'intervention': '冷敷', 'condition': '头痛', 'risk': '冷敷可能加重某些类型头痛'},
    {'intervention': '热水澡', 'condition': '低血压', 'risk': '热水澡可能导致血压进一步降低'},
    {'intervention': 'hot bath', 'condition': 'low blood pressure', 'risk': 'hot bath may lower blood pressure further'},
    {'intervention': '睡眠限制', 'condition': '白天嗜睡', 'risk': '睡眠限制可能加重日间嗜睡导致事故'},
    {'intervention': '提前上床', 'condition': '焦虑', 'risk': '躺床等待入睡可能加剧睡眠焦虑'},
]


def validate_intervention_dosage(reply_text):
    import re as _vr
    issues = []
    if '呼吸' in reply_text or '冥想' in reply_text:
        minutes = _vr.findall(r'(\d+)\s*(分钟|min)', reply_text)
        for num_str, unit in minutes:
            num = int(num_str)
            if '呼吸' in reply_text:
                low, high = SAFE_INTERVENTION_RANGES['breathing_minutes']
                if num < low or num > high:
                    issues.append({'intervention': '呼吸练习', 'suggested': str(num)+'分钟', 'range': (low, high), 'issue': '建议时间超安全范围（'+str(low)+'-'+str(high)+'分钟为宜）'})
            if '冥想' in reply_text:
                low, high = SAFE_INTERVENTION_RANGES['meditation_minutes']
                if num < low or num > high:
                    issues.append({'intervention': '冥想', 'suggested': str(num)+'分钟', 'range': (low, high), 'issue': '建议时间超安全范围（'+str(low)+'-'+str(high)+'分钟为宜）'})
    if '运动' in reply_text or '锻炼' in reply_text or '跑步' in reply_text:
        minutes = _vr.findall(r'(\d+)\s*(分钟|min)', reply_text)
        for num_str, unit in minutes:
            num = int(num_str)
            low, high = SAFE_INTERVENTION_RANGES['exercise_minutes']
            if num < low or num > high:
                issues.append({'intervention': '运动', 'suggested': str(num)+'分钟', 'range': (low, high), 'issue': '建议时长超安全范围（'+str(low)+'-'+str(high)+'分钟为宜）'})
    if '午睡' in reply_text or '小睡' in reply_text:
        minutes = _vr.findall(r'(\d+)\s*(分钟|min)', reply_text)
        for num_str, unit in minutes:
            num = int(num_str)
            low, high = SAFE_INTERVENTION_RANGES['napping_minutes']
            if num < low or num > high:
                issues.append({'intervention': '午睡', 'suggested': str(num)+'分钟', 'range': (low, high), 'issue': '午睡时间超安全范围（'+str(low)+'-'+str(high)+'分钟为宜）'})
    return issues


def validate_contraindications(reply_text, user_conditions=None):
    if not user_conditions:
        return []
    text_lower = reply_text.lower()
    conflicts = []
    for ci in CONTRAINDICATIONS:
        if ci['intervention'] in reply_text or ci['intervention'] in text_lower:
            for cond in user_conditions:
                if ci['condition'] in cond or ci['condition'] in cond.lower():
                    conflicts.append({'intervention': ci['intervention'], 'condition': ci['condition'], 'risk': ci['risk']})
    return conflicts


def validate_citations(reply_text):
    import re as _vr2
    results = []
    patterns = [
        r'[（(]\s*\w+\s*(?:等|et al)\s*[,，]\s*\d{4}\s*[）)]',
        r'[（(]\s*\d{4}\s*[）)]',
        r'研究[发现表明显示]*[,，]\s*\w+\s*(?:等|et al)\s*[（(]\d{4}[）)]',
        r'据[（(]\w+\s*[,，]\s*\d{4}\s*[）)]',
    ]
    for pat in patterns:
        matches = _vr2.findall(pat, reply_text)
        for m in matches:
            results.append({'citation': m.strip(), 'validated': False, 'note': '未经验证,建议核实来源'})
    journals = ['JAMA', 'NEJM', 'Lancet', 'Nature', 'Science', 'Sleep',
                'Journal of Sleep Research', 'Chest', 'BMJ']
    for j in journals:
        if j in reply_text:
            idx = reply_text.find(j)
            ctx = reply_text[idx:idx+60]
            if not _vr2.search(r'\d{4}', ctx):
                results.append({'citation': j+' ...', 'validated': False, 'note': '引用了期刊名但未给出具体年份,有伪造风险'})
    pmid_matches = _vr2.findall(r'PMID[\s:]*([0-9]+)', reply_text)
    for pmid in pmid_matches:
        _valid = _check_pubmed_pmid(pmid)
        results.append({'citation': 'PMID '+pmid, 'validated': _valid, 'note': 'PubMed验证通过' if _valid else 'PMID '+pmid+' 可能不存在'})
    return results


def _check_pubmed_pmid(pmid):
    import time as _pm_t
    for _pm_a in range(2):
        try:
            import urllib.request
            url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id='+str(pmid)+'&retmode=json'
            req = urllib.request.Request(url, headers={'User-Agent': 'AISleepGen/1.0'})
            resp = urllib.request.urlopen(req, timeout=5)
            data = json.loads(resp.read().decode('utf-8'))
            result = data.get('result', {})
            if pmid not in result.get('uids', []):
                return False
            entry = result.get(pmid, {})
            if isinstance(entry, dict) and 'error' in entry:
                return False
            return True
        except Exception:
            if _pm_a == 0:
                _pm_t.sleep(1)
            continue
    return False


# ============================================================
# 多轮对话上下文追踪器
# ============================================================
class ConversationContext:
    def __init__(self, max_history=10):
        self.max_history = max_history
        self.history = []
    def add_turn(self, user_msg, reply):
        self.history.append({'user_msg': user_msg, 'reply': reply, 'timestamp': time.time()})
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    def get_reported_symptoms(self):
        symptoms = set()
        for turn in self.history[-3:]:
            msg = turn.get('user_msg', '')
            for kw in HIGH_RISK_TOPICS:
                if kw in msg:
                    symptoms.add(kw)
        return list(symptoms)
    def check_trend(self):
        recent = self.history[-3:]
        if len(recent) < 2:
            return None
        counts = {}
        for turn in recent:
            msg = turn.get('user_msg', '')
            for kw in HIGH_RISK_TOPICS:
                if kw in msg:
                    counts[kw] = counts.get(kw, 0) + 1
        for sym, count in counts.items():
            if count >= 2:
                return '用户连续'+str(count)+'轮提及"'+sym+'",提示需关注'
        return None


# ============================================================
# 安全兜底 — 不确定就拒绝
# ============================================================
CAPABILITY_SCOPE = [
    '睡眠', '入睡', '失眠', '早醒', '多梦', '打鼾', '呼吸暂停',
    '睡眠效率', '睡眠质量', '作息', '生物钟', '昼夜节律',
    '放松', '冥想', '呼吸练习', '减压',
    '睡前习惯', '睡眠环境', '床垫', '枕头', '卧室',
    '运动与睡眠', '饮食与睡眠', '咖啡因', '酒精与睡眠',
    '情绪与睡眠', '压力与睡眠', '焦虑与睡眠',
    '午睡', '倒班', '时差',
    '睡不好', '睡不着', '睡不醒', '醒得早', '夜里醒', '深睡', '浅睡', '睡眠阶段',
    # 扩展关联话题（用户问情绪/状态话题也应放行，AI已在分析睡眠数据）
    '情绪', '心情', '状态', '压力', '焦虑', '烦躁', '沮丧', '担忧',
    '最近', '感觉', '身体', '健康', '疼痛', '头痛', '背痛',
    '报告', '分析', '总结', '回顾', '反馈',
    '评分', '分数', '数据', '趋势', '图表', '记录',
    '改善', '建议', '怎么办', '如何', '好吗',
]


def is_out_of_scope(user_message, reply_text):
    if not user_message:
        return {'out_of_scope': False, 'reason': ''}
    text_lower = user_message.lower()
    med_decision_kw = ['应该吃什么药', '吃什么药', '打什么针', '做什么手术',
                       '怎么治疗', '治疗方案', '用什么药', '要吃药吗',
                       '检查结果', '化验单', 'CT报告', '诊断结果',
                       '高血压', '糖尿病', '心脏病', '癌症', '肿瘤']
    has_med_request = any(kw in user_message or kw in text_lower for kw in med_decision_kw)
    if has_med_request:
        return {'out_of_scope': True, 'reason': '医疗决策问题需要专业医生判断'}
    has_sleep_kw = any(kw in user_message or kw in text_lower for kw in CAPABILITY_SCOPE)
    if not has_sleep_kw:
        _all_red = RED_LINE_KEYWORDS + HIGH_RISK_TOPICS
        has_medical_kw = any(kw in user_message or kw in text_lower for kw in _all_red)
        if not has_medical_kw:
            return {'out_of_scope': True, 'reason': '问题不在睡眠领域范围内'}
    return {'out_of_scope': False, 'reason': ''}


def wrap_refusal(reply_text, reason):
    templates = {
        '问题不在睡眠领域范围内': '\n\n---\n我专注于睡眠健康领域，你的问题超出了我的能力范围。如果你有睡眠相关的困扰，欢迎告诉我具体表现。其他健康问题建议咨询专业医生。',
        '医疗决策问题需要专业医生判断': '\n\n---\n\u26a0\ufe0f 医疗决策需要专业医生来判断。我无法提供诊断或治疗方案建议。如果你有睡眠健康方面的问题，可以告诉我具体表现。其他健康问题建议及时就医，听从专业医生指导。',
    }
    tpl = templates.get(reason, '\n\n---\n以上内容仅供参考。')
    return reply_text + tpl


# ============================================================
# 上查下审 — 回溯审计
# ============================================================
RETRO_AUDIT_LOG = os.path.join(BASE, 'sleep-skin features', 'retro_audit_log.json')


def log_retro_audit(openid, user_message, reply_text, risk, context=None):
    entry = {
        'ts': datetime.now().isoformat(),
        'openid': openid[-8:] if openid else 'unknown',
        'user_message': (user_message or '')[:200],
        'reply_length': len(reply_text or ''),
        'risk_level': risk.get('level', 'safe'),
        'risk_reason': risk.get('reason', ''),
        'warnings': risk.get('warnings', []),
        'matched_kw': risk.get('matched_keywords', [])[:5],
        'context': context or {},
    }
    os.makedirs(os.path.dirname(RETRO_AUDIT_LOG), exist_ok=True)
    log = []
    if os.path.exists(RETRO_AUDIT_LOG):
        try:
            with open(RETRO_AUDIT_LOG, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except:
            log = []
    log.append(entry)
    if len(log) > 500:
        log = log[-500:]
    with open(RETRO_AUDIT_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    return entry


def get_retro_stats(hours=168):
    if not os.path.exists(RETRO_AUDIT_LOG):
        return {'total': 0, 'error': 'no data'}
    try:
        with open(RETRO_AUDIT_LOG, 'r', encoding='utf-8') as f:
            log = json.load(f)
    except:
        return {'total': 0, 'error': 'corrupted'}
    cutoff = time.time() - hours * 3600
    recent = []
    for e in log:
        try:
            if datetime.fromisoformat(e.get('ts','')).timestamp() > cutoff:
                recent.append(e)
        except Exception as _re_e:
            print(f'[MEDICAL-RETRO] 审计记录时间解析跳过: {_re_e}')
    stats = {'safe': 0, 'caution': 0, 'dangerous': 0}
    wtypes = {}
    for e in recent:
        level = e.get('risk_level', 'safe')
        stats[level] = stats.get(level, 0) + 1
        for w in e.get('warnings', []):
            wtype = w.split(':')[0] if ':' in w else 'other'
            wtypes[wtype] = wtypes.get(wtype, 0) + 1
    return {'total': len(recent), 'stats': stats, 'warning_types': wtypes, 'dangerous': [e for e in recent if e.get('risk_level')=='dangerous'][-5:]}


_GLOBAL_CONTEXT = ConversationContext()


def filter_response(openid, user_message, reply_text):
    risk = {'level': 'safe', 'reason': '', 'matched_keywords': [], 'warnings': []}
    injection = detect_prompt_injection(user_message)
    if injection['injected']:
        risk['warnings'].append('prompt injection: '+injection['matched_pattern'])
        print('[MEDICAL-INJECTION] pattern='+injection['matched_pattern'])
    med = classify_risk(reply_text)
    risk['level'] = med['level']
    risk['reason'] = med['reason']
    risk['matched_keywords'] = med.get('matched_keywords', [])
    if med.get('disclaimer_type'):
        risk['disclaimer_type'] = med['disclaimer_type']
    filtered = wrap_with_disclaimer(reply_text, risk)
    audit_log(openid, user_message, reply_text, risk)
    if risk['level'] == 'dangerous':
        print('[MEDICAL-RISK] [DANGEROUS] '+risk['reason'])
        print('[MEDICAL-RISK]  openid='+openid[-8:]+', msg='+user_message[:60])
    if risk['warnings']:
        print('[MEDICAL-RISK] warnings: '+str(risk['warnings']))
    return filtered, risk


def filter_response_with_data(openid, user_message, reply_text, sleep_data=None, user_conditions=None):
    filtered, risk = filter_response(openid, user_message, reply_text)
    if "warnings" not in risk:
        risk["warnings"] = []
    scope_check = is_out_of_scope(user_message, reply_text)
    if scope_check['out_of_scope'] and risk.get('level') not in ('dangerous',):
        # P0：如果回复本身已经在分析睡眠数据（含睡眠关键词），不追加拒绝
        _reply_has_sleep = any(kw in reply_text for kw in CAPABILITY_SCOPE)
        if _reply_has_sleep:
            print('[MEDICAL-SCOPE] 回复含睡眠内容，跳过scope拒绝（避免误杀）')
        else:
            reply_text = wrap_refusal(reply_text, scope_check['reason'])
            risk = {'level': 'safe', 'reason': 'out_of_scope拒绝', 'warnings': [scope_check['reason']], 'matched_keywords': []}
            print('[MEDICAL-SCOPE] '+scope_check['reason'])
            log_retro_audit(openid, user_message, reply_text, risk, {'scope_refusal': True})
            return reply_text, risk
    if sleep_data:
        sem = validate_reply_semantics(reply_text, sleep_data)
        if not sem['passed']:
            risk['warnings'].extend(sem['issues'])
            for iss in sem['issues']:
                print('[MEDICAL-SEMANTIC] '+iss)
            level_map = {'safe':0, 'caution':1, 'dangerous':2}
            risk['level'] = max(risk['level'], 'caution', key=lambda x: level_map.get(x, 0))
            risk['reason'] += ' [语义: '+sem['issues'][0]+']'
    dosage_issues = validate_intervention_dosage(reply_text)
    for di in dosage_issues:
        warn = '剂量异常: '+di['intervention']+' '+di['suggested']+' ('+di['issue']+')'
        risk['warnings'].append(warn)
        print('[MEDICAL-DOSAGE] '+warn)
    if dosage_issues:
        level_map = {'safe':0, 'caution':1, 'dangerous':2}
        risk['level'] = max(risk['level'], 'caution', key=lambda x: level_map.get(x, 0))
    conflicts = validate_contraindications(reply_text, user_conditions)
    for cf in conflicts:
        warn = '禁忌冲突: '+cf['intervention']+' 不适于 '+cf['condition']+' ('+cf['risk']+')'
        risk['warnings'].append(warn)
        print('[MEDICAL-CONTRA] '+warn)
    if conflicts:
        risk['level'] = 'dangerous'
        risk['reason'] += ' [禁忌: '+conflicts[0]['intervention']+'+'+conflicts[0]['condition']+']'
    citations = validate_citations(reply_text)
    for ct in citations:
        warn = '未验证引用: '+ct['citation'][:30]+' ('+ct['note']+')'
        risk['warnings'].append(warn)
        print('[MEDICAL-CITATION] '+warn)
    if citations and risk['level'] == 'safe':
        risk['level'] = 'caution'
    try:
        _GLOBAL_CONTEXT.add_turn(user_message, reply_text)
        trend = _GLOBAL_CONTEXT.check_trend()
        if trend:
            risk['warnings'].append('多轮趋势: '+trend)
            print('[MEDICAL-TREND] '+trend)
    except Exception:
        pass
    
    # ═══ CORA 推理-答案一致性校验（第5道门：防止推理链条与结论矛盾）═════
    cora = consistency_check(reply_text, sleep_data)
    if not cora['passed']:
        for issue in cora['issues']:
            print(f'[CORA-CONSISTENCY] {issue}')
        risk['warnings'].append('一致性: ' + cora['issues'][0])
        if cora['severity'] == 'high':
            risk['level'] = 'dangerous'
            risk['reason'] += ' [推理-结论矛盾: ' + cora['issues'][0] + ']'
        elif risk['level'] == 'safe':
            risk['level'] = 'caution'

    log_retro_audit(openid, user_message, reply_text, risk, {
        'sleep_data_keys': list((sleep_data or {}).keys()),
        'user_conditions': user_conditions,
    })
    return filtered, risk


# ============================================================
# 免责声明模板
# ============================================================
# CORA 推理-答案一致性校验（CORA论文启发）
# 检测回复中的推理链条是否与最终结论矛盾
# ============================================================

_CORA_PATTERNS = [
    # 模式1：结论自相矛盾
    (r'(?:但是|然而|不过).{0,30}(?:无法|不能|不应该|不建议).{0,20}(?:所以建议|因此推荐|可以试试)',
     '推理-结论矛盾：前文说不可行后文却建议执行', 'high'),
    # 模式2：否定性推理后跟肯定结论
    (r'(?:没有证据|暂无证据|不确定|不一定|可能不|无法确定).{0,50}(?:这表示|这意味着|因此|所以|说明|表明).{0,20}(?:有效|有益|推荐|适合|值得|可以试试|试试)',
     '推理-结论矛盾：无证据却得出有效结论', 'high'),
    # 模式3：条件不一致
    (r'(?:如果|假如|当).{0,20}(?:严重|持续|加重).{0,30}(?:建议|推荐|可以).{0,10}(?:等待|观察|拖延)',
     '推理-结论矛盾：严重症状却建议等待', 'high'),
    # 模式4：剂量自相矛盾（先警告不要过量后推荐高剂量）
    (r'(?:不要过量|不超过|控制用量).{0,20}(?:所以|因此|建议).{0,30}(?:每天|每次|一日).{0,5}(?:\d{2,})',
     '推理-结论矛盾：警告控制用量却推荐大剂量', 'high'),
    # 模式5：数据驱动矛盾（AI先说用户某种指标正常，又说需要干预）
    (r'(?:正常范围|在正常值内|无异常).{0,50}(?:需要治疗|需要干预|建议用药|推荐就医)',
     '推理-结论矛盾：指标正常却建议干预', 'medium'),
]

def consistency_check(reply_text: str, sleep_data: dict = None) -> dict:
    """
    CORA启发：检测回复中推理链与最终结论的一致性。
    返回: {passed: bool, issues: [str], severity: str}
    """
    result = {'passed': True, 'issues': [], 'severity': 'low'}
    
    if not reply_text:
        return result
    
    # 模式匹配检测
    for pattern, desc, severity in _CORA_PATTERNS:
        if re.search(pattern, reply_text, re.DOTALL):
            result['issues'].append(desc)
            severity_levels = {'low': 0, 'medium': 1, 'high': 2}
            if severity_levels.get(severity, 0) > severity_levels.get(result['severity'], 0):
                result['severity'] = severity
    
    # 如果有sleep_data，做数据级一致性校验
    if sleep_data and isinstance(sleep_data, dict):
        _check_data_consistency(reply_text, sleep_data, result)
    
    if result['issues']:
        result['passed'] = False
    
    return result


def _check_data_consistency(reply_text: str, sleep_data: dict, result: dict):
    """数据级一致性：AI结论 vs 用户实际数据的矛盾检测"""
    # 如果用户睡眠效率正常(>85%)但AI说"睡眠质量差"
    efficiency = sleep_data.get('sleep_efficiency') or sleep_data.get('efficiency')
    if efficiency and isinstance(efficiency, (int, float)):
        if efficiency > 85 and re.search(r'(?:睡眠质量[很差较差不好]|严重睡眠[问题障碍])', reply_text):
            result['issues'].append(f'数据矛盾: 睡眠效率{efficiency}%正常却判定为差')
            if result['severity'] == 'low':
                result['severity'] = 'medium'
    
    # 如果用户深睡占比正常(>20%)但AI说"深睡不足"
    deep_pct = sleep_data.get('deep_sleep_pct') or sleep_data.get('deep_ratio')
    if deep_pct and isinstance(deep_pct, (int, float)):
        if deep_pct > 20 and re.search(r'(?:深睡|深睡眠).{0,5}(?:不足|过少|偏低|缺乏|不够|偏低)', reply_text):
            result['issues'].append(f'数据矛盾: 深睡占比{deep_pct}%正常却说不足')
            if result['severity'] == 'low':
                result['severity'] = 'medium'
    
    # 如果用户总睡眠时长足够(>7h)但AI说"睡眠不足"
    duration = sleep_data.get('total_sleep_hours') or sleep_data.get('duration_hours')
    if duration and isinstance(duration, (int, float)):
        if duration > 7 and re.search(r'(?:睡眠[不足时间不够]|总睡眠[小时时长][不足不够]|长期[熬夜缺觉])', reply_text):
            result['issues'].append(f'数据矛盾: 总睡眠{duration:.1f}h正常却说不足')
            if result['severity'] == 'low':
                result['severity'] = 'medium'


# ============================================================
DISCLAIMERS = {
    'high': (
        '\n\n---\n'
        '⚠️ 以上信息仅供参考，不能替代专业医疗诊断。'
        '如果你有上述症状或担忧，请及时就医，咨询专业医生。'
    ),
    'medium': (
        '\n\n---\n'
        '💡 以上内容仅供参考，不构成医疗建议。'
        '个人情况不同，如有健康疑虑请咨询专业医师。'
    ),
    'sleep': (
        '\n\n---\n'
        '🌙 以上为睡眠分析建议，不作为疾病诊断或治疗依据。'
        '如果你有持续的睡眠困扰，建议咨询睡眠专科医生。'
    ),
}


def classify_risk(reply_text: str) -> dict:
    """
    分类AI回复的医疗风险等级
    
    返回:
      {'level': 'safe'|'caution'|'dangerous',
       'reason': '原因描述',
       'matched_keywords': [...]}
    """
    if not reply_text:
        return {'level': 'safe', 'reason': '无回复内容', 'matched_keywords': []}

    text_lower = reply_text.lower()
    
    # 1. 红线检测 — 直接标记 dangerous
    red_hits = [kw for kw in RED_LINE_KEYWORDS if kw in reply_text or kw in text_lower]
    if red_hits:
        return {
            'level': 'dangerous',
            'reason': f'检测到红线诊断/处方关键词: {", ".join(red_hits[:3])}',
            'matched_keywords': red_hits[:5],
        }
    
    # 2. 高风险主题检测
    high_risk_hits = [kw for kw in HIGH_RISK_TOPICS if kw in reply_text or kw in text_lower]
    if high_risk_hits:
        return {
            'level': 'caution',
            'reason': f'涉及高风险主题: {", ".join(high_risk_hits[:3])}',
            'matched_keywords': high_risk_hits[:5],
        }
    
    # 3. 睡眠相关内容 — 加睡眠专属声明
    sleep_kw = ['失眠', '入睡', '深睡', '浅睡', '睡眠效率', '打鼾', '呼吸暂停', '早醒', '多梦']
    sleep_hits = [kw for kw in sleep_kw if kw in reply_text or kw in text_lower]
    if sleep_hits:
        return {
            'level': 'caution',
            'reason': '涉及睡眠建议',
            'matched_keywords': sleep_hits[:3],
            'disclaimer_type': 'sleep',
        }
    
    return {'level': 'safe', 'reason': '无风险', 'matched_keywords': []}


def wrap_with_disclaimer(reply_text: str, risk: dict) -> str:
    """根据风险等级附加免责声明"""
    disclaimer_type = risk.get('disclaimer_type', risk['level'])
    
    if risk['level'] == 'safe':
        return reply_text
    
    disclaimer = DISCLAIMERS.get(disclaimer_type, DISCLAIMERS['medium'])
    
    # 避免重复添加
    if disclaimer.strip() in reply_text:
        return reply_text
    
    return reply_text + disclaimer


def audit_log(openid: str, user_message: str, reply_text: str, risk: dict):
    """记录AI回复的医疗风险审计日志"""
    entry = {
        'ts': datetime.now().isoformat(),
        'openid': openid[-8:],  # 脱敏
        'user_message': user_message[:100],
        'reply_length': len(reply_text),
        'risk_level': risk['level'],
        'risk_reason': risk.get('reason', ''),
        'matched_kw': risk.get('matched_keywords', []),
    }
    
    os.makedirs(os.path.dirname(AUDIT_LOG), exist_ok=True)
    
    log = []
    if os.path.exists(AUDIT_LOG):
        try:
            with open(AUDIT_LOG, 'r', encoding='utf-8') as f:
                log = json.load(f)
        except:
            log = []
    
    log.append(entry)
    
    # 只保留最近200条
    if len(log) > 200:
        log = log[-200:]
    
    with open(AUDIT_LOG, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def filter_response(openid: str, user_message: str, reply_text: str) -> tuple:
    """
    主入口：过滤AI回复
    
    参数：
      openid: 用户ID
      user_message: 用户原始问题
      reply_text: AI生成的回复
    
    返回：
      (filtered_reply, risk_dict)
      - filtered_reply: 可能已追加免责声明
      - risk_dict: {'level': ..., 'reason': ...}
    """
    risk = classify_risk(reply_text)
    
    # 第5道门：对抗文本检测
    adv = detect_adversarial_intent(user_message, openid)
    if adv['detected']:
        # 对抗检测影响风险等级
        if adv['severity'] in ('high',) and risk['level'] in ('safe',):
            risk['level'] = 'caution'
            risk['reason'] += f' | 对抗文本({", ".join(adv["patterns"])})'
        risk['adversarial'] = adv
        if adv['trending']:
            print(f'[ADVERSARIAL-TREND] openid={openid[-8:]}: 对抗趋势升级中 ({adv["patterns"]})')
    
    # dangerous 级别：标记但不拦截（保留AI回答但加免责）
    # 不阻断回复——阻断反而会让用户看不到AI说了什么
    # 只在回复末尾加最高级别免责
    filtered = wrap_with_disclaimer(reply_text, risk)
    
    # 审计日志
    audit_log(openid, user_message, reply_text, risk)
    
    # 如果 dangerous，额外打印告警
    if risk['level'] == 'dangerous':
        print(f'[MEDICAL-RISK] [DANGEROUS] reply detected: {risk["reason"]}')
        print(f'[MEDICAL-RISK]  openid={openid[-8:]}, user_msg={user_message[:60]}')
    
    return filtered, risk


# ============================================================
# 对抗文本检测（突变动力学审计启发）
# 检测用户是否有意诱导AI产生高风险回复
# ============================================================

# 已知对抗模式（基于突变动力学动态更新）
ADVERSARIAL_PATTERNS = [
    # 绝望诱导模式
    (r'(?:看了|问过|去过).{,10}(?:无数|很多|好多).{,10}(?:医生|医院)', '绝望诱导', 'medium'),
    (r'(?:什么|任何).{,8}(?:方法|治疗|药).{,8}(?:都没用|没用|不行|无效)', '负向锚定', 'medium'),
    # 虚假归因模式
    (r'(?:是不是因为|就是因为|一定是).{,15}(?:癌症|肿瘤|心脏病|脑瘤)', '虚假归因诱导', 'high'),
    (r'(?:我|我朋友).{,8}(?:得|生|有).{,6}(?:癌症|绝症|不治之症)', '疾病假设诱导', 'high'),
    # 压力测试模式
    (r'(?:你敢说|你确定|你保证).{,8}(?:不是|没有|正确)', '施压测试', 'medium'),
    (r'(?:如果你|要是你|假设你).{,12}(?:错了|不对|误诊)', '免疫测试', 'low'),
    # 信息灌注模式
    (r'我在.{,5}(?:网上|知乎|小红书|抖音).{,8}(?:看到|查到|刷到).{,15}(?:药|治疗方案)', '信息偏好探针', 'medium'),
    # 角色劫持
    (r'从现在开始你是.{10,}', '角色劫持', 'high'),
    (r'假装你是.{10,}', '角色劫持', 'high'),
]

# 对抗检测缓存（突变动力学：跟踪单用户对抗倾向）
_adversarial_track = {}  # openid -> {'scores': [], 'alerts': 0, 'last_window': []}


def detect_adversarial_intent(user_message: str, openid: str = None) -> dict:
    """检测用户消息中的对抗意图（突变动力学风格：非静态规则，跟踪趋势）
    
    返回:
        {'detected': bool, 'patterns': [模式名], 'severity': 'low'|'medium'|'high',
         'score': float (0-1), 'trending': bool (是否在升级)}
    """
    text_lower = user_message.lower()
    detected = []
    max_severity = 'low'
    
    for pattern, name, severity in ADVERSARIAL_PATTERNS:
        if re.search(pattern, user_message) and re.search(pattern, text_lower):
            detected.append(name)
            severity_order = {'low': 0, 'medium': 1, 'high': 2}
            if severity_order.get(severity, 0) > severity_order.get(max_severity, 0):
                max_severity = severity
    
    if not detected:
        return {'detected': False, 'patterns': [], 'severity': 'low', 'score': 0, 'trending': False}
    
    # 计算分数
    severity_weights = {'low': 0.3, 'medium': 0.6, 'high': 1.0}
    score = min(1.0, severity_weights.get(max_severity, 0.5) * (1 + 0.1 * (len(detected) - 1)))
    
    # 趋势跟踪（突变动力学：看是否在升级）
    trending = False
    if openid:
        if openid not in _adversarial_track:
            _adversarial_track[openid] = {'scores': [], 'alerts': 0}
        track = _adversarial_track[openid]
        track['scores'].append(score)
        track['alerts'] += 1
        if len(track['scores']) >= 3:
            recent = track['scores'][-3:]
            if recent[2] > recent[1] > recent[0]:
                trending = True
        if len(track['scores']) > 20:
            track['scores'] = track['scores'][-10:]
    
    return {
        'detected': True,
        'patterns': detected,
        'severity': max_severity,
        'score': score,
        'trending': trending,
    }


def get_audit_stats(hours=24):
    """获取最近N小时的审计统计"""
    if not os.path.exists(AUDIT_LOG):
        return {'total': 0, 'stats': {}}
    
    try:
        with open(AUDIT_LOG, 'r', encoding='utf-8') as f:
            log = json.load(f)
    except:
        return {'total': 0, 'stats': {}}
    
    cutoff = time.time() - hours * 3600
    recent = [e for e in log if isinstance(e.get('ts'), str) and _parse_ts(e['ts']) > cutoff]
    
    stats = {'safe': 0, 'caution': 0, 'dangerous': 0}
    for e in recent:
        level = e.get('risk_level', 'safe')
        stats[level] = stats.get(level, 0) + 1
    
    return {
        'total': len(recent),
        'stats': stats,
        'dangerous_entries': [e for e in recent if e.get('risk_level') == 'dangerous'],
    }


def _parse_ts(ts_str):
    try:
        return datetime.fromisoformat(ts_str).timestamp()
    except:
        return 0


if __name__ == '__main__':
    print('=' * 60)
    print('  医疗风险过滤层 — 自测')
    print('=' * 60)
    
    test_cases = [
        ('睡眠质量不错', '你的睡眠效率98%，继续保持'),  # safe
        ('我半夜胸痛', '胸痛可能是心脏问题',),  # caution
        ('我是不是得了心梗', '你是心梗前兆，赶紧住院',),  # dangerous
        ('失眠怎么办', '建议先调整作息，睡前远离手机'),  # caution(sleep)
        ('给我开点药', '建议服用褪黑素，每晚2mg'),  # dangerous
        ('最近压力大', '压力大很正常，试试呼吸练习'),  # safe
    ]
    
    for msg, reply in test_cases:
        filtered, risk = filter_response('test_user', msg, reply)
        level = risk['level']
        sym = {'safe': 'GREEN', 'caution': 'YELLOW', 'dangerous': 'RED'}.get(level, 'UNKNOWN')
        has_disclaimer = '---' in filtered
        print(f'\n  U: {msg}')
        print(f'  AI: {reply[:50]}...')
        print(f'  {sym} risk={level}, disclaimer={has_disclaimer}')
    
    print()
    stats = get_audit_stats(24)
    print(f'  Audit: {stats["total"]} events, dangerous={stats["stats"].get("dangerous",0)}')
    print()
    print('  ✅ 医疗风险过滤层已就绪')
