// 科幻感渐进式肌肉放松 - 全息人体扫描 + 分步指令
Page({
  data: {
    step: 0,
    totalSteps: 7,
    currentPart: '',
    instruction: '',
    subStatus: 'ready',  // ready | tense | relax | done
    subCount: 5,
    relaxName: '全身渐进式放松',
    tip: '',
    displayTip: '',
    done: false,
    playState: false,
    _steps: [],
    _subTimer: null,
    _startTime: 0,
    _bodyPart: 0,    // 高亮部位索引
  },

  onLoad(e) {
    var p = {};
    try { p = JSON.parse(decodeURIComponent(e.params || '{}')); } catch(er) { if (e.inhale) p = e; }

    var steps = p.steps || [
      { part: '脚部', instruction: '用力绷紧双脚5秒...然后完全放松' },
      { part: '小腿', instruction: '小腿收紧5秒...松开放松' },
      { part: '大腿和臀部', instruction: '大腿和臀部收紧...放松' },
      { part: '腹部', instruction: '腹部收紧...放松' },
      { part: '手和手臂', instruction: '握拳、手臂收紧...放松' },
      { part: '肩膀', instruction: '耸肩到耳朵...放下' },
      { part: '脸部', instruction: '皱眉、咬牙...全面放松' },
    ];
    var name = p.name || '全身渐进式放松';
    var tip = p.tip || '跟着指令一步步来，感受从紧张到放松的对比';

    this.data._steps = steps;
    this.data._startTime = Date.now();

    this.setData({
      relaxName: name,
      totalSteps: steps.length,
      displayTip: tip,
      step: 0,
      currentPart: steps[0].part,
      instruction: steps[0].instruction,
      subStatus: 'ready',
      subCount: 5,
    });

    // 自动开始第一轮
    var self = this;
    setTimeout(function() { self._startPhase(); }, 800);
  },

  _startPhase() {
    if (this.data.done) return;
    this.setData({ subStatus: 'tense', subCount: 5, playState: true });

    var self = this;
    var count = 5;
    self.data._subTimer = setInterval(function() {
      count--;
      if (count <= 0) {
        clearInterval(self.data._subTimer);
        self._relaxPhase();
      } else {
        self.setData({ subCount: count });
      }
    }, 1000);
  },

  _relaxPhase() {
    this.setData({ subStatus: 'relax', subCount: 5 });

    var self = this;
    var count = 5;
    self.data._subTimer = setInterval(function() {
      count--;
      if (count <= 0) {
        clearInterval(self.data._subTimer);
        self._nextStep();
      } else {
        self.setData({ subCount: count });
      }
    }, 1000);
  },

  _nextStep() {
    var nextIdx = this.data.step + 1;
    if (nextIdx >= this.data._steps.length) {
      this._complete();
      return;
    }

    var step = this.data._steps[nextIdx];
    this.setData({
      step: nextIdx,
      currentPart: step.part,
      instruction: step.instruction,
      subStatus: 'ready',
      subCount: 5,
      _bodyPart: nextIdx,
    });

    var self = this;
    setTimeout(function() { self._startPhase(); }, 600);
  },

  _complete() {
    this.setData({
      done: true,
      subStatus: 'done',
      playState: false,
    });
    if (this.data._subTimer) clearInterval(this.data._subTimer);
  },

  // 手动下一轮
  nextStep() {
    if (this.data.done || this.data.playState) return;
    this._startPhase();
  },

  closeNow() {
    var pages = getCurrentPages();
    var prevPage = pages[pages.length - 2];
    if (prevPage) {
      prevPage.setData({
        breathDone: true,   // 复用呼吸页的闭环
        breathRounds: this.data.step,
        breathDuration: Math.floor((Date.now() - this.data._startTime) / 1000),
        breathCompleted: this.data.done,
        breathPattern: this.data.relaxName,
      });
    }
    // 通知后端干预完成
    try {
      var openid = wx.getStorageSync('openid') || 'default';
      api.request('/api/intervention-complete', {
        openid: openid,
        pattern: this.data.relaxName,
        rounds: this.data.step,
        duration: Math.floor((Date.now() - this.data._startTime) / 1000),
        completed: this.data.done,
      });
    } catch (e) {}
    if (this.data._subTimer) clearInterval(this.data._subTimer);
    wx.navigateBack({ delta: 1 });
  },

  onUnload() {
    if (this.data._subTimer) clearInterval(this.data._subTimer);
  },
});
