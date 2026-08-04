#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
nlp_extractor.py — AISleepGen 自然语言睡眠数据提取器

从用户的自然语言描述中提取结构化睡眠字段。
纯正则 + 关键词，零模型依赖。安全、可审计。
"""
from __future__ import unicode_literals
import re
from datetime import datetime
_S = chr(30561)  # 睡
_T = chr(25490)  # 躺
_LQ = chr(26469)  # 起
_XG = chr(37266)  # 醒
_BC = chr(21322)  # 半
_BB = chr(22812)  # 不
_HT = chr(20250)  # 会
_M = chr(27425)  # 没
_ZH = chr(30528)  # 着
_MX = chr(30496)  # 眠
_CP = chr(25289)  # 次
_HU = chr(22238)  # 回
_CJ = chr(25165)  # 才
_JIU = chr(23601)  # 就
_DOU = chr(37117)  # 都
_YO = chr(21448)  # 右
_DO = chr(22810)  # 多
_GE = chr(20010)  # 个
_FN = chr(38047)  # 钟
_XZ = chr(30562)  # 着


def _normalize_hour(h, m, default_h=23, default_m=30):
    """normalize hour to 0~23, minute to 0~59"""
    try:
        h = int(h) if h else default_h
        m = int(m) if m else 0
        if h > 24: h = h % 100
        if h >= 24: h = h - 12 if h >= 24 else h
        return '%02d:%02d' % (h, min(m, 59))
    except:
        return None


def _extract_bedtime(text):
    """extract bedtime"""
    # 匹配有"睡"的: "12点睡", "凌晨2点睡"
    m = re.search(r'(\d{1,2})\u70b9\s*\u7761', text)
    if m:
        h = int(m.group(1))
        if h <= 6: h += 12
        return '%02d:00' % (h % 24)

    # "凌晨2点上床" — 次要模式
    # (简化为最常见的 X点睡 已覆盖)

    return None


def _extract_wake_time(text):
    """extract wake/rise time"""
    wake_time = None

    # "X点起" — 最通用, using actual Unicode chars
    m = re.search(r'(\d{1,2})[\u70b9\uff1a.:\s]*(\d{0,2})\s*\u8d77', text)
    if m:
        h = int(m.group(1))
        mi = m.group(2).strip() if m.group(2) and m.group(2).strip() else '0'
        return _normalize_hour(h, int(mi) if mi else 0)

    # "X点醒"
    m = re.search(r'(\d{1,2})[\u70b9\uff1a.:\s]*(\d{0,2})\s*\u9192', text)
    if m:
        h = int(m.group(1))
        mi = m.group(2).strip() if m.group(2) and m.group(2).strip() else '0'
        return _normalize_hour(h, int(mi) if mi else 0)

    return None


def _extract_sleep_duration(text):
    """extract sleep duration in minutes"""
    # "X个小时" / "X小时"
    m = re.search(r'(\d+)\s*\u4e2a?\u5c0f\u65f6', text)
    if m:
        return int(m.group(1)) * 60
    # "X分钟"
    m = re.search(r'(\d+)\s*\u5206\??\u949f?', text)
    if m:
        return int(m.group(1))
    return None


def _extract_awake_times(text):
    """extract number of nighttime awakenings"""
    # "醒X次" / "醒X回"
    m = re.search(r'\u9192\s*(\d+)\s*(?:\u6b21|\u56de)', text)
    if m:
        return int(m.group(1))
    # "醒了X次/回"
    m = re.search(r'\u9192\u4e86\s*(\d+)\s*(?:\u6b21|\u56de)', text)
    if m:
        return int(m.group(1))
    # 隐含: 提到"醒来"或"醒"
    if '\u9192' in text or '\u591c\u9192' in text:
        return 1
    return None


def _extract_awake_duration(text):
    """extract awake duration in minutes"""
    # "半小时" near 醒
    m = re.search(r'\u534a\u5c0f\u65f6', text)
    if m:
        return 30
    # "X分钟睡不着"
    m = re.search(r'(\d+)\s*\u5206\??\u949f?\s*\u7761\u4e0d\u7740', text)
    if m:
        v = int(m.group(1))
        if v < 240: return v
    return None


def _extract_sleep_latency(text):
    """extract sleep latency in minutes"""
    # "躺X小时才睡着"  (1小时 = 60分, 2小时 = 120分)
    m = re.search(r'\u8eba[\u4e86]?\s*(\d+)\s*\u4e2a?\u5c0f\u65f6\s*(?:\u624d|\u90fd|\u5c31)?\s*\u7761\u7740', text)
    if m:
        v = int(m.group(1))
        return v * 60 if v <= 24 else v
    # "躺了X分钟睡着"
    m = re.search(r'\u8eba[\u4e86]?\s*(\d+)\s*\u5206\??\u949f?\s*\u624d?\s*\u7761\u7740', text)
    if m:
        v = int(m.group(1))
        if 5 <= v < 300: return v
    # "X分钟睡不着"
    m = re.search(r'(\d+)\s*\u5206\??\u949f?\s*\u7761\u4e0d\u7740', text)
    if m:
        v = int(m.group(1))
        if 5 <= v < 300: return v
    # "睡不着" + "半小时"
    if '\u534a\u5c0f\u65f6' in text or '30\u5206' in text:
        return 30
    # 隐含：有"睡不着"关键词
    if '\u7761\u4e0d\u7740' in text or '\u5165\u7761\u56f0\u96be' in text or '\u96be\u5165\u7761' in text:
        return 60
    return None


def _extract_stress_level(text):
    """extract stress level 1-10"""
    stress_keywords = [
        (r'\u538b\u529b[\u5f88\u5927]|\u7126\u8651|\u7d27\u5f20|\u5d29\u6e83|\u6050\u614c|\u5bb3\u6015', 8),
        (r'\u6709\u70b9|\u4e9b\u8bb8|\u5c0f\u538b\u529b|\u5fae\u538b\u529b', 5),
        (r'\u5fc3\u8df3[\u52a0\u5feb]|\u5fc3\u614c|\u5598\u4e0d\u8fc7\u6c14|\u80f8\u95f7', 7),
        (r'\u5de5\u4f5c|\u70e6\u8e81|\u5931\u7720|\u70e6\u607c', 6),
        (r'\u653e\u677e|\u8fd8\u597d|\u4e00\u822c|\u6ca1\u4ec0\u4e48', 3),
    ]
    for pat, level in stress_keywords:
        if re.search(pat, text):
            return level
    return None


def _extract_pain_info(text):
    """extract pain"""
    has_pain = any(kw in text for kw in ['\u75bc', '\u75db', '\u9178', '\u4e0d\u8212\u670d', '\u4e0d\u9002', '\u96be\u53d7'])
    area = ''
    for ap in ['\u5934\u75db', '\u8170\u75db', '\u80cc\u75db', '\u80a9\u8180', '\u8116\u5b50', '\u817f', '\u819d\u76d6', '\u624b\u81c2', '\u8179\u90e8', '\u5173\u8282', '\u5168\u8eab']:
        if ap in text:
            area = ap
            break
    return has_pain, area


def _extract_snore(text):
    return '\u6253\u9f3e' in text


def extract_sleep_fields(text):
    """extract structured sleep data from natural language text"""
    if not text or not isinstance(text, str):
        return {}

    result = {}

    b = _extract_bedtime(text)
    if b: result['bedtime'] = b

    w = _extract_wake_time(text)
    if w: result['wake_time'] = w

    d = _extract_sleep_duration(text)
    if d: result['total_duration'] = d

    l = _extract_sleep_latency(text)
    if l: result['sleep_latency'] = l

    a = _extract_awake_times(text)
    if a is not None: result['awake_times'] = a

    ad = _extract_awake_duration(text)
    if ad: result['awake_duration'] = ad

    s = _extract_stress_level(text)
    if s: result['stress_level'] = s

    hp, pa = _extract_pain_info(text)
    if hp:
        result['has_pain'] = True
        if pa: result['pain_area'] = pa

    if _extract_snore(text):
        result['snore_related'] = True

    return result


if __name__ == '__main__':
    import json as _json
    import sys
    for text in [
        '昨晚12点睡8点起，半夜醒2次',
        '我12点上床1点才睡着，早上6点半醒了',
        '晚上11点睡6点起，醒了3次，每次半小时睡不着，压力很大',
        '睡不着，躺了1小时才睡着，早上3点醒到现在',
        '我每天晚上1点睡9点起，打鼾，腰痛',
        '凌晨2点睡6点醒，压力很大，心慌',
        '睡了大概4个小时吧，半夜醒了头疼',
        '12点睡7点起，半夜醒2次',
        '半夜总是醒，睡不着',
        '躺了1小时才睡着，压力大',
    ]:
        ex = extract_sleep_fields(text)
        known = sum(1 for k in ['bedtime','wake_time','sleep_latency','awake_times','total_duration','stress_level'] if ex.get(k))
        sys.stdout.write(text[:40] + '\n')
        sys.stdout.write('  known=%d %s\n\n' % (known, _json.dumps(ex, ensure_ascii=False)))
