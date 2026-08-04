Page({
  data: {
    report: null,
    loaded: false
  },

  onLoad(options) {
    if (options.data) {
      try {
        const report = JSON.parse(decodeURIComponent(options.data));
        this.setData({ report, loaded: true });
      } catch(e) {
        console.error('解析报告数据失败', e);
      }
    }
  },

  onShareAppMessage() {
    return { title: '我的AISleepGen睡眠验证报告' };
  }
});
