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
    // 推送相关
    pushEnabled: false,
    pendingPushes: [],
    pushCount: 0,
    showPushPanel: false,
    pushSettings: {},
    subscriptions: {},
    // 趋势图
    trendLabels: [],
    trendValues: [],
  },

  onLoad() {
    this._loadProfile();
    this._loadPushStatus();
  },

  onShow() {
    if (this.data.userInfo.nickname) {
      this._loadProfile();
    }
    // 每次显示刷新推送状态
    this._loadPushStatus();
  },

  _loadProfile() {
    this.setData({ loading: true, error: '' });

    api.getUserProfile()
      .then(res => {
        const ui = res.user_info || {};
        const mb = res.member || {};
        const bh = res.behavior || {};
        const st = res.stats || {};

        const sdist = bh.stress_type_distribution || {};
        var stressTypeList = [];
        for (var key in sdist) {
          stressTypeList.push({ type: key, count: sdist[key] });
        }
        stressTypeList.sort(function(a, b) { return b.count - a.count; });

        // 本周活跃天数
        const recentScores = st.recent_scores || st.weekly_scores || [];
        const activeDays = recentScores.filter(s => s && s.score > 0).length;

        // 趋势数据
        const trendLabels = [];
        const trendValues = [];
        const now = new Date();
        const dayNames = ['日','一','二','三','四','五','六'];
        for (let i = 6; i >= 0; i--) {
          const d = new Date(now);
          d.setDate(d.getDate() - i);
          trendLabels.push(dayNames[d.getDay()]);
          const found = recentScores.find(s => {
            if (!s || !s.date) return false;
            const sd = new Date(s.date);
            return sd.toDateString() === d.toDateString();
          });
          trendValues.push(found && found.score > 0 ? found.score : 0);
        }

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
            activeDays: activeDays + '/7',
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
          trendLabels: trendLabels,
          trendValues: trendValues,
          loading: false,
        });
        setTimeout(() => this._drawTrend(), 500);
      })
      .catch(err => {
        this.setData({ loading: false, error: '加载失败' });
        console.warn('[Profile] Load error:', err);
      });
  },

  // ===== 推送相关 =====

  _loadPushStatus() {
    // 获取推送设置和未读推送
    api.getPushSettings().then(res => {
      this.setData({
        pushSettings: res.settings || {},
        subscriptions: res.subscriptions || {},
        pushEnabled: !!(res.subscriptions && res.subscriptions.sleep_tip),
      });
    }).catch(() => {});

    api.getPendingPush().then(res => {
      const pushes = res.push || [];
      this.setData({
        pendingPushes: pushes,
        pushCount: pushes.length,
      });
    }).catch(() => {});
  },

  // 订阅推送
  handleSubscribePush() {
    const self = this;
    // 先尝试真实订阅，如果 tmplIds 为空则优雅降级
    const tmplIds = []; // TODO: 替换为微信公众平台申请的模板ID
    if (tmplIds.length === 0) {
      // 降级：直接记录订阅状态，不走微信订阅弹窗
      api.subscribeMsg(['sleep_tip'], 'sleep_tip').then(() => {
        self._loadPushStatus();
        wx.showToast({ title: '睡眠关怀已开启', icon: 'success' });
      }).catch(() => {
        wx.showToast({ title: '已开启，稍后生效', icon: 'success' });
        self._loadPushStatus();
      });
      return;
    }
    wx.requestSubscribeMessage({
      tmplIds: tmplIds,
      success(res) {
        // 收集用户同意的模板
        const accepted = [];
        for (const key in res) {
          if (res[key] === 'accept') {
            accepted.push(key);
          }
        }
        if (accepted.length > 0) {
          // 通知后端记录订阅
          api.subscribeMsg(accepted, 'sleep_tip').then(() => {
            self._loadPushStatus();
            wx.showToast({ title: '订阅成功', icon: 'success' });
          }).catch(() => {
            wx.showToast({ title: '订阅已记录', icon: 'success' });
          });
        } else {
          wx.showToast({ title: '未选择订阅', icon: 'none' });
        }
      },
      fail(err) {
        console.warn('[Subscribe] Failed:', err);
        wx.showToast({ title: '订阅失败，稍后再试', icon: 'none' });
      }
    });
  },

  // 显示推送面板
  showPushPanel() {
    this.setData({ showPushPanel: true });
  },

  hidePushPanel() {
    this.setData({ showPushPanel: false });
  },

  // 标记推送已读
  markPushRead(e) {
    const pushId = e.currentTarget.dataset.id;
    api.markPushRead(pushId).then(() => {
      this._loadPushStatus();
    }).catch(() => {});
  },

  // 标记推送已接受（用户点击了推送）
  markPushAccepted(e) {
    const pushId = e.currentTarget.dataset.id;
    api.markPushAccepted(pushId).then(() => {
      this._loadPushStatus();
      wx.showToast({ title: '已记录', icon: 'success' });
    }).catch(() => {});
  },

  // 设置推送偏好
  togglePushSetting(e) {
    const key = e.currentTarget.dataset.key;
    const current = this.data.pushSettings[key] || false;
    const newSettings = {};
    newSettings[key] = !current;
    this.setData({
      ['pushSettings.' + key]: newSettings[key],
    });
    api.updatePushSettings(newSettings).catch(() => {});
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
    wx.navigateTo({ url: '/pages/privacy/privacy' });
  },

  formatDuration(s) {
    if (!s) return '0';
    if (s < 60) return s + '\u79D2';
    var m = Math.floor(s / 60);
    var se = s % 60;
    return m + '\u5206' + (se > 0 ? se + '\u79D2' : '');
  },

  getLevelInfo(level) {
    const map = {
      free: { label: '\u514D\u8D39\u7248', icon: '\uD83C\uDF19', color: '#667eea' },
      pro: { label: '\u4E13\u4E1A\u7248', icon: '\u2B50', color: '#f6d365' },
      unlimited: { label: '\u65E0\u9650\u7248', icon: '\uD83D\uDC51', color: '#48dbfb' },
    };
    return map[level] || map.free;
  },

  // 绘制本周趋势图
  _drawTrend() {
    const labels = this.data.trendLabels;
    const values = this.data.trendValues;
    if (!labels || labels.length === 0) return;

    const query = wx.createSelectorQuery();
    query.select('#profileTrendCanvas').fields({ node: true, size: true }).exec(function(res) {
      if (!res || !res[0]) return;
      const canvas = res[0].node;
      const ctx = canvas.getContext('2d');
      const dpr = wx.getSystemInfoSync().pixelRatio;
      const width = res[0].width * dpr;
      const height = res[0].height * dpr;
      canvas.width = width;
      canvas.height = height;

      ctx.scale(dpr, dpr);
      const w = res[0].width;
      const h = res[0].height;

      ctx.clearRect(0, 0, w, h);

      const maxVal = 100;
      const padL = 30, padR = 20, padT = 10, padB = 25;
      const chartW = w - padL - padR;
      const chartH = h - padT - padB;

      ctx.strokeStyle = 'rgba(255,255,255,0.04)';
      ctx.lineWidth = 1;
      for (let i = 0; i <= 4; i++) {
        const y = padT + chartH * (1 - i / 4);
        ctx.beginPath();
        ctx.moveTo(padL, y);
        ctx.lineTo(w - padR, y);
        ctx.stroke();
      }

      const valid = values.filter(v => v > 0);
      if (valid.length === 0) {
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('暂无本周数据', w / 2, h / 2);
        return;
      }

      const step = chartW / Math.max(values.length - 1, 1);
      const pts = values.map((v, i) => ({
        x: padL + i * step,
        y: padT + chartH * (1 - (v > 0 ? v / maxVal : 0)),
        v: v
      }));

      const gradient = ctx.createLinearGradient(0, padT, 0, padT + chartH);
      gradient.addColorStop(0, 'rgba(102, 126, 234, 0.3)');
      gradient.addColorStop(1, 'rgba(102, 126, 234, 0)');

      ctx.beginPath();
      ctx.moveTo(pts[0].x, padT + chartH);
      for (const p of pts) ctx.lineTo(p.x, p.v > 0 ? p.y : padT + chartH);
      ctx.lineTo(pts[pts.length-1].x, padT + chartH);
      ctx.closePath();
      ctx.fillStyle = gradient;
      ctx.fill();

      ctx.beginPath();
      for (const p of pts) {
        if (p.v > 0) {
          if (p === pts.find(p2 => p2.v > 0)) ctx.moveTo(p.x, p.y);
          else ctx.lineTo(p.x, p.y);
        }
      }
      ctx.strokeStyle = '#667eea';
      ctx.lineWidth = 2;
      ctx.stroke();

      for (const p of pts) {
        if (p.v > 0) {
          ctx.beginPath();
          ctx.arc(p.x, p.y, 3, 0, Math.PI * 2);
          ctx.fillStyle = '#667eea';
          ctx.fill();
        }
      }

      ctx.fillStyle = 'rgba(255,255,255,0.3)';
      ctx.font = '10px sans-serif';
      ctx.textAlign = 'center';
      for (let i = 0; i < labels.length; i++) {
        ctx.fillText(labels[i], padL + i * step, h - padB + 15);
      }

      ctx.fillStyle = 'rgba(255,255,255,0.5)';
      ctx.font = '9px sans-serif';
      for (const p of pts) {
        if (p.v > 0) {
          ctx.fillText(Math.round(p.v), p.x, p.y - 8);
        }
      }
    });
  },
});
