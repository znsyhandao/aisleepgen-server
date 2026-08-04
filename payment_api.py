# -*- coding: utf-8 -*-
"""
payment_api.py — 微信支付接入模块 v1.0
为 AISleepGen 微信小程序提供统一下单、支付回调、会员升级。

启动方式: 在 deepseek_proxy.py 中 import 本模块

依赖: requests (用于微信支付 API 调用)
      db_sqlite.py (日志持久化)

环境变量:
  WXPAY_APPID:      小程序 AppID
  WXPAY_MCHID:      商户号
  WXPAY_API_KEY:    支付 API Key
  WXPAY_NOTIFY_URL: 支付回调 URL（公网可访问）
"""
import json, os, time, hashlib, hmac, uuid, requests, threading
from datetime import datetime
from xml.etree import ElementTree

# ── 配置 ──
WXPAY_APPID = os.environ.get("WXPAY_APPID", "")
WXPAY_MCHID = os.environ.get("WXPAY_MCHID", "")
WXPAY_API_KEY = os.environ.get("WXPAY_API_KEY", "")
WXPAY_NOTIFY_URL = os.environ.get("WXPAY_NOTIFY_URL", "")
PAY_ENABLED = bool(WXPAY_APPID and WXPAY_MCHID and WXPAY_API_KEY)

# ── 会员定价 ──
MEMBERSHIP_PLANS = {
    "pro_monthly": {"name": "Pro月度", "price_fen": 1980, "days": 30, "level": "pro"},
    "pro_quarterly": {"name": "Pro季度", "price_fen": 4980, "days": 90, "level": "pro"},
    "pro_yearly": {"name": "Pro年度", "price_fen": 15800, "days": 365, "level": "pro"},
    "unlimited_monthly": {"name": "无限月度", "price_fen": 3980, "days": 30, "level": "unlimited"},
}

# ── 计费日志（线程安全） ──
_billing_lock = threading.Lock()
_billing_log = []

def log_billing(openid, action, amount_fen=0, plan="", out_trade_no="", result="ok"):
    """记录一条计费日志"""
    entry = {
        "time": datetime.now().isoformat(),
        "openid": openid,
        "action": action,
        "amount_fen": amount_fen,
        "plan": plan,
        "out_trade_no": out_trade_no,
        "result": result
    }
    with _billing_lock:
        _billing_log.append(entry)
        # 保留最近 10000 条
        if len(_billing_log) > 10000:
            _billing_log[:] = _billing_log[-5000:]
    # 同时写文件（持久化）
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "billing_log.json")
        existing = []
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)
        existing.append(entry)
        existing = existing[-10000:]
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("[pay] 计费日志写入失败: %s" % str(e)[:60])

def get_billing_summary(days=30):
    """获取计费汇总（用于看板）"""
    cutoff = time.time() - days * 86400
    total_users = set()
    total_revenue = 0
    recent = []
    for entry in _billing_log:
        try:
            et = datetime.fromisoformat(entry['time']).timestamp()
            if et >= cutoff and entry['result'] == 'ok':
                if entry['action'] == 'pay':
                    total_revenue += entry.get('amount_fen', 0)
                    total_users.add(entry['openid'])
                recent.append(entry)
        except Exception:
            pass
    return {
        "period_days": days,
        "total_revenue_yuan": round(total_revenue / 100, 2),
        "paying_users": len(total_users),
        "total_orders": len([e for e in recent if e['action'] == 'pay']),
        "recent_10": recent[-10:]
    }

# ── 微信支付 API ──

def _md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest().upper()

def _gen_nonce():
    return uuid.uuid4().hex[:16]

def _build_xml(params):
    """构建微信支付请求 XML"""
    root = ElementTree.Element("xml")
    for k, v in params.items():
        child = ElementTree.SubElement(root, k)
        child.text = str(v)
    # 排序后生成签名
    sorted_keys = sorted(params.keys())
    sign_str = "&".join(["%s=%s" % (k, params[k]) for k in sorted_keys])
    sign_str += "&key=%s" % WXPAY_API_KEY
    sign = _md5(sign_str)
    sign_el = ElementTree.SubElement(root, "sign")
    sign_el.text = sign
    return ElementTree.tostring(root, encoding='utf-8')

def _parse_xml(xml_bytes):
    """解析微信支付返回 XML"""
    root = ElementTree.fromstring(xml_bytes)
    result = {}
    for child in root:
        result[child.tag] = child.text
    return result

