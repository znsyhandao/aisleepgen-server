async def main():
    # 初始化AI代理
    agent = SleepAIAgent()
    
    # 获取用户ID (实际可从登录系统获取)
    user_id = "user123"  
    
    # 获取个性化减压方案
    interventions = await agent.get_stress_interventions(user_id)
    
    # 执行最优方案
    if interventions:
        best_intervention = interventions[0]
        
        # 根据不同类型执行干预
        if best_intervention['type'] == 'music':
            from audio.player import AudioPlayer
            player = AudioPlayer()
            player.play(best_intervention['subtype'])
            
        elif best_intervention['type'] == 'breathing':
            from interventions.breathing import BreathingCoach
            coach = BreathingCoach()
            await coach.guide(best_intervention['technique'])
            
        # 记录执行日志
        agent.log_intervention(user_id, best_intervention)

if __name__ == "__main__":
    asyncio.run(main())
