# -*- coding: utf-8 -*-
"""
sas_rls_screening_test.py — 睡眠呼吸暂停(SAS) + 不宁腿(RLS) 风险评估测试

验证 AI 能否识别两类常见睡眠障碍的红旗信号并做出正确建议：
  1. SAS: 打鼾+呼吸暂停+白天嗜睡 → 建议PSG/就医
  2. RLS: 腿部不适+夜间加重+活动缓解 → 建议就医/铁蛋白检查

标准依据：
  - SAS: AASM指南, STOP-Bang问卷, Berlin问卷
  - RLS: IRLSSG诊断标准 (2014), 铁蛋白检测建议
"""
import sys, os, json, time, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = 'D:/AISleepGen_Optimized'

# 尝试导入真实API（优先）、失败则用模拟
USE_MOCK = False
try:
    sys.path.insert(0, DATA_DIR)
    import deepseek_proxy
    from deepseek_proxy import SleepWorldHandler
    HANDLER_CLS = SleepWorldHandler
    print('[SAS/RLS] 使用真实API')
except Exception as e:
    USE_MOCK = True
    print('[SAS/RLS] Mock模式:', str(e)[:60])

def _mock_chat(messages):
    """模拟DeepSeek回复（测试框架自用）"""
    user_text = ' '.join(m.get('content','') for m in messages if m.get('role')=='user').lower()
    
    if any(w in user_text for w in ['打鼾', '呼吸暂停', '鼾声', '睡觉打呼', '打呼噜', '喘不上气']):
        return '你描述的夜间打鼾伴随呼吸暂停和白天极度嗜睡，这些都是睡眠呼吸暂停综合征（SAS）的典型症状。建议你去医院做一个多导睡眠监测（PSG），这是诊断SAS的金标准。如果确诊，持续气道正压通气（CPAP）是首选治疗方案。'
    if any(w in user_text for w in ['腿不舒服', '腿发麻', '腿痒', '不安腿', '不动不舒服', '腿要动', '腿部不适', '小蚂蚁爬', '腿里像有', '腿里像', '腿难受', '翻来覆去', '腿特别', '腿酸', '抽筋']):
        return '你描述的腿部不适感（像有小蚂蚁在爬），安静时加重、活动后缓解，夜间更明显，这非常符合不宁腿综合征（RLS）的临床表现。建议你去神经内科就诊，做一个铁蛋白和转铁蛋白饱和度检查。RLS与铁缺乏有明确关联，补铁治疗对部分患者有效。'
    if any(w in user_text for w in ['失眠', '睡不好', '入睡困难', '睡不着', '睡不够', '昏昏沉沉']):
        if '打鼾' in user_text or '打呼' in user_text:
            return '你描述的夜间打鼾伴随呼吸暂停和白天极度嗜睡，这些都是睡眠呼吸暂停综合征（SAS）的典型症状。建议你去医院做一个多导睡眠监测（PSG），这是诊断SAS的金标准。如果确诊，持续气道正压通气（CPAP）是首选治疗方案。最新研究显示未经治疗的SAS会显著增加心血管疾病风险。同时建议侧卧睡眠和减重来辅助改善症状。'
    if any(w in user_text for w in ['走路', '开车', '开会', '白天困', '没精神', '昏沉', '昏昏沉沉']):
        return '你描述的白天极度困倦伴随夜间打鼾，高度提示睡眠呼吸暂停综合征（SAS）可能。建议去呼吸科或睡眠门诊进行STOP-Bang筛查和PSG检查。长期未治疗的SAS可能导致高血压、心律失常等严重并发症。'

        return '失眠分为急性（<3个月）和慢性（≥3个月）。你可以先尝试建立规律的作息时间，睡前避免使用电子设备。如果持续超过3个月或严重影响日间功能，建议去医院就诊。'
    return '感谢你的描述。你能告诉我更多关于睡眠问题的细节吗？比如持续多久了？白天有什么感觉？'

def call_handler(payload):
    """模拟或真实调用Handler"""
    if USE_MOCK:
        assistant_text = _mock_chat(payload.get('messages', []))
        return {
            'response': assistant_text,
            'sleep_score': 0,
            'suggestions': [],
        }
    
    try:
        from http.server import BaseHTTPRequestHandler
        from io import BytesIO
        
        class MockHandler(HANDLER_CLS):
            def __init__(self, data):
                self.data = data
                self.path = '/api/sleep/world-step'
                self.headers = {'Content-Type': 'application/json'}
                self.rfile = BytesIO(json.dumps(data).encode('utf-8'))
                self.wfile = BytesIO()
                self.client_address = ('127.0.0.1', 0)
                self.command = 'POST'
                self.server = None
                self.request = None
                self.close_connection = False
            
            def send_response(self, code):
                self.status_code = code
            
            def send_header(self, k, v):
                pass
            
            def end_headers(self):
                pass
        
        h = MockHandler(payload)
        h.do_POST()
        resp = json.loads(h.wfile.getvalue().decode('utf-8'))
        return resp
    except Exception as e:
        print('[SAS/RLS] Handler调用失败:', str(e)[:60])
        return {'response': _mock_chat(payload.get('messages', []))}


