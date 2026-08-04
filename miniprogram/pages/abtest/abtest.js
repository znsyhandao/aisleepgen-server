// pages/abtest/abtest.js - A/B 实验管理
const api = require('../../utils/api');

Page({
  data: {
    loading: true,
    experiments: [],
    completedExperiments: [],
  },

  onLoad() {
    this.loadExperiments();
  },

  onShow() {
    if (!this.data.loading) {
      this.loadExperiments();
    }
  },

  loadExperiments() {
    var self = this;
    self.setData({ loading: true });

    api.getBizIntel('ab_testing').then(function(res)
      {
var running = res.running_experiments || res.experiments || [];
      var completed = res.completed_experiments || [];
      self.setData({
        experiments: running,
        completedExperiments: completed,
        loading: false,
      });
    }).catch(function() {
      // Fallback: try dashboard endpoint
      api.request('/api/dashboard', { openid: wx.getStorageSync('openid') || 'default' })
        .then(function(dash) {
          var ab = dash.ab_experiments || [];
          self.setData({
            experiments: ab,
            loading: false,
          });
        }).catch(function() {
          self.setData({
            experiments: [],
            loading: false,
          });
        });
    });
  },

  onShareAppMessage() {
    return { title: 'A/B 实验管理', path: '/pages/abtest/abtest' };
  },
});
