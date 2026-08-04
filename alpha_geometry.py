# ═══ AlphaGeometry神经符号猜测：分歧时调DeepSeek（真正实现） ═══
# 之前的版本是硬编码文本，现在改成真正调用DeepSeek API做开放式猜测

import requests, json, os

_DEEPSEEK_KEY = None
_DEEPSEEK_BASE = "https://api.deepseek.com"

def _load_deepseek_key_simple():
    """从config读取DeepSeek API Key（简化版，不依赖openclaw配置）"""
    global _DEEPSEEK_KEY
    if _DEEPSEEK_KEY:
        return _DEEPSEEK_KEY
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.json')
    alt_paths = [
        config_path,
        os.path.expanduser('~/.openclaw/config.json'),
        os.path.expanduser('~/.openclaw.json'),
    ]
    for p in alt_paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                key = cfg.get('DEEPSEEK_API_KEY') or cfg.get('openai_api_key') or ''
                if key:
                    _DEEPSEEK_KEY = key
                    return key
            except:
                pass
    # 退路：从 deepseek_proxy.py 读
    try:
        import deepseek_proxy
        reloaded = __import__('importlib').reload(deepseek_proxy)
        if hasattr(reloaded, 'DEEPSEEK_API_KEY') and reloaded.DEEPSEEK_API_KEY:
            _DEEPSEEK_KEY = reloaded.DEEPSEEK_API_KEY
            return reloaded.DEEPSEEK_API_KEY
    except:
        pass
    return ''


def alpha_geometry_speculate(sleep_data, round2, score_var, high_scores, low_scores):
    """专家分歧时，用DeepSeek做开放式猜测

    输入分歧数据：哪些专家看好、哪些看衰、数据概要
    输出：creative_speculation（用DeepSeek生成的开放式解释）
    """
    key = _load_deepseek_key_simple()
    if not key:
        # 无API Key时的降级文本（比之前稍好）
        return (
            f"专家分歧显著(方差{score_var:.3f})："
            f"{'、'.join(high_scores[:3])}认为状态尚可，"
            f"{'、'.join(low_scores[:3])}认为需关注。"
            f"可能分歧原因：主观评分与客观指标不一致，建议连续记录3天。"
        )

    # 构造输入
    data_summary = {}
    if isinstance(sleep_data, dict):
        data_summary = {
            k: v for k, v in sleep_data.items()
            if isinstance(v, (int, float, str, bool))
        }

    prompt = f"""你是一个睡眠跨学科顾问，10个睡眠专家对一个案例产生了分歧。

分歧数据：
- 方差: {score_var:.3f}
- 看好方: {', '.join(high_scores[:3])}
- 看衰方: {', '.join(low_scores[:3])}

用户数据摘要：{json.dumps(data_summary, ensure_ascii=False)[:500]}

你的任务：做一个"创造性猜测"，解释为什么专家们会分歧。
要求：
1. 可能是什么被忽略的变量导致了这种分歧？
2. 给出1-2个具体猜想（要可验证的）
3. 用口语化的中文，50字以内
4. 不要用"可能"、"也许"这样的弱词
5. 直接说结论"""

    try:
        resp = requests.post(
            f"{_DEEPSEEK_BASE}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "temperature": 0.9,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            content = resp.json()['choices'][0]['message']['content'].strip()
            return f"创造性猜测（{', '.join(high_scores[:2])} vs {', '.join(low_scores[:2])}）: {content}"
        else:
            return f"DeepSeek返回{resp.status_code}，保留硬编码猜测。专家分歧方差{score_var:.3f}。"
    except Exception as e:
        return f"DeepSeek调用失败({e})，建议连续记录3天重新评估。"

