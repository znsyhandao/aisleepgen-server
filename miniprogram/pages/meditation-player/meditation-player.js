/** pages/meditation-player/meditation-player.js — 眠小兔统一冥想播放器 */
const API_BASE = 'https://aisleepgen.com'
const APP = getApp()

Page({
  data: {
    // 内容
    series_id: '',
    item_id: '',
    title: '',
    series_name: '',
    duration: 0,

    // 播放状态
    status: 'ready',      // ready | playing | paused | completed
    currentTime: 0,
    progressPercent: 0,
    timeDisplay: '00:00',

    // 背景音
    ambient: '',
    ambientOn: true,
    ambientVolume: 50,
    ambientName: '氛围音',

    // 白噪音环境音列表
    ambientOptions: [
      { key: 'ocean', name: '🌊 海浪', icon: '🌊' },
      { key: 'rain', name: '☔ 雨声', icon: '☔' },
      { key: 'forest', name: '🌲 森林', icon: '🌲' },
      { key: 'night', name: '🌙 夏夜', icon: '🌙' },
      { key: 'birds', name: '🐦 鸟鸣', icon: '🐦' },
      { key: 'fire', name: '🔥 篝火', icon: '🔥' },
      { key: 'wind', name: '🍃 微风', icon: '🍃' },
      { key: 'water', name: '💧 溪流', icon: '💧' },
      { key: 'guqin', name: '🎵 古琴', icon: '🎵' },
      { key: 'piano', name: '🎹 钢琴', icon: '🎹' },
    ],
    selectedAmbient: 'ocean',

    // 评分
    showRating: false,
    rating: 0,

    // 手环数据浮窗
    showBandData: false,
    bandData: null,

    // 日志
    logs: [],
    audioCtx: null,
    ambientCtx: null,
    timer: null,
  },

  onLoad(options) {
    // 检测是否有推荐的冥想（从极简入口来的）
    const recId = wx.getStorageSync('recommended_meditation')
    var initTitle = '冥想', initSeries = '', initItem = '', initDur = 600
    if (recId && !options.item_id) {
      wx.removeStorageSync('recommended_meditation')
      initSeries = recId.includes('_') ? recId.split('_')[0] : 'pl'
      initItem = recId
      initTitle = options.title || decodeURIComponent(this.data.title || '冥想')
      initDur = parseInt(options.duration) || 720
    }
    const { series_id, item_id, title, series_name, duration, ambient } = options
    this.setData({
      series_id: series_id || initSeries,
      item_id: item_id || initItem,
      title: decodeURIComponent(title || initTitle),
      series_name: decodeURIComponent(series_name || ''),
      duration: parseInt(duration) || initDur,
      ambient: ambient || 'ambient_calm',
    })
    this.addLog('加载: ' + this.data.title)
    this._checkBandData()
    // 从极简入口来的，自动播放
    if (recId && !options.item_id) {
      setTimeout(() => this.startPlay(), 500)
    }
  },

  onUnload() {
    this._cleanup()
  },

  startPlay() {
    this.setData({ status: 'playing' })
    this.addLog('冥想开始...')

    // 1. 播放背景音
    this._playAmbient()

    // 2. 获取并播放人声引导（DeepSeek TTS）
    this._fetchGuideAudio()

    // 3. 开始计时
    this._startTimer()
  },

  pausePlay() {
    this.setData({ status: 'paused' })
    if (this.data.ambientCtx) this.data.ambientCtx.pause()
    if (this.data.audioCtx) this.data.audioCtx.pause()
    this._stopTimer()
  },

  resumePlay() {
    this.setData({ status: 'playing' })
    if (this.data.ambientCtx) this.data.ambientCtx.play()
    if (this.data.audioCtx) this.data.audioCtx.play()
    this._startTimer()
  },

  stopPlay() {
    this._cleanup()
    this.setData({ status: 'completed', showRating: true })
    this.addLog('冥想结束')
    this._recordSession(true)
  },

  /* ===== 背景音 ===== */
  selectAmbient(e) {
    const key = e.currentTarget.dataset.key
    this.setData({ selectedAmbient: key })
    this._playAmbient()
  },

  toggleAmbient() {
    const on = !this.data.ambientOn
    this.setData({ ambientOn: on })
    if (on) this._playAmbient()
    else if (this.data.ambientCtx) this.data.ambientCtx.stop()
  },

  _playAmbient() {
    const key = this.data.selectedAmbient
    if (this.data.ambientCtx) this.data.ambientCtx.stop()

    // 真实音频文件映射
    const fileMap = {
      'ocean':  API_BASE + '/static/audio/5.海洋.mp3',
      'rain':   API_BASE + '/static/audio/2.泉水.mp3',
      'forest': API_BASE + '/static/audio/4.森林.mp3',
      'night':  API_BASE + '/static/audio/6.星空.mp3',
      'birds':  API_BASE + '/static/audio/5.海洋.mp3',   // 暂用海风代替鸟鸣
      'fire':   API_BASE + '/static/audio/7.宇宙.mp3',
      'wind':   API_BASE + '/static/audio/5.海洋.mp3',
      'water':  API_BASE + '/static/audio/2.泉水.mp3',
      'guqin':  API_BASE + '/static/audio/meditation_music.mp3',
      'piano':  API_BASE + '/static/audio/meditation_music.mp3',
    }

    const ambientCtx = wx.createInnerAudioContext()
    ambientCtx.autoplay = true
    ambientCtx.loop = true
    ambientCtx.volume = this.data.ambientVolume / 100
    ambientCtx.src = fileMap[key] || fileMap.ocean

    ambientCtx.onError(() => {
      this.addLog('背景音加载失败，可继续冥想')
    })

    this.setData({ ambientCtx })
    this.addLog('播放: ' + key)
  },

  onAmbientVolume(e) {
    const v = e.detail.value
    this.setData({ ambientVolume: v })
    if (this.data.ambientCtx) {
      this.data.ambientCtx.volume = v / 100
    }
  },

  /* ===== 人声引导 ===== */
  _fetchGuideAudio() {
    this.addLog('正在获取AI引导音频...')
    wx.request({
      url: API_BASE + '/api/meditation/guide?series=' + encodeURIComponent(this.data.series_id) +
           '&item=' + encodeURIComponent(this.data.item_id) +
           '&title=' + encodeURIComponent(this.data.title),
      success: (res) => {
        const guideText = res.data || ''
        if (guideText.length > 50) {
          this.addLog('引导词就绪 ' + guideText.length + ' 字')
          this.setData({ guideText })
          // TTS播放引导词
          this._playGuideTTS(guideText)
        }
      },
      fail: () => {
        this.addLog('引导词获取失败')
      }
    })
  },

  _playGuideTTS(text) {
    if (this.data.audioCtx) this.data.audioCtx.stop()
    const audioCtx = wx.createInnerAudioContext()
    audioCtx.autoplay = true
    audioCtx.src = API_BASE + '/api/tts?text=' + encodeURIComponent(text)
    audioCtx.onError(() => {
      this.addLog('TTS播放失败')
    })
    this.setData({ audioCtx })
  },

  /* ===== 计时 ===== */
  _startTimer() {
    this._stopTimer()
    this.data.timer = setInterval(() => {
      const t = this.data.currentTime + 1
      const total = this.data.duration || 600
      const pct = Math.min(100, (t / total) * 100)
      const m = Math.floor(t / 60)
      const s = t % 60
      this.setData({
        currentTime: t,
        progressPercent: pct,
        timeDisplay: m.toString().padStart(2,'0') + ':' + s.toString().padStart(2,'0'),
      })
      if (t >= total) {
        this.stopPlay()
      }
    }, 1000)
  },

  _stopTimer() {
    if (this.data.timer) {
      clearInterval(this.data.timer)
      this.data.timer = null
    }
  },

  /* ===== 记录会话 ===== */
  _recordSession(completed) {
    wx.request({
      url: API_BASE + '/api/meditation/record',
      method: 'POST',
      header: { 'Content-Type': 'application/json' },
      data: {
        openid: this._getOpenid(),
        series_id: this.data.series_id,
        item_id: this.data.item_id,
        title: this.data.title,
        duration: this.data.currentTime,
        completed,
      },
      fail: () => {}
    })
  },

  /* ===== 评分 ===== */
  rate(e) {
    const r = parseInt(e.currentTarget.dataset.rating)
    this.setData({ rating: r })
    this.addLog('评分: ' + r + '/5')
    setTimeout(() => {
      wx.navigateBack()
    }, 800)
  },

  skipRating() {
    wx.navigateBack()
  },

  /* ===== 手环数据 ===== */
  _checkBandData() {
    const openid = this._getOpenid()
    wx.request({
      url: API_BASE + '/api/huawei/status?openid=' + openid,
      success: (res) => {
        const d = res.data || {}
        if (d.connected) {
          // 再去查睡眠数据
          wx.request({
            url: API_BASE + '/api/user-profile?openid=' + openid,
            success: (r2) => {
              const prof = r2.data || {}
              const sd = prof.devices && prof.devices.huawei_band && prof.devices.huawei_band.last_sleep_data
              if (sd) {
                this.setData({ bandData: sd })
              }
            },
            fail: () => {}
          })
        }
      },
      fail: () => {}
    })
  },

  toggleBandData() {
    this.setData({ showBandData: !this.data.showBandData })
  },

  /* ===== 工具 ===== */
  _getOpenid() {
    try {
      return (APP.globalData && APP.globalData.openid) || 'default'
    } catch (e) { return 'default' }
  },

  _cleanup() {
    this._stopTimer()
    if (this.data.ambientCtx) { this.data.ambientCtx.stop(); this.setData({ ambientCtx: null }) }
    if (this.data.audioCtx) { this.data.audioCtx.stop(); this.setData({ audioCtx: null }) }
  },

  addLog(msg) {
    const logs = this.data.logs
    const now = new Date()
    const t = now.getHours().toString().padStart(2,'0') + ':' +
              now.getMinutes().toString().padStart(2,'0') + ':' +
              now.getSeconds().toString().padStart(2,'0')
    logs.push('[' + t + '] ' + msg)
    if (logs.length > 30) logs.shift()
    this.setData({ logs })
  },
})
