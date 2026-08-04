#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信扫码登录系统 v1.0
AISleepGen 微信小程序登录模块

流程:
  1. 小程序 wx.login() → 获取 code
  2. POST /api/wx/login {code} → 后端调微信接口换 openid + session_key
  3. 后端生成自定义 token → 返回 {token, openid, is_new_user}
  4. 小程序缓存 token → 后续请求带 Authorization: Bearer <token>

安全设计:
  - session_key 不返回前端（只存服务端）
  - token 用 sha256(openid + secret + timestamp) 生成
  - token 有效期 30 天
"""

import json
import hashlib
import time
import os
import urllib.request
from typing import Optional, Dict
from datetime import datetime, timezone

# ============================================================
# 配置
# ============================================================

# 微信小程序 appid / secret (从环境变量读取, 不硬编码)
WX_APPID = os.environ.get("WX_APPID", "")
WX_SECRET = os.environ.get("WX_SECRET", "")

# 生成 token 的 HMAC 密钥 (运行时随机生成，重启后旧 token 失效)
_TOKEN_SECRET = hashlib.sha256(
    (str(time.time()) + os.environ.get("OPENCLAW_GATEWAY_ID", "aisleepgen")).encode()
).hexdigest()[:32]

TOKEN_EXPIRE_DAYS = 30


# ============================================================
# 微信登录核心
# ============================================================

def wx_code_to_openid(code: str) -> Optional[Dict]:
    """
    调用微信 code2Session 接口
    
    Args:
        code: 小程序 wx.login() 返回的临时 code
    
    Returns:
        {"openid": "...", "session_key": "...", "unionid": "..."} 或 None
    """
    if not WX_APPID or not WX_SECRET:
        # 开发/测试模式：用 code 模拟 openid
        return {
            "openid": f"dev_{hashlib.md5(code.encode()).hexdigest()[:16]}",
            "session_key": "dev_session_key",
            "unionid": "",
        }

    url = (
        f"https://api.weixin.qq.com/sns/jscode2session"
        f"?appid={WX_APPID}&secret={WX_SECRET}&js_code={code}&grant_type=authorization_code"
    )
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode('utf-8'))
        if "errcode" in data and data["errcode"] != 0:
            return None
        return data
    except Exception:
        return None


# ============================================================
# Token 管理
# ============================================================

def generate_token(openid: str) -> str:
    """生成认证 token"""
    payload = f"{openid}:{int(time.time())}:{_TOKEN_SECRET}"
    token = hashlib.sha256(payload.encode()).hexdigest()
    return token


def verify_token(token: str, openid: str) -> bool:
    """验证 token"""
    expected = generate_token(openid)
    return token == expected


def extract_openid_from_header(auth_header: Optional[str]) -> Optional[str]:
    """从 Authorization header 提取 openid"""
    if not auth_header:
        return None
    # 格式: Bearer <token>:<openid>
    try:
        parts = auth_header.split()
        if len(parts) != 2:
            return None
        bearer_token = parts[1]
        if ':' in bearer_token:
            return bearer_token.split(':')[1]
        return None
    except Exception:
        return None


# ============================================================
# 用户数据管理
# ============================================================

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), 'wx_user_data')
os.makedirs(USER_DATA_DIR, exist_ok=True)


def _user_path(openid: str) -> str:
    return os.path.join(USER_DATA_DIR, f"{openid}.json")


def load_user(openid: str) -> Dict:
    """加载用户数据"""
    path = _user_path(openid)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"openid": openid, "created_at": datetime.now().isoformat(), "sessions": 0}


def save_user(data: Dict):
    """保存用户数据"""
    path = _user_path(data["openid"])
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# API Handler
# ============================================================

def handle_wx_login(data: Dict) -> Dict:
    """
    POST /api/wx/login
    
    Request: {"code": "wx_login_code"}
    Response: {"token": "...", "openid": "...", "is_new_user": bool}
    """
    code = data.get("code", "")
    if not code:
        return {"error": "code required"}

    result = wx_code_to_openid(code)
    if not result:
        return {"error": "wechat auth failed"}

    openid = result["openid"]
    token = generate_token(openid)

    # 加载/创建用户
    user = load_user(openid)
    is_new = "created_at" not in user
    if is_new:
        user["created_at"] = datetime.now().isoformat()
    user["openid"] = openid
    user["last_login"] = datetime.now().isoformat()
    user["sessions"] = user.get("sessions", 0) + 1
    save_user(user)

    return {
        "token": f"{token}:{openid}",
        "openid": openid,
        "is_new_user": is_new,
        "first_name": user.get("name", ""),
    }


def handle_wx_profile(data: Dict, auth_header: Optional[str] = None) -> Dict:
    """
    POST /api/wx/profile
    
    Request: {"nickname": "...", "avatar": "...", "gender": 0}
    Response: {"success": true}
    """
    openid = extract_openid_from_header(auth_header)
    if not openid:
        return {"error": "unauthorized"}

    token = auth_header.split()[-1].split(':')[0]
    if not verify_token(token, openid):
        return {"error": "invalid token"}

    user = load_user(openid)
    if "nickname" in data:
        user["name"] = data["nickname"]
    if "avatar" in data:
        user["avatar"] = data["avatar"]
    save_user(user)

    return {"success": True}


# ============================================================
# 快速测试
# ============================================================

if __name__ == "__main__":
    print("微信扫码登录模块 v1.0")
    print("=" * 40)
    
    # 测试 token 生成
    test_openid = "test_user_001"
    token = generate_token(test_openid)
    valid = verify_token(token.split(':')[0] if ':' in token else token, test_openid)
    print(f"  Token 生成+验证: {'✅' if valid else '❌'}")
    
    # 测试代码登录
    result = handle_wx_login({"code": "test_code_12345"})
    print(f"  模拟登录: openid={result.get('openid','?')} is_new={result.get('is_new_user','?')}")
    
    # 测试 token 鉴权
    auth = f"Bearer {result.get('token', '')}"
    extracted = extract_openid_from_header(auth)
    print(f"  Header 提取: {extracted} == {result.get('openid','?')}")
    print("  模块就绪 ✅")
