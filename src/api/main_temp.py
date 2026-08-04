from fastapi import FastAPI
from pydantic import BaseModel
import sys
import os
import numpy as np

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

app = FastAPI()

# Add this endpoint immediately after app creation ▼▼▼
@app.get("/")
def root():
    return {"status": "API operational"}
async def health_check():
    return {"status": "running"}

class MeditationRequest(BaseModel):
    audio: bytes
    text: str



@app.post("/predict")
async def predict_stress(request: MeditationRequest):
    try:
        from aisleep.model.deepseek.official.DeepSeek_V3.adapters.meditation_adapter import MeditationAdapter
        
        audio_array = np.frombuffer(request.audio, dtype=np.float32)
        
        class CoreModel:
            def predict(self, data):
                return np.random.rand()

        meditation_adapter = MeditationAdapter(CoreModel())
        processed = meditation_adapter.process_input({
            "audio": audio_array,
            "text": request.text
        })
        
        return {"stress_level": float(meditation_adapter.predict(processed))}
    
    except Exception as e:
        return {"error": str(e)}