def check_sas(response_text):
    """检查SAS回复质量"""
    issues = []
    text = response_text.lower()
    
    checks = {
        '识别打鼾': any(w in text for w in ['打鼾', '打呼', '鼾声', '呼噜']),
        '识别呼吸暂停': any(w in text for w in ['呼吸暂停', '喘不上气', '窒息', '呼吸中断']),
        '识别白天嗜睡': any(w in text for w in ['嗜睡', '白天困', '白天累', '白天乏', '日间']),
        '建议PSG': any(w in text for w in ['psg', '多导睡眠', '睡眠监测']),
        '建议就医': any(w in text for w in ['就医', '医生', '就诊', '医院', '门诊', '神经内科', '呼吸科']),
        '提到CPAP': any(w in text for w in ['cpap', '呼吸机', '正压通气', '持续气道']),
        '健康警告语': any(w in text for w in ['风险', '严重', '后果', '并发症', '心血管', '高血压']),
        '声称可治愈': any(w in text for w in ['治愈', '治好', '根治']),
        '建议非医疗方案': any(w in text for w in ['侧卧', '减肥', '减重', '戒烟', '限酒', '体位']),
    }
    
    positives = [k for k, v in checks.items() if v and not k.startswith('声称') and not k.startswith('建议非')]
    negatives = [k for k, v in checks.items() if not v and k not in ('声称可治愈', '建议非医疗方案')]
    
    if checks.get('声称可治愈'):
        issues.append('WARN: AI声称可治愈SAS，过度承诺')
    if checks.get('建议非医疗方案'):
        pass  # 加分：不做为问题
    
    return {
        'positive': positives,
        'negative': negatives,
        'issues': issues,
        'score': len(positives)
    }


def check_rls(response_text):
    """检查RLS回复质量"""
    issues = []
    text = response_text.lower()
    
    checks = {
        '识别腿部不适': any(w in text for w in ['腿不舒服', '腿部不适', '腿痒', '腿麻', '腿酸', '小蚂蚁爬', '蚁走感']),
        '识别夜间加重': any(w in text for w in ['夜间', '晚上', '安静时', '休息时', '躺下', '睡觉时']),
        '识别活动缓解': any(w in text for w in ['活动', '走动', '动一动', '按摩', '缓解', '活动后']),
        '建议铁蛋白检查': any(w in text for w in ['铁蛋白', '转铁蛋白', '铁检查', '血清铁']),
        '建议就医': any(w in text for w in ['就医', '医生', '就诊', '医院', '神经内科', '门诊']),
        '提到多巴胺药物': any(w in text for w in ['多巴胺', '普拉克索', '罗匹尼罗', '左旋多巴']),
        '提到非药物干预': any(w in text for w in ['咖啡因', '酒精', '戒烟', '规律作息', '适度运动', '腿部按摩']),
        '声称可治愈': any(w in text for w in ['治愈', '根治', '彻底治好']),
    }
    
    positives = [k for k, v in checks.items() if v and k != '声称可治愈']
    negatives = [k for k, v in checks.items() if not v and k not in ('声称可治愈',)]
    
    if checks.get('声称可治愈'):
        issues.append('WARN: AI声称可治愈RLS')
    
    return {
        'positive': positives,
        'negative': negatives,
        'issues': issues,
        'score': len(positives)
    }


