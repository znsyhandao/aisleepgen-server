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
        ]
      },
      {
        title: '隐私设置',
        icon: '🔒',
        items: [
          { id: 'shareAnonymousData', label: '匿名数据共享', desc: '帮助改进服务质量', category: 'privacy', type: 'switch', value: true },
          { id: 'showInLeaderboard', label: '排行榜', desc: '在排行榜中显示数据', category: 'privacy', type: 'switch', value: false },
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
    
    wx.showToast({ title: '设置已更新', icon: 'success', duration: 1200 });
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
