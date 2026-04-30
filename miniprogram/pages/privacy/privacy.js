// pages/privacy/privacy.js — 隐私协议/用户协议
Page({
  data: {
    tab: 'privacy', // privacy | terms
  },
  switchTab(e) {
    this.setData({ tab: e.currentTarget.dataset.tab });
  },
  goBack() {
    wx.navigateBack();
  }
});
