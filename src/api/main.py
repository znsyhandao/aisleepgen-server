from fastapi import FastAPI
from pydantic import BaseModel
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class MeditationRequest(BaseModel):
    audio: bytes
    text: str


app = FastAPI()

@app.get("/")
def ground_truth():
 return {"reality_check":42}



@app.post("/validate-schema")
def debug_validate(request: MeditationRequest):
 return {
 "audio_length": len(request.audio),
 "text_length": len(request.text)
 }

@app.post("/predict")
async def predict_stress(request: MeditationRequest):
 # 处理预测逻辑 
 return {"prediction": "stress_level"}

@app.post("/test")
def test_endpoint():
 return {"success": True}






