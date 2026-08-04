import pytest
from src.aisleep.core.ai_agent import SleepAIAgent
import asyncio

@pytest.fixture
def sleep_ai_agent():
    """初始化 SleepAIAgent 实例"""
    return SleepAIAgent()

def test_model_loading(sleep_ai_agent):
    """测试 DeepSeek 模型加载"""
    assert sleep_ai_agent.deepseek_model is not None, "DeepSeek 模型加载失败"

def test_stress_interventions(sleep_ai_agent):
    """测试个性化减压方案推荐"""
    user_id = "test_user"

    async def run_test():
        interventions = await sleep_ai_agent.get_stress_interventions(user_id)
        assert interventions is not None

    asyncio.run(run_test())

def test_meditation_guide(sleep_ai_agent):
    """测试冥想引导"""
    user_profile = {
        "meditation_prefs": {
            "voice_type": "female_calm",
            "bgm_type": "nature",
            "guidance_level": "medium"
        }
    }

    async def run_test():
        chunks = []
        async for chunk in sleep_ai_agent.meditation_guide(user_profile):
            chunks.append(chunk)
        assert len(chunks) > 0

    asyncio.run(run_test())

def test_realtime_processing(sleep_ai_agent):
    """测试实时生物信号处理"""
    biometrics = {
        "hrv": 50,
        "gsr": 0.5,
        "eeg": [0.1, 0.2, 0.3]
    }

async def run_test():
    results = []
    async for result in sleep_ai_agent.realtime_intervention():
        results.append(result)
        # 假设只测试前两个结果
        if len(results) >= 2:
            break
    assert len(results) > 0

    asyncio.run(run_test())

