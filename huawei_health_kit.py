"""
huawei_health_kit.py — 华为Health Kit REST API客户端

从华为运动健康拉取睡眠数据 → 注入POMDP

使用流程：
  1. 用户手机授权 → 得到授权码
  2. 兑换access token
  3. 拉取睡眠数据
  4. 注入POMDP

目前先实现【手动授权获取token】模式，后续再自动化
"""
import requests
import json
import time
import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

# ============================
# 配置 - 你的华为Health Kit凭据
# ============================
CLIENT_ID = "6917604713668497296"
CLIENT_SECRET = "95acd3d3eba128cb0700d3b2edaddabe1645c11254170a152b7b1faa7107c1b8"
REDIRECT_URI = "https://localhost/huawei/callback"  # 授权回调，需要和开发者后台配置一致
AUTH_STATE = "aisleepgen_v1"

# 华为Health Kit API端点
AUTH_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/authorize"
TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
HEALTH_API_BASE = "https://health-api.cloud.huawei.com"

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(PROJECT_ROOT, "data", "huawei_token.json")

# ============================
# Token管理
# ============================

class TokenManager:
    """管理access_token和refresh_token的持久化"""
    
    def __init__(self, token_path=TOKEN_FILE):
        self.token_path = token_path
        os.makedirs(os.path.dirname(token_path), exist_ok=True)
    
    def load(self) -> Optional[dict]:
        if os.path.exists(self.token_path):
            with open(self.token_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
    
    def save(self, token_data: dict):
        with open(self.token_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=2, ensure_ascii=False)
        print(f"[Huawei] Token saved to {self.token_path}")
    
    def is_valid(self, token_data: dict) -> bool:
        """检查access_token是否有效（未过期）"""
        expires_at = token_data.get("expires_at", 0)
        return time.time() < expires_at - 60  # 提前60秒认为过期


# ============================
# 授权流程
# ============================

def get_authorization_url() -> str:
    """Step 1: 生成授权URL，用户在手机上打开授权
    
    用户打开这个URL → 登录华为账号 → 授权Health Kit → 跳转到REDIRECT_URI
    """
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": "https://www.huawei.com/healthkit/sleep.read",
        "state": AUTH_STATE,
    }
    query = "&".join([f"{k}={v}" for k, v in params.items()])
    url = f"{AUTH_URL}?{query}"
    return url


def exchange_code_for_token(auth_code: str) -> dict:
    """Step 2: 用授权码兑换access_token"""
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=10)
    token_data = resp.json()
    
    if "access_token" in token_data:
        # 计算过期时间
        expires_in = token_data.get("expires_in", 3600)
        token_data["expires_at"] = time.time() + expires_in
        token_data["obtained_at"] = datetime.now().isoformat()
        TokenManager().save(token_data)
        print("[Huawei] Token obtained successfully!")
    else:
        print(f"[Huawei] Failed to get token: {token_data}")
    
    return token_data


