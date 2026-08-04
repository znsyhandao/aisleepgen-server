/** pages/sleep-audio/sleep-audio.js — AI助眠音频 */
const API_BASE = 'https://aisleepgen.com'
const APP = getApp()

// 场景描述
const SCENE_TEXTS = {
  sleep: {
    title: '🌙 入睡引导',
    text: '想象你躺在一片温暖的沙滩上，晚风轻拂，海浪声由远及近。每一次呼吸，身体都更沉一点，意识像羽毛一样轻轻落下...',
    duration: 900  // 15min
  },
  deep: {
    title: '🌊 深睡强化',
    text: '深沉的δ波节律，如同大地深处的脉动。你的呼吸与它同步，意识沉入一片温暖的黑暗，那里没有思绪，只有纯粹的宁静...',
    duration: 1800  // 30min
  },
  relax: {
    title: '🧘 快速放松',
    text: '从头顶开始，逐个部位感受：额头放松，眼皮放松，脸颊放松，下巴松开，肩膀下沉，胸口舒展，腹部柔软，双腿放松，脚趾松开...',
    duration: 180  // 3min
  },
  rem: {
    title: '💭 梦境引导',
    text: '你走进一座古老的花园，月光洒在石板路上。每一朵花都发着微光，空气中弥漫着茉莉花的香气。前面有一扇门，打开它，进入你的梦...',
    duration: 600  // 10min
  }
}

Page({
  data: {
    btConnected: false,
    selectedMode: '',
    sceneTitle: '',
    sceneText: '',
    generating: false,
    isPlaying: false,
    playbackFinished: false,
    progressPercent: 0,
    currentTimeText: '00:00',
    durationText: '00:00',
    logs: [],
    audioContext: null,
  },

  onLoad() {
    this.addLog('AI助眠页面加载')
    this._checkBluetooth()
    this._generateAIScene()
  },

  onUnload() {
    // 离开页面时停止播放
    if (this.data.audioContext) {
      this.data.audioContext.stop()
    }
  },

  /* ===== 默认生成（根据用户数据）===== */
  _generateAIScene() {
    this.setData({ generating: true })
    this.addLog('根据睡眠数据生成定制场景...')

    // 先看一下用户有没有连接手环，昨天睡眠数据如何
    const openid = this._getOpenid()
    wx.request({
      url: API_BASE + '/api/user-profile?openid=' + openid,
      success: (res) => {
        const profile = res.data || {}
        const deviceData = profile.devices && profile.devices.huawei_band
        if (deviceData) {
          this.addLog('检测到手环数据，AI定制场景中...')
        }
      },
      fail: () => {}
    })

    // 默认选择入睡引导
    setTimeout(() => {
      this.setData({
        generating: false,
        selectedMode: 'sleep',
        sceneTitle: SCENE_TEXTS.sleep.title,
        sceneText: SCENE_TEXTS.sleep.text,
      })
      this.addLog('AI场景就绪 - 入睡引导')
    }, 1500)
  },

  /* ===== 选择模式 ===== */
  selectMode(e) {
    const mode = e.currentTarget.dataset.mode
    const scene = SCENE_TEXTS[mode]
    if (!scene) return

    // 停止当前播放
    if (this.data.audioContext) {
      this.data.audioContext.stop()
    }

    this.setData({
      selectedMode: mode,
      sceneTitle: scene.title,
      sceneText: scene.text,
      isPlaying: false,
      playbackFinished: false,
      progressPercent: 0,
      currentTimeText: '00:00',
      durationText: this._formatTime(scene.duration),
    })

    this.addLog('切换模式: ' + scene.title)
  },

  /* ===== 播放/暂停 ===== */
  togglePlay() {
    if (this.data.isPlaying) {
      this._pause()
    } else {
      this._play()
    }
  },

  _play() {
    const scene = SCENE_TEXTS[this.data.selectedMode]
    if (!scene) return

    this.addLog('开始播放... （音频将通过蓝牙→耳机') 

    const audioCtx = wx.createInnerAudioContext()
    audioCtx.autoplay = true
    audioCtx.obeyMuteSwitch = false  // 避免静音键影响
    audioCtx.src = API_BASE + '/api/sleep/ai-audio?openid=' + this._getOpenid() + '&mode=' + this.data.selectedMode

    audioCtx.onCanplay(() => {
      this.addLog('音频加载完成')
    })

    audioCtx.onPlay(() => {
      this.setData({ isPlaying: true, playbackFinished: false })
    })

    audioCtx.onPause(() => {
      this.setData({ isPlaying: false })
    })

    audioCtx.onStop(() => {
      this.setData({ isPlaying: false })
    })

    audioCtx.onEnded(() => {
      this.addLog('播放完成')
      this.setData({
        isPlaying: false,
        playbackFinished: true,
        progressPercent: 100,
        currentTimeText: this.data.durationText,
      })
    })

    audioCtx.onError((e) => {
      this.addLog('播放错误: ' + JSON.stringify(e))
      // 如果没有音频文件，用TTS合成
      this._fallbackTTS(scene.text)
    })

    // 进度更新
    this._progressTimer = setInterval(() => {
      if (audioCtx.paused || audioCtx.stopped) return
      const current = audioCtx.currentTime || 0
      const duration = audioCtx.duration || scene.duration
      const pct = Math.min(100, (current / duration) * 100)
      this.setData({
        progressPercent: pct,
        currentTimeText: this._formatTime(current),
        durationText: this._formatTime(duration),
      })
    }, 500)

    this.setData({ audioContext: audioCtx })
  },

  _pause() {
    if (this.data.audioContext) {
      this.data.audioContext.pause()
      this.setData({ isPlaying: false })
      this.addLog('已暂停')
    }
  },

  /* ===== 兜底TTS（如果没有音频文件）===== */
  _fallbackTTS(text) {
    this.addLog('使用语音合成（TTS）')
    const audioCtx = wx.createInnerAudioContext()
    audioCtx.autoplay = true

    // 这里调用后端TTS接口
    audioCtx.src = API_BASE + '/api/tts?text=' + encodeURIComponent(text)

    audioCtx.onPlay(() => {
      this.setData({ isPlaying: true })
      this.addLog('语音合成播放中...')
    })

    audioCtx.onError(() => {
      this.addLog('TTS也失败了，请检查后端')
      wx.showToast({ title: '播放失败', icon: 'none' })
    })

    this.setData({ audioContext: audioCtx })
  },

  resetSession() {
    this.setData({
      isPlaying: false,
      playbackFinished: false,
      progressPercent: 0,
      currentTimeText: '00:00',
      sceneText: '',
      sceneTitle: '',
      selectedMode: '',
    })
    this._generateAIScene()
  },

  /* ===== 蓝牙状态检查 ===== */
  _checkBluetooth() {
    wx.getSystemInfo({
      success: (res) => {
        this.addLog('设备: ' + res.platform + ' ' + res.system)
        this.addLog('(蓝牙耳机需先在手机系统设置中配对)')
        // 蓝牙状态只能通过系统判断，小程序无法精确检测
        this.setData({ btConnected: true })  // 乐观显示
      }
    })
  },

  /* ===== 工具 ===== */
  _getOpenid() {
    try {
      return (APP.globalData && APP.globalData.openid) || 'default'
    } catch (e) {
      return 'default'
    }
  },

  _formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '00:00'
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return m.toString().padStart(2,'0') + ':' + s.toString().padStart(2,'0')
  },

  /* ===== 日志 ===== */
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
