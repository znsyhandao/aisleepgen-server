const api = require('../../utils/api');

Page({
  data: {
    survey: {
      main_issue: '',
      sleep_type: '',
      stress_level: '',
      sound_pref: '',
      duration_pref: '',
    },
    issues: [
      { value: 'insomnia', label: '😫 睡不着' },
      { value: 'anxiety', label: '😰 焦虑紧张' },
      { value: 'stress', label: '😤 压力大' },
      { value: 'shallow', label: '😴 睡不深' },
    ],
    sleepTypes: [
      { value: 'night_owl', label: '🦉 夜猫子（12点后睡）' },
      { value: 'normal', label: '🌙 正常（11点左右）' },
      { value: 'early_bird', label: '🌅 早睡早起（10点前）' },
    ],
    stressLevels: [
      { value: 'low', label: '😊 还好' },
      { value: 'medium', label: '😐 一般' },
      { value: 'high', label: '😫 挺大的' },
    ],
    soundPrefs: [
      { value: 'ocean', label: '🌊 海浪' },
      { value: 'rain', label: '🌧️ 雨声' },
      { value: 'silence', label: '🤫 安静' },
    ],
    durationPrefs: [
      { value: 'short', label: '⏱️ 短（3轮）' },
      { value: 'medium', label: '⏱️ 中（5轮）' },
      { value: 'long', label: '⏱️ 长（8轮）' },
    ],
    allAnswered: false,
  },

  onLoad() {
    // 已经填过问卷的不要再来
    api.getUserProfile().then(res => {
      if (res.onboarding_done) {
        wx.switchTab({ url: '/pages/chat/chat' });
      }
    }).catch(() => {});
  },

  selectIssue(e) {
    this.setData({ 'survey.main_issue': e.currentTarget.dataset.value });
    this._checkAll();
  },

  selectSleepType(e) {
    this.setData({ 'survey.sleep_type': e.currentTarget.dataset.value });
    this._checkAll();
  },

  selectStressLevel(e) {
    this.setData({ 'survey.stress_level': e.currentTarget.dataset.value });
    this._checkAll();
  },

  selectSoundPref(e) {
    this.setData({ 'survey.sound_pref': e.currentTarget.dataset.value });
    this._checkAll();
  },

  selectDurationPref(e) {
    this.setData({ 'survey.duration_pref': e.currentTarget.dataset.value });
    this._checkAll();
  },

  _checkAll() {
    var s = this.data.survey;
    var allDone = s.main_issue && s.sleep_type && s.stress_level && s.sound_pref && s.duration_pref;
    this.setData({ allAnswered: !!allDone });
  },

  submitSurvey() {
    var s = this.data.survey;
    if (!s.main_issue || !s.sleep_type || !s.stress_level || !s.sound_pref || !s.duration_pref) {
      wx.showToast({ title: '请回答所有问题', icon: 'none' });
      return;
    }

    wx.showLoading({ title: '正在初始化…' });
    api.submitOnboardingSurvey(s)
      .then(() => {
        wx.hideLoading();
        wx.showToast({ title: '已了解你的睡眠习惯 🌙', icon: 'none' });
        setTimeout(() => {
          wx.switchTab({ url: '/pages/chat/chat' });
        }, 1200);
      })
      .catch(err => {
        wx.hideLoading();
        wx.showToast({ title: '提交失败，请重试', icon: 'none' });
        console.warn('[Onboarding] submit error:', err);
      });
  },
});
