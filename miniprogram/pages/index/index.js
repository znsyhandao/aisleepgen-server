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
    // 管家引擎
    butlerAlert: null,
    showBrief: false,
    briefExpanded: false,
    showBriefDetail: false,
    briefTitle: '',
    briefItems: [],
  },

  onLoad() {
    this.refresh();
    this.checkButler();
  },

  onShow() {
    this.refresh();
    this.checkButler();
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
      this.setData({
        weekAvg: avg,
        streakDays: stats.streak_days || 0,
        chartData: scores.map((s, i) => ({ value: s, label: labels[i] })),
        showChart: valid.length > 0,
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
});
