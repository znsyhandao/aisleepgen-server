// pages/algo-lab/algo-lab.js - AI 算法实验室
// 消费通道: 用户可运行 Nexus 进化引擎注入的算法, 让 token 产出兑现用户价值
const api = require('../../utils/api');

const PAGE_SIZE = 30;

Page({
  data: {
    loading: true,
    keyword: '',
    algos: [],
    featured: [],
    total: 0,
    shown: 0,
    hasMore: false,
    // 运行状态
    running: false,
    currentAlgo: '',
    result: null,
    resultText: '',
    resultError: '',
    interpret: '',
  },

  _allAlgos: [],

  onLoad() {
    this.loadAlgos();
  },

  loadAlgos() {
    this.setData({ loading: true });
    api.listAlgos().then(res => {
      const list = (res && res.algos) || [];
      this._allAlgos = list;
      this.setData({ total: list.length });
      this._pickFeatured(list);
      this._applyFilter();
    }).catch(err => {
      this.setData({ loading: false, total: 0 });
      wx.showToast({ title: '算法列表加载失败', icon: 'none' });
    });
  },

  // 精选推荐: 名称含睡眠/预测/临界/双过程等关键词
  _pickFeatured(list) {
    const keys = ['自组织', '临界', '双过程', '预测', '睡眠', '冥想'];
    const seen = {};
    const featured = [];
    for (let i = 0; i < list.length && featured.length < 3; i++) {
      const name = list[i].algo || '';
      for (let k = 0; k < keys.length; k++) {
        if (name.indexOf(keys[k]) >= 0 && !seen[name]) {
          seen[name] = true;
          featured.push(list[i]);
          break;
        }
      }
    }
    this.setData({ featured: featured });
  },

  onSearch(e) {
    this.setData({ keyword: e.detail.value || '' });
    this._applyFilter();
  },

  _applyFilter() {
    const kw = this.data.keyword.trim();
    let list = this._allAlgos;
    if (kw) {
      list = list.filter(a => (a.algo || '').indexOf(kw) >= 0);
    }
    const shown = Math.min(PAGE_SIZE, list.length);
    this.setData({
      algos: list.slice(0, shown),
      total: list.length,
      shown: shown,
      hasMore: list.length > shown,
      loading: false,
    });
  },

  loadMore() {
    const kw = this.data.keyword.trim();
    let list = this._allAlgos;
    if (kw) {
      list = list.filter(a => (a.algo || '').indexOf(kw) >= 0);
    }
    const next = this.data.shown + PAGE_SIZE;
    this.setData({
      algos: list.slice(0, next),
      shown: Math.min(next, list.length),
      hasMore: list.length > next,
    });
  },

  runAlgo(e) {
    const algo = e.currentTarget.dataset.algo;
    if (!algo) return;
    this.setData({ running: true, currentAlgo: algo, result: null, resultText: '', resultError: '', interpret: '' });
    api.runAlgo(algo, {}).then(res => {
      if (res && res.success) {
        const result = res.result || {};
        this.setData({
          running: false,
          result: result,
          resultText: JSON.stringify(result, null, 2),
          interpret: this._interpret(algo, result),
        });
      } else {
        this.setData({ running: false, result: {}, resultText: '', resultError: (res && res.error) || '运行失败' });
      }
    }).catch(err => {
      this.setData({ running: false, result: {}, resultText: '', resultError: '请求失败: ' + (err.errMsg || '网络错误') });
    });
  },

  // 将算法结果翻译成用户可读解读
  _interpret(algo, result) {
    const lines = [];
    if (typeof result !== 'object' || !result) return '';
    if (result.power_law_exponent !== undefined) {
      const p = result.power_law_exponent;
      lines.push('自组织临界性指数: ' + (typeof p === 'number' ? p.toFixed(3) : p));
      lines.push(p >= 1 && p <= 2 ? '系统处于自组织临界状态, 规律性与灵活性平衡良好。' : '系统偏离临界状态, 睡眠规律性可能需要调节。');
    }
    if (result.total_avalanches !== undefined) {
      lines.push('检测到 ' + result.total_avalanches + ' 次状态跃迁事件。');
    }
    if (result.mean_avalanche_size !== undefined) {
      lines.push('平均跃迁规模: ' + (typeof result.mean_avalanche_size === 'number' ? result.mean_avalanche_size.toFixed(2) : result.mean_avalanche_size));
    }
    if (result.prediction !== undefined) {
      lines.push('预测结果: ' + JSON.stringify(result.prediction).slice(0, 100));
    }
    if (result.score !== undefined) {
      lines.push('综合评分: ' + result.score);
    }
    if (result.recommendation) {
      lines.push('建议: ' + String(result.recommendation).slice(0, 120));
    }
    return lines.join('\n');
  },

  closeResult() {
    this.setData({ result: null, resultText: '', resultError: '', interpret: '' });
  },
});
