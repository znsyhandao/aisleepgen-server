/** 睡眠录音页面 JS */
const app = getApp()
const API_BASE = 'https://82.156.208.245:8090'

Page({
  data: {
    // 录音状态
    recording: false,
    paused: false,
    recordDuration: 0,      // 已录音秒数
    recordTimer: null,
    recorderManager: null,
    tempFilePath: '',
    
    // 显示状态
    phase: 'idle',          // idle | recording | done | analyzing | result
    statusText: '放好手机，开始整晚录音',
    
    // 分析结果
    analyzing: false,
    analysisProgress: 0,
    result: null,
    timeline: [],
    summary: null,
    quality: null,

    // 5维评分数据（替代内联 wxml 数组解决编译错误）
    dimensionList: [
      {label: '睡眠效率', key: 'sleep_efficiency', icon: '📏'},
      {label: '深睡质量', key: 'deep_sleep', icon: '🌊'},
      {label: 'REM质量', key: 'REM', icon: '💭'},
      {label: '睡眠连续', key: 'continuity', icon: '🔗'},
      {label: '入睡速度', key: 'sleep_latency', icon: '⏱️'},
    ],
  },

  onLoad() {
    // 创建录音管理器
    const recorderManager = wx.getRecorderManager()
    this.setData({ recorderManager })
    
    // 监听录音停止
    recorderManager.onStop((res) => {
      console.log('录音停止', res)
      this.setData({
        recording: false,
        phase: 'done',
        tempFilePath: res.tempFilePath,
        statusText: '录音完成，正在分析...'
      })
      // 自动开始分析
      this.analyzeRecording(res.tempFilePath)
    })
    
    // 监听录音错误
    recorderManager.onError((err) => {
      console.error('录音出错', err)
      wx.showToast({ title: '录音出错', icon: 'none' })
      this.setData({ recording: false, statusText: '录音出错，请重试' })
    })
    
    // 监听录音帧（可做电平显示）
    recorderManager.onFrameRecorded((res) => {
      // frameBuffer is audio data
    })
  },

  onUnload() {
    this.stopRecording()
  },

  /** 开始录音 */
  startRecording() {
    const rm = this.data.recorderManager
    if (!rm) {
      wx.showToast({ title: '录音器未初始化', icon: 'none' })
      return
    }
    
    const opts = {
      duration: 600 * 60 * 1000,  // 10小时，远大于整晚
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'aac',  // 生成.m4a
      frameSize: 50,  // 每帧50ms
    }
    
    rm.start(opts)
    
    // 计时
    this.setData({
      recording: true,
      phase: 'recording',
      statusText: '录音中...',
      recordDuration: 0,
    })
    
    this.data.recordTimer = setInterval(() => {
      this.setData({ recordDuration: this.data.recordDuration + 1 })
    }, 1000)
  },

  /** 停止录音 */
  stopRecording() {
    if (this.data.recordTimer) {
      clearInterval(this.data.recordTimer)
      this.data.recordTimer = null
    }
    if (this.data.recording) {
      this.data.recorderManager.stop()
    }
  },

  /** 上传录音文件到后端分析 */
  analyzeRecording(filePath) {
    this.setData({
      analyzing: true,
      phase: 'analyzing',
      statusText: '正在分析睡眠...',
    })
    
    wx.uploadFile({
      url: `${API_BASE}/api/sleep-analyze`,
      filePath: filePath,
      name: 'audio_file',
      success: (res) => {
        try {
          const data = JSON.parse(res.data)
          if (data.success) {
            this.setData({
              analyzing: false,
              phase: 'result',
              statusText: '分析完成',
              result: data,
              timeline: data.timeline || [],
              summary: data.summary,
              quality: data.quality,
            })
          } else {
            wx.showToast({ title: '分析失败: ' + (data.error || '未知错误'), icon: 'none' })
            this.setData({ analyzing: false, statusText: '分析失败' })
          }
        } catch (e) {
          wx.showToast({ title: '解析结果失败', icon: 'none' })
          this.setData({ analyzing: false, statusText: '解析失败' })
        }
      },
      fail: (err) => {
        wx.showToast({ title: '上传失败: ' + (err.errMsg || ''), icon: 'none' })
        this.setData({ analyzing: false, statusText: '上传失败，请重试' })
      }
    })
  },

  /** 查看详细报告 */
  viewReport() {
    if (!this.data.result) return
    wx.navigateTo({
      url: `../report/report?from=record&data=${encodeURIComponent(JSON.stringify(this.data.result))}`
    })
  },

  /** 重录 */
  reRecord() {
    this.setData({
      phase: 'idle',
      statusText: '放好手机，开始整晚录音',
      result: null,
      timeline: [],
      summary: null,
      quality: null,
      tempFilePath: '',
    })
  },

  /** 格式化时间 */
  formatTime(seconds) {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = seconds % 60
    if (h > 0) return `${h}时${m}分`
    if (m > 0) return `${m}分${s}秒`
    return `${s}秒`
  },
})
