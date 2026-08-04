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
      { value: 'insomnia', label: '\u{1F62B} 睡不着' },
      { value: 'anxiety', label: '\u{1F630} 焦虑紧张' },
      { value: 'stress', label: '\u{1F624} 压力大' },
      { value: 'shallow', label: '\u{1F634} 睡不深' },
    ],
    sleepTypes: [
      { value: 'night_owl', label: '\u{1F989} 夜猫子（12点后睡）' },
      { value: 'normal', label: '\u{1F319} 正常（11点左右）' },
      { value: 'early_bird', label: '\u{1F305} 早睡早起（10点前）' },
    ],
    stressLevels: [
      { value: 'low', label: '\u{1F60A} 还好' },
      { value: 'medium', label: '\u{1F610} 一般' },
      { value: 'high', label: '\u{1F62B} 挺大的' },
    ],
    soundPrefs: [
      { value: 'ocean', label: '\u{1F30A} 海浪' },
      { value: 'rain', label: '\u{1F327} 雨声' },
      { value: 'silence', label: '\u{1F92B} 安静' },
    ],
    durationPrefs: [
      { value: 'short', label: '\u23F1 短（3轮）' },
      { value: 'medium', label: '\u23F1 中（5轮）' },
      { value: 'long', label: '\u23F1 长（8轮）' },
    ],
    allAnswered: false,
    // ISI 复查模式（只做ISI不做onboarding）
    isiOnlyMode: false,
    // ISI 失眠评估
    isiQuestions: [
      '入睡困难的严重程度？',
      '维持睡眠困难（半夜醒）的严重程度？',
      '早醒（醒后无法再入睡）的严重程度？',
      '你对当前睡眠模式满意吗？',
      '睡眠问题干扰日常功能的程度？',
      '别人是否注意到你的睡眠问题影响了你的生活质量？',
      '你对自己的睡眠问题感到担忧/痛苦吗？',
    ],
    isiLabels: ['无', '轻微', '中等', '严重', '极重'],
    isiAnswers: [0, 0, 0, 0, 0, 0, 0],
    isiTotal: 0,
    isiSeverityText: '',
  },

  onLoad: function (options) {
    var that = this;
    options = options || {};

    if (options.mode === 'isi_only') {
      // 复查模式：只显示ISI部分
      that.setData({ isiOnlyMode: true, allAnswered: true });
    }

    api.getUserProfile().then(function (res) {
      if (res.onboarding_done && !options.mode) {
        wx.switchTab({ url: '/pages/chat/chat' });
      }
    }).catch(function () {});
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

  isiSlide(e) {
    var idx = e.currentTarget.dataset.index;
    var answers = this.data.isiAnswers.slice();
    answers[idx] = e.detail.value;
    var total = answers.reduce(function (a, b) { return a + b; }, 0);
    var text = total <= 7 ? '无临床意义' : total <= 14 ? '轻度失眠' : total <= 21 ? '中度失眠' : '重度失眠';
    this.setData({ isiAnswers: answers, isiTotal: total, isiSeverityText: text });
  },

  _checkAll() {
    var s = this.data.survey;
    var allDone = s.main_issue && s.sleep_type && s.stress_level && s.sound_pref && s.duration_pref;
    this.setData({ allAnswered: !!allDone });
  },

  submitSurvey() {
    try {
      var s = this.data.survey;
      var that = this;
      if (!s.main_issue || !s.sleep_type || !s.stress_level || !s.sound_pref || !s.duration_pref) {
        wx.showToast({ title: '请回答所有问题', icon: 'none' });
        return;
      }

      wx.showLoading({ title: '正在初始化\u2026' });

      var app = getApp();
      var isiData = { openid: (app && app.globalData && app.globalData.openid) || 'default', answers: {}, source: 'initial' };
      var hasIsi = false;
      var isiKeys = ['q1','q2','q3','q4','q5','q6','q7'];
      for (var i = 0; i < 7; i++) {
        var q = isiKeys[i];
        var v = that.data.isiAnswers[i];
        if (v !== undefined && v !== null) {
          isiData.answers[q] = v;
          hasIsi = true;
        }
      }

      // 不等待API返回，立刻跳转
      api.submitOnboardingSurvey(s).catch(function(){});
      if (hasIsi) {
        api.isiSubmit(isiData).catch(function(){});
      }
      wx.hideLoading();
      console.log('[Onboarding] hiding loading, now switching tab');
      setTimeout(function () {
        wx.switchTab({ url: '/pages/chat/chat' });
      }, 100);
    } catch (e) {
      wx.hideLoading();
      console.error('[Onboarding] submitSurvey error:', e);
    }
  },

  // ISI复查专用：跳过onboarding问卷，只提交ISI
  submitISIOnly: function () {
    var that = this;
    var isiData = { answers: {}, source: 'biweekly' };
    var isiKeys = ['q1','q2','q3','q4','q5','q6','q7'];
    for (var i = 0; i < 7; i++) {
      isiData.answers[isiKeys[i]] = that.data.isiAnswers[i];
    }

    wx.showLoading({ title: '\u63D0\u4EA4\u4E2D\u2026' });
    api.isiSubmit(isiData).then(function () {
      wx.hideLoading();
      wx.showToast({ title: '\u590D\u67E5\u5DF2\u5B8C\u6210\uFF0C\u611F\u8C22\u4F60\u7684\u53C2\u4E0E \u{1F31F}', icon: 'none' });
      setTimeout(function () {
        wx.navigateBack();
      }, 1200);
    }).catch(function (err) {
      wx.hideLoading();
      wx.showToast({ title: '\u63D0\u4EA4\u5931\u8D25\uFF0C\u8BF7\u91CD\u8BD5', icon: 'none' });
      console.warn('[ISI] submit error:', err);
    });
  },
});
