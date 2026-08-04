from deepseek_api import RealtimeEngine

class InterventionSystem:
    def __init__(self):
        self.engine = RealtimeEngine(
            model="deepseek-intervention-2.0",
            latency_threshold=0.5  # 500ms延迟要求
        )
    
    async def execute_intervention(self, plan: Dict):
        """执行实时干预方案"""
        return await self.engine.stream(
            task="execute_plan",
            params={
                "plan": plan,
                "adjustment_strategy": "dynamic"
            }
        )
