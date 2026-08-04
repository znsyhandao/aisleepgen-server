# -*- coding: utf-8 -*-
"""
neural_extractor.py — 基于LLM的睡眠数据提取器

取代 nlp_extractor.py 的脆弱正则，用 DeepSeek 直接从用户自然语言中
提取结构化睡眠数据。

用法:
  extractor = NeuralExtractor()
  fields = extractor.extract("昨晚喝了酒，肚子不舒服老醒")
  # -> {"awake_times": 3, "awake_cause": "消化不适", "drink": "alcohol", ...}

后备机制:
  1. 调用 DeepSeek 提取
  2. 如果失败（网络/API问题）→ 自动 fallback 到正则 nlp_extractor
"""

import json
import re
import logging
from typing import Optional

_log = logging.getLogger('aisleepgen.neural_extractor')

# 定义需要提取的字段列表（输出格式）
EXTRACTION_SCHEMA = {
    "bedtime": "string | null, e.g. '23:30' or '11点半'",
    "wake_time": "string | null, e.g. '07:00'",
    "total_duration": "int | null, minutes of total sleep",
    "sleep_latency": "int | null, minutes to fall asleep",
    "awake_times": "int | null, how many times woke up at night",
    "awake_duration": "int | null, total minutes awake at night",
    "awake_cause": "string | null, why they woke up, e.g. 'noise', 'stomach', 'anxiety', 'bathroom', 'unknown'",
    "stress_level": "int | null, 1-10 stress level",
    "has_pain": "boolean | null",
    "pain_area": "string | null, body part",
    "drink": "string | null, 'alcohol', 'coffee', 'tea', 'none' if mentioned",
    "meal": "string | null, e.g. 'heavy', 'spicy', 'late', 'none'",
    "mood": "string | null, e.g. 'anxious', 'relaxed', 'stressed', 'normal'",
    "overall_quality": "string | null, user's own assessment: 'good', 'fair', 'poor', 'terrible'",
    "key_complaint": "string | null, the main sleep issue in 2-5 words",
    "determined": "boolean, true if user provided enough data for meaningful analysis",
    "confidence": "string, 'high'|'medium'|'low' how confident you are in the extraction",
}


def _call_deepseek_extract(text: str) -> Optional[dict]:
    """调用 DeepSeek 提取结构化睡眠数据"""
    from ai_client import call_deepseek_api
    
    system_prompt = """你是一个睡眠数据提取专家。从用户的自然语言描述中提取结构化睡眠数据。

请严格按照下面的 JSON Schema 提取，只输出JSON，不要任何其他文字：

""" + json.dumps(EXTRACTION_SCHEMA, ensure_ascii=False, indent=2) + """

规则：
- 不要编造用户没提到的字段，不存在的字段设为 null
- awake_cause 是"夜间醒来的原因"
- determined=true 的条件：用户至少提供了 3 个有信息量的字段
- 如果用户说的内容与睡眠无关（纯聊天），设 determined=false
- 时间用24小时制字符串，如 "23:30"
- 时长用小单位（分钟）
- 置信度低于 medium 时，determined=false

只输出JSON，不要任何解释。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": '用户消息: "' + text + '"'},
    ]

    try:
        reply = call_deepseek_api(messages, use_async=False)
        if not reply:
            _log.warning('[NeuralExtract] DeepSeek returned None')
            return None
        
        # 清理回复
        reply = reply.strip()
        if reply.startswith('```'):
            reply = reply.split('\n', 1)[1] if '\n' in reply else reply[3:]
            reply = reply.rsplit('```', 1)[0] if '```' in reply else reply
        reply = reply.strip()
        
        result = json.loads(reply)
        if 'determined' not in result:
            result['determined'] = False
        if 'confidence' not in result:
            result['confidence'] = 'low'
        return result
    except Exception as e:
        _log.warning('[NeuralExtract] DeepSeek extraction failed: %s', e)
        return None


def _legacy_fallback(text: str) -> dict:
    """DeepSeek 失败时回退到正则提取"""
    from nlp_extractor import extract_sleep_fields
    fields = extract_sleep_fields(text)
    # 增加额外启发式
    result = {}
    for k, v in fields.items():
        result[k] = v
    
    # 附加启发式：检测常见原因
    text_lower = text.lower()
    if any(w in text_lower for w in ['酒', '红酒', '啤酒', '白酒']):
        result['drink'] = 'alcohol'
    if any(w in text_lower for w in ['咖啡', 'coffee']):
        result['drink'] = 'coffee'
    if any(w in text_lower for w in ['肚子', '胃', '消化', '吃多', '吃撑', '不消化']):
        result['awake_cause'] = '消化不适'
        result['has_pain'] = True
        result['pain_area'] = '腹部'
    if any(w in text_lower for w in ['压力', '焦虑', '紧张', '担心']):
        result['awake_cause'] = '焦虑'
        result['stress_level'] = 7
    if any(w in text_lower for w in ['老醒', '老让我醒', '老是被', '老起来', '频繁', '一直醒', '反复', '很多次', '总是醒', '不停']):
        # 如果已有的awake_times只是1，提权到3
        if result.get('awake_times', 0) <= 1:
            result['awake_times'] = 3
    if '睡不好' in text_lower or '质量差' in text_lower:
        result['overall_quality'] = 'poor'
    
    result['determined'] = len(result) >= 2
    result['confidence'] = 'low'
    return result


class NeuralExtractor:
    """基于LLM + 正则双重保障的睡眠数据提取器"""
    
    def __init__(self, prefer_llm: bool = True):
        self.prefer_llm = prefer_llm
    
    def extract(self, text: str) -> dict:
        """提取睡眠数据，优先DeepSeek，失败fallback到正则"""
        if not text or not isinstance(text, str) or len(text.strip()) < 2:
            return {'determined': False, 'confidence': 'low'}
        
        text = text.strip()
        
        # 优先 DeepSeek
        if self.prefer_llm:
            result = _call_deepseek_extract(text)
            if result and result.get('determined'):
                _log.info('[NeuralExtract] LLM extraction succeeded for "%s..."', text[:20])
                return result
        
        # Fallback 到增强版正则
        _log.info('[NeuralExtract] Falling back to regex extraction for "%s..."', text[:20])
        result = _legacy_fallback(text)
        return result


# 快速测试
if __name__ == '__main__':
    test_cases = [
        "昨晚喝了一杯红酒，可能有点凉？晚上睡眠感觉肚子不舒服，老让我醒",
        "失眠了，翻来覆去到两点才睡着",
        "今天压力太大了，焦虑得睡不着",
        "还行吧，7个小时",
        "睡了8个小时，挺好的",
        "半夜醒了两次，上了个厕所",
        "你好，今天天气不错",
    ]
    
    extractor = NeuralExtractor()
    for tc in test_cases:
        print(f'\nInput: {tc}')
        result = extractor.extract(tc)
        for k, v in result.items():
            if v is not None and v is not False:
                print(f'  {k}: {v}')
