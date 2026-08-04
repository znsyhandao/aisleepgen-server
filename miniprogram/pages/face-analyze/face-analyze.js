// face-analyze.js — 面容疲劳分析页
const app = getApp();
const API_BASE = app.globalData?.apiBase || 'http://100.77.59.81:8090';

Page({
  data: {
    mode: 'bedtime',
    photoPath: '',
    loading: false,
    result: null,
    error: '',
  },

  // 切换睡前/醒后
  switchMode(e) {
    const mode = e.currentTarget.dataset.mode;
    this.setData({ mode, result: null, error: '' });
  },

  // 拍照
  takePhoto() {
    const self = this;
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['camera'],
      camera: 'front',
      sizeType: ['compressed'],
      success(res) {
        const tempPath = res.tempFiles[0].tempFilePath;
        self.setData({
          photoPath: tempPath,
          result: null,
          error: '',
        });
      },
      fail(err) {
        if (err.errMsg.indexOf('cancel') === -1) {
          self.setData({ error: '拍照失败，请检查相机权限' });
        }
      }
    });
  },

  // 分析面容
  analyzeFace() {
    const self = this;
    if (!self.data.photoPath) return;

    self.setData({ loading: true, error: '', result: null });

    // 读取图片并转 base64
    wx.getFileSystemManager().readFile({
      filePath: self.data.photoPath,
      encoding: 'base64',
      success(fsRes) {
        const b64 = fsRes.data;
        const openid = wx.getStorageSync('openid') || 'default';

        wx.request({
          url: `${API_BASE}/api/sleep-from-face`,
          method: 'POST',
          data: {
            image: b64,
            mode: self.data.mode,
            openid: openid,
          },
          header: { 'content-type': 'application/json' },
          success(resp) {
            const data = resp.data;
            if (data.success) {
              self.setData({ result: data, loading: false });
            } else {
              self.setData({
                error: data.error || '分析失败，请重试',
                loading: false,
              });
            }
          },
          fail(err) {
            self.setData({
              error: '网络请求失败，请检查服务器是否运行',
              loading: false,
            });
          }
        });
      },
      fail(err) {
        self.setData({
          error: '读取图片失败',
          loading: false,
        });
      }
    });
  },

  // 回首页
  goBack() {
    wx.navigateBack({ delta: 1 });
  }
});