def refresh_token() -> Optional[dict]:
    """Step 2b: 刷新token（access_token过期后用refresh_token续命）"""
    tm = TokenManager()
    saved = tm.load()
    if not saved or "refresh_token" not in saved:
        print("[Huawei] No refresh_token available, need re-auth")
        return None
    
    data = {
        "grant_type": "refresh_token",
        "refresh_token": saved["refresh_token"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=10)
    token_data = resp.json()
    
    if "access_token" in token_data:
        expires_in = token_data.get("expires_in", 3600)
        token_data["expires_at"] = time.time() + expires_in
        token_data["obtained_at"] = datetime.now().isoformat()
        # 保留refresh_token（如果返回了新的则覆盖）
        if "refresh_token" not in token_data and "refresh_token" in saved:
            token_data["refresh_token"] = saved["refresh_token"]
        tm.save(token_data)
        print("[Huawei] Token refreshed!")
    else:
        print(f"[Huawei] Refresh failed: {token_data}")
        return None
    
    return token_data


def get_valid_token() -> Optional[str]:
    """获取可用的access_token（自动刷新）"""
    tm = TokenManager()
    saved = tm.load()
    
    if saved and tm.is_valid(saved):
        return saved["access_token"]
    
    if saved and "refresh_token" in saved:
        new = refresh_token()
        if new:
            return new["access_token"]
    
    print("[Huawei] No valid token available. Need user authorization.")
    return None


# ============================
# 数据拉取
# ============================

def fetch_sleep_data(access_token: str, date: str = None) -> dict:
    """拉取指定日期的睡眠数据
    
    Args:
        access_token: OAuth access_token
        date: 日期 YYYYMMDD 格式，默认为昨天
    
    Returns:
        dict: 睡眠数据
    """
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    
    start_time = f"{date}000000"
    end_time = f"{date}235959"
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    # 获取睡眠记录
    url = f"{HEALTH_API_BASE}/healthkit/v1/sleep/record"
    params = {
        "startTime": start_time,
        "endTime": end_time,
    }
    
    print(f"[Huawei] Fetching sleep data for {date}...")
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    
    if resp.status_code == 200:
        data = resp.json()
        print(f"[Huawei] Sleep data received!")
        return data
    else:
        print(f"[Huawei] API error: {resp.status_code} - {resp.text}")
        return {"error": resp.text, "status_code": resp.status_code}


def fetch_heart_rate(access_token: str, date: str = None) -> dict:
    """拉取心率数据"""
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"{HEALTH_API_BASE}/healthkit/v1/heartRate/record"
    params = {
        "startTime": f"{date}000000",
        "endTime": f"{date}235959",
    }
    
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text}


def fetch_hrv(access_token: str, date: str = None) -> dict:
    """拉取HRV数据"""
    if date is None:
        date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    
    url = f"{HEALTH_API_BASE}/healthkit/v1/hrv/record"
    params = {
        "startTime": f"{date}000000",
        "endTime": f"{date}235959",
    }
    
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    if resp.status_code == 200:
        return resp.json()
    return {"error": resp.text}


# ============================
# 数据→POMDP转换
# ============================

def format_sleep_for_pomdp(sleep_data: dict, hr_data: dict = None, hrv_data: dict = None) -> dict:
    """将华为Health Kit的睡眠数据格式化为POMDP观测
    
    Returns:
        dict: 包含 text 和 score 的POMDP观测
    """
    records = sleep_data.get("sleepRecords", [])
    if not records:
        return {"text": "", "score": 0, "available": False}
    
    record = records[0]  # 取第一条
    
    # 提取字段（华为API字段名可能不同，需要实测后调整）
    deep_sleep = record.get("deepSleepMinutes", record.get("deepSleep", 0))
    light_sleep = record.get("lightSleepMinutes", record.get("lightSleep", 0))
    rem = record.get("remMinutes", record.get("remSleep", 0))
    awake = record.get("awakeMinutes", record.get("awakeTime", 0))
    total = record.get("totalSleepMinutes", deep_sleep + light_sleep + rem)
    hr_avg = record.get("heartRateAvg", record.get("avgHeartRate", 0))
    hrv_avg = None
    if hrv_data:
        hrv_records = hrv_data.get("hrvRecords", [])
        if hrv_records:
            hrv_avg = hrv_records[0].get("avg", 0)
    
    # 计算评分调整
    score_adj = 0
    if total >= 420:  # 7h+
        score_adj += 2
    if deep_sleep >= 120:  # 2h+
        score_adj += 3
    if deep_sleep >= 180:  # 3h+
        score_adj += 2
    if awake <= 30:
        score_adj += 2
    elif awake >= 60:
        score_adj -= 3
    if hr_avg and 55 <= hr_avg <= 65:
        score_adj += 1
    if hrv_avg and hrv_avg > 30:
        score_adj += 2
    
    # 构建文本
    parts = ["[手环传感器]"]
    parts.append(f"睡眠{total}分钟")
    parts.append(f"深睡{deep_sleep}分钟")
    parts.append(f"浅睡{light_sleep}分钟")
    parts.append(f"REM{rem}分钟")
    if awake:
        parts.append(f"清醒{awake}分钟")
    if hr_avg:
        parts.append(f"心率{hr_avg}bpm")
    if hrv_avg:
        parts.append(f"HRV{hrv_avg}ms")
    
    text = ", ".join(parts)
    
    return {
        "text": text,
        "score": score_adj,
        "available": True,
        "raw": {
            "total_sleep_min": total,
            "deep_sleep_min": deep_sleep,
            "light_sleep_min": light_sleep,
            "rem_min": rem,
            "awake_min": awake,
            "heart_rate_avg": hr_avg,
            "hrv_avg": hrv_avg,
        }
    }


