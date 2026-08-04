/** pages/band/band.js — 设备数据导入（截图OCR + 手动输入） */
// API_BASE from app global config, fallback to default
const API_BASE = (getApp().globalData && getApp().globalData.apiBase) || 'https://aisleepgen.com'

Page({
  data: {
    loading: false,
    loadingText: '',
    activeTab: 'manual',

    // OCR tab
    ocrPreview: '',
    ocrResult: null,
    ocrConfirmed: false,
    ocring: false,

    // Manual input tab
    form: {
      sleep_score: '',
      bedtime: '',
      waketime: '',
      total_sleep_min: '',
      awake_count: '',
      deep_sleep_min: '',
      light_sleep_min: '',
      rem_min: '',
      heart_rate_avg: '',
      hrv: '',
    },
    submitting: false,
    manualSubmitted: false,
  },

  onLoad() {
    // 默认选手动输入（更直接）
  },

  /* ===== Tab 切换 ===== */
  switchTab(e) {
    const tab = e.currentTarget.dataset.tab
    this.setData({ activeTab: tab })
  },

  /* ===== 截图选择 ===== */
  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempPath = res.tempFiles[0].tempFilePath
        wx.compressImage({
          src: tempPath,
          quality: 80,
          success: (comp) => {
            this.setData({
              ocrPreview: comp.tempFilePath,
              ocrResult: null,
              ocrConfirmed: false,
            })
          },
          fail: () => {
            this.setData({
              ocrPreview: tempPath,
              ocrResult: null,
              ocrConfirmed: false,
            })
          }
        })
      }
    })
  },

  /* ===== OCR 识别 ===== */
  async ocrUpload() {
    if (!this.data.ocrPreview || this.data.ocring) return
    this.setData({ ocring: true, loading: true, loadingText: '正在识别截图中的睡眠数据...' })

    try {
      const openid = this._getOpenid()
      const fs = wx.getFileSystemManager()
      const base64 = fs.readFileSync(this.data.ocrPreview, 'base64')
      const imageData = 'data:image/jpeg;base64,' + base64

      const res = await this._request('/api/sleep/device-ocr', 'POST', {
        openid: openid,
        image_data: imageData,
      })
      const data = res.data || {}

      if (data.success) {
        this.setData({ ocrResult: data, ocrConfirmed: false })
        wx.showToast({ title: '识别成功', icon: 'success' })
      } else {
        wx.showToast({ title: data.error || '识别失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: '识别失败', icon: 'none' })
    } finally {
      this.setData({ ocring: false, loading: false })
    }
  },

  /* ===== 确认OCR结果 ===== */
  async confirmOcrResult() {
    this.setData({ loading: true, loadingText: '正在导入数据...' })
    try {
      this.setData({ ocrConfirmed: true })
      wx.showToast({ title: '数据已导入', icon: 'success' })
    } catch (e) {
      wx.showToast({ title: '导入失败', icon: 'none' })
    } finally {
      this.setData({ loading: false })
    }
  },

  /* ===== 手动输入 ===== */
  onFormInput(e) {
    const field = e.currentTarget.dataset.field
    const value = e.detail.value
    const form = { ...this.data.form }
    form[field] = value
    this.setData({ form: form, manualSubmitted: false })
  },

  async submitManual() {
    if (this.data.submitting) return
    this.setData({ submitting: true, loading: true, loadingText: '正在提交数据...' })

    try {
      const openid = this._getOpenid()
      const form = this.data.form
      const deviceData = { source: 'manual_input' }
      for (const [key, val] of Object.entries(form)) {
        if (val !== '' && val !== null && val !== undefined) {
          deviceData[key] = isNaN(Number(val)) ? val : Number(val)
        }
      }

      const res = await this._request('/api/sleep/device-data', 'POST', {
        openid: openid,
        device_data: deviceData,
      })
      const data = res.data || {}

      if (data.success) {
        this.setData({ manualSubmitted: true })
        wx.showToast({ title: '数据已导入', icon: 'success' })
      } else {
        wx.showToast({ title: data.error || '提交失败', icon: 'none' })
      }
    } catch (e) {
      wx.showToast({ title: '提交失败', icon: 'none' })
    } finally {
      this.setData({ submitting: false, loading: false })
    }
  },

  /* ===== 格式化分钟 ===== */
  formatMin(min) {
    if (!min && min !== 0) return '--'
    const h = Math.floor(min / 60)
    const m = min % 60
    return h + 'h' + m + 'm'
  },

  _request(url, method, data) {
    return new Promise((resolve, reject) => {
      const options = {
        url: url.startsWith('http') ? url : API_BASE + url,
        method: method || 'GET',
        success: (res) => resolve(res),
        fail: (err) => reject(err),
      }
      if (data && method === 'POST') {
        options.data = data
        options.header = { 'Content-Type': 'application/json' }
      }
      wx.request(options)
    })
  },

  _getOpenid() {
    try {
      const app = getApp()
      return (app.globalData && app.globalData.openid) || 'default'
    } catch (e) {
      return 'default'
    }
  },
})
