// app.js
const api = require('./utils/api');

App({
  onLaunch: function () {
    console.log('AISleepGen started');

    // ===== 隐私政策授权弹窗（微信2023新规必含）=====
    const privacyConsent = wx.getStorageSync('aisleepgen_privacy_consent');
    if (!privacyConsent) {
      // 暂不初始化登录，等用户同意隐私后再执行
      this._showPrivacyDialog();
    } else {
      this._initLogin();
    }
  },

  _showPrivacyDialog: function () {
    const that = this;
    wx.showModal({
      title: '隐私政策与用户协议',
      content: '在使用前，请仔细阅读并同意《隐私协议》和《用户协议》。我们将严格保护您的个人数据安全。',
      confirmText: '同意并继续',
      cancelText: '暂不使用',
      success: function (res) {
        if (res.confirm) {
          wx.setStorageSync('aisleepgen_privacy_consent', true);
          wx.showToast({ title: '感谢您的信任', icon: 'none', duration: 1500 });
          setTimeout(function () {
            that._initLogin();
          }, 1000);
        } else {
          wx.showToast({
            title: '需要同意隐私协议才能使用',
            icon: 'none',
            duration: 3000
          });
          // 给用户一个查看隐私协议全文的入口
          setTimeout(function () {
            wx.showModal({
              title: '查看隐私协议',
              content: '您可以随时在「我的-设置-隐私与协议」中查看完整协议。点击「同意并继续」开始使用。',
              confirmText: '同意并继续',
              cancelText: '暂不使用',
              success: function (r2) {
                if (r2.confirm) {
                  wx.setStorageSync('aisleepgen_privacy_consent', true);
                  that._initLogin();
                }
              }
            });
          }, 500);
        }
      }
    });
  },

  _initLogin: function () {
    const that = this;
    // 先检查本地缓存的openid
    const cached = wx.getStorageSync('aisleepgen_openid');
    if (cached) {
      that.globalData.openid = cached;
      console.log('[Login] 最终openid: ' + that.globalData.openid);
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
              console.log('[Login] 最终openid(新): ' + that.globalData.openid);
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
                } else {
                  // 已填过问卷，检查ISI到期
                  api.isiStatus().then(function(isi) {
                    if (isi && isi.needs_isi) {
                      setTimeout(function() {
                        wx.showModal({
                          title: '睡眠状况复查',
                          content: '距上次评估已过' + (isi.days_since_last || 2) + '天，花2分钟做个快速复查？',
                          confirmText: '好的',
                          cancelText: '下次',
                          success: function(res) {
                            if (res.confirm) {
                              wx.navigateTo({ url: '/pages/onboarding/onboarding?mode=isi_only' });
                            }
                          }
                        });
                      }, 1500);
                    }
                  }).catch(function(){});
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

  onError: function (error) {
    console.error('[AISleepGen] 未捕获错误:', error);
    try {
      wx.setStorageSync('aisleepgen_last_error', {
        msg: String(error).slice(0, 200),
        time: new Date().toISOString(),
      });
    } catch (e) {}
  },

  globalData: {
    userInfo: null,
    openid: 'default',
    version: '1.0.0'
  }
});
