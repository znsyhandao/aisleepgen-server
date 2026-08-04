// 科幻感沉浸式呼吸引导页 - 粒子系统 + 能量环 + 光晕渐变
Page({
  data: {
    phase: 'inhale',
    phaseText: '吸气',
    count: 4,
    round: 1,
    totalRounds: 5,
    breathName: '4-7-8 呼吸法',
    hintText: '慢慢吸入……',
    playing: true,
    done: false,
    progressPct: 0,
    soundOn: true,
    // 能量环参数
    ringRotation: 0,
    ringRotation2: 0,
    scale: 1,
    opacity: 1,
    // 光晕HSL插值
    glowHue: 190,    // 吸气起始
    glowSat: 80,
    glowLight: 60,
    // 粒子系统
    particles: [],
    canvasReady: false,
    _phases: [],
    _pi: 0,
    _interval: null,
    _particleInterval: null,
    _ringInterval: null,
    _startTime: 0,
    _audioCtx: null,
    _animFrame: null,
  },

  onLoad(e) {
    var p = {};
    try { 
      p = JSON.parse(decodeURIComponent(e.params || '{}')); 
    } catch(er) {
      if (e.inhale) p = e;
    }
    
    var inhale = parseInt(p.inhale) || 4;
    var hold = parseInt(p.hold) || 7;
    var exhale = parseInt(p.exhale) || 8;
    var rounds = parseInt(p.rounds) || 5;
    var name = p.name || '4-7-8 呼吸法';
    
    var phases = [
      { n: 'inhale', t: '吸气', d: inhale * 1000, hint: '慢慢吸入……' },
    ];
    if (hold > 0) {
      phases.push({ n: 'hold', t: '屏息', d: hold * 1000, hint: '轻轻屏住……' });
    }
    phases.push({ n: 'exhale', t: '呼气', d: exhale * 1000, hint: '缓缓呼出……' });
    
    this.data._phases = phases;
    this._startTime = Date.now();
    
    this.setData({ 
      totalRounds: rounds, 
      breathName: name,
      phaseText: phases[0].t,
      hintText: phases[0].hint,
      count: Math.floor(phases[0].d / 1000),
    });
    
    // 启动白噪音背景音
    this._startAmbientSound();
    
    // 启动粒子动画
    this._initParticles();
    
    // 启动能量环旋转
    this._startRingAnimation();
    
    var self = this;
    setTimeout(function() { self.nextPhase(); }, 600);
  },

  onReady() {
    // Canvas 就绪后初始化粒子
    var self = this;
    setTimeout(function() {
      self._initParticleCanvas();
    }, 500);
  },

  _initParticleCanvas() {
    var query = wx.createSelectorQuery();
    query.select('#particleCanvas').fields({ node: true, size: true }).exec(function(res) {
      if (!res || !res[0]) return;
      var canvas = res[0].node;
      if (!canvas) return;
      var ctx = canvas.getContext('2d');
      var dpr = wx.getSystemInfoSync().pixelRatio;
      var width = res[0].width;
      var height = res[0].height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
      
      // 生成粒子
      var particles = [];
      for (var i = 0; i < 60; i++) {
        particles.push({
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.4,
          vy: (Math.random() - 0.5) * 0.4,
          r: Math.random() * 2 + 0.5,
          alpha: Math.random() * 0.4 + 0.1,
          speed: Math.random() * 0.3 + 0.2,
        });
      }
      
      this.data._particleCtx = ctx;
      this.data._particleCanvas = canvas;
      this.data._particleWidth = width;
      this.data._particleHeight = height;
      this.data.particles = particles;
      this.setData({ canvasReady: true });
      
      // 开始帧循环
      this._particleLoop();
    }.bind(this));
  },

  _particleLoop() {
    if (this.data.done) return;
    var ctx = this.data._particleCtx;
    var w = this.data._particleWidth;
    var h = this.data._particleHeight;
    var particles = this.data.particles;
    var phase = this.data.phase;
    if (!ctx || !particles) return;
    
    ctx.clearRect(0, 0, w, h);
    
    // 呼吸相位影响粒子的聚集程度
    var breathFactor = 1;
    if (phase === 'inhale') breathFactor = 1 + 0.3;
    else if (phase === 'hold') breathFactor = 1 + 0.3;
    else breathFactor = 0.7;
    
    var cx = w / 2;
    var cy = h / 2;
    
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      
      // 向中心聚集/远离
      var dx = cx - p.x;
      var dy = cy - p.y;
      var dist = Math.sqrt(dx * dx + dy * dy);
      if (dist > 1) {
        var pull = 0.002 * breathFactor;
        p.vx += (dx / dist) * pull;
        p.vy += (dy / dist) * pull;
      }
      
      // 随机飘动
      p.vx += (Math.random() - 0.5) * 0.02;
      p.vy += (Math.random() - 0.5) * 0.02;
      
      // 速度限制
      var speed = Math.sqrt(p.vx * p.vx + p.vy * p.vy);
      if (speed > 1) {
        p.vx = (p.vx / speed) * 1;
        p.vy = (p.vy / speed) * 1;
      }
      
      p.x += p.vx;
      p.y += p.vy;
      
      // 边界回弹
      if (p.x < 0 || p.x > w) p.vx = -p.vx;
      if (p.y < 0 || p.y > h) p.vy = -p.vy;
      
      // 绘制粒子
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(150, 220, 255, ' + p.alpha * breathFactor * 0.8 + ')';
      ctx.fill();
    }
    
    this.data._animFrame = setTimeout(function() {
      this._particleLoop();
    }.bind(this), 33); // ~30fps
  },

  // 启动白噪音背景音（网易云高质量白噪音）
  _startAmbientSound() {
    try {
      var inn = wx.createInnerAudioContext();
      inn.autoplay = true;
      inn.loop = true;
      inn.volume = 0.12;
      inn.obeyMuteSwitch = false;
      inn.src = 'https://music.163.com/song/media/outer/url?id=569213211.mp3';
      inn.onError(function(err) {
        console.log('[Breathing] 白噪音加载失败:', err.errCode);
      });
      this.data._audioCtx = inn;
      this.setData({ soundOn: true });
    } catch(er) {
      console.log('[Breathing] 白噪音启动失败:', er);
    }
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

  // 能量环旋转动画
  _startRingAnimation() {
    var self = this;
    self.data._ringInterval = setInterval(function() {
      if (self.data.done) return;
      self.setData({
        ringRotation: (self.data.ringRotation + 1) % 360,
        ringRotation2: (self.data.ringRotation2 - 0.7) % 360,
      });
    }, 50);
  },

  nextPhase() {
    if (!this.data.playing) return;
    var d = this.data;
    
    if (d._interval) clearInterval(d._interval);
    
    if (d._pi >= d._phases.length) {
      d._pi = 0;
      var r = d.round + 1;
      if (r > d.totalRounds) {
        this.complete();
        return;
      }
      this.setData({ round: r });
    }
    
    var ph = d._phases[d._pi];
    var duration = ph.d;
    var countStart = Math.floor(duration / 1000);
    
    // 根据相位设置光晕颜色
    var hue = 190, sat = 80, light = 60;
    if (ph.n === 'inhale') {
      hue = 190; sat = 80; light = 60;  // 蓝
    } else if (ph.n === 'hold') {
      hue = 240; sat = 70; light = 55;  // 紫
    } else {
      hue = 280; sat = 60; light = 45;  // 紫红
    }
    
    // 根据相位设置缩放
    var scale = 1;
    if (ph.n === 'exhale') scale = 0.5;
    
    this.setData({ 
      phase: ph.n, 
      phaseText: ph.t, 
      hintText: ph.hint || '',
      count: countStart,
      glowHue: hue,
      glowSat: sat,
      glowLight: light,
      scale: scale,
    });
    
    var self = this;
    var count = countStart;
    d._interval = setInterval(function() {
      count--;
      if (count <= 0) {
        clearInterval(self.data._interval);
        self.data._pi++;
        self.data._timer = setTimeout(function() { self.nextPhase(); }, 150);
      } else {
        self.setData({ count: count });
      }
    }, 1000);
    
    this.updateProgress();
  },

  updateProgress() {
    var total = this.data.totalRounds * this.data._phases.length;
    var current = (this.data.round - 1) * this.data._phases.length + this.data._pi + 1;
    var pct = Math.min(100, Math.floor((current / total) * 100));
    this.setData({ progressPct: pct });
  },

  toggle() {
    if (this.data.done) return;
    var playing = !this.data.playing;
    this.setData({ playing: playing });
    if (playing) this.nextPhase();
  },

  complete() {
    this.setData({ 
      playing: false, 
      done: true,
      progressPct: 100,
      // 展开效果颜色
      glowHue: 320,
      glowSat: 90, 
      glowLight: 70,
    });
    // 停止背景音
    if (this.data._audioCtx) {
      this.data._audioCtx.stop();
    }
    // 停止动画
    if (this.data._ringInterval) clearInterval(this.data._ringInterval);
    if (this.data._animFrame) clearTimeout(this.data._animFrame);
    // 粒子绽放效果
    this._burstEffect();
  },

  _burstEffect() {
    var ctx = this.data._particleCtx;
    var w = this.data._particleWidth;
    var h = this.data._particleHeight;
    var particles = this.data.particles;
    if (!ctx || !particles) return;
    
    // 粒子高速扩散
    for (var i = 0; i < particles.length; i++) {
      var p = particles[i];
      var angle = Math.random() * Math.PI * 2;
      var speed = 3 + Math.random() * 5;
      p.vx = Math.cos(angle) * speed;
      p.vy = Math.sin(angle) * speed;
      p.alpha = 0.8;
    }
    
    // 绽放帧
    var burstFrames = 0;
    var burstInterval = setInterval(function() {
      if (burstFrames > 30) {
        clearInterval(burstInterval);
        return;
      }
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < particles.length; i++) {
        var p = particles[i];
        p.x += p.vx;
        p.y += p.vy;
        p.vx *= 0.97;
        p.vy *= 0.97;
        p.alpha *= 0.96;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r * (1 + burstFrames * 0.05), 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(255, 200, 255, ' + p.alpha + ')';
        ctx.fill();
      }
      burstFrames++;
    }.bind(this), 33);
  },

  closeNow() {
    // 后端通知：停止呼吸练习
    try {
      wx.request({
        url: require('../../utils/api').API_BASE + '/api/stop-breathing',
        method: 'POST',
        data: { 
          openid: wx.getStorageSync('aisleepgen_openid') || 'default',
          completed: this.data.done,
          rounds: this.data.round - 1,
        },
        timeout: 5000,
      });
    } catch(e) {}
    
    try {
      var pages = getCurrentPages();
      var prevPage = pages[pages.length - 2];
      var start = this._startTime || Date.now();
      if (prevPage) {
        try {
          prevPage.setData({ 
            breathDone: true, 
            breathRounds: this.data.round - 1,
            breathDuration: Math.floor((Date.now() - start) / 1000) || 0,
            breathCompleted: this.data.done || false,
            breathPattern: this.data.breathName,
          });
        } catch(e) {}
      }
    } catch(e) {}
    wx.navigateBack({ delta: 1 });
  },

  _cleanupNow() {
    if (this.data._audioCtx) { try { this.data._audioCtx.stop(); this.data._audioCtx.destroy(); } catch(e) {} }
    if (this.data._interval) clearInterval(this.data._interval);
    if (this.data._timer) clearTimeout(this.data._timer);
    if (this.data._ringInterval) clearInterval(this.data._ringInterval);
    if (this.data._animFrame) clearTimeout(this.data._animFrame);
  },

  onUnload() {
    // 呼吸完成后的反馈评分
    if (this.data.done) {
      var _this = this;
      wx.showModal({
        title: '做完感觉怎样？',
        content: '评分1-10（1很烦躁 / 10很放松）',
        editable: true,
        placeholderText: '输入1-10',
        success(fb) {
          if (fb.confirm && fb.content) {
            var score = parseInt(fb.content) || 0;
            if (score >= 1 && score <= 10) {
              wx.request({
                url: require('../../utils/api').HOST + '/api/relax-feedback',
                method: 'POST',
                data: { 
                  openid: wx.getStorageSync('openid'), 
                  score: score, 
                  pattern: _this.data.breathName || _this.options.name || '4-7-8' 
                },
                success() { wx.showToast({ title: '已记录评分', icon: 'success' }); }
              });
            }
          }
        }
      });
    }
    if (this.data._interval) clearInterval(this.data._interval);
    if (this.data._timer) clearTimeout(this.data._timer);
    if (this.data._ringInterval) clearInterval(this.data._ringInterval);
    if (this.data._animFrame) clearTimeout(this.data._animFrame);
    if (this.data._audioCtx) {
      this.data._audioCtx.stop();
      this.data._audioCtx.destroy();
    }
  },
});
