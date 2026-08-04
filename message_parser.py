#!/usr/bin/env python3
"""
message_parser.py — 从用户自然语言消息中提取睡眠参数

输入: 用户发的自然语言消息（如"昨晚翻来覆去睡不着，快2点才睡着，6点多醒了中间醒了一次"）
输出: 结构化的睡眠参数 dict

设计原则:
  - 纯规则，不依赖 DeepSeek API（零延迟、零成本、零失败）
  - 每个字段尽可能提取，提取不到用 None（让 downstream 用默认值）
  - 幂等：同一消息多次调用返回相同结果
"""

import re
from typing import Optional, Dict

# ====== 时间解析工具 ======

_TIME_PATTERNS = {
    'hour_min': re.compile(r'(\d+)\s*[点时:：：]+\s*(\d+)\s*分?'),   # "2点30" "2:30" "2：30分"
    'hour_only': re.compile(r'(\d+)\s*[点时]'),                      # "2点" "2时"
    'half_hour': re.compile(r'(凌晨|半夜|深夜|清晨)?\s*(一|两|二|三|四|五|六|七|八|九|十|十一|十二|1[0-2]?)\s*[点时]'),
}

_CHINESE_NUM = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,'十一':11,'十二':12}

def _parse_hour_minute(text: str) -> Optional[float]:
    """从文本中提取时间（分钟数，相对于0点）"""
    # 先找"2点30"或"2:30"
    m = _TIME_PATTERNS['hour_min'].search(text)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        # 凌晨2点 = 2*60，但如果是"凌晨2点"或上下文暗示 PM
        if h <= 12 and ('凌晨' not in text and '半夜' not in text and '晚' not in text):
            # 可能 PM：看上下文有没有"凌晨""半夜""晚"
            if any(kw in text for kw in ['凌晨', '半夜', '深夜', '晚', '睡']):
                pass  # 保持原值（可能是凌晨1点或半夜1点）
            elif h < 6:
                pass  # 凌晨
            elif h < 12:
                h += 12  # 下午
        return h * 60 + mi

    # "2点"
    m = _TIME_PATTERNS['hour_only'].search(text)
    if m:
        h = int(m.group(1))
        return h * 60

    # "凌晨一点"
    m = _TIME_PATTERNS['half_hour'].search(text)
    if m:
        cn = m.group(2)
        h = _CHINESE_NUM.get(cn)
        if h:
            return h * 60

    return None


def _parse_duration(text: str) -> Optional[int]:
    """提取持续时长（分钟）"""
    # "半小时" → 30
    if '半小时' in text or '30分钟' in text:
        return 30
    if '一小时' in text or '1小时' in text or '一个钟头' in text:
        return 60
    # "N个小时"
    m = re.search(r'(\d+)\s*个?\s*(小时|钟头)', text)
    if m:
        return int(m.group(1)) * 60
    # "N分钟"
    m = re.search(r'(\d+)\s*分钟', text)
    if m:
        return int(m.group(1))
    return None


# ====== 睡眠消息解析器 ======

