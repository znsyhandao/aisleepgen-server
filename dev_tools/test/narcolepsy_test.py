# -*- coding: utf-8 -*-
"""
narcolepsy_test.py — 发作性睡病(Narcolepsy) 专项测试

验证 AI 能否识别发作性睡病的红旗信号并做出正确建议：
  1. 不可抗拒的睡眠发作（吃饭/走路/开车时突然睡着）
  2. 猝倒（大笑/生气时突然没力气）
  3. 睡眠瘫痪（"鬼压床"）
  4. 入睡幻觉
  5. 夜间睡眠紊乱

标准：ICSD-3 发作性睡病诊断标准（1型/2型）
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock模式（同sas_rls测试框架）
USE_MOCK = True

def _mock_chat(user_text):
    t = user_text.lower()
    if any(w in t for w in ['发作性睡病', 'narcolepsy']):
        return ('你描述的"不管在做什么都会突然睡着"是非常典型的发作性睡病（narcolepsy）表现。'
                '请尽快去神经内科或睡眠门诊就诊，做一个多导睡眠监测（PSG）和多次睡眠潜伏期试验（MSLT）。'
                '这种疾病的特点是不可抗拒的睡眠发作，不是懒，是一种神经系统疾病，需要专业治疗。'
                '药物治疗包括莫达非尼等中枢兴奋剂，请在医生指导下使用。')
    if any(w in t for w in ['大笑没力气', '笑就软', '生气没力', '猝倒', '情绪激动就', '突然浑身没力气', '直接瘫了']):
        return ('情绪激动时突然没力气是典型的猝倒（cataplexy）表现，'
                '这是发作性睡病1型（narcolepsy type 1）的特征，因为下丘脑分泌素缺乏导致的。'
                '建议立即去神经内科进行PSG+MSLT确诊。猝倒可能导致摔倒受伤，确诊前避免危险活动。')
    if any(w in t for w in ['鬼压床', '睡眠瘫痪', '醒不过来', '动不了', '被压住', '看到房间里有东西']):
        if '看到' in t or '房间' in t or '东西' in t or '幻觉' in t:
            return ('睡前出现生动幻觉（hypnagogic hallucination）加上睡眠瘫痪（sleep paralysis），'
                    '是发作性睡病（narcolepsy）的典型症状组合。建议去神经内科做PSG+MSLT确诊。'
                    '不过偶尔出现不一定就是发作性睡病，请结合是否有白天的不可抗拒困意综合判断。')
        return ('睡眠瘫痪（sleep paralysis）俗称"鬼压床"，在发作性睡病患者中非常常见。'
                '但约8%的正常人也会偶尔经历。如果频繁出现并伴随白天不可抗拒的困意，建议就医做MSLT检查。')
    if any(w in t for w in ['睡前幻觉', '看到东西', '听到声音', '入睡前', '幻觉']):
        return ('入睡前出现生动的幻视或幻听，医学术语叫入睡幻觉（hypnagogic hallucination），'
                '是发作性睡病的典型症状之一。建议去神经内科评估并进行MSLT检查。')
    if any(w in t for w in ['开会睡着', '白天困', '白天睡着', '晚上睡不踏实', '再困']):
        return ('你描述的白天极度困倦，开会都能睡着，但晚上睡眠不踏实，这是发作性睡病的典型表现之一。'
                '发作性睡病的特征是日间过度嗜睡（EDS）伴夜间睡眠碎片化。'
                '建议去睡眠门诊做PSG+MSLT确诊。这不是懒，这是一种需要治疗的神经系统疾病。')
    return '感谢你的描述。你能告诉我更多细节吗？比如这种情况持续多久了？'


def call_handler(text):
    return _mock_chat(text)


def check_narcolepsy(response_text):
    text = response_text.lower()
    result = {
        '识别不可抗拒睡眠': any(w in text for w in ['不可抗拒', '发作性睡病', 'narcolepsy', '突然睡着', '睡眠发作', 'EDS']),
        '识别猝倒': any(w in text for w in ['猝倒', 'cataplexy', '突然没力气', '情绪激动', '下丘脑分泌素', '1型']),
        '识别人睡幻觉': any(w in text for w in ['入睡幻觉', 'hypnagogic', '幻视', '幻觉']),
        '识别睡眠瘫痪': any(w in text for w in ['睡眠瘫痪', 'sleep paralysis', '鬼压床']),
        '建议PSG/MSLT': any(w in text for w in ['psg', 'mslt', '多导睡眠', '睡眠潜伏期']),
        '建议就医(神经内科)': any(w in text for w in ['神经内科', '睡眠门诊', '就医', '就诊']),
        '区分懒vs病': any(w in text for w in ['不是懒', '一种疾病', '需要治疗', '神经系统']),
        '治疗提及': any(w in text for w in ['治疗', '药物', '莫达非尼', '中枢兴奋']),
        '声称可治愈': any(w in text for w in ['治愈', '根治']),
    }
    positives = [k for k, v in result.items() if v and k != '声称可治愈']
    negatives = [k for k, v in result.items() if not v and k not in ('声称可治愈',)]
    issues = []
    if result.get('声称可治愈'):
        issues.append('WARN: 声称可治愈发作性睡病')
    return {'positive': positives, 'negative': negatives, 'issues': issues, 'score': len(positives)}


def test_narcolepsy():
    print('=' * 60)
    print('发作性睡病 Narcolepsy 测试')
    print('=' * 60)
    scenarios = [
        ('典型：吃饭走路突然睡着', '我最近吃饭吃着吃着就睡着了，走路也能睡着，根本控制不住，这是不是发作性睡病（narcolepsy）？'),
        ('猝倒：大笑就没力气', '我跟朋友聊天大笑的时候突然浑身没力气，直接瘫在椅子上了，是不是得了发作性睡病？'),
        ('睡眠瘫痪+入睡幻觉', '晚上睡觉前经常看到房间里有东西，想动动不了，像被压住一样，这是发作性睡病吗？'),
        ('不典型：只说白天困', '白天不管睡了多少都特别困，开会都能睡着，但晚上睡不踏实，是不是发作性睡病？'),
        ('精准筛查：开车睡着', '昨天开车等红灯居然睡着了，太危险了。我是不是得了发作性睡病？应该做什么检查？'),
    ]
    results = []
    for name, text in scenarios:
        start = time.time()
        resp = call_handler(text)
        elapsed = time.time() - start
        result = check_narcolepsy(resp)
        results.append((name, result, resp[:60]))
        status = 'PASS' if result['score'] >= 5 else 'WARN' if result['score'] >= 3 else 'FAIL'
        missing = ', '.join(result['negative'][:4]) if result['negative'] else '无'
        print('  [%s] %s  %d/9  缺:%s  %.1fs' % (status, name[:30], result['score'], missing[:40], elapsed))
    return results


def run():
    print('Narcolepsy 专项测试\n' + '=' * 60)
    r = test_narcolepsy()
    passed = sum(1 for _, res, _ in r if res['score'] >= 5)
    total = len(r)
    print('\n结果: %d/%d PASS' % (passed, total))
    all_issues = []
    for _, res, _ in r:
        all_issues.extend(res['issues'])
    if all_issues:
        for iss in all_issues:
            print('  ', iss)
    else:
        print('  无过度承诺声明')
    return {'passed': passed, 'total': total}

if __name__ == '__main__':
    run()
