# -*- coding: utf-8 -*-
#import os
import sys
import time
import asyncio
import numpy as np
import torch
#from pathlib import Path
from typing import List, Dict, Any
from aisleep.core.ai_agent import SleepAIAgent
from fastapi import APIRouter

# FastAPI 核心依赖
from fastapi import FastAPI, Request, HTTPException, Body, Depends
#from fastapi.concurrency import run_in_threadpool
from fastapi.middleware import Middleware
from fastapi.middleware.cors import CORSMiddleware
#from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from contextlib import asynccontextmanager
from loguru import logger

# 自定义模块
from aisleep.model.deepseek.models import CNN_SleepModel
from scipy.fft import fft
#from fastapi_cache import FastAPICache
#from fastapi_cache.backends.redis import RedisBackend
#from fastapi_cache.decorator import cache
# ... existing imports ...

# 添加缺失的导入
import datetime
import platform
from fastapi.responses import StreamingResponse, JSONResponse







try:
    from prometheus_fastapi_instrumentator import Instrumentator
    PROMETHEUS_ENABLED = True
except ImportError:
    PROMETHEUS_ENABLED = False
    logger.warning("Prometheus instrumentation disabled - package not installed")
# ... rest of your imports ...
from prometheus_fastapi_instrumentator import Instrumentator
import uuid
from fastapi import status
from fastapi.responses import JSONResponse



api_router = APIRouter(prefix="/api/v1")



# 日志配置
logger.add(
    "logs/api.log",
    rotation="500 MB",
    retention="30 days",
    enqueue=True,
    backtrace=True,
    diagnose=True,
    level="DEBUG"
)

# 环境配置
# ... existing imports ...

class AppConfig(BaseSettings):
    signal_range: tuple = (-500, 500)
    signal_length: int = 3000
    model_path: str = "models/v1/cnn_sleep.pth"
    use_quantization: bool = False  # 默认不启用量化
    freq_bands: Dict[str, slice] = {
        'delta': slice(0, 4),
        'theta': slice(4, 8),
        'alpha': slice(8, 12)
    }
    max_concurrent: int = 50
    timeout_threshold: int = 30
    expected_max: float = 500.0
    valid_threshold: float = 500.0
    rate_limit: float = 0.1  # 默认100ms间隔
    ai_timeout: int = 15  # AI分析超时
    max_hardware: int = 10  # 最大硬件连接数
    ai_model_refresh: int = 3600  # 模型自动更新间隔(秒)
    feature_timeout: int = 5  # 特征计算超时(秒)
    model_timeout: int = 10   # 模型推理超时(秒)
    ai_timeout: int = 15      # 总AI分析超时(秒)
    
    class Config:
        env_file = ".env"
        env_prefix = "AISLEEP_"
        extra = 'ignore'  # Add this line to ignore extra fields


# 应用生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ai_agent

    ai_agent = SleepAIAgent()
    """应用生命周期管理"""
    global model, PREDICTION_SEMAPHORE, MODEL_LOADED
    MODEL_LOADED = False
    logger.info("Starting system...")
    #FastAPICache.init(RedisBackend("redis://localhost:6379"), prefix="fastapi-cache")
    try:
        logger.info("正在初始化Redis缓存...")
        
        logger.info("正在加载模型...")
        # 模型初始化
        
        model = CNN_SleepModel(input_channels=1)
        model.eval()
        if torch.cuda.is_available():
            model.cuda()
            logger.info(f"模型已加载到CUDA设备: {next(model.parameters()).device}")
        else:
            logger.warning("CUDA设备未找到，将使用CPU进行推理")
            
        model.device = next(model.parameters()).device  # 添加设备属性

        MODEL_LOADED = True
        logger.info("Model loaded successfully")
           
        # 信号量初始化
        PREDICTION_SEMAPHORE = asyncio.Semaphore(AppConfig().max_concurrent)
        logger.info("System initialized")
        yield

    except Exception as e:
        logger.warning(f"Redis连接失败: {str(e)}, 将使用内存缓存")
        logger.critical(f"System boot failed: {str(e)}")
        FastAPICache.init()
        sys.exit(1)
    finally:
        logger.info("System shutdown")
def check_model_loaded():
    if not MODEL_LOADED:
        raise HTTPException(503, "服务暂不可用，模型未加载完成")
    
# 新增商业化路由
@api_router.post("/ai/holistic", tags=["AI智能体"])
async def holistic_analysis(user_data: Dict = Body(...)):
    return await ai_agent.holistic_analysis(user_data)

@api_router.get("/ai/intervention", tags=["AI智能体"])
async def realtime_intervention():
    return StreamingResponse(
        ai_agent.realtime_intervention(),
        media_type="text/event-stream"
    )


