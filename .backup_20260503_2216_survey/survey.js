// pages/survey/survey.js - 统一评估入口（自适应版）
const api = require('../../utils/api');
const SleepAlgorithm = require('../../utils/sleep_algorithm');
const sleepAlgorithm = new SleepAlgorithm();

Page({
  data: {
    step: 0,
    qIndex: 0,
    qTotal: 7,
    qProgress: 0,
    generating: false,
    showBackButton: false,
    welcomeDesc: '回答 7 个简单问题<br/>AI 为你生成专业睡眠报告',
    startBtnText: '开始评估',
    quickConfirmTitle: '',
    q1Text: '昨晚几点上床睡觉的？',
    q2Text: '今早几点醒来的？',
    q3Text: '从上床到真正睡着,大概多久？',
    q4Text: '夜里醒了几次？',
    q5Text: '早上醒来感觉怎么样？',
    q6Text: '最近压力大吗？',
    q7Text: '睡前有没有看手机或电脑屏幕？',
    quickData: {
      bedtime: '23:00',
      wake_time: '07:00',
      sleepLatency: '15',
      awakeTimes: '1',
      feeling: 'normal',
      stressLevel: 5,
      screenTime: false
    },
    report: null
  },

  onLoad(options) {
    const pages = getCurrentPages();
    this.setData({ showBackButton: pages.length > 1 });
    this._checkExistingData();
  },

  /** 检查是否有历史数据可以预填 */
  _checkExistingData() {
    try {
      // 从本地存储取最近的 survey 或 chat 数据
      const lastSurvey = wx.getStorageSync('latest_survey_data') || {};
      const lastAnalysis = wx.getStorageSync('latest_analysis_result') || {};
      
      let hasData = lastSurvey.bedtime || lastAnalysis.surveyData;
      if (!hasData) return;

      // 提取最近一次数据
      const src = lastSurvey.bedtime ? lastSurvey : (lastAnalysis.surveyData || {});
      const bd = src.bedtime || '';
      const wk = src.wake_time || '';
      
      if (bd && wk) {
        const feelingMap = {
          'energetic': '精力充沛', 'refreshed': '神清气爽', 'normal': '一般般',
          'tired': '有点累', 'very_tired': '非常疲惫'
        };
        const feelingText = feelingMap[src.feeling] || '';
        this.setData({
          welcomeDesc: `检测到你有历史数据，可以快速确认或重新填写`,
          startBtnText: '继续评估',
          quickConfirmTitle: `上次记录: ${bd}上床 → ${wk}起床${feelingText ? ' · ' + feelingText : ''}\n和这次差不多吗？`,
          quickData: {
            bedtime: bd,
            wake_time: wk,
            sleepLatency: src.sleep_latency || src.sleepLatency || '15',
            awakeTimes: src.awake_times || src.awakeTimes || '1',
            feeling: src.feeling || 'normal',
            stressLevel: src.stress_level || src.stressLevel || 5,
            screenTime: src.screen_time || src.screenTime || false
          }
        });
      }
    } catch(e) {}
  },

  startSurvey() {
    // 如果有预填数据，先问确认
    if (this.data.quickConfirmTitle) {
      this.setData({ step: 2 });
    } else {
      this._beginQuestions();
    }
  },

  /** 用户确认数据相同，直接分析 */
  confirmYes() {
    this.submitQuick();
  },

  /** 用户说数据有变化，进完整问卷 */
  goFullSurvey() {
    this.setData({ quickConfirmTitle: '' });
    this._beginQuestions();
  },

  _beginQuestions() {
    this.setData({ step: 1, qIndex: 1, qTotal: 7, qProgress: Math.round(1/7*100) });
  },

  answerTime(e) {
    var type = e.currentTarget.dataset.type;
    var val = e.currentTarget.dataset.val;
    var nextIdx = this.data.qIndex + 1;
    var update = { qIndex: nextIdx, qProgress: Math.round(nextIdx / this.data.qTotal * 100) };
    if (type === 'bed') update['quickData.bedtime'] = val;
    if (type === 'wake') update['quickData.wake_time'] = val;
    this.setData(update);
  },

  answerValue(e) {
    var key = e.currentTarget.dataset.key;
    var val = e.currentTarget.dataset.val;
    var nextIdx = this.data.qIndex + 1;
    var update = { qIndex: nextIdx, qProgress: Math.round(nextIdx / this.data.qTotal * 100) };
    update['quickData.' + key] = val;
    this.setData(update);
  },

  answerScreen(e) {
    var answer = e.currentTarget.dataset.answer === 'true';
    this.setData({ 'quickData.screenTime': answer, qIndex: 8, qProgress: 100 });
  },

  // 统一提交入口
  submitQuick() {
    this.setData({ generating: true });
    var d = this.data.quickData;
    var surveyData = {
      bedtime: d.bedtime,
      wake_time: d.wake_time,
      sleep_latency: d.sleepLatency,
      awake_times: d.awakeTimes,
      feeling: d.feeling,
      stress_level: d.stressLevel,
      screen_time: d.screenTime,
      source: 'survey',
      sourceName: 'AI问卷评估'
    };

    wx.setStorageSync('latest_survey_data', surveyData);

    var self = this;
    var fallbackTimer = setTimeout(function() {
      self.fallbackLocal(surveyData);
    }, 8000);

    api.generateSleepReport(surveyData).then(function(result) {
      clearTimeout(fallbackTimer);
      if (result.report) {
        self.showReport(result.report, surveyData);
      } else {
        self.fallbackLocal(surveyData);
      }
    }).catch(function() {
      clearTimeout(fallbackTimer);
      self.fallbackLocal(surveyData);
    });
  },

  // 统一保存到全局存储
  saveFinalReport(report) {
    wx.setStorageSync('latest_analysis_result', report);
    wx.setStorageSync('latest_survey_data', report.surveyData || {});

    var history = wx.getStorageSync('report_history') || [];
    history.unshift({
      id: report.id,
      date: report.date,
      time: report.time,
      score: report.score,
      quality: report.quality,
      source: report.source,
      sourceName: report.sourceName
    });
    if (history.length > 50) history = history.slice(0, 50);
    wx.setStorageSync('report_history', history);

    this.setData({ report: report, step: 5, generating: false });
  },

  showReport(report, surveyData) {
    var localResult = sleepAlgorithm.analyze({
      totalDuration: this.calcDuration(surveyData),
      awakeTimes: parseInt(surveyData.awake_times) || 2,
      awakeDuration: (parseInt(surveyData.awake_times) || 2) * 8 + 5,
      sleepLatency: parseInt(surveyData.sleep_latency) || 15
    });

    var finalReport = {
      id: Date.now(),
      date: new Date().toLocaleDateString(),
      time: new Date().toLocaleString(),
      score: report.score || localResult.score || 75,
      quality: report.quality || localResult.quality || '良好',
      duration: localResult.duration || '7h 30m',
      type: 'AI深度分析',
      source: 'survey',
      sourceName: 'AI问卷评估',
      isAIGenerated: true,
      detailedAnalysis: report.detailedAnalysis || report.analysis || '',
      details: report.details || localResult.details || {},
      healthScores: report.healthScores || localResult.healthScores || {},
      sleepStages: localResult.sleepStages || [],
      trends: localResult.trends || { scoreTrend: '+1', durationTrend: '+15m', efficiencyTrend: '+2%' },
      suggestions: report.suggestions || localResult.suggestions || [],
      surveyData: surveyData
    };

    this.saveFinalReport(finalReport);
  },

  fallbackLocal(surveyData) {
    var result = sleepAlgorithm.analyze({
      totalDuration: this.calcDuration(surveyData),
      awakeTimes: parseInt(surveyData.awake_times) || 2,
      awakeDuration: (parseInt(surveyData.awake_times) || 2) * 8 + 5,
      sleepLatency: parseInt(surveyData.sleep_latency) || 15
    });

    var finalReport = {
      id: Date.now(),
      date: new Date().toLocaleDateString(),
      time: new Date().toLocaleString(),
      score: result.score || 75,
      quality: result.quality || '良好',
      duration: result.duration || '7h 30m',
      type: '本地算法分析',
      source: 'survey',
      sourceName: 'AI问卷评估',
      isAIGenerated: false,
      detailedAnalysis: '',
      details: result.details || {},
      healthScores: result.healthScores || {},
      sleepStages: result.sleepStages || [],
      trends: result.trends || { scoreTrend: '0', durationTrend: 'stable' },
      suggestions: result.suggestions || [],
      surveyData: surveyData
    };

    this.saveFinalReport(finalReport);
  },

  calcDuration(surveyData) {
    var bed = (surveyData.bedtime || '23:00').match(/(\d+):(\d+)/);
    var wake = (surveyData.wake_time || '07:00').match(/(\d+):(\d+)/);
    if (bed && wake) {
      var bh = parseInt(bed[1]), bm = parseInt(bed[2]);
      var wh = parseInt(wake[1]), wm = parseInt(wake[2]);
      if (wh < bh) wh += 24;
      return Math.max(180, (wh - bh) * 60 + (wm - bm) - (parseInt(surveyData.sleep_latency) || 15));
    }
    return 450;
  },

  doAnotherAnalysis() {
    this.setData({ step: 0, qIndex: 0, report: null, generating: false });
  },

  copyReport() {
    var r = this.data.report;
    if (!r) return;
    var text = '=== AI睡眠分析报告 ===\n';
    text += '评分: ' + r.score + '分 (' + r.quality + ')\n';
    text += '上床: ' + (r.surveyData?.bedtime || '--') + '\n';
    text += '起床: ' + (r.surveyData?.wake_time || '--') + '\n';
    text += '入睡: ' + (r.surveyData?.sleep_latency || 0) + '分钟\n';
    text += '醒来: ' + (r.surveyData?.awake_times || 0) + '次\n';
    if (r.suggestions && r.suggestions.length > 0) {
      text += '\n改善建议:\n';
      for (var i = 0; i < r.suggestions.length; i++) {
        text += (i + 1) + '. ' + r.suggestions[i] + '\n';
      }
    }
    wx.setClipboardData({ data: text, success: function() {
      wx.showToast({ title: '已复制到剪贴板', icon: 'success' });
    }});
  },

  viewHistory() { wx.navigateTo({ url: '/pages/history/history' }); },
  viewReport() { wx.navigateTo({ url: '/pages/report/report' }); },

  goBack() {
    var pages = getCurrentPages();
    if (pages.length > 1) wx.navigateBack();
    else wx.switchTab({ url: '/pages/index/index' });
  },

  onShareAppMessage() {
    var score = this.data.report ? this.data.report.score : 0;
    return { title: '我的AI睡眠报告 - ' + score + '分', path: '/pages/survey/survey' };
  }
});
