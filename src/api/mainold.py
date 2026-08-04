from fastapi import FastAPI
from pydantic import BaseModel
import sys
import os
from aisleep.model.deepseek.official.DeepSeek_V3.adapters.meditation_adapter import MeditationAdapter


sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "operational"}

class MeditationRequest(BaseModel):
    audio: bytes
    text: str

# ... rest of your implementation ...
@app.post("/validate-schema")
def debug_validate(request: MeditationRequest):
    return {
        "audio_length": len(request.audio),
        "text_length": len(request.text)
    }

@app.post("/predict")
async def predict_stress(request: MeditationRequest):
    # 延迟导入模型组件（保持启动速度）
    from aisleep.model.deepseek.official.DeepSeek_V3.adapters.meditation_adapter import MeditationAdapter
    
    # 初始化核心模型（此处为测试用随机数生成器）
    class CoreModel:
        def predict(self, data):
            import numpy as np
            return np.random.rand()  # 替换为实际模型推理代码
    
    try:
        # 实际业务逻辑
        meditation_adapter = MeditationAdapter(CoreModel())
        processed = meditation_adapter.process_input({
            "audio": request.audio,
            "text": request.text
        })
        return {"stress_level": meditation_adapter.predict(processed)}
    except Exception as e:
        return {"error": str(e)}
    




