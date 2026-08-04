const api = require('../../utils/api');

Page({
  data: {
    loading: true,
    error: '',
    userInfo: {},
    member: {},
    relaxStats: {
      total_sessions: 0,
      completed_sessions: 0,
      avg_duration: 0,
      relax_streak_days: 0,
      stress_type_distribution: {},
    },

    // 会员升级
    showUpgradeModal: false,
    pricing: null,
    selectedTier: 'pro',
    selectedPeriod: 'month',
    ordering: false,
    recommendation: null,          // AI智能推荐
    hasRecommendation: false,      // 是否有推荐
    upgradeSuccess: false,         // 升级成功提示
    paidDaysRemaining: 999,        // 剩余天数（有档期用）

    // 硬件设备
    huaweiConnected: false,
    lastSyncText: '',

    menuItems: [
      { icon: '📊', text: '历史记录', desc: '查看所有分析记录', page: '/pages/history/history' },
      { icon: '🔔', text: '推送设置', desc: '管理消息通知', page: '/pages/settings/settings' },
      { icon: '📝', text: '隐私政策', desc: '了解数据安全', page: '/pages/privacy/privacy' },
    ],
  },

  onLoad() {
    this._loadProfile();
    this._loadPricing();
  },

  _checkBandStatus() {
    const app = getApp();
    const openid = (app.globalData && app.globalData.openid) || '';
    if (!openid) return;
    wx.request({
      url: 'https://aisleepgen.com/api/huawei/status?openid=' + openid,
      success: (res) => {
        const d = res.data || {};
        this.setData({
          huaweiConnected: d.connected === true,
          lastSyncText: d.synced_at || '',
        });
      },
      fail: () => {}
    });
  },

  goBandPage() {
    wx.navigateTo({ url: '/pages/band/band' });
  },

  goMeditationLibrary() {
    wx.navigateTo({ url: '/pages/meditation-library/meditation-library' });
  },

  _loadProfile() {
    this.setData({ loading: true, error: '' });
    api.getUserProfile()
      .then(res => {
        const ui = res.user_info || {};
        const mb = res.member || {};
        const bh = res.behavior || {};

        const sdist = bh.stress_type_distribution || {};
        var stressTypeList = [];
        for (var key in sdist) {
          stressTypeList.push({ type: key, count: sdist[key] });
        }
        stressTypeList.sort(function(a, b) { return b.count - a.count; });

        this.setData({
          userInfo: {
            nickname: ui.nickname || '睡眠探索者',
            avatarUrl: ui.avatar_url || '',
          },
          member: {
            level: mb.level || 'free',
            totalSessions: mb.total_sessions || 0,
            totalDays: mb.total_days || 0,
            streakDays: mb.streak_days || 0,
            avgScore: mb.avg_score || 0,
            avgScore7d: mb.avg_score_7d || 0,
            joinedAt: mb.joined_at || '2025',
            expireAt: mb.expire_at || '',
          },
          relaxStats: {
            total_sessions: bh.total_relax_sessions || 0,
            completed_sessions: bh.total_completed_sessions || 0,
            interrupted_sessions: bh.total_interrupted_sessions || 0,
            total_seconds: bh.total_relax_seconds || 0,
            avg_duration: bh.avg_relax_duration || 0,
            relax_streak_days: bh.relax_streak_days || 0,
            stress_types: stressTypeList,
            weekly_counts: bh.weekly_counts || [],
          },
          loading: false,
        });

        // 加载完profile后检查智能推荐
        this._checkRecommendation();
      })
      .catch(err => {
        this.setData({ loading: false, error: '加载失败' });
        console.warn('[Profile] Load error:', err);
      });
  },

  _loadPricing() {
    api.getPricing()
      .then(res => {
        this.setData({ pricing: res.pricing });
      })
      .catch(() => {});
  },

  _checkRecommendation() {
    api.getTierRecommendation()
      .then(res => {
        if (res && res.should_recommend) {
          this.setData({
            recommendation: res,
            hasRecommendation: true,
          });
        }
      })
      .catch(() => {});
  },

  getUserInfo(e) {
    if (e.detail && e.detail.userInfo) {
      const info = e.detail.userInfo;
      api.updateUserProfile({
        nickname: info.nickName,
        avatar_url: info.avatarUrl,
        gender: info.gender || 0,
      }).catch(() => {});
      this.setData({
        'userInfo.nickname': info.nickName,
        'userInfo.avatarUrl': info.avatarUrl,
      });
    }
  },

  goHistory() {
    wx.navigateTo({ url: '/pages/history/history' });
  },

  goPrivacy() {
    wx.navigateTo({
      url: '/pages/privacy/privacy',
    });
  },

  formatDuration(s) {
    if (!s) return '0';
    if (s < 60) return s + '秒';
    var m = Math.floor(s / 60);
    var se = s % 60;
    return m + '分' + (se > 0 ? se + '秒' : '');
  },

  getLevelInfo(level) {
    const map = {
      free: { label: '免费版', icon: '🌙', color: '#667eea' },
      pro: { label: '专业版', icon: '⭐', color: '#f6d365' },
      unlimited: { label: '无限版', icon: '👑', color: '#48dbfb' },
    };
    return map[level] || map.free;
  },

  // ===== 会员升级 =====

  // 打开升级弹窗
  openUpgrade() {
    this.setData({
      showUpgradeModal: true,
      upgradeSuccess: false,
      selectedTier: 'pro',
      selectedPeriod: 'month',
    });
  },

  closeUpgrade() {
    this.setData({ showUpgradeModal: false });
  },

  selectTier(e) {
    var tier = e.currentTarget.dataset.tier;
    this.setData({ selectedTier: tier });
  },

  selectPeriod(e) {
    var period = e.currentTarget.dataset.period;
    this.setData({ selectedPeriod: period });
  },

  // 点击AI推荐 - 直接选推荐套餐
  applyRecommendation() {
    var rec = this.data.recommendation;
    if (!rec) return;
    this.setData({
      selectedTier: rec.tier,
      selectedPeriod: 'month',
    });
  },

  // 关闭推荐卡片
  dismissRecommendation() {
    this.setData({ hasRecommendation: false });
  },

  // 计算选定套餐价格
  getSelectedPrice() {
    var p = this.data.pricing;
    if (!p) return 0;
    var tc = p[this.data.selectedTier];
    if (!tc) return 0;
    var period = this.data.selectedPeriod;
    if (period === 'quarter' && tc.price_quarter) return tc.price_quarter;
    if (period === 'year' && tc.price_year) return tc.price_year;
    return tc.price;
  },

  // 确认支付
  doPayment() {
    var tier = this.data.selectedTier;
    var period = this.data.selectedPeriod;
    if (this.data.ordering) return;

    this.setData({ ordering: true });

    api.createOrder(tier, period)
      .then(res => {
        if (res.no_payment) {
          // 商户号未配置
          wx.showToast({
            title: '支付功能暂未开放',
            icon: 'none',
            duration: 2000,
          });
          this.setData({ ordering: false });
          return;
        }

        if (!res.success) {
          wx.showToast({ title: res.error || '下单失败', icon: 'none' });
          this.setData({ ordering: false });
          return;
        }

        // 调用微信支付
        var params = res.pay_params;
        wx.requestPayment({
          timeStamp: params.timeStamp,
          nonceStr: params.nonceStr,
          package: params.package,
          signType: params.signType || 'MD5',
          paySign: params.paySign,
          success: () => {
            // 支付成功，等待后端回调
            this.setData({
              ordering: false,
              upgradeSuccess: true,
            });
            // 刷新profile
            setTimeout(() => {
              this._loadProfile();
              this.closeUpgrade();
            }, 2000);
          },
          fail: (err) => {
            if (err.errMsg && err.errMsg.indexOf('cancel') > -1) {
              wx.showToast({ title: '已取消支付', icon: 'none' });
            } else {
              wx.showToast({ title: '支付失败: ' + (err.errMsg || ''), icon: 'none' });
            }
            this.setData({ ordering: false });
          },
          complete: () => {
            this.setData({ ordering: false });
          }
        });
      })
      .catch(err => {
        this.setData({ ordering: false });
        wx.showToast({ title: '请求失败', icon: 'none' });
        console.warn('[Profile] createOrder error:', err);
      });
  },

  // 阻止弹窗背景滑动穿透
  preventTouchMove() {},

  handleNavClick(e) {
    var page = e.currentTarget.dataset.page;
    if (page) {
      wx.navigateTo({ url: page });
    }
  },
  goClinicalReport() {
    var that = this;
    wx.showLoading({ title: '生成报告中...' });
    wx.request({
      url: 'http://82.156.208.245/api/clinical-report',
      method: 'POST',
      data: { openid: wx.getStorageSync('openid') || '' },
      success(res) {
        wx.hideLoading();
        if (res.data && res.data.success) {
          wx.navigateTo({
            url: '/pages/clinical-report/clinical-report?data=' + encodeURIComponent(JSON.stringify(res.data))
          });
        } else {
          wx.showToast({ title: '数据不足，请先记录睡眠', icon: 'none' });
        }
      },
      fail() {
        wx.hideLoading();
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  }
});
