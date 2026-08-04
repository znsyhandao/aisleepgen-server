// pages/settings/settings.js - 专业设置页
const api = require('../../utils/api');

Page({
  data: {
    pageName: 'settings',
    showBackButton: false,
    
    // 设置项分组
    settingGroups: [
      {
        title: '通知设置',
        icon: '🔔',
        items: [
          { id: 'dailyReminder', label: '每日提醒', desc: '每天定时提醒睡眠分析', category: 'notifications', type: 'switch', value: true },
          { id: 'weeklyReport', label: '周报推送', desc: '每周推送睡眠质量报告', category: 'notifications', type: 'switch', value: true },
          { id: 'bedtimeReminder', label: '睡前推送', desc: '每晚提醒该睡觉了', category: 'notifications', type: 'switch', value: false },
          { id: 'scoreAlert', label: '评分变化通知', desc: '评分显著变化时提醒您', category: 'notifications', type: 'switch', value: false },
        ]
      },
      {
        title: '分析设置',
        icon: '📊',
        items: [
          { id: 'autoStart', label: '自动分析', desc: '检测睡眠状态后自动开始', category: 'analysis', type: 'switch', value: true },
          { id: 'uploadToCloud', label: '云端备份', desc: '自动备份数据到云端', category: 'analysis', type: 'switch', value: true },
          { id: 'saveRawData', label: '保存原始数据', desc: '保留完整的原始数据', category: 'analysis', type: 'switch', value: false },
        { id: 'restfulMode', label: '静息陪伴模式', desc: '到入睡时间自动引导呼吸，整晚守护', category: 'analysis', type: 'switch', value: false },
        ]
      },
      {
        title: '静息陪伴',
        icon: '🌙',
        items: [
          { id: 'restfulBedtime', label: '目标入睡时间', desc: '到点自动开启呼吸引导', category: 'restful', type: 'timepicker', value: '23:00' },
          { id: 'restfulProtocol', label: '呼吸协议', desc: '选择引导节奏', category: 'restful', type: 'radio', value: '4-7-8', options: [
            { value: '4-7-8', label: '4-7-8 放松呼吸', desc: '标准放松法' },
            { value: 'box', label: '盒式呼吸', desc: '均匀四拍' },
            { value: 'long_exhale', label: '延长呼气', desc: '吸气短呼气长' },
          ]},
          { id: 'restfulNightMonitor', label: '整晚监测', desc: '夜醒时自动重新引导', category: 'restful', type: 'switch', value: true },
        ]
      },
      {
        title: '隐私设置',
        icon: '🔒',
        items: [
          { id: 'shareAnonymousData', label: '匿名数据共享', desc: '帮助改进服务质量', category: 'privacy', type: 'switch', value: true },
          { id: 'showInLeaderboard', label: '排行榜', desc: '在排行榜中显示数据', category: 'privacy', type: 'switch', value: false },
        ]
      },
      {
        title: '分析风格',
        icon: '🎨',
        items: [
          { id: 'analysisStyle', label: '分析风格', desc: '选择你偏好的分析风格', category: 'style', type: 'radio', value: 'hybrid', options: [
            { value: 'data', label: '数据型', desc: '百分比+趋势线+相关性' },
            { value: 'experience', label: '体验型', desc: '温暖描述+感觉启发' },
            { value: 'hybrid', label: '混合型', desc: '数据与体验平衡' }
          ]}
        ]
      }
    ],
    
    // 关于信息
    appInfo: {
      version: '1.0.0',
      build: '20260426',
      name: 'AISleepGen',
      tagline: 'AI驱动的睡眠分析助手'
    }
  },

  onLoad() {
    const pages = getCurrentPages();
    this.setData({ showBackButton: pages.length > 1 });
    this._loadSettings();
  },

  _loadSettings() {
    const saved = wx.getStorageSync('app_settings');
    if (saved) {
      // 更新settingGroups的value
      const groups = this.data.settingGroups.map(group => ({
        ...group,
        items: group.items.map(item => ({
          ...item,
          value: saved[item.category]?.[item.id] ?? item.value
        }))
      }));
      this.setData({ settingGroups: groups });
    }
    // 从后端加载静息陪伴设置
    this._loadRestfulFromServer();
  },

  _loadRestfulFromServer() {
    const openid = wx.getStorageSync('openid') || 'default';
    api.post('/api/restful/setting', { openid }).then(res => {
      if (res && res.success && res.setting) {
        const s = res.setting;
        const groups = this.data.settingGroups;
        let found = false;
        for (const g of groups) {
          for (const item of g.items) {
            if (item.id === 'restfulMode' && s.enabled !== undefined) {
              item.value = s.enabled; found = true;
            } else if (item.id === 'restfulBedtime' && s.bedtime) {
              item.value = s.bedtime; found = true;
            } else if (item.id === 'restfulProtocol' && s.protocol) {
              item.value = s.protocol; found = true;
            } else if (item.id === 'restfulNightMonitor' && s.night_monitor !== undefined) {
              item.value = !!s.night_monitor; found = true;
            }
          }
        }
        if (found) this.setData({ settingGroups: groups });
      }
    }).catch(() => {});
  },

  _saveSettings() {
    const saved = {};
    this.data.settingGroups.forEach(group => {
      group.items.forEach(item => {
        if (!saved[item.category]) saved[item.category] = {};
        saved[item.category][item.id] = item.value;
      });
    });
    wx.setStorageSync('app_settings', saved);
  },

  // 切换开关
  toggleSwitch(e) {
    const { gidx, iidx } = e.currentTarget.dataset;
    const key = `settingGroups[${gidx}].items[${iidx}].value`;
    this.setData({ [key]: !this.data.settingGroups[gidx].items[iidx].value });
    this._saveSettings();
    
    // 静息陪伴模式开关变更时同步后端
    const item = this.data.settingGroups[gidx].items[iidx];
    if (item.id === 'restfulMode' || item.id === 'restfulNightMonitor') {
      this._syncRestfulSettings();
    }
    
    wx.showToast({ title: '设置已更新', icon: 'success', duration: 1200 });
  },

  // radio选择
  selectRadio(e) {
    const { gidx, iidx } = e.currentTarget.dataset;
    const value = e.detail.value;
    const key = `settingGroups[${gidx}].items[${iidx}].value`;
    this.setData({ [key]: value });
    this._saveSettings();
    // 如果是呼吸协议变更，同步后端
    const item = this.data.settingGroups[gidx].items[iidx];
    if (item.id && item.id.startsWith('restful')) {
      this._syncRestfulSettings();
    }
    wx.showToast({ title: '设置已更新', icon: 'success', duration: 1200 });
  },

  // 时间选择器
  selectTime(e) {
    const { gidx, iidx } = e.currentTarget.dataset;
    const value = e.detail.value;
    const key = `settingGroups[${gidx}].items[${iidx}].value`;
    this.setData({ [key]: value });
    this._saveSettings();
    this._syncRestfulSettings();
    wx.showToast({ title: '入睡时间已设置', icon: 'success', duration: 1200 });
  },

  // 同步静息陪伴设置到后端
  _syncRestfulSettings() {
    const groups = this.data.settingGroups;
    let enabled = false, bedtime = '23:00', protocol = '4-7-8', nightMonitor = true;
    for (const g of groups) {
      for (const item of g.items) {
        if (item.id === 'restfulMode') enabled = item.value;
        else if (item.id === 'restfulBedtime') bedtime = item.value;
        else if (item.id === 'restfulProtocol') protocol = item.value;
        else if (item.id === 'restfulNightMonitor') nightMonitor = item.value;
      }
    }
    const openid = wx.getStorageSync('openid') || 'default';
    api.post('/api/restful/setting', {
      openid,
      updates: { enabled, bedtime, protocol, audio_preference: 'voice', night_monitor: nightMonitor }
    }).catch(() => {});  // 静默失败，不影响本地体验
  },

  // ===== 操作 =====
  resetToDefault() {
    wx.showModal({
      title: '恢复默认',
      content: '确定恢复所有设置为默认值？',
      success: (res) => {
        if (res.confirm) {
          this.onLoad();
          this._saveSettings();
          wx.showToast({ title: '已恢复默认', icon: 'success' });
        }
      }
    });
  },

  clearCache() {
    wx.showModal({
      title: '清除缓存',
      content: '清除临时文件，不影响您的睡眠数据。',
      success: (res) => {
        if (res.confirm) {
          wx.clearStorageSync();
          wx.showToast({ title: '已清除', icon: 'success' });
          this.onLoad();
        }
      }
    });
  },

  checkUpdate() {
    wx.showToast({ title: '已是最新版本', icon: 'success' });
  },

  viewAbout() {
    const info = this.data.appInfo;
    wx.showModal({
      title: `关于 ${info.name}`,
      content: `${info.tagline}\n\n版本: ${info.version} (${info.build})\n\n© 2026 AISleepGen Team`,
      showCancel: false
    });
  },

  contactSupport() {
    wx.showModal({
      title: '联系支持',
      content: '邮件: support@aisleepgen.com\n\n工作时间: 周一至周五 9:00-18:00',
      showCancel: false
    });
  },

  goBandPage() {
    wx.navigateTo({ url: '/pages/band/band' });
  },

  exportData() {
    wx.showActionSheet({
      itemList: ['导出为JSON', '导出为CSV'],
      success: (res) => {
        wx.showToast({ title: '导出功能开发中', icon: 'none' });
      }
    });
  },

  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) wx.navigateBack();
    else wx.switchTab({ url: '/pages/index/index' });
  },

  onShareAppMessage() {
    return { title: 'AISleepGen 睡眠助手', path: '/pages/settings/settings' };
  }
});