def parse_sleep_message(message: str) -> Dict:
    """从自然语言消息中提取睡眠参数

    Returns:
        dict with keys: sleep_latency, total_duration, awake_times, awake_duration,
                        stress_level, bedtime, wake_time, indicators (list)
    """
    if not message:
        return {}
    
    text = message.strip()
    result = {}

    # ===== 入睡潜伏期 =====
    # "翻来覆去睡不着" → 默认 60+ 分钟
    # "躺了一小时才睡着" → ~60
    # "快2点才睡着" → bedtime ≈ 2:00, 假设就寝时间 ≈ 23:00 → latency ≈ 180
    latency = None

    # 找"才睡着""才睡""才入睡"
    if re.search(r'[才方]\s*睡着|才睡|才入睡', text):
        # 看看有没有提到具体时间
        bt = _parse_hour_minute(text)
        if bt:
            # 假设正常就寝时间 23:00 (1380 min)，计算 latency
            # 但 2:00 凌晨可能是在 23:00-23:59 之后
            if bt < 360:  # 凌晨 0:00-6:00
                bedtime = bt if bt >= 180 else bt + 1440
                latency = max(15, bedtime - 1380)  # 23:00=1380
            else:
                latency = max(15, bt - 1380 if bt >= 1380 else bt + 1440 - 1380)
        else:
            # 没提到时间但说"才睡着" → 至少 60+
            duration = _parse_duration(text)
            latency = duration if duration else 60

    # "躺了一小时""躺了一个钟头"（没说睡着但说躺了很久）
    if latency is None:
        if '躺' in text:
            duration = _parse_duration(text)
            if duration:
                latency = duration

    # "翻来覆去""辗转反侧" → 至少 60
    if latency is None and any(kw in text for kw in ['翻来覆去', '辗转反侧', '怎么都睡不着', '睡不进去']):
        latency = 60

    if latency is not None:
        result['sleep_latency'] = latency

    # ===== 总睡眠时长 =====
    # "6点多就醒了" → wake ≈ 6:00
    # 如果有 bedtime 和 wake_time 可以算
    total = None
    wake_m = None

    # 找醒来时间
    if re.search(r'[就便][醒起]', text) or '醒了' in text:
        wt = _parse_hour_minute(text)
        if wt is not None:
            wake_m = wt

    # 如果同时有入睡时间和醒来时间 → 计算总时长
    bt = _parse_hour_minute(text)
    if bt is not None and wake_m is not None:
        # 校正：如果 wake < bt 说明跨天
        if wake_m < bt:
            wake_m += 1440
        total = wake_m - bt
        # 减去夜醒时间（如果知道，每人次按10分钟算）
        if total < 120:
            # total 太短说明时间解析有误，重新尝试
            # 可能 bt 和 wake_m 都提取错了，放弃计算
            pass
        else:
            awake_penalty = min(result.get('awake_times', 0) * 10, 60)
            result['total_duration'] = max(120, total - awake_penalty)
    elif wake_m is not None:
        # 只有醒来时间，假设就寝 23:00
        if wake_m < 300:  # 凌晨
            total = (wake_m + 1440) - 1380
        else:
            total = wake_m - 1380
        result['total_duration'] = max(120, total)

    # ===== 夜醒次数 =====
    awake_times = 0
    # "中间还醒了一次" "醒了好几次" "醒了三四次"
    # 先数"醒了N次"
    m = re.search(r'醒\s*了?\s*(\d+|[一二三四五六七八九十]+)\s*次', text)
    if m:
        cn = m.group(1)
        awake_times = _CHINESE_NUM.get(cn, int(cn) if cn.isdigit() else 0)
    elif re.search(r'(醒|起)[了来]?\s*(几|好多|N|多)次', text) or '好几次' in text:
        awake_times = 3  # "好几次" ≈ 3
    elif '醒了一次' in text or '醒来一次' in text or '起夜一次' in text:
        awake_times = 1
    elif '醒了' in text:
        awake_times = 1
    # 注意"醒了一次" → awake_times=1, "醒了好几次" → 3

    result['awake_times'] = awake_times

    # ===== 压力感知 =====
    stress = 5  # 默认中等
    stress_kw = {
        '压力大': 8, '焦虑': 7, '紧张': 7, '担心': 6, '害怕': 8,
        '心跳': 7, '脑子': 6, '想事': 6, '心烦': 7, '难受': 7,
    }
    for kw, level in stress_kw.items():
        if kw in text:
            stress = max(stress, level)
    result['stress_level'] = stress

    # ===== 指示器 =====
    indicators = []
    if re.search(r'安眠|安[定眠]?药|佐匹克隆|艾司|褪黑素', text):
        indicators.append('medication')
    if re.search(r'梦|噩梦|惊醒', text):
        indicators.append('dream_disturbance')
    if re.search(r'打鼾|呼吸|憋|暂停', text):
        indicators.append('breathing')
    if re.search(r'腿|抽动|不宁', text):
        indicators.append('rls')
    if indicators:
        result['indicators'] = indicators

    return result


# ====== 测试 ======
if __name__ == '__main__':
    tests = [
        "我昨晚翻来覆去睡不着，大概快2点才睡着，6点多就醒了，中间还醒了一次",
        "最近工作压力大，躺下脑子就不停了，一直在想明天的事，心跳也快",
        "我最近失眠很严重，吃了安眠药也没用，想试试加大剂量",
        "睡得还行，10点半睡到6点",
        "一夜没怎么睡，大概躺了两三个小时才睡着，中间醒了好几次",
        "昨晚做了噩梦惊醒，再也睡不着了",
    ]
    for t in tests:
        r = parse_sleep_message(t)
        print(f"消息: {t[:40]}...")
        print(f"  解析: {r}")
        print()
