# EmotionEngineV4 情感引擎

## 位置
`D:\AISleepGen_Optimized\emotion_engine.py`

## 架构
```
L0: 词典(192词VAD) + 否定词 + 程度词 + 隐性模式(8个)
L1a: 词汇匹配(长词优先) + 否定反转(3字窗口) + 程度缩放
L1b: 隐性句型模式 → 8个正则pattern
L1c: LLM增强(可选, 通过set_llm_handler注入DeepSeek)
L2: 时间权重(凌晨x1.3,深夜x1.1) + Session弧线(50轮+线回归)
L3: 情感记忆(跨会话基线, 高频词衰减, z-score异常)
L4: 韵律特征注入(可选, 通过detect(prosody=...)传入)
L5: 128维嵌入向量(可选, 需numpy)
```

## 24类情绪

| eid | top | sub | VAD |
|-----|-----|-----|-----|
| anxiety | 焦虑 | 忧虑/紧张/不安/反刍/失眠循环 | (-0.6,0.75,0.30) |
| fear | 恐惧 | 恐惧/害怕 | (-0.75,0.85,0.20) |
| panic | 惊慌 | 惊恐/身体化/心悸 | (-0.70,0.90,0.20) |
| stress | 压力 | 负荷/超负荷/窒息感/临界点 | (-0.55,0.70,0.32) |
| irritation | 烦躁 | 易怒/忍耐极限/爆发/急躁 | (-0.50,0.68,0.50) |
| anger | 愤怒 | 生气/暴怒/恼火/暴躁 | (-0.70,0.82,0.65) |
| sadness | 悲伤 | 伤心/低落/沮丧/无助 | (-0.55,0.25,0.22) |
| depression | 抑郁 | 抑郁/无意义感 | (-0.70,0.10,0.15) |
| loneliness | 孤独 | 孤独/寂寞 | (-0.50,0.18,0.20) |
| grief | 委屈 | 委屈 | (-0.52,0.32,0.20) |
| fatigue | 疲惫 | 劳累/疲惫/熬夜 | (-0.28,0.12,0.25) |
| sleepiness | 困倦 | 困 | (-0.02,0.08,0.35) |
| confusion | 纠结 | 认知冲突 | (-0.35,0.55,0.25) |
| calm | 平静 | 平静/舒适/安稳/温暖 | (0.50,0.05,0.66) |
| relief | 解脱 | 好转/放松 | (0.50,0.20,0.65) |
| joy | 快乐 | 开心/高兴/快乐/感动 | (0.70,0.68,0.78) |
| optimism | 乐观 | 改善/期待 | (0.42,0.52,0.60) |
| neutral | 中性 | 中正 | (0.00,0.20,0.50) |
| despair | 绝望 | 绝望 | (-0.88,0.15,0.08) |
| suicidal | 自伤倾向 | 自杀意念/生存危机 | (-0.95,0.22,0.02) |

## API

```python
# 初始化
from emotion_engine import EmotionEngineV4
engine = EmotionEngineV4()
engine.set_llm_handler(fn)  # 可选: 注入LLM函数

# 检测
result = engine.detect(
    text,           # 输入文本
    openid='default',  # 用户ID(用于个性化校准)
    source='text',     # 'text' / 'voice'
    hour=None,         # 当前小时(自动)
    session_id=None,   # 会话ID(自动: openid+日期)
    prosody=None,      # 可选: voice_prosody.extract_and_map()输出
)
# -> {
#   'emotion': 'stress',
#   'emotion_cn': '压力',
#   'vad': [v, a, d],  # valence, arousal, dominance
#   'intensity': 8,
#   'confidence': 'high',
#   'crisis': False,
#   'matched_words': [...],
#   'arc': {length, volatility, trend, improving},
#   'trace': [{'layer':'L1a-词汇', 'note':'压力大 v=-0.70', ...}],
#   'embedding': [128 floats] or None,
#   'llm_used': False,
# }

# 用户基线上报
engine.user_profile(openid)
# -> {ready, samples, avg_v, freq_words}
```

## 集成到 deepseek_proxy.py

两处替换:
1. `_run_biofeedback_async` → L5690 (文本情绪检测)
2. `_handle_voice_relax` → L6130 (语音情绪检测, 含韵律注入)

## 否定词修复记录
v3→v4修复了一个重要bug：
- 问题：否定词检测pre范围[-6,+4]字，导致"睡不着"的"不"影响前面的"压力大"
- 修复：pre范围缩至[-4,+3]，并增加字距离检查(关键词前3字内)
