from fastapi import FastAPI, HTTPException
from meditation_adapter import MeditationAdapter

app = FastAPI()
adapter = MeditationAdapter(core_model=load_model())

@app.post("/v1/meditation")
async def create_session(user_data: dict):
    """商业化API端点"""
    try:
        # 输入预处理
        processed = adapter.process_input(user_data)
        
        # 压力预测
        stress_level = adapter.predict({
            'audio': processed['audio'],
            'text': processed['text']
        })
        
        # 生成计费记录
        charge_id = create_billing(
            user_id=user_data['user_id'],
            service='meditation'
        )
        
        return {
            'session_id': str(uuid.uuid4()),
            'audio': processed['audio'],
            'stress_level': stress_level,
            'charge_id': charge_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@app.post("/v1/subscribe")
async def subscribe(user_data: dict):
    """订阅支付端点"""
    try:
        adapter = get_adapter()
        if not adapter.check_quota(user_data['user_id']):
            return adapter.create_order(
                user_data['user_id'],
                user_data.get('plan', 'basic')
            )
        return {"status": "already_subscribed"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
