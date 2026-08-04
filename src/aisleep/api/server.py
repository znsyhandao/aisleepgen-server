from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import torch
from ..model.deepseek.models import CNN_SleepModel
from pydantic import BaseModel
from typing import Optional

app = FastAPI()

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    hr: Optional[float] = None
    spo2: Optional[float] = None

@app.post("/analyze")
async def analyze_sleep(
    edf_file: UploadFile = File(...),
    hr: Optional[float] = None,
    spo2: Optional[float] = None
):
    """实时睡眠分析端点"""
    # 加载预训练模型
    model = CNN_SleepModel.load("models/sleep_model.pth")
    
    # 处理上传的EDF文件
    edf_data = await edf_file.read()
    signals = process_edf(edf_data)  # 需要实现EDF处理函数
    
    # 执行预测
    with torch.no_grad():
        if hr and spo2:
            pred = model(signals, hr=hr, spo2=spo2)
        else:
            pred = model(signals)
    
    return {
        "sleep_stages": pred.argmax(-1).tolist(),
        "confidence": torch.softmax(pred, dim=1).max().item()
    }

def process_edf(edf_data: bytes) -> torch.Tensor:
    """将EDF字节数据转换为模型输入张量"""
    # 实现EDF解析逻辑...
    return torch.tensor(...)  # 返回(1, channels, seq_len)形状的张量
