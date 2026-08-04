// pages/analyze/analyze.js — AI 睡眠数据看板
const api = require('../../utils/api');

Page({
  data: {
    loading: true,
    // 顶部统计
    avgScore: '--',
    streakDays: 0,
    totalDays: 0,
    totalSessions: 0,
    // 7天趋势
    chartScores: [],
    chartLabels: [],
    showChart: false,
    // 干预效果对比
    relaxTotal: 0,
    relaxCompleted: 0,
    relaxAvgDuration: 0,
    relaxStreakDays: 0,
    stressTypes: {},
    // 最近记录
    records: [],
    // 评分趋势方向
    trend: 'stable', // up / down / stable
    trendLabel: '',
  },

  onLoad() { this.refresh(); },
  onShow() { this.refresh(); },

  refresh() {
    this.setData({ loading: true });
    
    // 从后端获取睡眠统计
    api.getSleepStats().then(stats => {
      const scores = (stats.recent_scores || []).filter(s => s.score !== null && s.score > 0);
      const labels = scores.map(s => {
        const p = s.date.split('-');
        return p[1] + '/' + p[2];
      });
      const valid = scores.length;
      const avg = valid > 0 ? Math.round(scores.reduce((a,b) => a + b.score, 0) / valid) : '--';

      // 判断趋势方向
      let trend = 'stable';
      let trendLabel = '';
      if (valid >= 3) {
        const recent = scores.map(s => s.score);
        const first = recent[0];
        const last = recent[recent.length - 1];
        if (last > first + 3) { trend = 'up'; trendLabel = '↑ 趋势上升'; }
        else if (last < first - 3) { trend = 'down'; trendLabel = '↓ 趋势下降'; }
        else { trendLabel = '→ 趋于稳定'; }
      }

      const rs = stats.relax_stats || {};
      const stressTypes = rs.stress_type_distribution || {};

      this.setData({
        avgScore: avg,
        streakDays: stats.streak_days || 0,
        totalDays: stats.total_days || 0,
        totalSessions: stats.total_sessions || 0,
        chartScores: scores.map(s => s.score),
        chartLabels: labels,
        showChart: valid > 1,
        trend: trend,
        trendLabel: trendLabel,
        relaxTotal: rs.total_sessions || 0,
        relaxCompleted: rs.completed_sessions || 0,
        relaxAvgDuration: rs.avg_duration || 0,
        relaxStreakDays: rs.relax_streak_days || 0,
        stressTypes: Object.keys(stressTypes).length > 0 ? stressTypes : {},
        loading: false,
      });
    }).catch(() => {
      // fallback: 本地存储
      const lastResult = wx.getStorageSync('latest_analysis_result');
      const history = wx.getStorageSync('analysis_history') || [];
      this.setData({
        avgScore: lastResult && lastResult.score ? lastResult.score : '--',
        records: history.slice(0, 10),
        loading: false,
      });
      // 加载深度洞察
      this.loadInsights();
    });

    // 取历史记录
    const history = wx.getStorageSync('analysis_history') || [];
    this.setData({ records: history.slice(0, 10) });
  },

  startAnalysis() {
    wx.navigateTo({ url: '/pages/survey/survey' });
  },

  viewDetail(e) {
    const idx = e.currentTarget.dataset.index;
    const record = this.data.records[idx];
    if (record) {
      wx.setStorageSync('viewing_report', record);
      wx.navigateTo({ url: '/pages/report/report' });
    }
  },

  goToHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  /** ===== 深度洞察加载 ===== */
  loadInsights() {
    const that = this;
    wx.request({
      url: api.baseUrl + '/api/sleep-insights',
      data: {},
      success(res) {
        const data = res.data || {};
        const ins = data.insights || {};
        const cards = [];

        // 1. 模式分析
        if (ins.pattern && ins.pattern.status === 'normal') {
          const names = (ins.pattern.components || []).map(c => c.name).filter(Boolean);
          cards.push({
            type: 'pattern',
            icon: '🧠',
            title: '你的睡眠模式',
            desc: names.length ? '主要模式: ' + names.join(', ') : '数据正常',
            detail: ins.pattern,
          });
        } else if (ins.pattern && ins.pattern.status === 'anomaly') {
          cards.push({
            type: 'pattern',
            icon: '⚠️',
            title: '检测到异常模式',
            desc: (ins.pattern.anomalies || []).join(', ') || '未知异常',
            detail: ins.pattern,
          });
        }

        // 2. 未来预测
        if (ins.forecast) {
          const trend = ins.forecast.trend || '→';
          const finalScore = ins.forecast.days && ins.forecast.days.length > 0
            ? ins.forecast.days[ins.forecast.days.length-1].predicted : '?';
          cards.push({
            type: 'forecast',
            icon: trend.includes('改善') ? '📈' : trend.includes('下降') ? '📉' : '📊',
            title: trend + ' 趋势',
            desc: ins.forecast.story || '5天趋势预测',
            detail: ins.forecast,
            finalScore: finalScore,
          });
        }

        // 3. 因果链
        if (ins.causal_chain) {
          const edges = ins.causal_chain.edges || [];
          const topLink = edges.length > 0
            ? edges[0].from + '→' + edges[0].to
            : '无显著关联';
          cards.push({
            type: 'causal',
            icon: '🔗',
            title: '关键因素关联',
            desc: topLink,
            detail: ins.causal_chain,
            edgeCount: edges.length,
          });
        }

        // 4. 相似历史
        if (ins.similar_past && ins.similar_past.length > 0) {
          const top = ins.similar_past[0];
          cards.push({
            type: 'similar',
            icon: '🔄',
            title: '历史相似记录',
            desc: top.text || '发现相关模式',
            similarity: top.similarity || 0,
            detail: ins.similar_past,
          });
        }

        // 5. 偏好学习
        if (ins.preference) {
          const total = ins.preference.total_feedback || 0;
          cards.push({
            type: 'preference',
            icon: '🎯',
            title: '个性化学习',
            desc: total > 0 ? '已学习' + total + '条反馈' : '暂无反馈数据',
            totalFeedback: total,
            detail: ins.preference,
          });
        }

        that.setData({ insightCards: cards, insightsLoaded: true });
      },
      fail() {
        that.setData({ insightsLoaded: true });
      }
    });
  },
});
