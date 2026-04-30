// pages/history/history.js - 完整版
Page({
  data: {
    pageName: 'history',
    showBackButton: false,
    
    // 筛选条件
    filters: {
      dateRange: 'week', // week, month, year, all
      minScore: 0,
      maxScore: 100,
      quality: 'all', // all, excellent, good, average, poor
      sortBy: 'date', // date, score, duration
      sortOrder: 'desc' // asc, desc
    },
    
    // 历史记录
    historyRecords: [],
    
    // 统计数据
    stats: {
      totalRecords: 0,
      averageScore: 0,
      bestScore: 0,
      worstScore: 100,
      totalDuration: 0,
      consistency: 0
    },
    
    // 图表数据
    chartData: {
      dates: [],
      scores: [],
      durations: []
    },
    
    // 加载状态
    loading: false,
    hasMore: true,
    showEmpty: false,
    showList: false,
    showLoadMore: false,
    page: 1,
    pageSize: 20
  },

  onLoad() {
    console.log('历史记录页面加载');
    
    // 检查页面栈
    const pages = getCurrentPages();
    if (pages.length > 1) {
      this.setData({
        showBackButton: true
      });
    }
    
    // 加载历史记录
    this.loadHistoryRecords();
  },

  onShow() {
    // 页面显示时刷新数据
    this.loadHistoryRecords();
  },

  loadHistoryRecords() {
    this.setData({ loading: true });
    
    // 从本地存储加载历史记录
    const allRecords = wx.getStorageSync('analysis_history') || [];
    
    // 如果没有数据,生成模拟数据
    if (allRecords.length === 0) {
      this.generateMockData();
      return;
    }
    
    // 应用筛选条件
    let filteredRecords = this.applyFilters(allRecords);
    
    // 应用排序
    filteredRecords = this.applySorting(filteredRecords);
    
    // 分页
    const startIndex = (this.data.page - 1) * this.data.pageSize;
    const endIndex = startIndex + this.data.pageSize;
    const pagedRecords = filteredRecords.slice(startIndex, endIndex);
    
    // 更新数据
    var hasMore = endIndex < filteredRecords.length;
    var records = pagedRecords;
    this.setData({
      historyRecords: records,
      loading: false,
      hasMore: hasMore,
      showEmpty: !this.data.loading && records.length === 0,
      showList: !this.data.loading && records.length > 0,
      showLoadMore: hasMore && !this.data.loading
    });
    
    // 计算统计数据
    this.calculateStats(filteredRecords);
    
    // 更新图表数据
    this.updateChartData(filteredRecords);
  },

  // 生成模拟数据
  generateMockData() {
    const mockRecords = [];
    const now = new Date();
    
    for (let i = 0; i < 30; i++) {
      const date = new Date(now);
      date.setDate(date.getDate() - i);
      
      const score = 60 + Math.floor(Math.random() * 35); // 60-95
      const hours = 6 + Math.floor(Math.random() * 3); // 6-8
      const minutes = Math.floor(Math.random() * 60);
      
      mockRecords.push({
        id: Date.now() + i,
        date: date.toLocaleDateString(),
        time: date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
        score: score,
        duration: `${hours}h ${minutes}m`,
        quality: this.getQualityLevel(score),
        type: ['自动分析', '快速分析', '手动分析'][Math.floor(Math.random() * 3)]
      });
    }
    
    // 保存模拟数据
    wx.setStorageSync('analysis_history', mockRecords);
    
    // 重新加载
    this.loadHistoryRecords();
  },

  applyFilters(records) {
    const { dateRange, minScore, maxScore, quality } = this.data.filters;
    
    return records.filter(record => {
      // 日期范围筛选
      if (dateRange !== 'all') {
        const recordDate = new Date(record.date);
        const now = new Date();
        let startDate;
        
        switch(dateRange) {
          case 'week':
            startDate = new Date(now.setDate(now.getDate() - 7));
            break;
          case 'month':
            startDate = new Date(now.setMonth(now.getMonth() - 1));
            break;
          case 'year':
            startDate = new Date(now.setFullYear(now.getFullYear() - 1));
            break;
        }
        
        if (recordDate < startDate) {
          return false;
        }
      }
      
      // 分数范围筛选
      if (record.score < minScore || record.score > maxScore) {
        return false;
      }
      
      // 质量筛选
      if (quality !== 'all') {
        const recordQuality = this.getQualityLevel(record.score);
        if (recordQuality !== quality) {
          return false;
        }
      }
      
      return true;
    });
  },

  applySorting(records) {
    const { sortBy, sortOrder } = this.data.filters;
    
    return records.sort((a, b) => {
      let comparison = 0;
      
      switch(sortBy) {
        case 'date':
          comparison = new Date(b.date) - new Date(a.date);
          break;
        case 'score':
          comparison = b.score - a.score;
          break;
        case 'duration':
          const durationA = this.parseDuration(a.duration);
          const durationB = this.parseDuration(b.duration);
          comparison = durationB - durationA;
          break;
      }
      
      return sortOrder === 'asc' ? -comparison : comparison;
    });
  },

  parseDuration(durationStr) {
    // 解析 "7h 30m" 格式的时长
    const match = durationStr.match(/(\d+)h\s*(\d+)m/);
    if (match) {
      return parseInt(match[1]) * 60 + parseInt(match[2]);
    }
    return 0;
  },

  getQualityLevel(score) {
    if (score >= 85) return '优秀';
    if (score >= 75) return '良好';
    if (score >= 65) return '一般';
    return '需要改善';
  },

  calculateStats(records) {
    if (records.length === 0) {
      this.setData({
        stats: {
          totalRecords: 0,
          averageScore: 0,
          bestScore: 0,
          worstScore: 100,
          totalDuration: 0,
          consistency: 0
        }
      });
      return;
    }
    
    let totalScore = 0;
    let totalDuration = 0;
    let bestScore = 0;
    let worstScore = 100;
    
    records.forEach(record => {
      totalScore += record.score;
      totalDuration += this.parseDuration(record.duration);
      bestScore = Math.max(bestScore, record.score);
      worstScore = Math.min(worstScore, record.score);
    });
    
    // 计算一致性(分数标准差)
    const averageScore = totalScore / records.length;
    let variance = 0;
    records.forEach(record => {
      variance += Math.pow(record.score - averageScore, 2);
    });
    const stdDev = Math.sqrt(variance / records.length);
    const consistency = Math.max(0, 100 - stdDev * 2);
    
    this.setData({
      stats: {
        totalRecords: records.length,
        averageScore: Math.round(averageScore),
        bestScore,
        worstScore,
        totalDuration: Math.round(totalDuration / 60), // 转换为小时
        consistency: Math.round(consistency)
      }
    });
  },

  updateChartData(records) {
    // 取最近15条记录用于图表
    const recentRecords = records.slice(0, 15).reverse();
    
    const dates = recentRecords.map(r => {
      const date = new Date(r.date);
      return `${date.getMonth() + 1}/${date.getDate()}`;
    });
    
    const scores = recentRecords.map(r => r.score);
    const durations = recentRecords.map(r => this.parseDuration(r.duration) / 60); // 转换为小时
    
    this.setData({
      chartData: { dates, scores, durations }
    });
  },

  // 更新筛选条件
  updateFilter(e) {
    const { key, value } = e.currentTarget.dataset;
    this.setData({
      [`filters.${key}`]: value
    });
    
    // 重新加载数据
    this.setData({ page: 1 });
    this.loadHistoryRecords();
  },

  // 查看记录详情
  viewRecordDetail(e) {
    const index = e.currentTarget.dataset.index;
    const record = this.data.historyRecords[index];
    
    if (record) {
      wx.showModal({
        title: `记录详情 - ${record.date}`,
        content: `时间: ${record.time}\n评分: ${record.score}分\n时长: ${record.duration}\n质量: ${record.quality}\n类型: ${record.type}`,
        confirmText: '查看完整报告',
        cancelText: '关闭',
        success: (res) => {
          if (res.confirm) {
            // 这里可以跳转到详细报告页面
            wx.showToast({
              title: '报告功能开发中',
              icon: 'none'
            });
          }
        }
      });
    }
  },

  // 删除记录
  deleteRecord(e) {
    const index = e.currentTarget.dataset.index;
    const record = this.data.historyRecords[index];
    
    if (!record) return;
    
    wx.showModal({
      title: '删除记录',
      content: `确定要删除 ${record.date} 的记录吗？`,
      success: (res) => {
        if (res.confirm) {
          this.confirmDeleteRecord(record.id);
        }
      }
    });
  },

  confirmDeleteRecord(id) {
    // 从本地存储删除
    let allRecords = wx.getStorageSync('analysis_history') || [];
    allRecords = allRecords.filter(r => r.id !== id);
    
    wx.setStorageSync('analysis_history', allRecords);
    
    // 重新加载数据
    this.loadHistoryRecords();
    
    wx.showToast({
      title: '记录已删除',
      icon: 'success'
    });
  },

  // 导出数据
  exportData() {
    wx.showActionSheet({
      itemList: ['导出为JSON', '导出为CSV', '导出为PDF报告'],
      success: (res) => {
        if (res.tapIndex === 0) {
          this.exportAsJSON();
        } else if (res.tapIndex === 1) {
          this.exportAsCSV();
        } else {
          this.exportAsPDF();
        }
      }
    });
  },

  exportAsJSON() {
    const allRecords = wx.getStorageSync('analysis_history') || [];
    const dataStr = JSON.stringify(allRecords, null, 2);
    
    wx.showToast({
      title: 'JSON导出功能开发中',
      icon: 'none'
    });
  },

  exportAsCSV() {
    wx.showToast({
      title: 'CSV导出功能开发中',
      icon: 'none'
    });
  },

  exportAsPDF() {
    wx.showToast({
      title: 'PDF报告功能开发中',
      icon: 'none'
    });
  },

  // 加载更多
  loadMore() {
    if (this.data.loading || !this.data.hasMore) {
      return;
    }
    
    this.setData({
      page: this.data.page + 1
    });
    
    this.loadHistoryRecords();
  },

  // 刷新数据
  refreshData() {
    this.setData({
      page: 1,
      historyRecords: []
    });
    
    this.loadHistoryRecords();
    
    wx.showToast({
      title: '数据已刷新',
      icon: 'success'
    });
  },

  // 查看统计详情
  viewStatsDetail() {
    const stats = this.data.stats;
    
    wx.showModal({
      title: '详细统计',
      content: `总记录数: ${stats.totalRecords}条\n平均评分: ${stats.averageScore}分\n最佳评分: ${stats.bestScore}分\n最差评分: ${stats.worstScore}分\n总睡眠时长: ${stats.totalDuration}小时\n睡眠一致性: ${stats.consistency}%`,
      showCancel: false
    });
  },

  // 返回
  goBack() {
    const pages = getCurrentPages();
    if (pages.length > 1) {
      wx.navigateBack();
    } else {
      wx.switchTab({
        url: '/pages/index/index'
      });
    }
  },

  // 分享
  onShareAppMessage() {
    const stats = this.data.stats;
    return {
      title: `我的睡眠历史 - 平均${stats.averageScore}分`,
      path: '/pages/history/history',
      imageUrl: '/images/history-share.png'
    };
  }
});