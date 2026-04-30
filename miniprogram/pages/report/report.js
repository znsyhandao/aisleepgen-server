// pages/report/report.js - 专业睡眠报告（真实数据版）
const SleepAlgorithm = require('../../utils/sleep_algorithm');
const sleepAlgorithm = new SleepAlgorithm();

Page({
  data: {
    pageName: 'report',
    showBackButton: false,
    loading: true,
    canShare: false,
    showReport: false,
    
    // 报告数据
    reportData: null,
    
    // 雷达图数据（6维度）
    radarData: [
      { label: '睡眠时长', value: 80, max: 100 },
      { label: '深睡质量', value: 70, max: 100 },
      { label: '入睡效率', value: 75, max: 100 },
      { label: '睡眠连续', value: 65, max: 100 },
      { label: 'REM睡眠', value: 80, max: 100 },
      { label: '身体恢复', value: 72, max: 100 },
    ],
    
    // 评分动画
    scoreAnimateValue: 0,
    
    // 活跃的报告索引（用于收藏等）
    activeReportId: null,
  },

  onLoad(options) {
    console.log('[Report] 专业报告页面加载');
    
    const pages = getCurrentPages();
    if (pages.length > 1) {
      this.setData({ showBackButton: true });
    }
    
    if (wx.canIUse('showShareMenu')) {
      this.setData({ canShare: true });
    }
    
    if (options.result) {
      try {
        const result = JSON.parse(decodeURIComponent(options.result));
        this._displayResult(result);
      } catch (e) {
        this._loadFromStorage();
      }
    } else {
      this._loadFromStorage();
    }
  },

  _displayResult(result) {
    // 补全
    if (!result.healthScores || !result.suggestions) {
      result = this._completeResult(result);
    }
    
    // 计算雷达图数据
    const radarData = this._calculateRadarData(result);
    
    this.setData({
      reportData: result,
      radarData: radarData,
      loading: false,
      showReport: true,
      activeReportId: result.id
    });
    
    // 评分动画
    this._animateScore(0, result.score || 75);
    
    this._saveToHistory(result);
  },

  _loadFromStorage() {
    const lastResult = wx.getStorageSync('latest_analysis_result');
    if (lastResult) {
      this._displayResult(lastResult);
    } else {
      this._generateDefaultReport();
    }
  },

  _generateDefaultReport() {
    this.setData({ loading: true });
    const result = sleepAlgorithm.analyze({});
    result.id = Date.now();
    result.time = new Date().toLocaleString();
    result.type = '自动分析';
    
    setTimeout(() => { this._displayResult(result); }, 500);
  },

  _completeResult(result) {
    const algoResult = sleepAlgorithm.analyze({
      totalDuration: this._parseDurationToMinutes(result.duration || '7h 30m'),
      deepSleepPercent: result.details?.deepSleep ? this._parsePercent(result.details.deepSleep, 450) : 25,
      remSleepPercent: result.details?.remSleep ? this._parsePercent(result.details.remSleep, 450) : 23,
      lightSleepPercent: 47,
      awakeTimes: result.details?.awakeTimes || 2,
      awakeDuration: result.details?.awakeTime ? this._parseDurationToMinutes(result.details.awakeTime) : 15,
      sleepLatency: result.details?.sleepLatency ? this._parseDurationToMinutes(result.details.sleepLatency) : 15
    });
    
    return {
      ...result,
      healthScores: algoResult.healthScores,
      suggestions: algoResult.suggestions,
      sleepStages: algoResult.sleepStages,
      trends: algoResult.trends,
      details: { ...result.details, ...algoResult.details }
    };
  },

  // 6维度雷达图数据计算
  _calculateRadarData(result) {
    const score = result.score || 75;
    const details = result.details || {};
    const health = result.healthScores || {};
    
    const durationHours = this._parseDurationToMinutes(result.duration || '7h 30m') / 60;
    const durationScore = Math.min(100, Math.round((durationHours / 8) * 100));
    
    const deepPct = details.deepSleep ? this._parsePercent(details.deepSleep, this._parseDurationToMinutes(result.duration || '7h 30m')) : 25;
    const deepScore = Math.min(100, Math.round((deepPct / 25) * 100));
    
    const latencyMinutes = details.sleepLatency ? this._parseDurationToMinutes(details.sleepLatency) : 15;
    const latencyScore = Math.min(100, Math.round(Math.max(0, (1 - latencyMinutes / 60) * 100)));
    
    const awakeTimes = details.awakeTimes || 2;
    const continuityScore = Math.min(100, Math.round(Math.max(0, (1 - awakeTimes / 5) * 100)));
    
    const remMinutes = details.remSleep ? this._parseDurationToMinutes(details.remSleep) : 105;
    const totalMinutes = this._parseDurationToMinutes(result.duration || '7h 30m');
    const remPct = totalMinutes > 0 ? (remMinutes / totalMinutes) * 100 : 20;
    const remScore = Math.min(100, Math.round((remPct / 23) * 100));
    
    const recovery = health.physical || health.cardiovascular || 75;
    
    return [
      { label: '睡眠时长', value: durationScore, max: 100 },
      { label: '深睡质量', value: deepScore, max: 100 },
      { label: '入睡效率', value: latencyScore, max: 100 },
      { label: '睡眠连续', value: continuityScore, max: 100 },
      { label: 'REM睡眠', value: remScore, max: 100 },
      { label: '身体恢复', value: Math.round(recovery), max: 100 },
    ];
  },

  // 评分动画
  _animateScore(from, to) {
    const diff = to - from;
    const steps = 20;
    let current = from;
    const step = diff / steps;
    
    for (let i = 1; i <= steps; i++) {
      setTimeout(() => {
        current = Math.round(from + step * i);
        this.setData({ scoreAnimateValue: current });
      }, i * 30);
    }
  },

  _parseDurationToMinutes(durationStr) {
    if (!durationStr) return 450;
    const match = durationStr.match(/(\d+)h\s*(\d+)m/);
    if (match) return parseInt(match[1]) * 60 + parseInt(match[2]);
    return 450;
  },

  _parsePercent(durationStr, totalMinutes) {
    const minutes = this._parseDurationToMinutes(durationStr);
    return Math.round((minutes / totalMinutes) * 100);
  },

  _saveToHistory(reportData) {
    if (!reportData) return;
    wx.setStorageSync('latest_analysis_result', reportData);
    
    let history = wx.getStorageSync('report_history') || [];
    const historyItem = {
      id: reportData.id || Date.now(),
      date: reportData.time || reportData.date || new Date().toLocaleString(),
      score: reportData.score,
      duration: reportData.duration,
      quality: reportData.quality
    };
    
    // 去重
    history = history.filter(h => h.id !== historyItem.id);
    history.unshift(historyItem);
    if (history.length > 100) history = history.slice(0, 100);
    wx.setStorageSync('report_history', history);
  },

  // ===== 操作 =====
  viewDetail(e) {
    const key = e.currentTarget.dataset.key;
    const value = this.data.reportData?.details?.[key];
    const labels = {
      deepSleep: '深睡时长', remSleep: 'REM睡眠', lightSleep: '浅睡时长',
      awakeTime: '清醒时间', sleepEfficiency: '睡眠效率',
      sleepLatency: '入睡潜伏期', awakeTimes: '夜间醒来次数'
    };
    wx.showModal({ title: labels[key] || key, content: `${value}`, showCancel: false });
  },

  viewHealthScore(e) {
    const type = e.currentTarget.dataset.type;
    const score = this.data.reportData?.healthScores?.[type];
    const descriptions = {
      cardiovascular: '睡眠对心脏健康的影响',
      cognitive: '睡眠对记忆和思维能力的影响',
      emotional: '睡眠对情绪稳定性的影响',
      physical: '睡眠对身体修复和恢复的影响'
    };
    wx.showModal({ 
      title: this._getHealthTypeName(type) + '健康', 
      content: `评分: ${score}分\n${descriptions[type] || ''}`, 
      showCancel: false 
    });
  },

  _getHealthTypeName(type) {
    const names = { cardiovascular: '心血管', cognitive: '认知', emotional: '情绪', physical: '身体' };
    return names[type] || type;
  },

  shareReport() {
    if (!this.data.canShare) {
      wx.showToast({ title: '当前环境不支持分享', icon: 'none' });
      return;
    }
    wx.showShareMenu({ withShareTicket: true });
  },

  onShareAppMessage() {
    const report = this.data.reportData;
    return { title: `我的睡眠报告 - ${report?.score || 0}分`, path: '/pages/report/report' };
  },

  copyReport() {
    const r = this.data.reportData;
    if (!r) return;
    
    let text = '=== AI睡眠分析报告 ===\n';
    text += `评分: ${r.score}分 (${r.quality})\n`;
    text += `来源: ${r.sourceName || '分析'}\n`;
    text += `时间: ${r.date || ''}\n`;
    if (r.surveyData) {
      text += `上床: ${r.surveyData.bedtime || '--'}\n`;
      text += `起床: ${r.surveyData.wake_time || '--'}\n`;
      text += `入睡: ${r.surveyData.sleep_latency || 0}分钟\n`;
      text += `醒来: ${r.surveyData.awake_times || 0}次\n`;
    }
    if (r.suggestions?.length > 0) {
      text += '\n改善建议:\n';
      r.suggestions.forEach((s, i) => { text += `${i+1}. ${s}\n`; });
    }
    
    wx.setClipboardData({ data: text, success: () => {
      wx.showToast({ title: '已复制', icon: 'success' });
    }});
  },

  favoriteReport() {
    const report = this.data.reportData;
    if (!report) return;
    
    let favorites = wx.getStorageSync('favorite_reports') || [];
    const existingIndex = favorites.findIndex(f => f.date === (report.time || report.date));
    
    if (existingIndex >= 0) {
      favorites.splice(existingIndex, 1);
      wx.showToast({ title: '已取消收藏', icon: 'success' });
    } else {
      favorites.push({ date: report.time || report.date, score: report.score, duration: report.duration });
      wx.showToast({ title: '已收藏报告', icon: 'success' });
    }
    wx.setStorageSync('favorite_reports', favorites);
  },

  viewHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) wx.navigateBack();
    else wx.switchTab({ url: '/pages/index/index' });
  }
});
