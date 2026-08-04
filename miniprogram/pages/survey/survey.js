// pages/survey/survey.js — 三步睡眠记录向导
const api = require('../../utils/api');

Page({
  data: {
    showBack: true,
    step: 1,
    progress: 1,
    saving: false,
    data: {
      bedtime: null,
      latency: null,
      awakeTimes: null,
      duration: null,
    },
    canSubmit: false,
  },

  onLoad() {
    var pages = getCurrentPages();
    this.setData({ showBack: pages.length > 1 });
  },

  // ===== 步骤1：入睡时间 =====
  selectBedtime(e) {
    var time = e.currentTarget.dataset.time;
    this.setData({ 'data.bedtime': time });
  },

  // ===== 步骤2：入睡时长 =====
  selectLatency(e) {
    var min = e.currentTarget.dataset.min;
    this.setData({ 'data.latency': min });
  },

  // ===== 步骤3：醒来次数 + 时长 =====
  selectAwake(e) {
    var times = e.currentTarget.dataset.times;
    this.setData({ 'data.awakeTimes': times }, () => {
      this._checkCanSubmit();
    });
  },

  selectDuration(e) {
    var hours = e.currentTarget.dataset.hours;
    this.setData({ 'data.duration': hours }, () => {
      this._checkCanSubmit();
    });
  },

  _checkCanSubmit() {
    var d = this.data.data;
    this.setData({ canSubmit: d.awakeTimes !== null && d.duration !== null });
  },

  // ===== 导航 =====
  nextStep() {
    var next = Math.min(this.data.step + 1, 3);
    this.setData({ step: next, progress: next });
  },

  prevStep() {
    var prev = Math.max(this.data.step - 1, 1);
    this.setData({ step: prev, progress: prev });
  },

  goBack() {
    wx.navigateBack();
  },

  // ===== 提交流程 =====
  submitSurvey() {
    if (!this.data.canSubmit) return;

    var d = this.data.data;
    this.setData({ saving: true });

    // 计算起床时间 = 入睡时间 + 入睡时长 + 总睡眠时长
    var hour = parseInt(d.bedtime.split(':')[0]);
    var bedtimeHour = hour;
    var latencyMin = parseInt(d.latency);
    var durHours = parseInt(d.duration);
    var wakeHour = (hour + Math.ceil((latencyMin + durHours * 60) / 60)) % 24;

    var surveyData = {
      bedtime: d.bedtime,
      wake_time: wakeHour + ':00',
      sleep_latency: latencyMin,
      total_duration: durHours * 60,
      awake_times: parseInt(d.awakeTimes),
    };

    var openid = wx.getStorageSync('aisleepgen_openid') || wx.getStorageSync('openid') || 'default';

    // 保存到 user profile
    api.request('/api/update-profile', {
      openid: openid,
      profile: {
        latest: surveyData,
        user_info: {
          main_issue: '入睡困难',
          bedtime: d.bedtime,
          awake_times: parseInt(d.awakeTimes),
          sleep_latency: latencyMin,
          duration_pref: durHours + '小时',
        },
        last_survey: new Date().toISOString(),
      }
    })
    .then(() => {
      // 添加到历史记录
      return api.request('/api/update-profile', {
        openid: openid,
        profile: {
          history: [{
            date: new Date().toISOString().slice(0, 10),
            wm_score: 0,
            total_duration: durHours * 60,
            bedtime: d.bedtime,
            sleep_latency: latencyMin,
            awake_times: parseInt(d.awakeTimes),
          }]
        }
      });
    })
    .then(() => {
      this.setData({ saving: false });
      wx.showToast({ title: '已记录', icon: 'success', duration: 1500 });
      // 跳转到首页看结果
      setTimeout(() => {
        wx.switchTab({ url: '/pages/chat/chat' });
      }, 1500);
    })
    .catch(err => {
      console.warn('[Survey] Save error:', err);
      this.setData({ saving: false });
      wx.showToast({ title: '保存失败', icon: 'none' });
    });
  },
});
