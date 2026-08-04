/**
 * 冥想引导算法模块
 * 基于 meditation_guide.py 和 breathing_meditation.py 的真实算法逻辑
 * 移植为微信小程序可用的 JavaScript 版本
 */

class MeditationAlgorithm {
  constructor() {
    // 冥想类型库（来自 meditation_guide.py）
    this.meditationTypes = {
      breathing: {
        name: '呼吸练习',
        description: '专注于呼吸的冥想，适合初学者',
        durationOptions: [5, 10, 15],
        benefits: ['减轻压力', '提高专注力', '平静心情'],
        icon: '🌬️'
      },
      body_scan: {
        name: '身体扫描',
        description: '从头部到脚趾的身体感知练习',
        durationOptions: [10, 20, 30],
        benefits: ['放松肌肉', '提高身体感知', '缓解疼痛'],
        icon: '🔍'
      },
      sleep_prep: {
        name: '睡前冥想',
        description: '帮助入睡的放松练习',
        durationOptions: [10, 15, 20],
        benefits: ['改善睡眠质量', '减少失眠', '深度放松'],
        icon: '😴'
      },
      stress_relief: {
        name: '压力缓解',
        description: '针对高压状态的快速放松',
        durationOptions: [5, 10, 15],
        benefits: ['快速减压', '情绪稳定', '恢复精力'],
        icon: '🧘'
      },
      focus: {
        name: '专注力训练',
        description: '提高注意力和工作效率',
        durationOptions: [10, 15, 20],
        benefits: ['提高专注', '增强记忆力', '减少分心'],
        icon: '🎯'
      }
    };

    // 引导语库（来自 meditation_guide.py）
    this.guidancePhrases = {
      breathing: [
        '轻轻闭上眼睛，感受自然的呼吸',
        '吸气时，感受空气进入鼻腔，充满肺部',
        '呼气时，感受身体的放松和释放',
        '不需要控制呼吸，只是观察它',
        '如果思绪飘走，温柔地带回呼吸',
        '感受每一次呼吸带来的平静',
        '让呼吸成为你的锚点'
      ],
      body_scan: [
        '将注意力带到头顶，感受头部的感觉',
        '慢慢向下，感受面部、颈部的肌肉',
        '注意肩膀是否紧张，允许它们放松',
        '感受胸部的起伏，心脏的跳动',
        '继续向下扫描腹部、背部、腰部',
        '感受双腿和双脚与地面的接触',
        '从头到脚，全身都在放松'
      ],
      sleep_prep: [
        '让自己舒服地躺下，准备好入睡',
        '从脚趾开始，感受每个部位的放松',
        '想象自己漂浮在平静的湖面上',
        '让白天的思绪像云朵一样飘走',
        '允许自己完全放松，进入睡眠',
        '感受床铺对身体的支撑',
        '每一次呼吸都带你更深入放松'
      ],
      stress_relief: [
        '找一个安静的地方，开始放松',
        '深吸一口气，感受空气充满肺部',
        '缓慢呼出，释放所有的紧张和压力',
        '让肩部的紧张随着呼气消散',
        '想象压力像雾气一样慢慢散去',
        '感受内心的平静逐渐升起',
        '你正在变得越来越放松'
      ],
      focus: [
        '坐直身体，保持警觉而放松',
        '将注意力集中在呼吸上',
        '当杂念出现时，温柔地回到呼吸',
        '观察思绪的来去，不评判',
        '保持对当下的觉察',
        '让专注力如灯塔般稳定',
        '你正在训练心智的专注力'
      ]
    };

    // 呼吸模式库（来自 meditation_guide.py）
    this.breathingPatterns = {
      '4-7-8': {
        name: '4-7-8呼吸法',
        description: '帮助快速放松和入睡的呼吸技巧',
        pattern: [4, 7, 8],
        steps: [
          '用鼻子吸气4秒',
          '屏住呼吸7秒',
          '用嘴巴呼气8秒',
          '重复4次'
        ],
        benefits: ['快速放松', '帮助入睡', '减轻焦虑'],
        icon: '🌙'
      },
      'box': {
        name: '方形呼吸法',
        description: '平衡神经系统，提高专注力',
        pattern: [4, 4, 4, 4],
        steps: [
          '吸气4秒',
          '屏气4秒',
          '呼气4秒',
          '屏气4秒',
          '重复5-10次'
        ],
        benefits: ['平衡情绪', '提高专注', '稳定心率'],
        icon: '⬜'
      },
      'deep': {
        name: '深度腹式呼吸',
        description: '完全放松的深度呼吸',
        pattern: [5, 0, 5],
        steps: [
          '手放腹部，感受呼吸',
          '缓慢吸气5秒，腹部鼓起',
          '缓慢呼气5秒，腹部收缩',
          '保持节奏，持续5分钟'
        ],
        benefits: ['深度放松', '改善呼吸', '缓解紧张'],
        icon: '💨'
      }
    };
  }

  /**
   * 分析睡眠数据，确定冥想需求
   * 来源: meditation_guide.py 的 analyze_sleep_data
   */
  analyzeSleepData(sleepData) {
    if (!sleepData) return 'breathing';

    const score = sleepData.score || 75;

    if (score < 60) return 'sleep_prep';        // 睡眠差，需要睡前冥想
    if (score < 75) return 'stress_relief';      // 睡眠一般，需要减压
    if (score > 85) return 'focus';              // 睡眠好，专注训练
    return 'breathing';                          // 一般情况，呼吸练习
  }

