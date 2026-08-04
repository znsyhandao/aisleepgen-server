class FeedbackDatabase:
    def __init__(self):
        print("FeedbackDatabase initialized")

    async def store(self, user_id: str, intervention_id: str, effectiveness: float):
        """模拟存储用户反馈"""
        print(f"Storing feedback for user {user_id}: {intervention_id}, {effectiveness}")

    def get_user_history(self, user_id: str):
        """模拟获取用户历史记录"""
        return []