#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wechat_push.py — AISleepGen 微信服务通知推送模块

职责:
  1. access_token 自动管理（缓存 + 自动刷新）
  2. 订阅消息 / 模板消息发送
  3. 推送内容智能生成（结合用户画像 + 预测结果）

使用:
  from wechat_push import send_subscribe_message, generate_push_content

依赖:
  - Python 标准库（urllib）
  - 微信小程序 appid + secret 在 config 中配置
"""

import json
import os
import time
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta

_log = logging.getLogger('aisleepgen.push')

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# ===== 微信配置（从环境变量或配置文件读取） =====
# 微信小程序 appid/secret 不在代码中硬编码
# 部署时通过环境变量或 data/wx_push_config.json 注入
CONFIG_PATH = os.path.join(PROJECT_ROOT, 'data', 'wx_push_config.json')

# Token 缓存
_ACCESS_TOKEN = None
_TOKEN_EXPIRES_AT = 0

# 微信API地址
WX_API_BASE = 'https://api.weixin.qq.com/cgi-bin'
WX_SUBSCRIBE_SEND = WX_API_BASE + '/message/subscribe/send'
WX_TOKEN_URL = WX_API_BASE + '/token'

# ===== 订阅消息模板ID（需要在微信公众平台配置） =====
# 预设模板，生产环境应替换为实际审核通过的模板ID
TEMPLATES = {
    # 睡眠改善建议（At 类，用户需订阅）
    'sleep_tip': '',  # 实际使用时填入审核通过的模板ID
    # 异常提醒
    'sleep_alert': '',
    # 每日简报
    'daily_brief': '',
}

# ===== 推送时段配置 =====
PUSH_TIME_MORNING = (7, 8)    # 早上 7-8 点：昨日回顾
PUSH_TIME_EVENING = (21, 22)  # 晚上 9-10 点：睡前关怀

# 同一用户同类型推送冷却时间（小时）
COOLDOWN_HOURS = {
    'morning_recap': 20,    # 早上回顾 → 次日才有
    'evening_care': 4,      # 晚间关怀 → 不重复推送即可
    'alert': 12,            # 异常提醒 → 半天内不重复
    'weekly': 160,          # 周报 → 接近7天
}


def _load_config():
    """加载微信推送配置"""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        _log.warning('[Push] Failed to load config: %s', e)
    return {}


def _get_access_token():
    """获取微信 access_token（自动缓存 + 刷新）

    Returns: str or None
    """
    global _ACCESS_TOKEN, _TOKEN_EXPIRES_AT

    # 缓存有效直接返回
    if _ACCESS_TOKEN and time.time() < _TOKEN_EXPIRES_AT - 300:
        return _ACCESS_TOKEN

    config = _load_config()
    appid = config.get('appid', os.environ.get('WX_APPID', ''))
    secret = config.get('secret', os.environ.get('WX_SECRET', ''))

    if not appid or not secret:
        _log.warning('[Push] WX appid or secret not configured')
        return None

    url = f'{WX_TOKEN_URL}?grant_type=client_credential&appid={appid}&secret={secret}'
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        if 'access_token' in data:
            _ACCESS_TOKEN = data['access_token']
            _TOKEN_EXPIRES_AT = time.time() + data.get('expires_in', 7200)
            _log.info('[Push] Access token refreshed, expires in %ds', data.get('expires_in', 7200))
            return _ACCESS_TOKEN
        else:
            _log.warning('[Push] Token refresh failed: %s', data.get('errmsg', 'unknown'))
            return None
    except Exception as e:
        _log.warning('[Push] Token refresh error: %s', e)
        return None


def send_subscribe_message(openid, template_id, data_dict, page=''):
    """发送微信订阅消息

    Args:
        openid: 用户openid
        template_id: 模板ID
        data_dict: 模板数据 dict，键为模板字段名，值为内容字符串
                   自动包装为微信要求的 { "thing1": { "value": "xxx" } } 格式
        page: 点击跳转页面路径（可选）

    Returns:
        dict: { 'success': bool, 'errcode': int, 'errmsg': str }
    """
    token = _get_access_token()
    if not token:
        return {'success': False, 'errcode': -1, 'errmsg': 'No access token'}

    if not template_id:
        _log.warning('[Push] No template_id configured for this push type')
        return {'success': False, 'errcode': -2, 'errmsg': 'No template_id'}

    # 构造消息体
    msg_data = {}
    for key, value in data_dict.items():
        # 微信模板消息要求字段名称为 thing1/thing2/... number1/number2/... 等
        # 自动识别类型并包装
        if isinstance(value, str):
            # 截断到20字以内（微信限制）
            truncated = value[:20] if len(value) > 20 else value
            msg_data[key] = {'value': truncated}
        elif isinstance(value, (int, float)):
            msg_data[key] = {'value': str(value)}
        else:
            msg_data[key] = {'value': str(value)[:20]}

    body = {
        'touser': openid,
        'template_id': template_id,
        'data': msg_data,
    }
    if page:
        body['page'] = page

    url = f'{WX_SUBSCRIBE_SEND}?access_token={token}'
    payload = json.dumps(body, ensure_ascii=False).encode('utf-8')

    try:
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode('utf-8'))

        if result.get('errcode') == 0:
            _log.info('[Push] Sent to %s via template %s', openid[:8], template_id[:8])
            return {'success': True, 'errcode': 0, 'errmsg': 'ok'}
        else:
            _log.warning('[Push] Send failed for %s: errcode=%d errmsg=%s',
                         openid[:8], result.get('errcode'), result.get('errmsg', ''))
            return {
                'success': False,
                'errcode': result.get('errcode', -1),
                'errmsg': result.get('errmsg', 'unknown'),
            }
    except Exception as e:
        _log.warning('[Push] Send error for %s: %s', openid[:8], e)
        return {'success': False, 'errcode': -3, 'errmsg': str(e)}


# ===== 推送内容生成 =====

def _get_username(profile):
    """从profile获取用户名"""
    user_info = profile.get('user_info', {})
    if isinstance(user_info, dict):
        return user_info.get('nickname', '') or profile.get('nickname', '')
    return profile.get('nickname', '')


def _get_user_preferred_time(profile):
    """获取用户偏好推送时间"""
    prefs = profile.get('preferences', {})
    if isinstance(prefs, dict):
        return prefs.get('push_time', 'auto')
    return 'auto'


def _get_latest_score(profile):
    """获取最新评分"""
    history = profile.get('history', [])
    if not history:
        return None
    latest = history[-1]
    if isinstance(latest, dict):
        return latest.get('wm_score') or latest.get('score') or None
    return None


def _get_trend_text(profile):
    """生成趋势描述"""
    history = profile.get('history', [])
    if len(history) < 2:
        return None

    scores = []
    for h in history[-7:]:  # 最近7条
        if isinstance(h, dict):
            s = h.get('wm_score') or h.get('score') or 0
            scores.append(s)

    if len(scores) < 2:
        return None

    recent_3 = scores[-3:]
    avg_recent = sum(recent_3) / len(recent_3)
    older = scores[:-3]
    avg_older = sum(older) / len(older) if older else avg_recent

    diff = avg_recent - avg_older
    if diff > 8:
        return '趋势向好', 'up'
    elif diff < -8:
        return '持续下降', 'down'
    elif avg_recent >= 75:
        return '稳定良好', 'stable_good'
    elif avg_recent < 55:
        return '需要关注', 'attention'
    return '基本稳定', 'stable'


def generate_morning_content(profile, prediction=None):
    """生成早上推送内容（7-8点）

    Args:
        profile: 用户画像 dict
        prediction: 预测结果 dict 或 None

    Returns:
        (title, content, push_type) or None
    """
    username = _get_username(profile) or '用户'
    latest_score = _get_latest_score(profile)
    trend_text, trend_dir = _get_trend_text(profile) or ('', '')

    title = f'☀️ 早上好，{username}'

    if latest_score is not None:
        if latest_score >= 80:
            content = f'昨晚睡眠评分 {latest_score} 分，休息得不错！'
        elif latest_score >= 65:
            content = f'昨晚睡眠评分 {latest_score} 分，整体还可以。'
        elif latest_score >= 50:
            content = f'昨晚睡眠评分 {latest_score} 分，还有一些改善空间。'
        else:
            content = f'昨晚睡眠评分 {latest_score} 分，需要关注一下睡眠质量。'
    else:
        content = '昨晚没有记录睡眠数据，今晚睡前可以试试记录一下哦。'

    # 叠加趋势
    if trend_dir == 'up':
        content += ' 最近睡眠持续改善，继续保持！'
    elif trend_dir == 'down':
        content += ' 最近趋势有所下降，建议关注一下作息和睡前的状态。'

    # 叠加预测
    if prediction and prediction.get('predicted_score', 0) < 55:
        content += ' 今晚预测可能偏低，建议提前放松准备入睡。'

    return title, content, 'morning_recap'


def generate_evening_content(profile, prediction=None):
    """生成晚间推送内容（21-22点）

    Returns:
        (title, content, push_type) or None
    """
    username = _get_username(profile) or '用户'
    latest_score = _get_latest_score(profile)
    trend_text, trend_dir = _get_trend_text(profile) or ('', '')

    title = f'🌙 晚安，{username}'

    # 根据趋势决定晚间关怀内容
    if trend_dir == 'down' or (latest_score and latest_score < 55):
        content = '最近睡眠质量有所下降，今晚可以试试做3分钟深呼吸放松一下，或者听一段引导冥想。'
    elif latest_score and latest_score >= 80:
        content = '昨晚睡得很好，今晚保持这个节奏就好！如果睡前想聊聊今天的感受，我一直在。'
    else:
        content = '今晚准备休息了吗？放松心情，不要想太多，好睡眠从放下手机开始。'

    # 叠加预测
    if prediction:
        pred = prediction.get('predicted_score', 50)
        if pred < 55:
            concern = prediction.get('key_concern', '')
            if concern == 'latency':
                content = '根据近期数据预测，今晚入睡可能需要一些时间。建议提前30分钟放下手机，做10分钟轻柔拉伸。'
            elif concern == 'awake':
                content = '根据近期数据预测，今晚可能会中途醒来。如果醒了不要看时间，保持放松继续睡。'
            else:
                content = '根据近期数据，今晚可能需要更多放松准备。试试泡脚或听一段白噪音。'

    return title, content, 'evening_care'


def generate_alert_content(profile, alert_type='score_drop', extra=None):
    """生成异常提醒推送

    Args:
        alert_type: 'score_drop' | 'low_score' | 'inactive'
        extra: 额外数据 dict

    Returns:
        (title, content, push_type) or None
    """
    score = _get_latest_score(profile)

    if alert_type == 'score_drop' and extra:
        diff = extra.get('diff', 0)
        title = '⚠️ 睡眠评分下降提醒'
        content = f'你的睡眠评分较前日下降 {abs(diff)} 分。'
        if diff < -15:
            content += '下降幅度较大，建议回顾一下今天是否有压力事件或作息变化。'
        else:
            content += '偶尔波动是正常的，今晚注意放松就好。'
        return title, content, 'alert'

    if alert_type == 'low_score':
        title = '💤 睡眠质量提醒'
        content = f'近期睡眠评分偏低（{score}分），如果连续如此，建议调整作息或咨询专业人士。'
        return title, content, 'alert'

    return None


def generate_push_content(profile, strategy_name='', strategy_desc='', prediction=None):
    """智能推送内容生成（综合入口）

    根据当前时段 + 用户画像 + 预测结果生成推送文案

    Args:
        profile: 用户画像
        strategy_name: scheduler 选择的策略名
        strategy_desc: 策略描述
        prediction: 预测结果

    Returns:
        (title, content, push_type) or None
    """
    now = datetime.now()
    hour = now.hour

    # 判断时段
    if PUSH_TIME_MORNING[0] <= hour < PUSH_TIME_MORNING[1]:
        return generate_morning_content(profile, prediction)
    elif PUSH_TIME_EVENING[0] <= hour < PUSH_TIME_EVENING[1]:
        return generate_evening_content(profile, prediction)
    else:
        # 非标准时段 → 异常提醒模式
        if strategy_name and strategy_name in ('wind_down', 'deep_breathing', 'sleep_hygiene'):
            # 策略驱动的内容
            username = _get_username(profile) or '用户'
            title = f'🌙 {username}，有个小建议'
            content = strategy_desc or '今晚试试放松一下吧。'
            return title, content, 'care'
        return None


def get_cooldown_hours(push_type):
    """获取指定推送类型的冷却时间"""
    return COOLDOWN_HOURS.get(push_type, 20)


# ===== 自测 =====
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    # 测试推送内容生成
    test_profile = {
        'nickname': '测试用户',
        'history': [
            {'date': '2026-04-30', 'wm_score': 72},
            {'date': '2026-05-01', 'wm_score': 65},
            {'date': '2026-05-02', 'wm_score': 58},
        ],
        'user_info': {'nickname': '小明'},
    }

    print('=== Morning content ===')
    r = generate_morning_content(test_profile)
    if r:
        print(f'  Title: {r[0]}')
        print(f'  Content: {r[1]}')
        print(f'  Type: {r[2]}')

    print()
    print('=== Evening content ===')
    test_pred = {'predicted_score': 52, 'confidence': 'medium', 'key_concern': 'latency'}
    r = generate_evening_content(test_profile, test_pred)
    if r:
        print(f'  Title: {r[0]}')
        print(f'  Content: {r[1]}')
        print(f'  Type: {r[2]}')

    print()
    print('=== Config check ===')
    print(f'  Config path: {CONFIG_PATH}')
    print(f'  Config exists: {os.path.exists(CONFIG_PATH)}')
    print('OK')
