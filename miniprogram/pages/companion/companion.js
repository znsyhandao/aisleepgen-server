// companion.js — 睡眠AI陪伴模式
// 从呼吸页面改造：保留呼吸动画 + 连接后端状态机

const api = require('../../utils/api');

Page({
  data: {
    // 协议
    protocol: '4-7-8',
    protocolLabel: '4-7-8 呼吸法',
    companionActive: true,
    companionDone: false,

    // 呼吸动画
    showBreathCircle: true,
    showScanArea: false,
    showMonitorArea: false,
    showReleaseArea: false,
    breathPhase: 'inhale',
    breathPhaseText: '吸气',
    breathCount: 4,
    scale: 1,
    breathTimer: null,

    // 扫描
    currentAreaIndex: -1,

    // 监测
    monitorPulse: false,
    guideText: '',
    guideHint: '',

    // 音频
    soundOn: true,
    _audioCtx: null,
    _pollTimer: null,
    _startTime: 0,

    // 粒子
    particles: [],
    canvasReady: false,
  },

  onLoad(e) {
    var protocol = e.protocol || '4-7-8';
    var fromChat = e.from_chat === 'true';
    var message = e.message || '';

    this.setData({
      protocol: protocol,
      fromChat: fromChat,
    });

    // 启动陪伴
    this._startCompanion(protocol, message);
  },

  onUnload() {
    this._cleanup();
  },

  // ===== 启动陪伴 =====
  _startCompanion(protocol, message) {
    var self = this;

    api.startCompanion(protocol, message).then(res => {
      console.log('[Companion] Started:', res.state);

      self.setData({
        protocolLabel: res.protocol_name || protocol,
        companionActive: true,
        showBreathCircle: true,
        guideText: res.intro || '',
      });

      self._startTime = Date.now();

      // 启动白噪音
      self._startAmbientSound();

      // 启动粒子
      self._initParticles();

      // 启动轮询
      self._startPolling();

      // 2秒后发送第一个无体动反馈（开始引导）
      setTimeout(() => {
        self._sendFeedback({ movement_detected: false, time_elapsed: 2 });
      }, 2000);
    }).catch(err => {
      console.warn('[Companion] Start failed:', err);
      wx.showToast({ title: '启动失败', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
    });
  },

  // ===== 轮询更新 =====
  _startPolling() {
    var self = this;
    var lastTick = Date.now();

    function poll() {
      if (!self.data.companionActive || self.data.companionDone) {
        return;
      }

      var elapsed = (Date.now() - lastTick) / 1000;
      lastTick = Date.now();

      self._sendFeedback({
        movement_detected: false, // 小程序目前没有加速度计融合，默认为无体动
        time_elapsed: Math.min(elapsed, 5), // 限制最大步长
        user_cancel: false,
      });

      self.data._pollTimer = setTimeout(poll, 3000);
    }

    poll();
  },

  _sendFeedback(feedback) {
    var self = this;

    api.updateCompanion(feedback).then(res => {
      self._handleAction(res);
    }).catch(err => {
      console.warn('[Companion] Update failed:', err);
    });
  },

  _handleAction(action) {
    if (!action) return;

    var state = action.state || '';
    var actionType = action.action || '';
    var text = action.text || '';
    var duration = action.duration_s || 3;
    var hint = action.hint || '';

    // 更新指引文本
    this.setData({
      guideText: text,
      guideHint: hint,
    });

    // 根据状态切换UI
    if (state === 'CALMING' || state === 'RELAPSE') {
      this._showBreathing(action);
    } else if (state === 'GUIDING') {
      this._showScanning(action);
    } else if (state === 'MONITORING') {
      this._showMonitoring(action);
    } else if (state === 'RELEASE') {
      this._showRelease(action);
    } else if (state === 'EXIT' || actionType === 'exit') {
      this._showDone(action);
    }
  },

  _showBreathing(action) {
    var phase = action.phase || 'inhale';
    var text = action.text || '';
    var duration = action.duration_s || 4;
    var hint = action.hint || '';
    var scale = phase === 'inhale' ? 1.3 : (phase === 'exhale' ? 0.85 : 1.3);
    var phaseText = phase === 'inhale' ? '吸' : (phase === 'hold' ? '屏' : '呼');

    this.setData({
      showBreathCircle: true,
      showScanArea: false,
      showMonitorArea: false,
      showReleaseArea: false,
      breathPhase: phase,
      breathPhaseText: phaseText,
      breathCount: duration,
      scale: scale,
      guideHint: hint,
    });

    // 倒计时
    var self = this;
    if (this.data.breathTimer) clearInterval(this.data.breathTimer);
    var count = duration;
    this.data.breathTimer = setInterval(function() {
      count--;
      if (count <= 0) {
        clearInterval(self.data.breathTimer);
        self.data.breathTimer = null;
      }
      self.setData({ breathCount: Math.max(count, 0) });
    }, 1000);
  },

  _showScanning(action) {
    this.setData({
      showBreathCircle: false,
      showScanArea: true,
      showMonitorArea: false,
      showReleaseArea: false,
    });
  },

  _showMonitoring(action) {
    this.setData({
      showBreathCircle: false,
      showScanArea: false,
      showMonitorArea: true,
      showReleaseArea: false,
      monitorPulse: true,
    });
  },

  _showRelease(action) {
    this.setData({
      showBreathCircle: false,
      showScanArea: false,
      showMonitorArea: false,
      showReleaseArea: true,
    });

    // 渐弱音量
    if (this.data._audioCtx) {
      this.data._audioCtx.volume = 0.06;
    }
  },

  _showDone(action) {
    this.setData({
      companionActive: false,
      companionDone: true,
      showBreathCircle: false,
      showScanArea: false,
      showMonitorArea: false,
      showReleaseArea: false,
      guideText: '',
      guideHint: '',
    });

    // 停止轮询
    if (this.data._pollTimer) {
      clearTimeout(this.data._pollTimer);
      this.data._pollTimer = null;
    }

    // 渐弱音乐
    if (this.data._audioCtx) {
      this.data._audioCtx.stop();
    }

    // 自动返回
    setTimeout(() => {
      wx.navigateBack();
    }, 3000);
  },

  // ===== 用户操作 =====
  cancelCompanion() {
    var self = this;
    api.stopCompanion().then(() => {
      self._cleanup();
      wx.navigateBack();
    }).catch(() => {
      self._cleanup();
      wx.navigateBack();
    });
  },

  toggleSound() {
    if (this.data._audioCtx) {
      if (this.data.soundOn) {
        this.data._audioCtx.pause();
      } else {
        this.data._audioCtx.play();
      }
    }
    this.setData({ soundOn: !this.data.soundOn });
  },

  closeNow() {
    this.cancelCompanion();
  },

  goBack() {
    wx.navigateBack();
  },

  // ===== 音频 =====
  _startAmbientSound() {
    try {
      var inn = wx.createInnerAudioContext();
      inn.autoplay = true;
      inn.loop = true;
      inn.volume = 0.10;
      inn.obeyMuteSwitch = false;
      inn.src = 'https://music.163.com/song/media/outer/url?id=569213211.mp3';
      inn.onError(function(err) {
        console.log('[Companion] 白噪音加载失败:', err.errCode);
      });
      this.data._audioCtx = inn;
    } catch(er) {
      console.log('[Companion] 音频启动失败:', er);
    }
  },

  // ===== 粒子 =====
  _initParticles() {
    var self = this;
    var query = wx.createSelectorQuery();
    query.select('#particleCanvas').fields({ node: true, size: true }).exec(function(res) {
      if (!res || !res[0]) return;
      var canvas = res[0].node;
      var ctx = canvas.getContext('2d');
      var dpr = wx.getSystemInfoSync().pixelRatio;
      var w = res[0].width * dpr;
      var h = res[0].height * dpr;
      canvas.width = w;
      canvas.height = h;
      ctx.scale(dpr, dpr);
      var cw = res[0].width;
      var ch = res[0].height;

      var particles = [];
      for (var i = 0; i < 30; i++) {
        particles.push({
          x: Math.random() * cw,
          y: Math.random() * ch,
          r: Math.random() * 2 + 1,
          a: Math.random() * 0.3 + 0.1,
          vx: (Math.random() - 0.5) * 0.3,
          vy: -Math.random() * 0.2 - 0.1,
        });
      }

      function draw() {
        ctx.clearRect(0, 0, cw, ch);
        for (var p of particles) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fillStyle = 'rgba(150, 180, 255, ' + p.a + ')';
          ctx.fill();
          p.x += p.vx;
          p.y += p.vy;
          if (p.y < -10) { p.y = ch + 10; p.x = Math.random() * cw; }
          if (p.x < -10 || p.x > cw + 10) { p.x = Math.random() * cw; }
        }
        self._particleFrame = canvas.requestAnimationFrame(draw);
      }
      draw();
    });
  },

  // ===== 清理 =====
  _cleanup() {
    if (this.data._pollTimer) {
      clearTimeout(this.data._pollTimer);
      this.data._pollTimer = null;
    }
    if (this.data.breathTimer) {
      clearInterval(this.data.breathTimer);
      this.data.breathTimer = null;
    }
    if (this.data._audioCtx) {
      this.data._audioCtx.stop();
      this.data._audioCtx.destroy();
    }
    if (this._particleFrame) {
      this._particleFrame = null;
    }
  },
});
