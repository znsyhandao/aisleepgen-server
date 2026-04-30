// pages/analyze/analyze.js — 极简版
const api = require('../../utils/api');

Page({
  data: {
    lastScore: '--',
    records: [],
    loading: true,
  },

  onLoad() {
    this.loadData();
  },

  onShow() {
    this.loadData();
  },

  loadData() {
    this.setData({ loading: true });

    // 从本地存读取最近的评分和记录
    const lastResult = wx.getStorageSync('latest_analysis_result');
    const history = wx.getStorageSync('analysis_history') || [];

    this.setData({
      lastScore: lastResult && lastResult.score ? lastResult.score : '--',
      records: history.slice(0, 10),
      loading: false,
    });
  },

  startAnalysis() {
    wx.navigateTo({
      url: '/pages/survey/survey'
    });
  },

  viewDetail(e) {
    const idx = e.currentTarget.dataset.index;
    const record = this.data.records[idx];
    if (record) {
      wx.setStorageSync('viewing_report', record);
      wx.navigateTo({ url: '/pages/report/report' });
    }
  },
});