# 应用实例化
app = FastAPI(
    title="AI Sleep Stage Prediction API",
    version="1.0.0",  # 添加API版本
    lifespan=lifespan,
    docs_url="/docs",  # 确保文档路径正确
    redoc_url="/redoc",  # 可选：添加redoc文档
    openapi_url="/api/v1/openapi.json",  # 版本化OpenAPI文档
    middleware=[Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )],
    swagger_ui_parameters={
        "syntaxHighlight": True,
        "tryItOutEnabled": True,
        "displayRequestDuration": True
    }
)





# ... 其他导入保持不变 ...
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    PROMETHEUS_ENABLED = True
except ImportError:
    PROMETHEUS_ENABLED = False
    logger.warning("Prometheus instrumentation disabled - package not installed")

# ... 其他代码保持不变 ...

# 修改 Prometheus 初始化部分
if PROMETHEUS_ENABLED:
    Instrumentator().instrument(app).expose(app)
    logger.info("Prometheus metrics enabled")
else:
    logger.info("Running without Prometheus metrics")






# 数据模型
# 修改PredictRequest模型
class PredictRequest(BaseModel):
    audio: List[float] = Field(..., min_length=3000, max_length=3000)
    hr: float = Field(..., ge=30.0, le=200.0)
    text: str = Field(default="", max_length=100)


class PredictionResult(BaseModel):
    prediction: int
    prediction_label: str
    probabilities: List[float]
    inference_ms: float
    debug_info: Dict[str, Any]
    hr: float = Field(..., description="处理后的心率值")


# 工具函数
def validate_signal(audio_data):
    """验证输入信号格式"""
    config = AppConfig()
    if len(audio_data) != config.signal_length:
        raise HTTPException(422, f"信号长度必须为{config.signal_length}个采样点")
    
    if not all(isinstance(x, (int, float)) for x in audio_data):
        raise HTTPException(422, "包含非数字值")
    
    signal = np.array(audio_data, dtype=np.float32)
    
    if np.any(signal < config.signal_range[0]) or np.any(signal > config.signal_range[1]):
        raise HTTPException(422, f"信号超出范围({config.signal_range}μV)")
    
    return signal

def spectral_analysis(signal):
    """执行FFT频谱分析"""
    if len(signal) % 2 != 0:
        signal = signal[:-1]
    n = len(signal)
    freq = fft(signal)[:n//2]
    return np.abs(freq).tolist()

def calculate_stats(signal):
    """计算时域统计特征"""
    return {
        'mean': np.mean(signal),
        'std': np.std(signal),
        'peak': np.max(np.abs(signal))
    }

def convert_tensor_to_list(tensor: torch.Tensor) -> list:
    """转换Tensor为列表"""
    return tensor.cpu().detach().numpy().tolist()

# 依赖项
def get_model():
    return model

def get_semaphore():
    return PREDICTION_SEMAPHORE

# 中间件
# 合并两个中间件为一个
@app.middleware("http")

async def combined_middleware(request: Request, call_next):
    config = AppConfig()
    if config.rate_limit <= 0:
        logger.warning("无效的rate_limit配置，使用默认值0.1秒")
        config.rate_limit = 0.1
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    config = AppConfig()
    
    # 限流逻辑
    if request.url.path == "/api/v1/predict":
        if hasattr(request.state, "last_predict_call"):
            if time.time() - request.state.last_predict_call < 0.1:
                return JSONResponse(
                    {"detail": f"请求过于频繁，最小间隔{config.rate_limit}秒"},
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS
                )
        request.state.last_predict_call = time.time()
    
    # 请求日志和计时逻辑
    process_start = time.time()
    try:
        response = await call_next(request)
    except asyncio.TimeoutError:
        logger.warning(f"请求超时: {request.method} {request.url.path}")
        raise HTTPException(status_code=504, detail="请求处理超时")
    except Exception as e:
        logger.error(f"请求错误: {str(e)}")
        raise
    
    # 添加处理时间头
    process_time = (time.time() - process_start) * 1000
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code}",
        process_time=f"{process_time:.1f}ms"
    )
    response.headers["X-Request-ID"] = request_id
    return response






# 保留并使用这个版本化的健康检查端点（已在前面定义）
@api_router.get("/health", response_model=Dict[str, Any])
#@cache(expire=60, namespace="healthcheck", key="health_status")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "system": {
            "python_version": sys.version,
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "model_loaded": MODEL_LOADED,  # 添加模型加载状态
            "max_concurrent": AppConfig().max_concurrent,  # 添加最大并发数
            "timeout_threshold": AppConfig().timeout_threshold,  # 添加超时阈值
            "expected_max": AppConfig().expected_max,  # 添加预期最大值
            "valid_threshold": AppConfig().valid_threshold,  # 添加有效阈值
            "model_version": "1.0.0"  # 添加模型版本信息    
        }
    }