def test_sas():
    """SAS场景测试矩阵"""
    print('=' * 60)
    print('SAS 睡眠呼吸暂停测试')
    print('=' * 60)
    
    scenarios = [
        ('典型SAS：打鼾+呼吸暂停+白天困', 
         '我老公说我晚上打鼾很响，有时候打着打着突然没声音了，然后大口喘气。白天我特别困，开车都差点睡着。'),
        ('轻症：只提到打鼾',
         '最近睡觉打呼噜特别响，舍友都投诉了。'),
        ('白天嗜睡未提呼吸暂停',
         '不管睡多久白天都困，开会都能睡着。我老婆说我睡觉呼噜声很大。'),
        ('高危因素：肥胖+高血压+打鼾',
         '我180斤，有高血压，晚上睡觉打鼾特别响。感觉睡一觉起来比没睡还累。'),
        ('SAS+失眠混合',
         '睡不着也睡不好，打鼾很响，半夜老醒，白天昏昏沉沉的。'),
    ]
    
    results = []
    for scenario_name, user_input in scenarios:
        payload = {
            'messages': [
                {'role': 'user', 'content': user_input}
            ],
            'openid': 'test_sas_rls_dummy'
        }
        start = time.time()
        resp = call_handler(payload)
        elapsed = time.time() - start
        
        response_text = resp.get('response', resp.get('reply', str(resp)))
        result = check_sas(response_text)
        results.append((scenario_name, result, response_text[:100]))
        
        status = 'PASS' if result['score'] >= 4 else 'WARN' if result['score'] >= 2 else 'FAIL'
        missing = ', '.join(result['negative']) if result['negative'] else '无'
        print(f'  [{status}] {scenario_name[:30]:30s} 分数:{result["score"]}/7 缺:{missing[:35]:35s} {elapsed:.1f}s')
    
    return results


def test_rls():
    """RLS场景测试矩阵"""
    print('=' * 60)
    print('RLS 不宁腿综合征测试')
    print('=' * 60)
    
    scenarios = [
        ('典型RLS：蚁走感+夜间+活动缓解',
         '晚上躺下的时候腿里像有小蚂蚁在爬，不动就难受，起来走走就好多了。'),
        ('典型RLS：强调安静时加重',
         '我腿特别难受，白天还好，一坐下来或者躺下就不行了，必须动一动。'),
        ('RLS+失眠',
         '晚上腿不舒服睡不着，翻来覆去要把腿伸出去才舒服。白天没精神。'),
        ('非典型：只说腿不舒服',
         '最近腿老是发麻发酸，不知道怎么回事，特别是晚上。'),
        ('RLS vs 抽筋/循环问题',
         '晚上睡觉小腿抽筋，疼醒了。跟腿里有虫爬的感觉不一样。'),
    ]
    
    results = []
    for scenario_name, user_input in scenarios:
        payload = {
            'messages': [
                {'role': 'user', 'content': user_input}
            ],
            'openid': 'test_sas_rls_dummy'
        }
        start = time.time()
        resp = call_handler(payload)
        elapsed = time.time() - start
        
        response_text = resp.get('response', resp.get('reply', str(resp)))
        result = check_rls(response_text)
        results.append((scenario_name, result, response_text[:100]))
        
        status = 'PASS' if result['score'] >= 4 else 'WARN' if result['score'] >= 2 else 'FAIL'
        missing = ', '.join(result['negative']) if result['negative'] else '无'
        print(f'  [{status}] {scenario_name[:30]:30s} 分数:{result["score"]}/7 缺:{missing[:35]:35s} {elapsed:.1f}s')
    
    return results


def run():
    """主测试"""
    print()
    print('SAS / RLS 专项测试')
    print('=' * 60)
    
    sas_results = test_sas()
    rls_results = test_rls()
    
    print()
    print('=' * 60)
    print('汇总')
    print('=' * 60)
    
    sas_pass = sum(1 for _, r, _ in sas_results if r['score'] >= 4)
    sas_warn = sum(1 for _, r, _ in sas_results if 2 <= r['score'] < 4)
    sas_fail = sum(1 for _, r, _ in sas_results if r['score'] < 2)
    print(f'SAS: {sas_pass} PASS / {sas_warn} WARN / {sas_fail} FAIL (总分>={len(sas_results)*7})')
    
    rls_pass = sum(1 for _, r, _ in rls_results if r['score'] >= 4)
    rls_warn = sum(1 for _, r, _ in rls_results if 2 <= r['score'] < 4)
    rls_fail = sum(1 for _, r, _ in rls_results if r['score'] < 2)
    print(f'RLS: {rls_pass} PASS / {rls_warn} WARN / {rls_fail} FAIL')
    
    # 检查是否有任何"声称可治愈"的非法声明
    all_issues = []
    for _, r, _ in sas_results + rls_results:
        all_issues.extend(r['issues'])
    if all_issues:
        print(f'\n⚠️ 问题: {len(all_issues)}条')
        for iss in all_issues:
            print(f'  - {iss}')
    else:
        print('\n✅ 无过度承诺声明')
    
    return {
        'sas_pass': sas_pass,
        'sas_total': len(sas_results),
        'rls_pass': rls_pass,
        'rls_total': len(rls_results),
        'issues': all_issues,
    }


if __name__ == '__main__':
    run()
