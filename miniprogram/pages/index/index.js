// pages/index/index.js — AI智能体时代版
const api = require('../../utils/api');

Page({
  data: {
    greeting: '早上好 🌅',
    dateStr: '',
    lastScore: '--',
    lastDuration: '--',
    lastQuality: '--',
    streakDays: 0,
    weekAvg: '--',
    chartData: [],
    showChart: false,
    // 极简情绪入口
    showMoodPicker: true,
    moodSelected: '',
    moodResult: null,
    // 管家引擎
    butlerAlert: null,
    showBrief: false,
    briefExpanded: false,
    showBriefDetail: false,
    briefTitle: '',
    briefItems: [],
    // 清醒的质量
    userRole: '',
    showRolePicker: false,
    decisionQuality: '',
    decisionColor: '',
    decisionConfidence: '--',
    mentalLoad: '--',
    showDecisionCard: false,
    // 韧性指数
    hasResilience: false,
    resilienceOverall: 0,
    resilienceLevel: '',
    resilienceLevelText: '',
    resilienceRingColor: '#667eea',
    resilienceRingDeg: 0,
    resilienceCircadian: 0,
    resilienceEmotion: 0,
    resiliencePhysical: 0,
    resilienceDetail: '',
  },

  onLoad() {
    this.initRole();
    this.refresh();
    this.checkButler();
    this._initABTest();
  },

  onShow() {
    this.refresh();
    this.checkButler();
    // 恢复上次的情绪选择（同一天内）
    var lastMood = wx.getStorageSync('last_mood');
    var lastDate = wx.getStorageSync('last_mood_date');
    if (lastMood && lastDate === new Date().toDateString()) {
      this.setData({ moodSelected: lastMood });
    }
  },

  // A/B测试分组
  _initABTest() {
    var app = getApp();
    var openid = app.globalData.openid || wx.getStorageSync('aisleepgen_openid') || 'anon';
    var variant = wx.getStorageSync('ab_variant');
    if (!variant) {
      // 简单哈希取模
      var hash = 0;
      for (var i = 0; i < openid.length; i++) {
        hash = ((hash << 5) - hash) + openid.charCodeAt(i);
        hash = hash & hash;
      }
      variant = Math.abs(hash) % 2 === 0 ? 'A' : 'B';
      wx.setStorageSync('ab_variant', variant);
    }
    this.setData({
      abVariant: variant,
      showMoodPicker: variant === 'B'
    });
  },

  // 埋点—情绪选择
  _trackMood(mood) {
    var app = getApp();
    var openid = app.globalData.openid || wx.getStorageSync('aisleepgen_openid') || 'anon';
    wx.request({
      url: require('../../utils/api').API_BASE + '/api/update-profile',
      method: 'POST',
      data: { openid: openid, last_mood: mood, last_mood_time: new Date().toISOString() },
      fail: function() {}
    });
  },

  // 埋点—冥想完成追踪
  _trackMeditation() {
    var variant = wx.getStorageSync('ab_variant') || 'A';
    var key = variant === 'B' ? 'ab_b_mood_count' : 'ab_a_mood_count';
    var count = wx.getStorageSync(key) || 0;
    wx.setStorageSync(key, count + 1);
  },

  // 醒来：角色初始化
  initRole() {
    const role = wx.getStorageSync('userRole');
    if (role) {
      this.setData({ userRole: role });
      if (role === 'founder') this.loadDecisionQuality();
    } else {
      // 新用户，显示角色选择弹窗
      this.setData({ showRolePicker: true });
    }
  },

  // 设置角色
  setRole(e) {
    const role = e.currentTarget.dataset.role;
    wx.setStorageSync('userRole', role);
    this.setData({ userRole: role, showRolePicker: false });
    if (role === 'founder') {
      this.loadDecisionQuality();
      // 通知后端
      var app = getApp();
      var openid = app.globalData.openid || wx.getStorageSync('aisleepgen_openid');
      if (openid) {
        wx.request({
          url: api.API_BASE + '/api/update-profile',
          method: 'POST',
          data: { openid: openid, role: role },
        });
      }
    }
  },

  // 加载决策质量数据
  loadDecisionQuality() {
    var app = getApp();
    var openid = app.globalData.openid || wx.getStorageSync('aisleepgen_openid');
    if (!openid) {
      // 需要先登录
      return;
    }
    var that = this;
    wx.request({
      url: api.API_BASE + '/api/decision-quality',
      method: 'POST',
      data: { openid: openid },
      success: function(r) {
        var dq = r.data;
        if (!dq) return;
        that.setData({
          decisionQuality: dq.decision_quality || '',
          decisionColor: dq.decision_color || '#888',
          decisionConfidence: dq.confidence ? (dq.confidence * 100).toFixed(0) + '%' : '--',
          mentalLoad: dq.mental_load || '--',
          showDecisionCard: true,
        });
      }
    });
  },

  refresh() {
    const now = new Date();
    const h = now.getHours();
    let g = '晚上好 🌙';
    if (h < 6) g = '夜深了 🌃';
    else if (h < 9) g = '早上好 🌅';
    else if (h < 12) g = '上午好 ☀️';
    else if (h < 14) g = '中午好 🌤';
    else if (h < 18) g = '下午好 🌇';
    const days = ['日','一','二','三','四','五','六'];
    const ds = now.getMonth()+1 + '月' + now.getDate() + '日 周' + days[now.getDay()];
    this.setData({ greeting: g, dateStr: ds });

    const last = wx.getStorageSync('latest_analysis_result');
    if (last) {
      this.setData({
        lastScore: last.score || '--',
        lastDuration: last.duration || '--',
        lastQuality: last.quality || '--',
      });
    }

    api.getSleepStats().then(stats => {
      const scores = (stats.recent_scores || []).map(s => s.score);
      const labels = (stats.recent_scores || []).map(s => {
        const p = s.date.split('-');
        return p[1] + '/' + p[2];
      });
      const valid = scores.filter(s => s !== null && s > 0);
      const avg = valid.length > 0 ? Math.round(valid.reduce((a,b) => a+b, 0) / valid.length) : '--';
      // 解析韧性指数
      const ri = stats.resilience_index || {};
      const hasResilience = ri && ri.overall > 0;
      const levelMap = { '优秀': '#4CAF50', '良好': '#667eea', '一般': '#FF9800', '偏弱': '#F44336', '薄弱': '#C62828' };
      const levelEngMap = { '优秀': 'excellent', '良好': 'good', '一般': 'fair', '偏弱': 'weak', '薄弱': 'poor' };
      const level = ri.level || '';
      const levelClass = levelEngMap[level] || '';
      const ringColor = levelMap[level] || '#667eea';
      this.setData({
        weekAvg: avg,
        streakDays: stats.streak_days || 0,
        chartData: scores.map((s, i) => ({ value: s, label: labels[i] })),
        showChart: valid.length > 0,
        hasResilience: hasResilience,
        resilienceOverall: ri.overall || 0,
        resilienceLevel: levelClass,
        resilienceLevelText: level,
        resilienceRingColor: ringColor,
        resilienceRingDeg: (ri.overall || 0) / 100 * 360,
        resilienceCircadian: (ri.dimensions && ri.dimensions.circadian_resilience) || 0,
        resilienceEmotion: (ri.dimensions && ri.dimensions.emotional_resilience) || 0,
        resiliencePhysical: (ri.dimensions && ri.dimensions.physical_resilience) || 0,
        resilienceDetail: ri.detail || '',
      });
    }).catch(() => {});
  },

  // 主动管家检测
  checkButler() {
    const that = this;
    api.butlerCheck().then(function(res) {
      var alert = null;
      if (res.alerts && res.alerts.length > 0) {
        var a = res.alerts[0];
        var iconMap = { warning: '📌', info: '💡', positive: '🎉' };
        var actionHintMap = {
          start_breathing: '开始呼吸练习',
          meditation: '开始冥想',
          white_noise: '播放白噪音',
        };
        var hint = '';
        if (a.actions && a.actions.length > 0) {
          hint = actionHintMap[a.actions[0]] || '';
        }
        alert = {
          type: a.type,
          icon: iconMap[a.level] || '💡',
          message: a.message,
          actions: a.actions || [],
          actionHint: hint,
        };
      }

      var showBrief = res.show_brief || false;
      var briefTitle = showBrief ? '📡 AI行业日报 · 点击查看' : '';

      that.setData({
        butlerAlert: alert,
        showBrief: showBrief,
        showBriefDetail: false,
        briefArrowText: '展开',
        briefTitle: briefTitle,
        briefItems: res.brief ? res.brief.ai_trends.concat(res.brief.sleep_science) : [],
      });
      that.data._butlerData = res;
    }).catch(function() {});
  },

  // 管家行为执行
  doButlerAction() {
    if (!this.data.butlerAlert || !this.data.butlerAlert.actions) return;
    var actions = this.data.butlerAlert.actions;
    if (actions.indexOf('start_breathing') >= 0) {
      wx.navigateTo({ url: '/pages/breathing/breathing' });
    } else if (actions.indexOf('meditation') >= 0) {
      wx.navigateTo({ url: '/pages/meditation/meditation' });
    } else if (actions.indexOf('white_noise') >= 0) {
      wx.navigateTo({ url: '/pages/meditation/meditation' });
    }
  },

  // 切换简报展开/收起
  toggleBrief() {
    var expanded = !this.data.briefExpanded;
    this.setData({ 
      briefExpanded: expanded, 
      showBriefDetail: expanded && this.data.showBrief,
      briefArrowText: expanded ? '收起' : '展开'
    });
    if (expanded) {
      api.markBriefRead();
    }
  },

  barHeight(val) {
    if (!val || val <= 0) return 2;
    return Math.min(Math.max(val * 0.7, 4), 100);
  },

  goToReport() {
    wx.navigateTo({ url: '/pages/report/report' });
  },

  goToFace() {
    wx.navigateTo({ url: '/pages/face-analyze/face-analyze' });
  },

  // 极简情绪入口
  onMoodTap(e) {
    const mood = e.currentTarget.dataset.mood;
    this.setData({ moodSelected: mood });
    this._trackMood(mood);
    // 记住本次选择
    wx.setStorageSync('last_mood', mood);
    wx.setStorageSync('last_mood_date', new Date().toDateString());
    var that = this;
    var app = getApp();
    var openid = app.globalData.openid || wx.getStorageSync('aisleepgen_openid') || 'temp_user';
    wx.request({
      url: require('../../utils/api').API_BASE + '/api/sleep/one-tap',
      method: 'POST',
      data: { mood: mood, openid: openid },
      success: function(r) {
        if (r.data && r.data.success) {
          that.setData({ moodResult: r.data });
        }
      }
    });
  },

  goMeditation(e) {
    const mid = e.currentTarget.dataset.mid;
    if (mid) {
      wx.setStorageSync('recommended_meditation', mid);
    }
    wx.navigateTo({ url: '/pages/meditation-player/meditation-player' });
  },

  goToPage(e) {
    const routes = {
      survey: '/pages/survey/survey',
      chat: '/pages/chat/chat',
      meditation: '/pages/meditation/meditation',
      history: '/pages/history/history',
    };
    const url = routes[e.currentTarget.dataset.page];
    if (!url) return;
    if (url === '/pages/chat/chat') {
      wx.switchTab({ url });
    } else {
      wx.navigateTo({ url });
    }
  },

  // 半夜语音唤醒
  goChatVoiceSleep() {
    wx.switchTab({
      url: '/pages/chat/chat?source=voice_sleep',
    });
  },
});
