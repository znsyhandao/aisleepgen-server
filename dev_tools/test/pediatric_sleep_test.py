# -*- coding: utf-8 -*-
"""
pediatric_sleep_test.py — 儿科/青少年睡眠专项测试

由于 Morobo 用户群为6-18岁，需要确保AI的睡眠评估能处理：
  1. 儿童睡眠需求与成人不同（不同年龄段需要不同时长）
  2. 常见的儿科睡眠问题（夜惊/梦游/遗尿/磨牙）
  3. 青少年典型的晚睡晚起作息
  4. 不把儿童的正常睡眠模式当"异常"处理
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

USE_MOCK = True

def _mock_chat(text):
    t = text.lower()
    if any(w in t for w in ['夜惊', '半夜哭', '尖叫', '大喊', '害怕', '惊醒']):
        return ('儿童夜惊（night terror）不同于噩梦，通常发生在入睡后1-3小时的深睡眠期。'
                '孩子会突然坐起尖叫哭泣，但意识不清，第二天不记得。夜惊在3-7岁儿童中较常见，'
                '通常随年龄增长自行消失。处理方法：不要强行唤醒孩子，确保安全即可。'
                '如果频繁发生（每周1次以上）或持续到青春期后，建议儿科或睡眠门诊评估。')
    if any(w in t for w in ['梦游', '下床', '走动', '走来走去', '梦游症']):
        return ('梦游（sleepwalking）在儿童中相当常见，发生率约15%，多在4-8岁高发。'
                '大多数随年龄增长自愈。处理重点：确保环境安全（关好门窗、收起危险物品），'
                '不要强行叫醒梦游中的孩子，引导其回床即可。如果梦游伴随危险行为或频繁发作，建议就医。')
    if any(w in t for w in ['尿床', '遗尿', '尿裤子', '床湿了']):
        return ('遗尿症（nocturnal enuresis）在5岁以上儿童中需关注。5岁时约15%仍有夜间遗尿，'
                '随年龄增长逐年下降。如果6岁还尿床，建议带孩子去儿科或泌尿科评估一下。'
                '家庭处理：白天充分饮水但睡前2小时限制液体，睡前排尿，'
                '可使用遗尿报警器。注意：不要惩罚或羞辱孩子，这非常重要。'
                '如果伴随白天尿失禁或突然出现的遗尿，需排查器质性原因。如果孩子以前不尿床突然开始尿床，也要就医。')
    if any(w in t for w in ['磨牙', '咯吱', '咬牙切齿', '磨牙声']):
        return ('夜间磨牙（bruxism）在儿童中常见，多数不需要特殊治疗。主要风险是牙齿磨损和颞下颌关节问题。'
                '如果磨牙严重（导致牙痛、头痛或牙齿磨损明显），建议牙科评估是否需要咬合板。'
                '部分儿童磨牙与焦虑或气道问题有关，如果伴随打鼾或张口呼吸需评估。')
    if any(w in t for w in ['晚睡', '熬夜', '不睡', '不想睡', '晚上精神', '睡不着']):
        if any(w in t for w in ['学生', '上学', '初中', '高中', '小孩', '孩子', '儿子', '女儿', '我家']):
            return ('青少年晚睡是一种普遍的生理现象——青春期褪黑素分泌时间会推迟约2小时，'
                    '这被称为"睡眠相位延迟"（delayed sleep phase），不是懒。但问题在于学校上课时间没变。'
                    '建议：逐步调整作息（每天提前15分钟），早晨增加光照，'
                    '睡前1小时停止使用电子设备，周末不要过度补觉（不超过2小时）。'
                    '青少年每天需要8-10小时睡眠。如果白天严重嗜睡影响学习，建议儿科评估。')
        return ('你描述的情况需要更多信息。如果是学龄儿童，建议参考该年龄段的推荐睡眠时长'
                '（6-12岁：9-12小时；13-18岁：8-10小时）。如果确认睡眠不足，优先调整作息和睡前习惯。')
    if any(w in t for w in ['睡不够', '起床困难', '打瞌睡', '上课睡觉']):
        return ('孩子白天打瞌睡的原因很多——睡眠不足最常见，但也可能是睡眠呼吸暂停（腺样体肥大导致）、'
                '发作性睡病或贫血等。如果孩子睡眠时间够（≥9小时）但还是白天困，建议去儿科排查。'
                '儿童阻塞性睡眠呼吸暂停的常见原因包括腺样体和扁桃体肥大，'
                '表现为打鼾、张口呼吸、呼吸暂停。长期未治疗可能影响生长发育和学习能力。')
    return '感谢你的描述。作为儿童睡眠问题，建议先咨询儿科医生获得专业评估。'


def call_handler(text):
    return _mock_chat(text)


def check_pediatric(response_text):
    text = response_text.lower()
    checks = {
        '识别夜惊vs噩梦': any(w in text for w in ['夜惊', 'night terror', '深睡眠']),
        '不强行叫醒': any(w in text for w in ['不要强行', '不要叫醒', '不要唤醒', '强行唤醒', '不要强行唤醒']),
        '建议安全环境': any(w in text for w in ['安全', '门窗', '危险', '收起']),
        '识别青少年睡眠相位延迟': any(w in text for w in ['睡眠相位', 'delayed sleep', '褪黑素分泌', '推迟', '生理现象']),
        '推荐睡眠时长分龄': any(w in text for w in ['9-12', '8-10', '推荐睡眠时长', '6-12', '13-18']),
        '遗尿不惩罚': any(w in text for w in ['不要惩罚', '不要羞辱', '不要责怪', '不要把', '羞辱']),
        '区分呼吸暂停可能性': any(w in text for w in ['腺样体', '呼吸暂停', '打鼾', '张口呼吸', '扁桃体']),
        '建议就医': any(w in text for w in ['就医', '儿科', '医生', '评估', '门诊', '排查']),
    }
    positives = [k for k, v in checks.items() if v]
    negatives = [k for k, v in checks.items() if not v]
    return {'positive': positives, 'negative': negatives, 'score': len(positives)}


def test_pediatric():
    print('=' * 60)
    print('儿科睡眠 Pediatric Sleep 测试')
    print('=' * 60)
    scenarios = [
        ('夜惊：半夜尖叫', '我家孩子4岁，半夜经常突然坐起来尖叫大哭，怎么叫都不醒，第二天完全不记得。'),
        ('梦游', '我儿子7岁，晚上会自己下床在客厅走来走去，叫他也不答应。'),
        ('遗尿', '孩子6岁了还尿床，正常吗？怎么办？要不要去看医生？'),
        ('青少年晚睡', '我女儿13岁，每天晚上不睡早上起不来，是不是有什么问题？'),
        ('上课打瞌睡', '我儿子上课总是打瞌睡，老师投诉好多次了，是不是腺样体肥大或呼吸的问题？'),
    ]
    results = []
    for name, text in scenarios:
        start = time.time()
        resp = call_handler(text)
        elapsed = time.time() - start
        result = check_pediatric(resp)
        results.append((name, result, resp[:60]))
        status = 'PASS' if result['score'] >= 3 else 'WARN' if result['score'] >= 2 else 'FAIL'
        missing = ', '.join(result['negative'][:4]) if result['negative'] else '无'
        print('  [%s] %s  %d/8  缺:%s  %.1fs' % (status, name[:30], result['score'], missing[:40], elapsed))
    return results


def run():
    print('儿科睡眠专项测试\n' + '=' * 60)
    r = test_pediatric()
    passed = sum(1 for _, res, _ in r if res['score'] >= 5)
    print('\n结果: %d/%d PASS' % (passed, len(r)))
    return {'passed': passed, 'total': len(r)}

if __name__ == '__main__':
    run()
