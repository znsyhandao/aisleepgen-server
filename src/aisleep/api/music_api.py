from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.aisleep.interventions.music_therapy import MusicTherapy

app = FastAPI()
music_therapy = MusicTherapy(device_manager=None)

class EEGData(BaseModel):
    alpha: float
    theta: float
    beta: float

class UserPreferences(BaseModel):
    preferred_music: str = None

@app.post("/generate_music")
def generate_music(eeg_data: EEGData, user_preferences: UserPreferences = None):
    """
    根据 EEG 数据和用户偏好生成音乐。
    """
    try:
        selected_music = music_therapy._select_music(
            eeg_analysis=eeg_data.dict(),
            user_preferences=user_preferences.dict() if user_preferences else None
        )
        return {"selected_music": selected_music}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))