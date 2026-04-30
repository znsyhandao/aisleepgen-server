// pages/chat/chat.js - 沉浸式深色聊天界面
const api = require('../../utils/api');
const SleepAlgorithm = require('../../utils/sleep_algorithm');
const sleepAlgorithm = new SleepAlgorithm();

Page({
  data: {
    pageName: 'chat',
    messages: [],
    inputText: '',
    thinking: false,
    scrollToId: '',
    msgId: 1,
    showReportBtn: false,
    showModal: false,
    
    // 快速回复标签
    quickReplies: [
      '怎么快速入睡？',
      '半夜醒来怎么办',
      '怎样提高深睡',
      '做一次睡眠评估',
      '早上起不来怎么办',
    ],
    
    // 语音输入
    isRecording: false,
    showVoiceInput: false,
    
    // 睡眠评分卡片（内嵌显示）
    scoreCardData: null,
    showScoreCard: false,
  },

  onLoad() {
    this.setData({
      messages: [],
      msgId: 1,
      showReportBtn: false,
      showModal: false,
      scoreCardData: null,
      showScoreCard: false,
      butlerAlert: null,
      showBrief: false,
      briefExpanded: false,
      showBriefDetail: false,
      briefArrowText: '展开',
      briefTitle: '',
      briefItems: [],
    });
    this._checkService();
    this.checkButler();
  },

  onShow() {
    if (this.data.navMask) {
      this.setData({ navMask: false });
    }
    // 从呼吸页返回 → 自动发送反馈（含详细数据）
    if (this.data.breathDone) {
      var rounds = this.data.breathRounds || 0;
      var duration = this.data.breathDuration || 0;
      var completed = this.data.breathCompleted !== false;
      var pattern = this.data.breathPattern || '4-7-8 呼吸法';
      this.setData({ breathDone: false, breathRounds: 0, breathDuration: 0, breathCompleted: false, breathPattern: '' });
      var feedback = '做完了';
      if (!completed) feedback = '没做完，先关了';
      else if (duration > 0) feedback = '做完了，大概用了' + duration + '秒，做了' + rounds + '轮';
      this.sendMessage(feedback);
    }
    this.checkButler();
  },

  checkButler() {
    var that = this;
    console.log('[Butler] 开始检测...');
    api.butlerCheck().then(function(res) {
      console.log('[Butler] 返回:', JSON.stringify(res));
      var alert = null;
      if (res.alerts && res.alerts.length > 0) {
        var a = res.alerts[0];
        var iconMap = { warning: '📌', info: '💡', positive: '🎉' };
        var actionHintMap = {
          start_breathing: '开始呼吸练习',
          meditation: '开始冥想',
          white_noise: '播放白噪音',
        };
        var hint = '';
        if (a.actions && a.actions.length > 0) {
          hint = actionHintMap[a.actions[0]] || '';
        }
        alert = {
          type: a.type,
          icon: iconMap[a.level] || '💡',
          message: a.message,
          actions: a.actions || [],
          actionHint: hint,
        };
      }

      var showBrief = res.show_brief || false;
      var briefTitle = showBrief ? '📡 AI行业日报 · 点击查看' : '';

      that.setData({
        butlerAlert: alert,
        showBrief: showBrief,
        showBriefDetail: false,
        briefArrowText: '展开',
        briefTitle: briefTitle,
        briefItems: res.brief ? res.brief.ai_trends.concat(res.brief.sleep_science) : [],
      });
    }).catch(function() {});
  },

  doButlerAction() {
    if (!this.data.butlerAlert || !this.data.butlerAlert.actions) return;
    var actions = this.data.butlerAlert.actions;
    if (actions.indexOf('start_breathing') >= 0) {
      wx.navigateTo({ url: '/pages/breathing/breathing' });
    } else if (actions.indexOf('meditation') >= 0) {
      wx.navigateTo({ url: '/pages/meditation/meditation' });
    }
  },

  toggleBrief() {
    var expanded = !this.data.briefExpanded;
    this.setData({ 
      briefExpanded: expanded, 
      showBriefDetail: expanded && this.data.showBrief,
      briefArrowText: expanded ? '收起' : '展开'
    });
    if (expanded) {
      api.markBriefRead();
    }
  },

  toggleEvidence() {
    this.setData({ showEvDetail: !this.data.showEvDetail });
  },

  toggleEvList() {
    this.setData({ showEvList: !this.data.showEvList });
  },

  copyText(e) {
    var text = e.currentTarget.dataset.text;
    wx.setClipboardData({
      data: text,
      success: function() {
        wx.showToast({ title: '已复制', icon: 'success', duration: 1500 });
      }
    });
  },

  _checkService() {
    api.checkHealth().then(ok => {
      if (!ok) {
        this._addMessage('ai', '💫 你好，我是你的AI睡眠助手！\n\n请先启动后端服务：\n`python deepseek_proxy.py`\n\n启动后我可以帮你分析睡眠问题、生成专业报告。');
      } else {
        this._addMessage('ai', '💫 你好！我是AI睡眠助手，可以帮你：\n\n• 分析你的睡眠问题\n• 提供改善建议\n• 生成专业睡眠报告\n\n试试点击下面的快捷问题，或者直接描述你的睡眠情况吧！');
      }
    });
  },

  // ===== 快速回复 =====
  onQuickQuestion(e) {
    const q = e.currentTarget.dataset.q;
    if (q.indexOf('睡眠评估') >= 0 || q.indexOf('评估') >= 0) {
      wx.navigateTo({ url: '/pages/survey/survey' });
      return;
    }
    this._sendUserMessage(q);
  },

  // ===== 输入处理 =====
  onInput(e) {
    this.setData({ inputText: e.detail.value });
  },

  sendMessage() {
    const text = this.data.inputText.trim();
    if (!text || this.data.thinking) return;
    this._sendUserMessage(text);
  },

  _sendUserMessage(text) {
    this._addMessage('user', text);
    this.setData({ inputText: '', thinking: true });
    this._scrollToBottom();

    api.chatWithAI(text, this._getHistory())
      .then(res => {
        this.setData({ thinking: false });
        const reply = typeof res === 'string' ? res : (res.reply || '');
        this._addMessage('ai', reply);
        
        // 检查自动生成的迷你睡眠卡
        if (res && res.auto_report && res.auto_report.score) {
          this._showScoreCard(res.auto_report);
        } else if (res && res.score && res.detailedAnalysis) {
          this._showScoreCard(res);
        } else {
          // 尝试从回复提取睡眠数据
          this._checkForSleepData(reply);
        }
        
        this._updateReportBtn();
        this._scrollToBottom();
        
        // 科幻感呼吸/放松引导入口
        // 呼吸/放松引导路由
        if (res && res.action && res.action_params) {
          var ap = res.action_params;
          var lastMsg = this.data.messages[this.data.messages.length - 1];
          if (lastMsg && lastMsg.role === 'ai') {
            lastMsg.breathAction = true;
            lastMsg.breathParams = JSON.stringify(ap);
            lastMsg.breathName = ap.name || '放松练习';
            lastMsg.breathTip = ap.tip || '点击开始';
            this.setData({ messages: this.data.messages });
          }
          if (res.action === 'start_breathing') {
            this._goToBreathing(ap);
          } else if (res.action === 'start_progressive_relaxation') {
            this._goToRelaxation(ap);
          }
        }
      })
      .catch((err) => {
        this.setData({ thinking: false });
        var errMsg = typeof err === 'string' ? err : (err.message || err.errMsg || '');
        if (errMsg.indexOf('timeout') >= 0 || errMsg.indexOf('超时') >= 0) {
          this._addMessage('ai', '😅 回复超时了，再试一次？');
        } else if (errMsg.indexOf('无回复') >= 0 || !errMsg) {
          this._addMessage('ai', '😅 连接好像不太稳定，稍等一下重试好吗？');
        } else {
          this._addMessage('ai', '😅 ' + errMsg);
        }
        this._scrollToBottom();
      });
  },

  // 检查回复是否包含睡眠数据从而显示评分卡
  _checkForSleepData(reply) {
    const scoreMatch = reply.match(/评分[：:]\s*(\d+)\s*分/);
    if (scoreMatch) {
      const score = parseInt(scoreMatch[1]);
      const qualityMatch = reply.match(/质量[：:]\s*(\S+)/);
      this._showScoreCard({
        score: score,
        quality: qualityMatch ? qualityMatch[1] : this._getQualityLevel(score)
      });
    }
  },

  _showScoreCard(data) {
    // 从后端统一分数源读取当前评分（覆盖 DeepSeek 回复中波动分数）
    var unifiedScore = data.score || 75;
    var that = this;
    api.getUserProfile().then(function(prof) {
      if (prof && prof.member && prof.member.current_score > 0) {
        unifiedScore = prof.member.current_score;
      }
      that._renderScoreCardInner(data, unifiedScore);
    }).catch(function() {
      that._renderScoreCardInner(data, unifiedScore);
    });
  },

  _renderScoreCardInner(data, score) {
    const quality = data.quality || this._getQualityLevel(score);
    const rawDims = data.dimension_scores || {};
    const dimKeys = Object.keys(rawDims);
    
    // 判断维度格式（新版: {name: {score, label, icon}} vs 旧版: {name: number}）
    const isNewFormat = dimKeys.length > 0 && typeof rawDims[dimKeys[0]] === 'object';
    
    const dimList = [];
    if (isNewFormat) {
      for (const [name, info] of Object.entries(rawDims)) {
        dimList.push({
          name: name,
          score: info.score || 0,
          label: info.label || '',
          icon: info.icon || '📋',
          barWidth: Math.min(info.score || 0, 100) + '%',
          confidence: info.confidence || 0.8,
          lowConfidence: (info.confidence || 0.8) < 0.4,
        });
      }
    } else {
      for (const [name, score] of Object.entries(rawDims)) {
        dimList.push({
          name: name,
          score: score,
          label: '',
          icon: '📋',
          barWidth: Math.min(score, 100) + '%',
          confidence: 0.8,
          lowConfidence: false,
        });
      }
    }

    // 减压建议
    const relax = data.relaxation || {};
    const retro = data.retrospective || [];
    const risks = data.risk_items || [];
    
    // 行动建议
    const takeaway = data.action_takeaway || data.primary_focus || '';
    const reasoning = data.reasoning || '';
    const tags = data.user_tags || [];
    const evidenceCount = data.evidence_count || 0;
    
    // 趋势数据
    const trend = data.trend || {};
    const trendDirection = trend.direction || data.trend || 'stable';
    const trendDelta = trend.delta_7d || 0;
    const trendLabels = trend.labels || [];
    const showTrend = trendLabels.length >= 3;

    this.setData({
      scoreCardData: {
        score: score,
        quality: quality,
        dimensions: dimList,
        relaxation: relax,
        retrospective: retro,
        risk_items: risks,
        summary: data.summary || '',
        primary_focus: data.primary_focus || '',
        action_takeaway: takeaway,
        reasoning: reasoning,
        user_tags: tags,
        evidence_count: evidenceCount,
        trendDirection: trendDirection,
        trendDelta: trendDelta,
        trendLabels: trendLabels,
        showConfidence: !!(data.confidence_bounds && data.confidence_bounds.margin_of_error),
        confidence_bounds: data.confidence_bounds || null,
        showTrend: showTrend,
        showDim: dimList.length > 0,
        showRelax: !!(relax.primary_therapy || relax.arousal_type),
        showRetro: retro.length > 0,
        showTakeaway: !!takeaway,
        showReasoning: !!reasoning,
        showTags: tags.length > 0,
        showEvidence: evidenceCount > 0,
        showEvDetail: false,
        showEvList: false,
      },
      showScoreCard: true
    });
    // 延迟加载时间线（确保渲染完成）
    setTimeout(() => { this.loadTimeline(); }, 500);
  },

  _getQualityLevel(score) {
    if (score >= 85) return '优秀';
    if (score >= 75) return '良好';
    if (score >= 65) return '一般';
    if (score >= 50) return '较差';
    return '需要改善';
  },

  // ===== 语音输入 =====
  toggleVoiceInput() {
    this.setData({ showVoiceInput: !this.data.showVoiceInput });
  },

  startRecording() {
    const recorder = wx.getRecorderManager();
    this.setData({ isRecording: true });
    
    recorder.start({
      duration: 15000,
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000,
      format: 'mp3',
    });

    const self = this;
    recorder.onStop(function(res) {
      self.setData({ isRecording: false });
      wx.showLoading({ title: '识别中...' });
      self._uploadAndSend(res.tempFilePath, self);
    });

    recorder.onError(function() {
      self.setData({ isRecording: false });
      wx.showToast({ title: '录音失败', icon: 'none' });
    });

    // 自动停止
    setTimeout(() => { recorder.stop(); }, 15000);
  },

  stopRecording() {
    try {
      wx.getRecorderManager().stop();
    } catch(e) {}
    this.setData({ isRecording: false });
  },

  _uploadAndSend(filePath, self) {
    wx.uploadFile({
      url: api.API_BASE + '/api/voice-relax',
      filePath: filePath,
      name: 'voice',
      formData: { source: 'wechat' },
      success: function(res) {
        wx.hideLoading();
        try {
          const data = JSON.parse(res.data);
          if (data.text) {
            self._sendUserMessage(data.text);
          } else {
            wx.showToast({ title: '未识别到语音内容', icon: 'none' });
          }
        } catch(e) {
          wx.showToast({ title: '处理失败', icon: 'none' });
        }
      },
      fail: function() {
        wx.hideLoading();
        wx.showToast({ title: '上传失败', icon: 'none' });
      }
    });
  },

  // ===== 报告生成 =====
  showConsentModal() {
    this.setData({ showModal: true });
  },

  closeModal() {
    this.setData({ showModal: false });
  },

  generateReport() {
    this.setData({ showModal: false, thinking: true });
    this._addMessage('ai', '📊 正在分析对话，生成睡眠报告...');

    const history = this._getHistory();
    api.generateReportFromChat(history)
      .then(result => {
        this.setData({ thinking: false });

        if (result.success === false) {
          const msg = result.message || result.error || '信息不足，请提供更多睡眠细节';
          wx.showModal({ title: '信息不足', content: msg, showCancel: false });
          return;
        }

        try {
          const report = typeof result.report === 'string' ? JSON.parse(result.report) : result.report;
          this._saveAndNavigate(report);
        } catch (e) {
          this._saveAndNavigate({ detailedAnalysis: result.report || result.content });
        }
      })
      .catch(() => {
        this.setData({ thinking: false });
        this._addMessage('ai', '😅 报告生成失败，请确认后端正在运行。');
      });
  },

  _saveAndNavigate(reportData) {
    const report = reportData || {};
    const hasData = report.score && report.detailedAnalysis && report.detailedAnalysis.length > 20;
    
    if (!hasData) {
      this.setData({ thinking: false });
      wx.showModal({
        title: '信息不足',
        content: '请先告诉我你的睡眠情况（入睡时间、醒来次数、睡眠质量等），再生成报告。',
        showCancel: false
      });
      return;
    }

    const finalReport = {
      id: Date.now(),
      time: new Date().toLocaleString(),
      date: new Date().toLocaleDateString(),
      type: 'AI Chat Deep Analysis',
      isAIGenerated: true,
      source: 'chat',
      sourceName: 'AI聊天生成',
      score: report.score || 75,
      quality: report.quality || '良好',
      duration: report.duration || '7h 30m',
      durationMinutes: report.durationMinutes || 450,
      detailedAnalysis: report.detailedAnalysis || report.analysis || '',
      details: report.details || {
        deepSleep: '2h 0m', remSleep: '1h 45m', lightSleep: '3h 30m',
        awakeTime: '15m', sleepEfficiency: 85, sleepLatency: '15m'
      },
      healthScores: report.healthScores || { cardiovascular: 75, cognitive: 70, emotional: 75, physical: 70 },
      sleepStages: report.sleepStages || [
        { name: '深睡', value: 25, color: '#4A90D9' },
        { name: 'REM', value: 23, color: '#7B68EE' },
        { name: '浅睡', value: 47, color: '#82B74B' },
        { name: '清醒', value: 5, color: '#E57373' }
      ],
      trends: report.trends || { scoreTrend: '+1', durationTrend: '+15m', efficiencyTrend: '+2%' },
      suggestions: report.suggestions || []
    };

    wx.setStorageSync('latest_analysis_result', finalReport);

    const history = wx.getStorageSync('report_history') || [];
    history.unshift({ 
      id: finalReport.id, date: finalReport.date, score: finalReport.score, 
      quality: finalReport.quality, source: 'chat', sourceName: 'AI聊天生成' 
    });
    if (history.length > 50) history = history.slice(0, 50);
    wx.setStorageSync('report_history', history);

    this._addMessage('ai', `✅ 报告已生成！评分: ${finalReport.score}分 (${finalReport.quality})`);
    this._addMessage('ai', '📄 正在跳转报告页面...');

    setTimeout(() => {
      wx.navigateTo({ url: '/pages/report/report' });
    }, 1500);
  },

  _updateReportBtn() {
    if (this.data.messages.length >= 4 && !this.data.showReportBtn) {
      this.setData({ showReportBtn: true });
    }
  },

  // ===== 消息管理 =====
  _addMessage(role, content, extra) {
    const id = this.data.msgId;
    var msg = { id, role, content };
    // 支持扩展字段（breathAction 等）
    if (extra) {
      if (extra.breathAction) msg.breathAction = true;
      if (extra.breathParams) msg.breathParams = extra.breathParams;
      if (extra.breathName) msg.breathName = extra.breathName;
      if (extra.breathTip) msg.breathTip = extra.breathTip;
    }
    const msgs = this.data.messages.concat([msg]);
    this.setData({ messages: msgs, msgId: id + 1 });
  },

  // 点击呼吸引导入口 → 跳转呼吸页
  invokeBreathing(e) {
    var params = e.currentTarget.dataset.params;
    if (params) {
      if (typeof params === 'string') {
        try { params = JSON.parse(params); } catch(er) {}
      }
      this._goToBreathing(params);
    }
  },

  _goToBreathing(params) {
    if (!params) params = {};
    var q = encodeURIComponent(JSON.stringify(params));
    wx.navigateTo({ url: '/pages/breathing/breathing?params=' + q });
  },

  _goToRelaxation(params) {
    if (!params) params = {};
    var q = encodeURIComponent(JSON.stringify(params));
    wx.navigateTo({ url: '/pages/relaxation/relaxation?params=' + q });
  },

  _getHistory() {
    return this.data.messages.map(m => ({
      role: m.role === 'ai' ? 'assistant' : 'user',
      content: m.content
    }));
  },

  _scrollToBottom() {
    setTimeout(() => {
      const msgs = this.data.messages;
      if (msgs.length > 0) {
        this.setData({ scrollToId: 'msg-' + msgs[msgs.length - 1].id });
      }
    }, 100);
  },

  _startBreathingGuide(params) {
    this.setData({ navMask: true });
    wx.navigateTo({
      url: '/pages/breathing/breathing?params=' + encodeURIComponent(JSON.stringify(params)),
    });
  },

  // ===== 生命周期 =====
  goBack() {
    wx.switchTab({ url: '/pages/index/index' });
  },
  goToDashboard() {
    wx.switchTab({ url: '/pages/index/index' });
  },

  onShareAppMessage() {
    return { title: 'AI Sleep Assistant - 智能睡眠分析', path: '/pages/chat/chat' };
  },

  /** 加载时间线数据并绘制到 Canvas */
  loadTimeline: function() {
    const self = this;
    const openid = wx.getStorageSync('openid') || 'default';
    wx.request({
      url: api.API_BASE + '/api/timeline?openid=' + openid + '&limit=20',
      success(res) {
        const pts = res.data.points || [];
        if (pts.length < 2) return;
        
        // 提取分数序列
        const scores = pts.map(p => p.score);
        const dates = pts.map(p => {
          const d = p.date || '';
          return d.slice(5); // MM-DD
        });
        
        // 找出最高最低分
        const minScore = Math.min(...scores) - 5;
        const maxScore = Math.max(...scores) + 5;
        const range = maxScore - minScore || 40;
        
        // Canvas绘制
        const query = wx.createSelectorQuery();
        query.select('#timelineCanvas').fields({ node: true, size: true }).exec((res) => {
          const canvas = res[0].node;
          const ctx = canvas.getContext('2d');
          const width = res[0].width || 320;
          const height = res[0].height || 120;
          
          // 实际大小（物理像素）
          const dpr = wx.getSystemInfoSync().pixelRatio;
          canvas.width = width * dpr;
          canvas.height = height * dpr;
          ctx.scale(dpr, dpr);
          
          // 背景
          ctx.clearRect(0, 0, width, height);
          
          // 网格线
          ctx.strokeStyle = 'rgba(255,255,255,0.08)';
          ctx.lineWidth = 1;
          for (let i = 0; i < 4; i++) {
            const y = 20 + i * 25;
            ctx.beginPath();
            ctx.moveTo(40, y);
            ctx.lineTo(width - 10, y);
            ctx.stroke();
            
            // 刻度标签
            const labelVal = Math.round(maxScore - (i * range / 3));
            ctx.fillStyle = 'rgba(255,255,255,0.3)';
            ctx.font = '10px sans-serif';
            ctx.fillText(labelVal, 5, y + 4);
          }
          
          // 折线
          const step = (width - 50) / Math.max(pts.length - 1, 1);
          ctx.beginPath();
          ctx.strokeStyle = '#667eea';
          ctx.lineWidth = 2;
          ctx.lineJoin = 'round';
          
          // 总面积填充（渐变）
          const gradient = ctx.createLinearGradient(0, 20, 0, height - 10);
          gradient.addColorStop(0, 'rgba(102, 126, 234, 0.2)');
          gradient.addColorStop(1, 'rgba(102, 126, 234, 0.0)');
          
          for (let i = 0; i < pts.length; i++) {
            const x = 40 + i * step;
            const y = 20 + ((maxScore - scores[i]) / range) * 75;
            
            if (i === 0) {
              ctx.moveTo(x, y);
            } else {
              ctx.lineTo(x, y);
            }
            
            // 数据点
            ctx.fillStyle = '#667eea';
            ctx.beginPath();
            ctx.arc(x, y, 3, 0, Math.PI * 2);
            ctx.fill();
            
            // 日期标签（每隔一个显示）
            if (i % 2 === 0 || i === pts.length - 1) {
              ctx.fillStyle = 'rgba(255,255,255,0.3)';
              ctx.font = '9px sans-serif';
              ctx.textAlign = 'center';
              ctx.fillText(dates[i], x, height - 2);
            }
          }
          
          // 填充面积
          ctx.lineTo(40 + (pts.length - 1) * step, 20 + ((maxScore - scores[pts.length - 1]) / range) * 75);
          ctx.lineTo(40 + (pts.length - 1) * step, height - 10);
          ctx.lineTo(40, height - 10);
          ctx.closePath();
          ctx.fillStyle = gradient;
          ctx.fill();
          
          // 最后画线（覆盖在填充上面）
          ctx.beginPath();
          for (let i = 0; i < pts.length; i++) {
            const x = 40 + i * step;
            const y = 20 + ((maxScore - scores[i]) / range) * 75;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
          }
          ctx.strokeStyle = '#667eea';
          ctx.lineWidth = 2;
          ctx.stroke();
        });
      }
    });
  }
});
