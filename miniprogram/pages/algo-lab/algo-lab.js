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
    // 个性化推荐 (v3)
    recommendations: [],
    recoLoading: false,
    recoError: '',
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
    this.loadRecommendations();
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

  // v3: 个性化推荐 (只读规则映射, 失败不阻塞主列表)
  loadRecommendations() {
    this.setData({ recoLoading: true, recoError: '' });
    const openid = wx.getStorageSync('openid') || '';
    api.recommendAlgos(openid).then(res => {
      const recs = (res && res.recommendations) || [];
      this.setData({ recommendations: recs, recoLoading: false });
    }).catch(err => {
      this.setData({ recoLoading: false, recoError: '推荐加载失败' });
    });
  },

  runRecommended(e) {
    const algo = e.currentTarget.dataset.algo;
    if (!algo) return;
    this.setData({ keyword: algo, });
    this._applyFilter();
    // 滚动到列表并高亮
    this.runAlgoByName(algo);
  },

  runAlgoByName(algo) {
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

  _fmt(n, digits) {
    if (typeof n !== 'number' || isNaN(n)) return String(n);
    return n.toFixed(digits === undefined ? 2 : digits);
  },

  _pct(n) {
    if (typeof n !== 'number') return String(n);
    return Math.round(n * 100) + '%';
  },

  // v2: 将算法结果翻译成用户可读报告 (按算法类型分类解读)
  _interpret(algo, result) {
    if (typeof result !== 'object' || !result) return '';
    const lines = [];
    const name = algo || '';

    // ① 自组织临界性/动力学类
    if (result.power_law_exponent !== undefined) {
      const p = result.power_law_exponent;
      lines.push('【系统动力学】自组织临界性指数 ' + this._fmt(p) + '（理想区间 1.0~2.0）：' +
        (p >= 1 && p <= 2 ? '睡眠系统处于自组织临界状态，规律性与适应性平衡良好。' : '系统偏离临界状态，建议保持规律作息以恢复稳定节律。'));
      if (result.total_avalanches !== undefined) lines.push('检测到 ' + result.total_avalanches + ' 次状态跃迁，平均跃迁规模 ' + this._fmt(result.mean_avalanche_size, 1) + '。');
      if (result.power_law_exponent !== undefined && result.avalanche_sizes) {
        lines.push('跃迁规模呈幂律分布，说明系统具备自我调节能力。');
      }
    }

    // ② 双过程/睡眠节律类
    if (name.indexOf('双过程') >= 0 || result.process_s !== undefined || result.process_c !== undefined) {
      lines.push('【睡眠节律】双过程模型评估：');
      if (result.process_s !== undefined) lines.push('· 稳态压力(S过程) ' + this._fmt(result.process_s) + ' — ' + (result.process_s > 0.7 ? '睡眠压力较高，适合尽早入睡。' : '睡眠压力适中。'));
      if (result.process_c !== undefined) lines.push('· 昼夜节律(C过程) ' + this._fmt(result.process_c) + ' — ' + (result.process_c > 0.7 ? '处于清醒高峰，不建议此时入睡。' : '节律相位适宜入睡。'));
      if (result.sleep_efficiency !== undefined) lines.push('· 睡眠效率 ' + this._pct(result.sleep_efficiency) + (result.sleep_efficiency >= 0.85 ? '（优秀）' : result.sleep_efficiency >= 0.75 ? '（良好）' : '（偏低，建议改善）'));
    }

    // ③ 预测类
    if (result.prediction !== undefined || name.indexOf('预测') >= 0) {
      const pred = result.prediction;
      let predText = '';
      if (typeof pred === 'object' && pred) {
        if (pred.score !== undefined) predText = '预测睡眠质量 ' + this._fmt(pred.score) + '/100';
        else if (pred.quality !== undefined) predText = '预测质量: ' + pred.quality;
        else predText = JSON.stringify(pred).slice(0, 80);
      } else {
        predText = String(pred).slice(0, 80);
      }
      lines.push('【睡眠预测】' + predText);
      if (result.confidence !== undefined) lines.push('预测置信度 ' + this._pct(result.confidence));
    }

    // ④ 冥想类
    if (name.indexOf('冥想') >= 0 || result.focus_score !== undefined || result.calm_score !== undefined) {
      lines.push('【冥想引导】');
      if (result.focus_score !== undefined) lines.push('· 专注度 ' + this._fmt(result.focus_score) + (result.focus_score >= 70 ? ' — 专注状态良好。' : ' — 建议从呼吸觉察开始。'));
      if (result.calm_score !== undefined) lines.push('· 平静度 ' + this._fmt(result.calm_score) + (result.calm_score >= 70 ? ' — 身心平静，适合深度放松。' : ' — 可尝试 4-7-8 呼吸法助静。'));
      if (result.recommendation) lines.push('· 建议: ' + String(result.recommendation).slice(0, 100));
    }

    // ⑤ 脑波/睡眠结构类
    if (result.deep_sleep_pct !== undefined || result.rem_pct !== undefined || result.latency !== undefined) {
      lines.push('【睡眠结构】');
      if (result.deep_sleep_pct !== undefined) lines.push('· 深睡占比 ' + this._pct(result.deep_sleep_pct) + (result.deep_sleep_pct >= 0.2 ? '（充足，身体修复良好）' : '（偏低，注意睡前减少咖啡因）'));
      if (result.rem_pct !== undefined) lines.push('· REM 占比 ' + this._pct(result.rem_pct) + (result.rem_pct >= 0.2 ? '（记忆巩固良好）' : '（偏低）'));
      if (result.latency !== undefined) lines.push('· 入睡潜伏期 ' + this._fmt(result.latency, 0) + ' 分钟' + (result.latency <= 30 ? '（正常）' : '（偏长，建议放松练习）'));
      if (result.wake_count !== undefined) lines.push('· 夜间醒来 ' + result.wake_count + ' 次' + (result.wake_count <= 2 ? '（正常）' : '（偏多，注意环境噪音）'));
    }

    // ⑥ 情绪/压力类
    if (result.stress_level !== undefined || name.indexOf('情绪') >= 0 || name.indexOf('压力') >= 0) {
      lines.push('【情绪压力】');
      if (result.stress_level !== undefined) lines.push('· 压力水平 ' + this._fmt(result.stress_level) + (result.stress_level > 0.6 ? ' — 偏高，建议睡前冥想减压。' : result.stress_level > 0.3 ? ' — 中等，可控。' : ' — 平稳。'));
      if (result.mood_score !== undefined) lines.push('· 情绪指数 ' + this._fmt(result.mood_score));
    }

    // ⑦ 通用评分/建议
    if (result.score !== undefined && lines.length === 0) {
      lines.push('【综合评分】' + this._fmt(result.score) + (result.score >= 85 ? ' — 状态优秀。' : result.score >= 70 ? ' — 状态良好。' : ' — 有改善空间。'));
    }
    if (result.recommendation && lines.length > 0 && name.indexOf('冥想') < 0) {
      lines.push('【建议】' + String(result.recommendation).slice(0, 120));
    }
    if (lines.length === 0) {
      // 兜底: 提取数值型键做摘要
      const nums = [];
      for (const k in result) {
        if (typeof result[k] === 'number' && k !== 'status' && k !== 'code') {
          nums.push(k + ': ' + this._fmt(result[k]));
        }
        if (nums.length >= 5) break;
      }
      if (nums.length) lines.push('关键指标: ' + nums.join('、'));
    }
    return lines.join('\n');
  },

  closeResult() {
    this.setData({ result: null, resultText: '', resultError: '', interpret: '' });
  },
});
