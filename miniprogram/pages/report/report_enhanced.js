// pages/report/report.js - 增强版
Page({
  data: {
    pageName: 'report',
    showBackButton: false,
    
    // 报告数据
    reportData: {
      date: '2026-04-23',
      score: 85,
      duration: '7h 30m',
      quality: '良好',
      
      // 详细指标
      details: {
        deepSleep: '2h 15m',
        remSleep: '1h 45m',
        lightSleep: '3h 30m',
        awakeTime: '15m',
        sleepEfficiency: 92,
        sleepLatency: '12m',
        awakeTimes: 2
      },
      
      // 睡眠阶段分布
      sleepStages: [
        { name: '深睡', value: 30, color: '#4A90E2' },
        { name: 'REM', value: 23, color: '#64b5f6' },
        { name: '浅睡', value: 47, color: '#90caf9' }
      ],
      
      // 趋势对比
      trends: {
        scoreTrend: '+3',
        durationTrend: '+15m',
        efficiencyTrend: '+2%'
      },
      
      // 建议
      suggestions: [
        '保持规律的睡眠时间',
        '睡前避免使用电子设备',
        '适当进行放松训练',
        '保持卧室环境安静黑暗'
      ],
      
      // 健康评分
      healthScores: {
        cardiovascular: 88,
        cognitive: 82,
        emotional: 85,
        physical: 90
      }
    },
    
    // 分享相关
    canShare: false,
    
    // 加载状态
    loading: false
  },
  
  onLoad(options) {
    console.log('报告页面加载');
    
    // 检查页面栈
    const pages = getCurrentPages();
    if (pages.length > 1) {
      this.setData({
        showBackButton: true
      });
    }
    
    // 检查是否有传递的分析结果
    if (options.result) {
      try {
        const result = JSON.parse(decodeURIComponent(options.result));
        this.loadAnalysisResult(result);
      } catch (error) {
        console.error('解析分析结果失败:', error);
        this.loadMockData();
      }
    } else {
      this.loadMockData();
    }
    
    // 检查分享能力
    this.checkShareAbility();
  },
  
  // 加载分析结果
  loadAnalysisResult(result) {
    console.log('加载分析结果:', result);
    
    const reportData = {
      date: result.time || new Date().toLocaleDateString(),
      score: result.score || 85,
      duration: result.duration || '7h 30m',
      quality: this.getQualityLevel(result.score || 85),
      details: result.details || {
        deepSleep: '2h 15m',
        remSleep: '1h 45m',
        lightSleep: '3h 30m',
        awakeTime: '15m',
        sleepEfficiency: 92,
        sleepLatency: '12m',
        awakeTimes: 2
      },
      sleepStages: this.calculateSleepStages(result.details),
      trends: this.calculateTrends(result.score || 85),
      suggestions: this.generateSuggestions(result.score || 85, result.details),
      healthScores: this.calculateHealthScores(result.details)
    };
    
    this.setData({
      reportData: reportData,
      loading: false
    });
    
    // 保存到历史
    this.saveToHistory(reportData);
  },
  
  // 加载模拟数据
  loadMockData() {
    console.log('加载模拟数据');
    
    this.setData({
      loading: true
    });
    
    // 模拟加载延迟
    setTimeout(() => {
      const mockData = {
        date: new Date().toLocaleDateString(),
        score: 85,
        duration: '7h 30m',
        quality: '良好',
        details: {
          deepSleep: '2h 15m',
          remSleep: '1h 45m',
          lightSleep: '3h 30m',
          awakeTime: '15m',
          sleepEfficiency: 92,
          sleepLatency: '12m',
          awakeTimes: 2
        },
        sleepStages: [
          { name: '深睡', value: 30, color: '#4A90E2' },
          { name: 'REM', value: 23, color: '#64b5f6' },
          { name: '浅睡', value: 47, color: '#90caf9' }
        ],
        trends: {
          scoreTrend: '+3',
          durationTrend: '+15m',
          efficiencyTrend: '+2%'
        },
        suggestions: [
          '保持规律的睡眠时间',
          '睡前避免使用电子设备',
          '适当进行放松训练',
          '保持卧室环境安静黑暗'
        ],
        healthScores: {
          cardiovascular: 88,
          cognitive: 82,
          emotional: 85,
          physical: 90
        }
      };
      
      this.setData({
        reportData: mockData,
        loading: false
      });
    }, 1000);
  },
  
  // 计算睡眠阶段分布
  calculateSleepStages(details) {
    if (!details) return [
      { name: '深睡', value: 30, color: '#4A90E2' },
      { name: 'REM', value: 23, color: '#64b5f6' },
      { name: '浅睡', value: 47, color: '#90caf9' }
    ];
    
    // 这里可以根据实际数据计算
    return [
      { name: '深睡', value: 30, color: '#4A90E2' },
      { name: 'REM', value: 23, color: '#64b5f6' },
      { name: '浅睡', value: 47, color: '#90caf9' }
    ];
  },
  
  // 计算趋势
  calculateTrends(score) {
    // 这里可以根据历史数据计算趋势
    return {
      scoreTrend: score >= 85 ? '+3' : score >= 75 ? '+1' : '-2',
      durationTrend: '+15m',
      efficiencyTrend: '+2%'
    };
  },
  
  // 生成建议
  generateSuggestions(score, details) {
    const suggestions = [];
    
    if (score < 70) {
      suggestions.push('建议咨询医生进行专业评估');
      suggestions.push('建立规律的作息时间表');
      suggestions.push('考虑进行睡眠环境改善');
    } else if (score < 80) {
      suggestions.push('保持规律的睡眠时间');
      suggestions.push('睡前避免使用电子设备');
      suggestions.push('适当进行放松训练');
    } else {
      suggestions.push('继续保持良好的睡眠习惯');
      suggestions.push('定期进行睡眠质量评估');
      suggestions.push('分享您的健康经验给他人');
    }
    
    // 根据详细数据添加具体建议
    if (details) {
      if (details.awakeTimes > 3) {
        suggestions.push('夜间醒来次数较多,建议检查睡眠环境');
      }
      if (parseInt(details.sleepEfficiency) < 85) {
        suggestions.push('睡眠效率有待提高,减少床上清醒时间');
      }
    }
    
    return suggestions.slice(0, 4); // 最多4条建议
  },
  
  // 计算健康评分
  calculateHealthScores(details) {
    if (!details) return {
      cardiovascular: 88,
      cognitive: 82,
      emotional: 85,
      physical: 90
    };
    
    // 这里可以根据详细数据计算
    return {
      cardiovascular: 85 + Math.floor(Math.random() * 10),
      cognitive: 80 + Math.floor(Math.random() * 10),
      emotional: 83 + Math.floor(Math.random() * 10),
      physical: 88 + Math.floor(Math.random() * 10)
    };
  },
  
  // 获取质量等级
  getQualityLevel(score) {
    if (score >= 85) return '优秀';
    if (score >= 75) return '良好';
    if (score >= 65) return '一般';
    return '需要改善';
  },
  
  // 保存到历史
  saveToHistory(reportData) {
    let history = wx.getStorageSync('report_history') || [];
    
    const historyItem = {
      id: Date.now(),
      date: reportData.date,
      score: reportData.score,
      duration: reportData.duration,
      quality: reportData.quality
    };
    
    history.unshift(historyItem);
    if (history.length > 100) history = history.slice(0, 100);
    
    wx.setStorageSync('report_history', history);
  },
  
  // 检查分享能力
  checkShareAbility() {
    if (wx.canIUse('showShareMenu')) {
      this.setData({
        canShare: true
      });
    }
  },
  
  // 查看详细指标
  viewDetail(e) {
    const key = e.currentTarget.dataset.key;
    const value = this.data.reportData.details[key];
    const labels = {
      deepSleep: '深睡时长',
      remSleep: 'REM睡眠',
      lightSleep: '浅睡时长',
      awakeTime: '清醒时间',
      sleepEfficiency: '睡眠效率',
      sleepLatency: '入睡潜伏期',
      awakeTimes: '夜间醒来次数'
    };
    
    wx.showModal({
      title: labels[key] || key,
      content: `${value}${key === 'sleepEfficiency' ? '%' : ''}`,
      showCancel: false
    });
  },
  
  // 查看健康评分详情
  viewHealthScore(e) {
    const type = e.currentTarget.dataset.type;
    const score = this.data.reportData.healthScores[type];
    
    const descriptions = {
      cardiovascular: '心血管健康:反映睡眠对心脏健康的影响',
      cognitive: '认知功能:睡眠对记忆和思维能力的影响',
      emotional: '情绪健康:睡眠对情绪稳定性的影响',
      physical: '身体恢复:睡眠对身体修复和恢复的影响'
    };
    
    wx.showModal({
      title: `${this.getHealthTypeName(type)}健康`,
      content: `评分: ${score}分\n${descriptions[type]}`,
      showCancel: false
    });
  },
  
  getHealthTypeName(type) {
    const names = {
      cardiovascular: '心血管',
      cognitive: '认知',
      emotional: '情绪',
      physical: '身体'
    };
    return names[type] || type;
  },
  
  // 分享报告
  shareReport() {
    if (!this.data.canShare) {
      wx.showToast({
        title: '当前环境不支持分享',
        icon: 'none'
      });
      return;
    }
    
    wx.showShareMenu({
      withShareTicket: true
    });
  },
  
  onShareAppMessage() {
    const report = this.data.reportData;
    return {
      title: `我的睡眠报告 - ${report.score}分`,
      path: '/pages/report/report',
      imageUrl: '/images/report-share.png'
    };
  },
  
  // 导出报告
  exportReport() {
    wx.showActionSheet({
      itemList: ['保存为图片', '导出为PDF', '分享给医生'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.saveAsImage();
        } else if (res.tapIndex === 1) {
          this.exportAsPDF();
        } else {
          this.shareToDoctor();
        }
      }
    });
  },
  
  saveAsImage() {
    wx.showToast({
      title: '图片保存功能开发中',
      icon: 'none'
    });
  },
  
  exportAsPDF() {
    wx.showToast({
      title: 'PDF导出功能开发中',
      icon: 'none'
    });
  },
  
  shareToDoctor() {
    wx.showToast({
      title: '医生分享功能开发中',
      icon: 'none'
    });
  },
  
  // 收藏报告
  favoriteReport() {
    const report = this.data.reportData;
    
    let favorites = wx.getStorageSync('favorite_reports') || [];
    const existingIndex = favorites.findIndex(f => f.date === report.date);
    
    if (existingIndex >= 0) {
      favorites.splice(existingIndex, 1);
      wx.showToast({
        title: '已取消收藏',
        icon: 'success'
      });
    } else {
      favorites.push({
        date: report.date,
        score: report.score,
        duration: report.duration
      });
      wx.showToast({
        title: '已收藏报告',
        icon: 'success'
      });
    }
    
    wx.setStorageSync('favorite_reports', favorites);
  },
  
  // 返回
  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.switchTab({
        url: '/pages/index/index'
      });
    }
  },
  
  // 查看历史报告
  viewHistory() {
    wx.navigateTo({
      url: '/pages/history/history'
    });
  }
});