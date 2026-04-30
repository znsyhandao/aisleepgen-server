// pages/meditation/meditation.js - 真实算法版
var MeditationAlgorithm = require('../../utils/meditation_algorithm');
var api = require("../../utils/api");
var meditationAlgo = new MeditationAlgorithm();

Page({
  data: {
    pageName: 'meditation',
    showBackButton: false,
    
    // 冥想状态
    meditationStatus: 'idle', // idle, playing, paused, completed
    currentTime: 0,
    totalTime: 600, // 10分钟
    progress: 0,
    
    // 当前冥想
    currentMeditation: null,
    
    // 冥想课程列表
    meditationList: [],
    
    // 会话脚本
    sessionScript: [],
    currentScriptIndex: 0,
    
    // 播放器设置
    playerSettings: {
      volume: 80,
      backgroundSound: 'rain',
      guidanceVoice: 'female'
    },
    
    // 计时器
    timer: null
  },

  onLoad() {
    console.log('冥想页面加载(真实算法版)');
    
    // 检查页面栈
    var pages = getCurrentPages();
    if (pages.length > 1) {
      this.setData({ showBackButton: true });
    }
    
    // 加载冥想列表
    this.loadMeditationList();
    
    // 初始化时间显示
    this.updateTimeStrs();
    
    // 加载设置
    this.loadSettings();
    
    // 加载睡眠数据(如果有)
    this.loadSleepData();
  },

  // 加载冥想列表(来自真实算法)
  loadMeditationList() {
    var types = meditationAlgo.getAllMeditationTypes();
    
    var list = types.map((t, index) => ({
      id: index + 1,
      typeId: t.id,
      title: t.name,
      description: t.description,
      duration: t.durationOptions[1] * 60, // 中间档时长(秒)
      durationOptions: t.durationOptions,
      category: t.id,
      icon: t.icon,
      benefits: t.benefits,
      favorite: false,
      durationStr: this.formatTime(t.durationOptions[1] * 60)
    }));
    
    this.setData({ meditationList: list });
    
    // 自动选择推荐的冥想
    var recommendedType = meditationAlgo.getRecommendedMeditation();
    var recommended = list.find(m => m.typeId === recommendedType) || list[0];
    this.selectMeditationById(recommended);
  },

  // 选择冥想
  selectMeditationById(meditation) {
    if (!meditation) return;
    
    // 生成冥想计划(使用真实算法)
    var sleepData = wx.getStorageSync('latest_analysis_result');
    var plan = meditationAlgo.generatePlan(sleepData, meditation.duration / 60, meditation.typeId);
    
    // 生成会话脚本
    var script = meditationAlgo.createSessionScript(plan);
    
    this.setData({
      currentMeditation: {
        ...meditation,
        plan: plan,
        description: plan.description
      },
      totalTime: plan.durationMinutes * 60,
      meditationStatus: 'idle',
      meditationActive: false,
      currentTime: 0,
      progress: 0,
      sessionScript: script,
      currentScriptIndex: 0
    });
    
    // 停止当前播放
    this.clearTimer();
  },

  // 选择冥想(从列表点击)
  selectMeditation(e) {
    var id = e.currentTarget.dataset.id;
    var meditation = this.data.meditationList.find(m => m.id === id);
    
    if (meditation) {
      this.selectMeditationById(meditation);
      
      wx.showToast({
        title: `已选择: ${meditation.title}`,
        icon: 'success'
      });
      this.updateTimeStrs();
      this.updateBreathingGuide(currentTime);
    }
  },

  // 音频管理
  audioContext: null,
  gainNode: null,
  oscillatorNode: null,

  // 开始冥想
  startMeditation() {
    if (this.data.meditationStatus === 'playing') return;
    
    this.setData({
      meditationStatus: 'playing',
      meditationActive: true,
      currentScriptIndex: 0
    });
    
    this.startTimer();
    this.startBackgroundSound();
    
    this.playChime();
    wx.showToast({ title: '开始冥想', icon: 'success' });
  },

  // 背景音 - 使用InnerAudioContext循环播放
  startBackgroundSound() {
    try {
      var sound = this.data.playerSettings.backgroundSound;
      if (!sound || sound === "none") return;

      this.stopBackgroundSound();

      var fileMap = {
        rain: api.AUDIO_BASE + "/audio/bg_rain.mp3",
        ocean: api.AUDIO_BASE + "/audio/bg_ocean.mp3",
        forest: api.AUDIO_BASE + "/audio/bg_forest.mp3",
        music: api.AUDIO_BASE + "/audio/bg_music.mp3"
      };
      var filePath = fileMap[sound];
      if (!filePath) return;

      var audio = wx.createInnerAudioContext();
      audio.src = filePath;
      audio.loop = true;
      audio.obeyMuteSwitch = false;
      audio.autoplay = true;
      audio.volume = this.data.playerSettings.volume / 100;

      var self = this;
      audio.onError(function(res) {
        console.log("Audio error:", res.errCode, res.errMsg);
      });

      this._bgAudio = audio;
    } catch (e) {
      console.log("Audio init error:", e);
    }
  },

  // 停止背景音
  stopBackgroundSound() {
    try {
      if (this._bgAudio) {
        this._bgAudio.stop();
        this._bgAudio.destroy();
        this._bgAudio = null;
      }
    } catch (e) {
      console.log("Stop audio error:", e);
    }
  },





  // 播放提示音
  playChime() {
    try {
      var chime = wx.createInnerAudioContext();
      chime.src = api.AUDIO_BASE + "/audio/bell.mp3";
      chime.volume = 0.3;
      var self = this;
      chime.onError(function(res) {
        console.log("Chime error:", res.errCode);
      });
      chime.autoplay = true;
      chime.obeyMuteSwitch = false;
      this._chimeAudio = chime;
    } catch (e) {
      console.log("Chime error:", e);
    }
  },

  // 呼吸引导更新
  updateBreathingGuide(currentTime) {
    var total = this.data.totalTime;
    var phase = currentTime % 8;  // 8-second breath cycle
    
    var guideText = '';
    var guideSub = '';
    
    if (phase < 4) {
      guideText = '深深吸一口气...';
      guideSub = '用鼻子慢慢吸气';
    } else if (phase < 7) {
      guideText = '缓缓呼出...';
      guideSub = '用嘴巴慢慢呼气';
    } else {
      guideText = '屏住呼吸...';
      guideSub = '感受身体的平静';
    }
    
    // 每30秒更新一次引导界面
    if (currentTime % 30 === 0) {
      var phases = [
        '放松你的肩膀...',
        '感受呼吸的节奏...',
        '让思绪慢慢沉淀...',
        '专注于当下的感受...',
        '身体正在放松...',
        '每一口气都带来平静...'
      ];
      var pIdx = Math.floor(currentTime / 30) % phases.length;
      guideText = phases[pIdx];
      guideSub = '';
    }
    
    this.setData({ guideText: guideText, guideSub: guideSub });
  },

  // 开始计时器
  startTimer() {
    this.clearTimer();
    
    this.timer = setInterval(() => {
      var currentTime = this.data.currentTime + 1;
      var progress = (currentTime / this.data.totalTime) * 100;
      
      // 更新引导语
      this.updateGuidance(currentTime);
      
      if (currentTime >= this.data.totalTime) {
        currentTime = this.data.totalTime;
        progress = 100;
        this.completeMeditation();
      }
      
      this.setData({ currentTime, progress });
      this.updateTimeStrs();
      this.updateBreathingGuide(currentTime);
    }, 1000);
  },

  // 更新引导语
  updateGuidance(currentTime) {
    var script = this.data.sessionScript;
    var nextIndex = script.findIndex(s => s.timeSeconds > currentTime);
    var currentIndex = nextIndex > 0 ? nextIndex - 1 : 0;
    
    if (currentIndex !== this.data.currentScriptIndex && currentIndex >= 0) {
      this.setData({ currentScriptIndex: currentIndex });
    }
  },

  // 暂停冥想
  pauseMeditation() {
    if (this.data.meditationStatus !== 'playing') return;
    
    this.setData({ meditationStatus: 'paused', meditationActive: true });
    this.clearTimer();
    
    wx.showToast({ title: '已暂停', icon: 'success' });
  },

  // 恢复冥想
  resumeMeditation() {
    if (this.data.meditationStatus !== 'paused') return;
    
    this.setData({ meditationStatus: 'playing', meditationActive: true });
    this.startTimer();
    
    wx.showToast({ title: '继续冥想', icon: 'success' });
  },

  // 停止冥想
  stopMeditation() {
    this.setData({
      meditationStatus: 'idle',
      meditationActive: false,
      currentTime: 0,
      progress: 0,
      currentScriptIndex: 0
    });
    
    this.clearTimer();
    
    wx.showToast({ title: '已停止', icon: 'success' });
  },

  // 完成冥想
  completeMeditation() {
    this.clearTimer();
    this.stopBackgroundSound();
    
    this.setData({
      meditationStatus: 'completed',
      meditationActive: false,
      currentTime: this.data.totalTime,
      progress: 100
    });
    
    // 保存冥想记录
    this.playChime();
    this.saveMeditationRecord();
    
    setTimeout(() => {
      wx.showModal({
        title: '冥想完成',
        content: `您已完成 ${this.formatTime(this.data.totalTime)} 的冥想练习\n坚持练习,改善睡眠质量!`,
        showCancel: false,
        confirmText: '太棒了!'
      });
    }, 500);
  },

  // 保存冥想记录
  saveMeditationRecord() {
    var meditation = this.data.currentMeditation;
    if (!meditation) return;
    
    var records = wx.getStorageSync('meditation_records') || [];
    records.unshift({
      id: Date.now(),
      title: meditation.title,
      duration: this.data.totalTime,
      completedAt: new Date().toLocaleString(),
      type: meditation.typeId
    });
    if (records.length > 100) records = records.slice(0, 100);
    
    wx.setStorageSync('meditation_records', records);
  },

  // 清理计时器
  clearTimer() {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  },

  // 格式化时间
  formatTime(seconds) {
    var mins = Math.floor(seconds / 60);
    var secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  },

  // 更新时间字符串(WXML不支持函数调用)
  updateTimeStrs() {
    this.setData({
      currentTimeStr: this.formatTime(this.data.currentTime),
      totalTimeStr: this.formatTime(this.data.totalTime)
    });
  },

  // 切换收藏
  toggleFavorite(e) {
    var id = e.currentTarget.dataset.id;
    var index = this.data.meditationList.findIndex(m => m.id === id);
    
    if (index >= 0) {
      var key = `meditationList[${index}].favorite`;
      var newValue = !this.data.meditationList[index].favorite;
      
      this.setData({ [key]: newValue });
      
      wx.showToast({
        title: newValue ? '已收藏' : '已取消收藏',
        icon: 'success'
      });
    }
  },

  // 加载设置
  loadSettings() {
    var savedSettings = wx.getStorageSync('meditation_settings');
    if (savedSettings) {
      this.setData({ playerSettings: savedSettings });
    }
  },

  // 加载睡眠数据
  loadSleepData() {
    var sleepData = wx.getStorageSync('latest_analysis_result');
    if (sleepData) {
      console.log('已加载睡眠数据,冥想将个性化推荐');
    }
  },

  // 更新音量
  updateVolume(e) {
    var volume = e.detail.value;
    this.setData({ 'playerSettings.volume': volume });
    wx.setStorageSync('meditation_settings', this.data.playerSettings);
  },

  // 切换背景音
  changeBackgroundSound(e) {
    var sound = e.currentTarget.dataset.sound;
    this.setData({ 'playerSettings.backgroundSound': sound });
    wx.setStorageSync('meditation_settings', this.data.playerSettings);
    
    wx.showToast({ title: `背景音: ${sound}`, icon: 'success' });
  },

  // 切换引导声音
  changeGuidanceVoice(e) {
    var voice = e.currentTarget.dataset.voice;
    this.setData({ 'playerSettings.guidanceVoice': voice });
    wx.setStorageSync('meditation_settings', this.data.playerSettings);
    
    wx.showToast({
      title: `引导声音: ${voice === 'female' ? '女声' : '男声'}`,
      icon: 'success'
    });
  },

  // 设置提醒
  setReminder() {
    wx.showToast({ title: '提醒设置功能开发中', icon: 'none' });
  },

  // 返回
  goBack() {
    var pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.switchTab({ url: '/pages/index/index' });
    }
  },

  onUnload() {
    this.clearTimer();
    this.stopBackgroundSound();
  }
});