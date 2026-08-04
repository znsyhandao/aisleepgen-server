def score_audio(features, is_voice, voice_prob):
    """基于声学特征+分类器输出映射睡眠指数和减压指数
    使用决策树分类（不依赖SVM类型输出，而是结合声学指标）"""
    cv = features[13]      # 能量CV
    zcr = features[14]     # 零交叉率
    centroid = features[15] # 谱质心
    flatness = features[16] # 谱平坦度
    low_pct = features[17]  # 低频占比
    mid_pct = features[18]  # 中频占比
    high_pct = features[19] # 高频占比
    active_ratio = features[20] # 活跃率
    tpm = features[21]     # 过零切换率
    
    result = {}
    
    # ===== 决策树分类 =====
    # 1. 白噪音: 极稳+持续+平坦
    if active_ratio > 0.95 and cv < 0.3 and flatness > 0.02:
        result['type'] = 'white_noise'
        result['sleep'] = 8
        result['relax'] = 5
        result['cog_load'] = 0
        result['best_scene'] = '入睡辅助'
        result['scenes'] = [{'scene':'入睡辅助','score':8},{'scene':'专注','score':5}]
        result['contraindications'] = ['睡前使用(低频恒定,可能干扰深度睡眠)']
        result['time_of_day'] = '全天'
    
    # 2. 呼吸引导: 低活跃率+高CV+间歇说话
    elif active_ratio < 0.5 and cv > 2.0 and tpm > 15:
        result['type'] = 'breathing_guide'
        result['sleep'] = 6
        result['relax'] = 7
        result['cog_load'] = 3
        result['best_scene'] = '减压放松'
        result['scenes'] = [{'scene':'减压放松','score':7},{'scene':'睡前放松','score':6}]
        result['contraindications'] = []
        result['time_of_day'] = '睡前/午间'
    
    # 3. 解说叙事: is_voice+部分SVM置信 或 声学指标符合人声模式
    elif (is_voice and voice_prob > 0.5) or (not is_voice and active_ratio < 0.85 and tpm > 10 and cv > 0.5):
        speech_density = min((active_ratio + tpm/50) / 2, 1.0)
        music_quality = min(low_pct / 20, 1.0) if low_pct > 10 else 0.2
        sleep_score = int(10 * (1 - speech_density * 0.7) + music_quality * 2)
        relax_score = int(10 * (1 - speech_density * 0.5) + music_quality * 3)
        result['type'] = 'narration'
        result['sleep'] = max(1, min(10, sleep_score))
        result['relax'] = max(1, min(10, relax_score))
        result['cog_load'] = int(3 + speech_density * 7)
        result['best_scene'] = '专注白天' if speech_density > 0.6 else '放松引导'
        scenes = [{'scene':'白天引导','score':result['relax']}]
        if result['sleep'] >= 4: scenes.append({'scene':'轻度助眠','score':result['sleep']})
        result['scenes'] = scenes
        result['contraindications'] = ['高认知负荷(有解说)'] if result['cog_load'] > 6 else []
        result['time_of_day'] = '白天' if speech_density > 0.6 else '午后/傍晚'
    
    # 4. 自然声(海浪/流水): 持续高能+中低CV+适中平坦度
    elif active_ratio > 0.85 and cv < 0.8 and flatness > 0.02:
        result['type'] = 'natural_ambient'
        result['sleep'] = 8
        result['relax'] = 8
        result['cog_load'] = 0
        result['best_scene'] = '入睡辅助/减压放松'
        result['scenes'] = [{'scene':'入睡辅助','score':8},{'scene':'减压放松','score':8}]
        result['contraindications'] = []
        result['time_of_day'] = '全天'
    
    # 5. 纯音乐/氛围: 低频主导+低质心+低平坦度
    elif low_pct > 15 and centroid < 3000 and flatness < 0.05:
        result['type'] = 'music'
        result['sleep'] = 6
        result['relax'] = 7
        result['cog_load'] = 2
        result['best_scene'] = '减压放松'
        result['scenes'] = [{'scene':'减压放松','score':7},{'scene':'轻度助眠','score':6}]
        result['contraindications'] = ['注意力需求(音乐结构丰富的片段)']
        result['time_of_day'] = '全天'
    
    # 6. 环境音(fallback)
    else:
        result['type'] = 'ambient'
        result['sleep'] = 7
        result['relax'] = 6
        result['cog_load'] = 1
        result['best_scene'] = '背景环境'
        result['scenes'] = [{'scene':'背景环境','score':7},{'scene':'轻度减压','score':6}]
        result['contraindications'] = []
        result['time_of_day'] = '全天'
    
    result['voice_prob'] = round(voice_prob, 2)
    result['features'] = {
        'active_ratio': round(active_ratio, 2),
        'tpm': tpm,
        'cv': round(cv, 2),
        'centroid': round(centroid, 0),
        'flatness': round(flatness, 4),
        'low_pct': round(low_pct, 1),
        'mid_pct': round(mid_pct, 1),
        'zcr': round(zcr, 4)
    }
    
    return result