def unified_order(openid, plan_key, ip="127.0.0.1"):
    """
    统一下单
    plan_key: MEMBERSHIP_PLANS 的 key（如 pro_monthly）
    返回: {success, prepay_id, nonce_str, err_code, ...}
    """
    if not PAY_ENABLED:
        return {"success": False, "error": "支付未配置（WXPAY_APPID/MCHID/API_KEY 未设置）"}

    plan = MEMBERSHIP_PLANS.get(plan_key)
    if not plan:
        return {"success": False, "error": "不存在的会员方案: %s" % plan_key}

    out_trade_no = "%s%d" % (datetime.now().strftime('%Y%m%d%H%M%S'), int(time.time() * 1000) % 10000)
    nonce = _gen_nonce()

    params = {
        "appid": WXPAY_APPID,
        "mch_id": WXPAY_MCHID,
        "nonce_str": nonce,
        "body": "AISleepGen %s" % plan['name'],
        "out_trade_no": out_trade_no,
        "total_fee": str(plan['price_fen']),
        "spbill_create_ip": ip,
        "notify_url": WXPAY_NOTIFY_URL,
        "trade_type": "JSAPI",
        "openid": openid
    }

    try:
        xml_body = _build_xml(params)
        r = requests.post("https://api.mch.weixin.qq.com/pay/unifiedorder",
                          data=xml_body, headers={"Content-Type": "text/xml"},
                          timeout=10)
        if r.status_code != 200:
            return {"success": False, "error": "微信支付接口返回 %d" % r.status_code}

        resp = _parse_xml(r.content)
        if resp.get("return_code") == "SUCCESS" and resp.get("result_code") == "SUCCESS":
            prepay_id = resp.get("prepay_id", "")
            # 生成小程序端调起支付需要的参数
            pay_params = {
                "appId": WXPAY_APPID,
                "timeStamp": str(int(time.time())),
                "nonceStr": _gen_nonce(),
                "package": "prepay_id=%s" % prepay_id,
                "signType": "MD5"
            }
            # 二次签名
            sign_str = "&".join(["%s=%s" % (k, pay_params[k]) for k in sorted(pay_params.keys())])
            sign_str += "&key=%s" % WXPAY_API_KEY
            pay_params["paySign"] = _md5(sign_str)

            log_billing(openid, "unified_order", plan['price_fen'], plan_key, out_trade_no)

            return {
                "success": True,
                "prepay_id": prepay_id,
                "out_trade_no": out_trade_no,
                "pay_params": pay_params,
                "plan_name": plan['name'],
                "price_yuan": plan['price_fen'] / 100
            }
        else:
            err = resp.get("err_code_des", resp.get("return_msg", "未知错误"))
            log_billing(openid, "unified_order_fail", plan['price_fen'], plan_key, out_trade_no, err[:60])
            return {"success": False, "error": err}

    except Exception as e:
        return {"success": False, "error": "支付请求异常: %s" % str(e)[:60]}

def verify_notification(xml_bytes):
    """
    验证支付回调通知
    返回: {success, openid, out_trade_no, total_fee}
    """
    try:
        resp = _parse_xml(xml_bytes)
        # 验证签名
        received_sign = resp.pop("sign", "")
        sorted_keys = sorted(resp.keys())
        sign_str = "&".join(["%s=%s" % (k, resp[k]) for k in sorted_keys])
        sign_str += "&key=%s" % WXPAY_API_KEY
        calculated_sign = _md5(sign_str)
        resp["sign"] = received_sign  # 放回去

        if calculated_sign != received_sign:
            return {"success": False, "error": "签名验证失败"}

        if resp.get("return_code") != "SUCCESS":
            return {"success": False, "error": "return_code != SUCCESS"}

        if resp.get("result_code") != "SUCCESS":
            return {"success": False, "error": "result_code != SUCCESS"}

        openid = resp.get("openid", "")
        out_trade_no = resp.get("out_trade_no", "")
        total_fee = int(resp.get("total_fee", 0))

        log_billing(openid, "pay", total_fee, "", out_trade_no)
        print("[pay] 支付成功: openid=%s out_trade_no=%s fee=%.2f" % (
            openid[:8], out_trade_no, total_fee / 100))

        return {
            "success": True,
            "openid": openid,
            "out_trade_no": out_trade_no,
            "total_fee_fen": total_fee
        }

    except Exception as e:
        return {"success": False, "error": "通知解析失败: %s" % str(e)[:60]}

def query_order(out_trade_no):
    """查询订单状态"""
    if not PAY_ENABLED:
        return {"success": False, "error": "支付未配置"}
    params = {
        "appid": WXPAY_APPID,
        "mch_id": WXPAY_MCHID,
        "out_trade_no": out_trade_no,
        "nonce_str": _gen_nonce()
    }
    try:
        xml_body = _build_xml(params)
        r = requests.post("https://api.mch.weixin.qq.com/pay/orderquery",
                          data=xml_body, headers={"Content-Type": "text/xml"},
                          timeout=10)
        if r.status_code == 200:
            resp = _parse_xml(r.content)
            return {
                "success": resp.get("return_code") == "SUCCESS",
                "trade_state": resp.get("trade_state", ""),
                "total_fee": resp.get("total_fee", 0),
                "transaction_id": resp.get("transaction_id", "")
            }
        return {"success": False, "error": "HTTP %d" % r.status_code}
    except Exception as e:
        return {"success": False, "error": str(e)[:60]}

# ── 导出 ──
__all__ = ["unified_order", "verify_notification", "query_order",
           "get_billing_summary", "MEMBERSHIP_PLANS", "PAY_ENABLED"]
