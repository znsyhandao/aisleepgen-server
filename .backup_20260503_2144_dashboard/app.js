// app.js
const api = require('./utils/api');

App({
  onLaunch: function () {
    console.log('AISleepGen started');
    // 启动时获取微信登录code，换取openid
    this._initLogin();
  },

  _initLogin: function () {
    const that = this;
    // 先检查本地缓存的openid
    const cached = wx.getStorageSync('aisleepgen_openid');
    if (cached) {
      that.globalData.openid = cached;
      console.log('[Login] 使用缓存openid: ' + cached.slice(0, 8) + '...');
      // 同时后台调self-heal检测（不阻塞）
      api.selfHeal().catch(function(){});
      return;
    }
    // wx.login获取code，后端换openid
    wx.login({
      success: function (res) {
        if (res.code) {
          api.wxLogin(res.code).then(function (data) {
            if (data.openid) {
              that.globalData.openid = data.openid;
              wx.setStorageSync('aisleepgen_openid', data.openid);
              console.log('[Login] 获取openid: ' + data.openid.slice(0, 8) + '...');
              // 后台调self-heal检测（不阻塞）
              api.selfHeal().catch(function(){});
              // 检测问卷状态，未填则跳转onboarding
              api.getUserProfile().then(function(prof) {
                if (!prof.onboarding_done) {
                  setTimeout(function() {
                    wx.redirectTo({ url: '/pages/onboarding/onboarding' });
                  }, 800);
                }
              }).catch(function(){});
            }
          }).catch(function () {
            console.warn('[Login] 登录失败，使用默认openid');
            that.globalData.openid = 'default';
          });
        }
      },
      fail: function () {
        console.warn('[Login] wx.login失败，使用默认openid');
        that.globalData.openid = 'default';
      }
    });
  },

  onShow: function () {
    console.log('app shown');
  },

  onHide: function () {
    console.log('app hidden');
  },

  globalData: {
    userInfo: null,
    openid: 'default',
    version: '1.0.0'
  }
});
