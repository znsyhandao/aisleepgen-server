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
    insights: [],        // 智能洞察列表
    showInsights: false,
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

  _buildInsights(stats) {
    const insights = [];
    const scores = (stats.recent_scores || []).map(s => s.score).filter(s => s !== null && s > 0);
    const avg = stats.avg_score || 0;
    const streak = stats.streak_days || 0;
    const relaxStats = stats.relax_stats || {};
    const relaxSessions = relaxStats.total_sessions || 0;
    const relaxStreak = relaxStats.relax_streak_days || 0;

    // 1. 首次使用
    if (scores.length === 0) {
      insights.push({
        icon: '👋',
        text: '欢迎使用！今晚的记录一下睡眠，我会为你分析',
        type: 'welcome',
      });
      return insights;
    }

    // 2. 连续记录里程碑
    if (streak >= 7) {
      insights.push({
        icon: '🔥',
        text: '太棒了！已连续记录' + streak + '天，这是了不起的习惯',
        type: 'milestone',
      });
    } else if (streak >= 3) {
      insights.push({
        icon: '🔥',
        text: '已连续记录' + streak + '天，坚持就是胜利',
        type: 'milestone',
      });
    }

    // 3. 趋势洞察（近3天方向）
    const last3 = scores.slice(-3);
    if (last3.length >= 3) {
      if (last3[0] > last3[1] && last3[1] > last3[2]) {
        insights.push({
          icon: '📉',
          text: '最近3天评分持续下降，今天注意多休息',
          type: 'trend_down',
        });
      } else if (last3[0] < last3[1] && last3[1] < last3[2]) {
        insights.push({
          icon: '📈',
          text: '最近3天评分持续上升，继续保持！',
          type: 'trend_up',
        });
      }
    }

    // 4. 总记录数里程碑
    const total = stats.total_sessions || 0;
    if (total >= 10) {
      insights.push({
        icon: '🏅',
        text: '已有' + total + '次睡眠记录，你的数据画像越来越丰富了',
        type: 'milestone',
      });
    }

    // 5. 放松练习鼓励
    if (relaxSessions >= 5) {
      insights.push({
        icon: '🧘',
        text: '做了' + relaxSessions + '次呼吸练习，放松习惯很棒',
        type: 'positive',
      });
    } else if (relaxSessions > 0 && streak >= 2) {
      insights.push({
        icon: '💡',
        text: '做呼吸练习可以帮助改善睡眠，今晚试试？只需3分钟',
        type: 'suggestion',
      });
    }

    // 6. 放松连续天数
    if (relaxStreak >= 3) {
      insights.push({
        icon: '🎯',
        text: '已连续' + relaxStreak + '天做放松练习，效果会越来越好',
        type: 'positive',
      });
    }

    // 7. 总天数里程碑
    const totalDays = stats.total_days || 0;
    if (totalDays >= 30) {
      insights.push({
        icon: '🌟',
        text: '使用满30天！你的睡眠数据已经有足够深度了',
        type: 'milestone',
      });
    }

    return insights.slice(0, 5); // 最多5条
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
      
      // 趋势检测：最近3天连续下降？
      let trendWarning = '';
      let trendDir = 'stable';
      let trendDiff = 0;
      const lastScores = scores.filter(s => s !== null && s > 0);
      if (lastScores.length >= 3) {
        const last3 = lastScores.slice(-3);
        const last2 = lastScores.slice(-2);
        if (last3[0] > last3[1] && last3[1] > last3[2]) {
          trendWarning = '您最近3天睡眠持续下降，今晚注意放松哦';
          trendDir = 'down';
        } else if (last3[0] < last3[1] && last3[1] < last3[2]) {
          trendDir = 'up';
        }
        // 每条柱的dropFlag
        for (let i = 1; i < lastScores.length; i++) {
          if (lastScores[i] < lastScores[i-1]) {
            lastScores._dropFlags = lastScores._dropFlags || {};
            lastScores._dropFlags[i] = true;
          }
        }
      }
      
      // 标记chartData的下降柱
      let chartData = scores.map((s, i) => {
        let dropFlag = false;
        if (lastScores._dropFlags && lastScores._dropFlags[i]) dropFlag = true;
        return { value: s, label: labels[i], dropFlag };
      });
      
      // 智能洞察引擎
      const insights = this._buildInsights(stats);

      this.setData({
        weekAvg: avg,
        streakDays: stats.streak_days || 0,
        chartData: chartData,
        showChart: valid.length > 0,
        insights: insights,
        showInsights: insights.length > 0,
        trendDir: trendDir,
        trendDiff: trendDiff,
        trendWarning: trendWarning,
        showStats: valid.length > 0 && typeof avg === 'number',
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
      record: '/pages/record/record',
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
