// pages/meditation-library/meditation-library.js — 眠小兔冥想内容库
const API_BASE = 'https://aisleepgen.com'

Page({
  data: {
    series: [],
    selectedSeries: null,
    items: [],
    loading: true,
    detailLoading: false,
    tags: [
      { id: 'all', name: '全部' },
      { id: 'sleep', name: '助眠' },
      { id: 'anxiety', name: '焦虑' },
      { id: 'focus', name: '专注' },
      { id: 'energy', name: '能量' },
      { id: 'stress', name: '减压' },
      { id: 'general', name: '通用' },
    ],
    activeTag: 'all',
    ambientName: '',
    logs: [],
  },

  onLoad() {
    this._loadSeries()
  },

  async _loadSeries() {
    this.setData({ loading: true })
    try {
      const res = await this._request('/api/meditation/series')
      this.setData({ series: res.data || [], loading: false })
      this.addLog('加载了 ' + (res.data ? res.data.length : 0) + ' 个冥想系列')
    } catch (e) {
      this.setData({ loading: false })
      this.addLog('加载失败: ' + (e.errMsg || ''))
    }
  },

  onSeriesTap(e) {
    const sid = e.currentTarget.dataset.sid
    const series = this.data.series.find(s => s.id === sid)
    if (!series) return

    this.setData({
      selectedSeries: series,
      items: [],
      detailLoading: true,
      ambientName: series.ambient || '',
    })

    wx.request({
      url: API_BASE + '/api/meditation/items?series_id=' + sid,
      success: (res) => {
        const data = res.data || {}
        this.setData({
          items: data.items || [],
          detailLoading: false,
        })
        this.addLog('加载 ' + (series.name || '') + ': ' + (data.items ? data.items.length : 0) + ' 集')
      },
      fail: () => {
        this.setData({ detailLoading: false })
        this.addLog('加载详情失败')
      }
    })
  },

  onItemTap(e) {
    const mid = e.currentTarget.dataset.mid
    const title = e.currentTarget.dataset.title
    const series = this.data.selectedSeries
    const ambient = this.data.ambientName

    // 跳转到统一冥想播放器
    wx.navigateTo({
      url: '/pages/meditation-player/meditation-player' +
           '?series_id=' + encodeURIComponent(series ? series.id : '') +
           '&item_id=' + encodeURIComponent(mid) +
           '&title=' + encodeURIComponent(title) +
           '&series_name=' + encodeURIComponent(series ? series.name : '') +
           '&duration=900' +
           '&ambient=' + encodeURIComponent(ambient),
    })
  },

  onTagTap(e) {
    const tag = e.currentTarget.dataset.tag
    this.setData({ activeTag: tag })
    this._loadSeries()
  },

  goBack() {
    this.setData({ selectedSeries: null, items: [], ambientName: '' })
  },

  _request(url) {
    return new Promise((resolve, reject) => {
      wx.request({
        url: url.startsWith('http') ? url : API_BASE + url,
        success: resolve,
        fail: reject,
      })
    })
  },

  addLog(msg) {
    const logs = this.data.logs
    const now = new Date()
    const t = now.getHours().toString().padStart(2,'0') + ':' +
              now.getMinutes().toString().padStart(2,'0') + ':' +
              now.getSeconds().toString().padStart(2,'0')
    logs.push('[' + t + '] ' + msg)
    if (logs.length > 20) logs.shift()
    this.setData({ logs })
  },
})
