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
  },

  onLoad() {
    this._loadProfile();
  },

  onShow() {
    if (this.data.userInfo.nickname) {
      this._loadProfile();
    }
  },

  _loadProfile() {
    this.setData({ loading: true, error: '' });

    console.log('[Profile] _loadProfile calling getUserProfile');
    api.getUserProfile()
      .then(res => {
        console.log('[Profile] getUserProfile returned, behavior:', JSON.stringify(res.behavior));
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
      })
      .catch(err => {
        this.setData({ loading: false, error: '加载失败' });
        console.warn('[Profile] Load error:', err);
      });
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
    wx.navigateTo({ url: '/pages/privacy/privacy' },
    );
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
});