def inject_sleep_to_pomdp(openid: str = "default"):
    """完整流程：拉取数据 → 格式化 → 注入POMDP"""
    token = get_valid_token()
    if not token:
        print("[Huawei] Cannot inject: no valid token")
        print("[Huawei] Open this URL in browser to authorize:")
        print(get_authorization_url())
        return {"status": "need_auth"}
    
    # 拉取数据
    sleep_data = fetch_sleep_data(token)
    hr_data = fetch_heart_rate(token)
    hrv_data = fetch_hrv(token) if hasattr(fetch_hrv, '__call__') else None
    
    # 格式化
    obs = format_sleep_for_pomdp(sleep_data, hr_data, hrv_data)
    if not obs.get("available"):
        print("[Huawei] No sleep data available for today")
        return {"status": "no_data"}
    
    # 注入POMDP
    try:
        from pomdp_learner import get_engine
        engine = get_engine()
        belief = engine.observe(
            openid=openid,
            text=obs["text"],
            score=obs["score"],
            effect="positive" if obs["score"] > 0 else "neutral"
        )
        
        result = {
            "status": "injected",
            "text": obs["text"],
            "score_adjustment": obs["score"],
            "new_belief_score": belief.get("expected_score"),
        }
        print(f"[Huawei] POMDP injection OK: score_adj={obs['score']}, new_belief={belief.get('expected_score')}")
        return result
    except ImportError:
        print("[Huawei] pomdp_learner not available, data prepared")
        return {"status": "data_ready", **obs}


def set_auth_code(code: str):
    """手动设置授权码（用户在授权页面拿到code后调用）"""
    result = exchange_code_for_token(code)
    return result


# ============================
# 手动授权指引
# ============================

def print_auth_instructions():
    """打印完整的授权流程指引"""
    print("=" * 60)
    print("华为Health Kit 授权指引")
    print("=" * 60)
    print()
    print("Step 1: 打开下面的链接 → 登录华为账号 → 授权")
    print()
    print("  " + get_authorization_url())
    print()
    print("Step 2: 授权成功后，浏览器地址栏会跳转到类似：")
    print("  https://localhost/huawei/callback?code=XXX&state=...")
    print()
    print("Step 3: 复制 code=后面的那串参数，运行：")
    print("  python -c \"from huawei_health_kit import set_auth_code; set_auth_code('你的code')\"")
    print()
    print("Step 4: 自动拉取并注入POMDP：")
    print("  python -c \"from huawei_health_kit import inject_sleep_to_pomdp; inject_sleep_to_pomdp()\"")
    print("=" * 60)


# ============================
# 测试入口
# ============================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        print_auth_instructions()
    elif len(sys.argv) > 2 and sys.argv[1] == "--code":
        set_auth_code(sys.argv[2])
    elif len(sys.argv) > 1 and sys.argv[1] == "--inject":
        inject_sleep_to_pomdp()
    else:
        print("Usage:")
        print("  python huawei_health_kit.py --auth           # 打印授权链接")
        print("  python huawei_health_kit.py --code <CODE>   # 用授权码兑换token")
        print("  python huawei_health_kit.py --inject         # 拉取数据并注入POMDP")
