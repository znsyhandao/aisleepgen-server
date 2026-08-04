from hashlib import sha256
import xml.etree.ElementTree as ET
from fastapi import Request

from sqlalchemy.orm import Session
from models import Subscription, PaymentRecord
from database import get_db
from fastapi import HTTPException
from starlette import status
from redis import Redis
from contextlib import contextmanager
from config import REDIS_URL
import logging
from datetime import datetime
import json
from uuid import uuid4

from prometheus_client import Counter, Histogram
logging.basicConfig(filename='payment.log', level=logging.INFO)
from config import settings
# 定义监控指标
PAYMENT_COUNTER = Counter('payment_processed', 'Processed payments', ['method', 'status'])
PROCESSING_TIME = Histogram('payment_processing_time', 'Payment processing time')




# 在log_payment函数中添加更多上下文
def log_payment(data: dict, extra: dict = None):
    log_data = {
        "time": datetime.now().isoformat(),
        "event": "payment_success",
        "order_id": data.get('out_trade_no'),
        "user_id": data.get('attach'),
        "amount": data.get('total_fee'),  # 新增金额字段
        "trace_id": str(uuid4()),
        **({"extra": extra} if extra else {})
    }

    logging.info(json.dumps(log_data))

def log_error(error: Exception, context: dict = None):
    """结构化错误日志"""
    logging.error(json.dumps({
        "time": datetime.now().isoformat(),
        "event": "payment_error",
        "error": str(error),
        "type": type(error).__name__,
        "trace_id": str(uuid4()),
        **({"context": context} if context else {})
    }))


redis = Redis.from_url(REDIS_URL)

@contextmanager
def distributed_lock(lock_key: str, timeout=10):
    """分布式锁上下文管理器"""
    lock = redis.lock(lock_key, timeout=timeout)
    acquired = lock.acquire(blocking=False)
    try:
        if acquired:
            yield
        else:
            raise HTTPException(status_code=409, detail="操作正在处理中")
    finally:
        if acquired:
            lock.release()

def update_subscription(db: Session, user_id: str, months: int):
    """更新订阅时长（数据库实现）"""
    sub = db.query(Subscription).filter_by(user_id=user_id).first()
    if sub:
        # 续费逻辑
        from datetime import datetime, timedelta
        new_expire = sub.expire_at if sub.expire_at > datetime.now() else datetime.now()
        db.query(Subscription).filter_by(user_id=user_id).update({
            'expire_at': new_expire + timedelta(days=30*months),
            'remaining_minutes': sub.remaining_minutes + 1000*months
        })
    else:
        # 新用户订阅
        db.add(Subscription(
            user_id=user_id,
            expire_at=datetime.now() + timedelta(days=30*months),
            remaining_minutes=1000*months
        ))
    db.commit()

def mark_as_processed(db: Session, order_id: str):
    """记录已处理订单"""
    db.add(PaymentRecord(
        order_id=order_id,
        processed_at=datetime.now()
    ))
    db.commit()


@app.post("/payment/wechat/callback")
@PROCESSING_TIME.time()
async def wechat_callback(request: Request, db: Session = Depends(get_db)):
    """微信支付回调验证"""
    # 初始化计时和追踪ID
    start_time = time.time()
    trace_id = str(uuid4())
    
    # 解析XML格式回调数据
    body = await request.body()
    xml_data = ET.fromstring(body.decode('utf-8'))
    callback_data = {child.tag: child.text for child in xml_data}
    
    # 记录请求接收日志
    logging.info(json.dumps({
        "trace_id": trace_id,
        "event": "payment_received",
        "order_id": callback_data.get('out_trade_no')
    }))

    try:
        with distributed_lock(f"payment_lock:{callback_data['out_trade_no']}"):
            if verify_signature(callback_data) and callback_data.get('return_code') == 'SUCCESS':
                if not is_processed(db, callback_data['out_trade_no']):
                    update_subscription(db, callback_data['attach'], int(callback_data['total_fee'])/100)
                    mark_as_processed(db, callback_data['out_trade_no'])
                
                # 记录成功日志和耗时
                processing_time = time.time() - start_time
                log_payment(callback_data, {
                    "trace_id": trace_id,
                    "processing_time": f"{processing_time:.3f}s"
                })
                PAYMENT_COUNTER.labels(method='wechat', status='success').inc()
                return {"code": "SUCCESS", "msg": "OK", "trace_id": trace_id}
            
            # 验证失败情况
            PAYMENT_COUNTER.labels(method='wechat', status='invalid').inc()
            return {"code": "FAIL", "msg": "签名验证失败", "trace_id": trace_id}
            
    except HTTPException:
        raise
    except Exception as e:
        # 错误处理
        PAYMENT_COUNTER.labels(method='wechat', status='failed').inc()
        log_error(e, {
            "trace_id": trace_id,
            "order_id": callback_data.get('out_trade_no'),
            "stage": "processing",
            "raw_data": str(callback_data)[:200]
        })
        raise HTTPException(
            status_code=400,
            detail=f"支付处理失败: {str(e)}",
            headers={
                "X-Trace-ID": trace_id,
                "X-Error-Type": type(e).__name__
            }
        )


def is_processed(db: Session, order_id: str) -> bool:
    """检查订单是否已处理"""
    return db.query(PaymentRecord).filter_by(order_id=order_id).first() is not None

@app.post("/payment/alipay/callback")
async def alipay_callback(request: Request, db: Session = Depends(get_db)):
    """支付宝回调处理"""
    try:
        data = await request.json()
        with distributed_lock(f"alipay_lock:{data['out_trade_no']}"):
            if verify_alipay_signature(data):
                if not is_processed(db, data['out_trade_no']):
                    update_subscription(db, data['passback_params'], float(data['total_amount']))
                    mark_as_processed(db, data['out_trade_no'])
                    log_payment(data)
                return {"code": "SUCCESS"}
            return {"code": "FAIL"}
    except Exception as e:
        log_error(e)
        raise HTTPException(status_code=400, detail=str(e))

# ... 保留现有导入 ...
from config import settings

def verify_alipay_signature(data: dict) -> bool:
    """完整的支付宝签名验证"""
    from Crypto.PublicKey import RSA
    from Crypto.Hash import SHA256
    from Crypto.Signature import PKCS1_v1_5
    
    sign = data.pop('sign')
    params = sorted(data.items(), key=lambda x: x[0])
    message = '&'.join([f"{k}={v}" for k,v in params if v])
    
    # 实际应从安全存储获取公钥
    public_key = RSA.import_key(settings.ALIPAY_PUBLIC_KEY)
    verifier = PKCS1_v1_5.new(public_key)
    h = SHA256.new(message.encode())
    return verifier.verify(h, sign.encode())