# 将预测接口从@app改为@api_router
@api_router.post("/predict", 
    response_model=PredictionResult,
    responses={
        422: {"description": "无效输入"},
        500: {"description": "服务器内部错误"},
        504: {"description": "请求超时"}
    },
    summary="睡眠阶段预测",
    description="""
    ## 功能说明
    根据输入的EEG信号预测睡眠阶段
    
    ## 参数要求
    - audio: 长度必须为3000的浮点数数组
    - text: 可选文本备注
    """,
    tags=["预测接口"]
)


async def predict_sleep_stage(
    request: PredictRequest = Body(...),
    model: CNN_SleepModel = Depends(get_model),
    semaphore: asyncio.Semaphore = Depends(get_semaphore),
    _: bool = Depends(check_model_loaded)
):
    try:
        logger.debug(f"开始处理请求，请求数据: {request.dict()}")
        
        # 验证请求数据
        if not hasattr(request, 'hr'):
            raise HTTPException(422, detail="请求缺少hr字段")
        
        # 提取hr值
        hr_value = float(request.hr)
        
        async with semaphore:
            try:
                # 信号验证
                raw_signal = validate_signal(request.audio)
                logger.debug(f"信号验证通过，hr_value={hr_value}")
                
                # 模型推理
                input_tensor = torch.as_tensor(raw_signal, dtype=torch.float32)
                if torch.cuda.is_available():
                    input_tensor = input_tensor.cuda()
                
                with torch.no_grad():
                    output = model(input_tensor.unsqueeze(0).unsqueeze(0), hr=torch.tensor([hr_value], device=model.device))
                    probabilities = torch.nn.functional.softmax(output.squeeze(), dim=-1)
                    prediction = torch.argmax(probabilities).item()
                    probabilities_list = probabilities.cpu().numpy().tolist()
                    logger.debug(f"模型推理完成，预测结果: {prediction}")

                return {
                    "prediction": prediction,
                    "prediction_label": ["Wake", "NREM", "REM"][prediction],
                    "probabilities": probabilities_list,
                    "hr": hr_value,
                    "debug_info": {
                        "hr_value": hr_value,
                        "signal_length": len(raw_signal)
                    }
                }
                
            except Exception as e:
                logger.error(f"处理失败: {str(e)}", exc_info=True)
                raise HTTPException(500, detail=f"处理失败: {str(e)}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"系统错误: {str(e)}", exc_info=True)
        raise HTTPException(500, detail="内部服务器错误")



# 将测试接口改为版本化路由
@api_router.get("/test/signal", tags=["测试接口"])
async def generate_test_signal():
    """生成测试用EEG信号"""
    return {
        "audio": np.random.uniform(-500, 500, 3000).tolist(),
        "description": "随机生成的测试信号"
    }


@api_router.post("/commercial/report", tags=["商业化"])
async def generate_commercial_report(user: Dict = Body(...)):
    """生成付费报告"""
    return await ai_agent.generate_report(user["id"])

@api_router.get("/hardware/status", tags=["智能硬件"])
async def check_hardware_status():
    """检查硬件连接状态"""
    return ai_agent.device_manager.get_status()

@api_router.get("/ping")
async def ping():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

@api_router.get("/deep-test")
async def deep_test():
    """深度测试端点"""
    try:
        # 更健壮的检查方式
        db_ok = False
        if hasattr(ai_agent, 'check_db_connection') and callable(ai_agent.check_db_connection):
            db_ok = ai_agent.check_db_connection()
        else:
            logger.warning("SleepAIAgent 缺少可调用的 check_db_connection 方法")
        
        return {
            "status": "ok",
            "db_connection": db_ok,
            "model_loaded": MODEL_LOADED,
            "system": platform.platform(),
            "warning": "check_db_connection not available" if not hasattr(ai_agent, 'check_db_connection') else None
        }
    except Exception as e:
        logger.error(f"深度测试失败: {str(e)}")
        raise HTTPException(500, detail=str(e))



# Ensure this comes AFTER all route definitions
app.include_router(api_router)


# Add route debug print
def print_routes():
    print("\nRegistered Routes:")
    for route in app.routes:
        print(f"{route.path} - {route.methods}")


if __name__ == "__main__":
    # 增强调试信息
    print("=== 系统初始化状态 ===")
    print(f"MODEL_LOADED: {MODEL_LOADED}")
    print(f"ai_agent 初始化: {'成功' if 'ai_agent' in globals() else '失败'}")
    
    # 打印所有注册的路由
    print("\n=== 注册的路由 ===")
    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", "")
        print(f"{path} - {methods}")
        if path and path.endswith("deep-test"):
            print(">>> 找到 deep-test 路由 <<<")
    
    # 启动时添加更多调试参数
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="trace",  # 更详细的日志级别
        reload=True,        # 启用热重载
        access_log=True     # 启用访问日志
    )