  /**
   * 生成个性化冥想计划
   * 来源: meditation_guide.py 的 generate_meditation_plan
   */
  generatePlan(sleepData = null, duration = 10, meditationType = null) {
    // 确定冥想类型
    let type = meditationType;
    if (!type) {
      type = this.analyzeSleepData(sleepData);
    }

    const typeInfo = this.meditationTypes[type];
    if (!typeInfo) {
      return this.generatePlan(sleepData, duration, 'breathing');
    }

    // 选择最接近的时长
    const chosenDuration = typeInfo.durationOptions.reduce((prev, curr) =>
      Math.abs(curr - duration) < Math.abs(prev - duration) ? curr : prev
    );

    // 生成引导语序列
    const guidance = this.guidancePhrases[type] || this.guidancePhrases.breathing;
    const guidanceSequence = this._shuffleArray(guidance).slice(0, 4);

    // 构建计划
    return {
      type: type,
      typeName: typeInfo.name,
      description: typeInfo.description,
      durationMinutes: chosenDuration,
      benefits: typeInfo.benefits,
      icon: typeInfo.icon,
      guidanceSequence: guidanceSequence,
      personalizedReason: this._getPersonalizationReason(sleepData, type),
      breathingPattern: type === 'breathing' || type === 'stress_relief' || type === 'sleep_prep' ? '4-7-8' : null
    };
  }

  /**
   * 获取个性化选择的理由
   */
  _getPersonalizationReason(sleepData, type) {
    if (!sleepData) return '维持日常冥想习惯，提升整体健康';

    const score = sleepData.score || 75;
    const reasons = [];

    if (score < 60) {
      reasons.push(`睡眠评分较低 (${score}/100)，需要改善睡眠质量`);
    } else if (score < 75) {
      reasons.push(`睡眠质量一般 (${score}/100)，建议通过减压改善`);
    } else {
      reasons.push(`睡眠状态良好 (${score}/100)，维持日常冥想习惯`);
    }

    return reasons.join('；');
  }

  /**
   * 生成冥想会话脚本
   * 来源: meditation_guide.py 的 create_session_script
   */
  createSessionScript(plan) {
    const script = [];
    const totalSeconds = plan.durationMinutes * 60;

    // 开场
    script.push({
      time: '0:00',
      timeSeconds: 0,
      action: '准备',
      guidance: `开始${plan.typeName}冥想，时长${plan.durationMinutes}分钟`
    });

    script.push({
      time: '0:30',
      timeSeconds: 30,
      action: '姿势调整',
      guidance: '找一个舒服的姿势，可以坐着或躺着，保持脊柱挺直但放松'
    });

    // 引导语（均匀分布在冥想时长中）
    const guidanceInterval = Math.max(30, Math.floor(totalSeconds / (plan.guidanceSequence.length + 1)));
    
    plan.guidanceSequence.forEach((guidance, index) => {
      const timeSeconds = 30 + (index + 1) * guidanceInterval;
      if (timeSeconds < totalSeconds - 30) {
        script.push({
          time: this._formatTime(timeSeconds),
          timeSeconds: timeSeconds,
          action: '引导',
          guidance: guidance
        });
      }
    });

    // 呼吸练习引导
    if (plan.breathingPattern) {
      const breathTime = Math.max(30, totalSeconds - 120);
      const pattern = this.breathingPatterns[plan.breathingPattern] || this.breathingPatterns['4-7-8'];
      
      script.push({
        time: this._formatTime(breathTime),
        timeSeconds: breathTime,
        action: '呼吸练习',
        guidance: `尝试${pattern.name}: ${pattern.steps.slice(0, 2).join('；')}`
      });
    }

    // 结束引导
    if (totalSeconds >= 60) {
      script.push({
        time: this._formatTime(totalSeconds),
        timeSeconds: totalSeconds,
        action: '结束',
        guidance: '慢慢将注意力带回当下。轻轻活动手指和脚趾。慢慢睁开眼睛，感受冥想后的平静。'
      });
    }

    return script;
  }

  /**
   * 生成呼吸练习
   * 来源: meditation_guide.py 的 generate_breathing_exercise
   */
  getBreathingExercise(pattern = '4-7-8') {
    return this.breathingPatterns[pattern] || this.breathingPatterns['4-7-8'];
  }

  /**
   * 获取所有呼吸模式
   */
  getAllBreathingPatterns() {
    return Object.keys(this.breathingPatterns).map(key => ({
      id: key,
      ...this.breathingPatterns[key]
    }));
  }

  /**
   * 获取所有冥想类型
   */
  getAllMeditationTypes() {
    return Object.keys(this.meditationTypes).map(key => ({
      id: key,
      ...this.meditationTypes[key]
    }));
  }

  /**
   * 获取推荐冥想（基于当前时间）
   */
  getRecommendedMeditation() {
    const hour = new Date().getHours();
    
    if (hour >= 21 || hour < 6) {
      return 'sleep_prep';  // 晚上推荐睡前冥想
    } else if (hour >= 12 && hour < 14) {
      return 'stress_relief'; // 中午推荐减压
    } else if (hour >= 9 && hour < 12) {
      return 'focus';  // 上午推荐专注
    } else {
      return 'breathing';  // 其他时间呼吸练习
    }
  }

  /**
   * 格式化时间
   */
  _formatTime(totalSeconds) {
    const mins = Math.floor(totalSeconds / 60);
    const secs = totalSeconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  /**
   * 数组随机打乱
   */
  _shuffleArray(array) {
    const shuffled = [...array];
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
    }
    return shuffled;
  }
}

module.exports = MeditationAlgorithm;