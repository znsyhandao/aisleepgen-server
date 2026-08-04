// pages/meditation/meditation.js - 沉浸式引导 v2
var api = require("../../utils/api");

Page({
  data: {
    pageName: 'meditation',
    showBackButton: true,
    status: 'loading',
    protocol: '',
    protocolName: '',
    totalDuration: 0,

    // 当前引导
    steps: [],
    currentStepIndex: 0,
    currentTime: 0,
    progress: 0,
    remaining: 0,

    // 圆环
    ringPercent: 0,
    ringAngle: 0,

    // 步进点（最多9个）
    visibleDots: [],

    // 轮次
    currentCycle: 0,

    // 声音
    bgSoundOn: false,
    ambient: {},

    // 评分
    rating: 0,

    // 协议 icon
    protocolIcons: {
      '4-7-8': '🌬️', 'box_breathing': '⬜', 'breathing': '🌊',
      'pursed_lip': '👄', 'body_scan': '🔍', 'pmr': '💪',
      'autogenic': '🪶', 'safe_place': '🏝️', 'cloud_float': '☁️',
      'sound_bath': '🎵', 'cognitive_unloading': '📓',
      'paradoxical_intention': '👁️', 'stimulus_control': '🛏️',
      'sleep_hygiene': '✅', 'cognitive_restructuring': '🧠'
    },
    protocolDescs: {
      '4-7-8': '深吸慢呼，快速镇定', 'box_breathing': '四拍等长呼吸',
      'breathing': '把注意力锚定在呼吸上', 'pursed_lip': '缩唇慢呼',
      'body_scan': '从头到脚逐一放松', 'pmr': '收紧-放松释放紧张',
      'autogenic': '自我暗示进入深度放松', 'safe_place': '在脑海中构建安全港湾',
      'cloud_float': '躺在云端', 'sound_bath': '声音洗涤身心',
      'cognitive_unloading': '把担忧写下来清空大脑',
      'paradoxical_intention': '努力保持清醒反而入睡',
      'stimulus_control': '重新建立床和睡眠的关联',
      'sleep_hygiene': '逐项优化睡眠环境',
      'cognitive_restructuring': '挑战不合理信念'
    }
  },

  onLoad(options) {
    var protocol = options.protocol || '4-7-8';
    var duration = options.duration || 5;
    this.setData({ protocol: protocol, status: 'loading' });
    this._loadPlan(protocol, duration);
  },

  _loadPlan(protocol, duration) {
    var self = this;
    api.request('/api/meditation-plan', {
      openid: self._getOpenid(),
      protocol: protocol,
      duration: parseInt(duration)
    }).then(function(res) {
      if (res && res.steps && res.steps.length > 0) {
        var total = res.total_duration || res.steps[res.steps.length - 1].second + 10;
        self.setData({
          steps: res.steps,
          protocolName: res.protocol_name || protocol,
          totalDuration: total,
          status: 'ready',
          currentTime: 0,
          currentStepIndex: 0,
          progress: 0,
          remaining: total,
          ringPercent: 0,
          visibleDots: self._calcDots(0, res.steps),
          currentCycle: res.steps[0] ? (res.steps[0].cycle || 0) : 0
        });

      // 应用场景氛围（背景色/文字色）
      if (res.ambient_atmosphere) {
        var atm = res.ambient_atmosphere;
        self.setData({ ambient: atm });
      }
      } else {
        self.setData({ status: 'ready', ambient: {} });
      }
    }).catch(function(err) {
      console.log('Load plan error:', err);
      self.setData({ status: 'ready', ambient: {} });
    });
  },

  _getOpenid() {
    try { return wx.getStorageSync('openid') || 'default'; } catch(e) { return 'default'; }
  },

  start() {
    if (this.data.status === 'playing') return;
    this.setData({ status: 'playing' });
    this._startTimer();
    this._reportComplete(false);
  },

  pause() {
    if (this.data.status !== 'playing') return;
    this.setData({ status: 'paused' });
    this._stopTimer();
  },

  resume() {
    if (this.data.status !== 'paused') return;
    this.setData({ status: 'playing' });
    this._startTimer();
  },

  stop() {
    this._stopTimer();
    this._reportComplete(false);
    wx.navigateBack();
  },

  complete() {
    this._stopTimer();
    this.setData({ status: 'completed', progress: 1, ringPercent: 100, ringAngle: 360 });
    this._reportComplete(true);
  },

  // 计时器 - 每秒更新一次降低setData频率
  _startTimer() {
    var self = this;
    this._stopTimer();
    this._tickCount = 0;

    this._timer = setInterval(function() {
      var ct = self.data.currentTime + 1;
      var total = self.data.totalDuration;
      if (total <= 0) { self.complete(); return; }

      var pct = Math.min(Math.round(ct / total * 100), 100);
      var remain = Math.max(total - ct, 0);

      self._tickCount++;

      // 1) 步骤变更检测（总是检查，但只在步骤变了时setData）
      var steps = self.data.steps;
      if (steps && steps.length > 0) {
        var idx = 0;
        for (var i = steps.length - 1; i >= 0; i--) {
          if (ct >= steps[i].second) { idx = i; break; }
        }
        if (idx !== self.data.currentStepIndex) {
          var update = { currentStepIndex: idx };
          if (steps[idx] && steps[idx].cycle) { update.currentCycle = steps[idx].cycle; }
          update.visibleDots = self._calcDots(idx, steps);
          self.setData(update);
          wx.vibrateShort({ type: 'light' }).catch(function() {});
        }
      }

      // 2) 进度更新：每3秒只刷一次（减少setData频率90%）
      if (self._tickCount % 3 === 0 && ct < self.data.totalDuration) {
        self.setData({
          currentTime: ct,
          remaining: remain,
          ringPercent: pct
        });
      }

      if (ct >= total) {
        self.complete();
      }
    }, 1000);
  },

  _stopTimer() {
    if (this._timer) {
      clearInterval(this._timer);
      this._timer = null;
    }
  },

  _updateCurrentStep(time) {
    var steps = this.data.steps;
    if (!steps || steps.length === 0) return;

    var idx = 0;
    for (var i = steps.length - 1; i >= 0; i--) {
      if (time >= steps[i].second) {
        idx = i;
        break;
      }
    }

    if (idx !== this.data.currentStepIndex) {
      var update = { currentStepIndex: idx };
      // 轮次
      if (steps[idx] && steps[idx].cycle) {
        update.currentCycle = steps[idx].cycle;
      }
      // 步进点
      update.visibleDots = this._calcDots(idx, steps);
      this.setData(update);

      // 振动
      wx.vibrateShort({ type: 'light' }).catch(function() {});
    }
  },

  // 计算可见步进点（当前步前后各4个，最多9个）
  _calcDots(idx, steps) {
    if (!steps || steps.length === 0) return [];
    var total = steps.length;
    var half = 4;
    var start = Math.max(0, idx - half);
    var end = Math.min(total, idx + half + 1);
    // 如果不够前4个，往后补
    if (end - start < 9 && end < total) {
      end = Math.min(total, start + 9);
    }
    // 如果不够后4个，往前补
    if (end - start < 9 && start > 0) {
      start = Math.max(0, end - 9);
    }

    var dots = [];
    for (var i = start; i < end; i++) {
      dots.push({
        active: i === idx,
        done: i < idx
      });
    }
    return dots;
  },

  formatTime(seconds) {
    if (seconds <= 0) return '完成';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return (m > 0 ? m + '分' : '') + s + '秒';
  },

  _reportComplete(completed) {
    try {
      api.request('/api/intervention-complete', {
        openid: this._getOpenid(),
        protocol: this.data.protocol,
        duration: Math.floor(this.data.currentTime / 60),
        completed: completed,
        rating: completed ? 5 : 0
      });
    } catch(e) {}
  },

  rate(e) {
    var rating = e.currentTarget.dataset.rating || 3;
    try {
      api.request('/api/intervention-complete', {
        openid: this._getOpenid(),
        protocol: this.data.protocol,
        duration: Math.floor(this.data.currentTime / 60),
        completed: true,
        rating: rating
      });
    } catch(e) {}
    wx.navigateBack();
  },

  _toggleSound() {
    this.setData({ bgSoundOn: !this.data.bgSoundOn });
  },

  onUnload() {
    this._stopTimer();
  }
});
