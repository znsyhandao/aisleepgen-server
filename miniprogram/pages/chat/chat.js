// pages/chat/chat.js - 沉浸式深色聊天界面（支持流式 SSE）

const api = require('../../utils/api');

const SleepAlgorithm = require('../../utils/sleep_algorithm');

const sleepAlgorithm = new SleepAlgorithm();



// 检测是否支持流式（基础库 2.26+ 有 enableChunked）

var _canStream = false;

/* 恢复方法：把上面这行改成下面这4行，并把 false 去掉

try {

  var baseInfo = wx.getAppBaseInfoSync();

  var baseLibVer = (baseInfo.SDKVersion || '2.0.0').split('.').map(Number);

  _canStream = baseLibVer[0] > 2 || (baseLibVer[0] === 2 && baseLibVer[1] >= 26);

} catch(e) { _canStream = false; }

*/



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



    // 快速回复标签（动态）

    quickReplies: [],



    // 语音输入

    isRecording: false,

    showVoiceInput: false,



    // 睡眠评分卡片（内嵌显示）

    scoreCardData: null,

    showScoreCard: false,

  },



  onLoad(options) {

    // ★ 对话入口来源（不可挽回缺口 8）

    if (options && options.source) {

      this._entrySource = options.source;

    } else {

      this._entrySource = 'manual';

    }

    // ★ 半夜语音唤醒：来源 = voice_sleep 时自动进入录音模式

    if (this._entrySource === 'voice_sleep') {

      this.setData({ showVoiceInput: true });

      // 延迟一点后自动开始录音

      var that = this;

      setTimeout(function() {

        that.setData({ showVoiceInput: true });

        // 不自动开始录音，让用户看到录音按钮后主动按住

        // 但显示一段友好的夜间提示

        that._addSystemMessage('半夜醒来没关系，按住说话，我陪你');

      }, 800);

    }

    // data 初始化时 this 不可用，移到 onLoad 中

    this.setData({ quickReplies: this._getQuickReplies() });

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

          play_audio: '播放助眠音',

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

        // 姬心脏主动对话
        activeConversation: res.active_conversation || null,

        // 话题卡片（从active_conversation或butler预警生成）
        quickReplies: getQuickReplies(res),

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

    } else if (actions.indexOf('white_noise') >= 0 || actions.indexOf('play_audio') >= 0) {

      this.playWhiteNoise('rain');

    }

  },



  playWhiteNoise(soundType) {

    var soundMap = {

      rain: '/assets/sounds/rain.mp3',

      ocean: '/assets/sounds/ocean.mp3',

      forest: '/assets/sounds/forest.mp3',

      brown: '/assets/sounds/rain.mp3',

    };

    var src = soundMap[soundType] || soundMap['rain'];

    if (this._audioCtx) {

      this._audioCtx.stop();

      this._audioCtx.destroy();

    }

    this._audioCtx = wx.createInnerAudioContext();

    this._audioCtx.src = src;

    this._audioCtx.loop = true;

    this._audioCtx.volume = 0.6;

    this._audioCtx.play();

    wx.showToast({ title: '🌧 播放助眠音', icon: 'none', duration: 2000 });

  },



  stopAudio() {

    if (this._audioCtx) {

      this._audioCtx.stop();

      this._audioCtx.destroy();

      this._audioCtx = null;

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



  // v7.2: 展开/收起记忆上下文

  toggleMemory() {

    this.setData({ memoryExpanded: !this.data.memoryExpanded });

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

      const msg = this._getWelcomeMessage(ok);

      this._addMessage('ai', msg);

    })

      .catch(err => console.error("[API]", err));

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

    // 前端去重：5秒内相同文字不重复发送
    if (text === this._lastSentText && this._lastSentTime && (Date.now() - this._lastSentTime < 3000)) {
      wx.showToast({ title: '已发送过了', icon: 'none' });
      return;
    }
    this._lastSentText = text;
    this._lastSentTime = Date.now();

    this._sendUserMessage(text);

  },



  _sendUserMessage(text) {

    this._addMessage('user', text);

    this.setData({ inputText: '', thinking: true });

    this._scrollToBottom();



    // ===== 音效意图快速匹配 =====

    var soundTriggers = {

      rain: ['雨声', '下雨', '听雨', '白噪音', '雨'],

      ocean: ['海浪', '海声', '海浪声', '大海', '海'],

      forest: ['森林', '溪流', '流水', '鸟鸣', '自然'],

      brown: ['棕噪', '低频', '低沉', '棕色噪音'],

    };

    var matchedSound = null;

    for (var soundType in soundTriggers) {

      var triggers = soundTriggers[soundType];

      for (var t = 0; t < triggers.length; t++) {

        if (text.indexOf(triggers[t]) >= 0) {

          matchedSound = soundType;

          break;

        }

      }

      if (matchedSound) break;

    }

    // 排除"哔"、"打扰一下"等误触发

    var excludeWords = ['信号', '电话', '哔', '滴', '咚咚'];

    var isExcluded = false;

    for (var e = 0; e < excludeWords.length; e++) {

      if (text.indexOf(excludeWords[e]) >= 0) { isExcluded = true; break; }

    }

    if (matchedSound && !isExcluded && text.length < 30) {

      // 短句直接触发播放，让AI正常回复

      this.playWhiteNoise(matchedSound);

    }

    // 停止音频 - 任何包含停止/关闭 + 音频相关词

    var stopWords = ['停止', '关掉', '停掉', '关了', '关', '停下', '不听了', '静音', '静默'];

    var foundStop = false;

    for (var sw = 0; sw < stopWords.length; sw++) {

      if (text.indexOf(stopWords[sw]) >= 0) {

        // 确认是关音频不是关别的

        if (text.indexOf('白噪音') >= 0 || text.indexOf('雨声') >= 0 || 

            text.indexOf('海浪') >= 0 || text.indexOf('声音') >= 0 ||

            text.indexOf('音乐') >= 0 || text.indexOf('它') >= 0 ||

            text.indexOf('这个') >= 0 || text.length <= 6) {

          this.stopAudio();

          foundStop = true;

          break;

        }

      }

    }



    var self = this;



    // ===== v7.2: 非侵入式记忆检索 =====

    // 在发送用户消息之前，后台静默加载记忆上下文

    // 不阻塞用户发送，记忆加载完成后再追加到后续请求

    api.getMemoryRecall().then(function(memRes) {

      if (memRes && memRes.success && memRes.recall_text && memRes.recall_text.length > 20) {

        self.setData({ memoryContext: memRes.recall_text });

      }

    }).catch(function() {});



    if (_canStream) {

      // === 流式模式：逐 token 显示 ===

      // 先添加空的 AI 消息占位

      self._addMessage('ai', '', null);

      self.setData({ thinking: true });

      api.chatWithAIStream(text, self._getHistory(), function(token) {

        // 每个 token 实时追加

        self._appendToLastAiMsg(token);

        self._scrollToBottom();

      }).then(function(reply) {

        self.setData({ thinking: false });

        self._onChatComplete(reply, null);

      }).catch(function(err) {

        self.setData({ thinking: false });

        self._handleChatError(err);

      });

    } else {

      // === 非流式回退 ===

      api.chatWithAI(text, self._getHistory(), self._entrySource)

        .then(res => {

          this.setData({ thinking: false });

          var reply = typeof res === 'string' ? res : (res.reply || '');

          // 世界模型数据卡片

          if (res && res.world_model && res.world_model.arousal_state && res.world_model.arousal_state !== 'unknown' && res.world_model.arousal_state !== '') {

            var wm = res.world_model;

            var stateIcons = {'anxious':'😰','alert':'😐','calm':'😌','drowsy':'😴','sleeping':'💤'};

            var icon = stateIcons[wm.arousal_state] || '❓';

            var confPct = Math.round((wm.arousal_confidence || 0) * 100);

            var bpmText = wm.recommended_bpm ? ('呼吸节奏: ' + wm.recommended_bpm + ' bpm') : '';

            reply += '\n\n📊 ' + icon + ' 当前状态: ' + wm.arousal_state + ' (' + confPct + '%)';

            if (bpmText) reply += '\n🎵 ' + bpmText;

          }

          if (reply) { self._addMessage('ai', reply); }
          var msgs = self.data.messages;
          var lastAi = msgs[msgs.length - 1];
          if (lastAi && lastAi.role === 'ai') {
            if (res.ai_insight) { lastAi.aiInsight = res.ai_insight; }
            if (res.rag_context) { lastAi.ragContext = res.rag_context; }
            self.setData({ messages: msgs });
          }
          self._onChatComplete(res, null);

        })

        .catch((err) => {

          this.setData({ thinking: false });

          self._handleChatError(err);

        });

    }

  },



  // 追加 token 到最后一条 AI 消息

  _appendToLastAiMsg: function(token) {

    var msgs = this.data.messages;

    for (var i = msgs.length - 1; i >= 0; i--) {

      if (msgs[i].role === 'ai') {

        msgs[i].content += token;

        this.setData({ messages: msgs });

        return;

      }

    }

  },



  // 聊天完成后的共同处理逻辑

  _onChatComplete: function(res, expertExtra) {

    // 回复完成后重置去重标记
    this._lastSentTime = 0;

    // res 可能是对象 {reply, score, ...} 或字符串

    var reply = typeof res === 'string' ? res : (res.reply || '');

    var expertExtra = null;

    if (res && res.expert_detail) {

      expertExtra = this._formatExpertData(res.expert_detail);

    }



    // 检查陪伴模式触发

        if (res && res.companion && res.companion.session_active) {

          console.log('[Companion] Chat triggered companion mode');

          var protocol = res.companion.protocol || '4-7-8';

          var self = this;

          setTimeout(function() {

            wx.navigateTo({

              url: '/pages/companion/companion?protocol=' + protocol + '&from_chat=true&message=' + encodeURIComponent(reply)

            });

          }, 500);

          return;

        }



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



        // 沉浸式引导：独立检测 action 字段跳转到冥想引导页

        // 单独的条件，不依赖 action_params（旧格式）

        if (res && res.meditation_protocol && res.meditation_protocol !== 'null') {

          var protocol = res.meditation_protocol;

          var self = this;

          setTimeout(function() {

            wx.navigateTo({

              url: '/pages/meditation/meditation?protocol=' + protocol + '&from_chat=true'

            });

          }, 300);

          return;

        }



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

          // ═══ 呼吸反馈弹框 ═══

          if (res.request_feedback && res.feedback_prompt) {

            var _this = this;

            wx.showModal({

              title: '呼吸练习评分',

              content: res.feedback_prompt + '（1-10）',

              editable: true,

              placeholderText: '输入1-10',

              success: function (fb) {

                if (fb.confirm && fb.content) {

                  var score = parseInt(fb.content) || 0;

                  if (score >= 1 && score <= 10) {

                    wx.request({

                      url: api.HOST + '/api/relax-feedback',

                      method: 'POST',

                      data: { openid: wx.getStorageSync('openid'), score: score, pattern: ap.name || '4-7-8' },

                      success() { wx.showToast({ title: '已记录', icon: 'success' }); }

                    });

                  }

                }

              }

            });

          }

        }

      },  // end of _onChatComplete



  // 聊天出错处理

  _handleChatError: function(err) {

    // 错误时重置去重标记
    this._lastSentTime = 0;

    var errMsg = typeof err === 'string' ? err : (err.message || err.errMsg || '');

    if (errMsg.indexOf('timeout') >= 0 || errMsg.indexOf('超时') >= 0) {

      this._addMessage('ai', '😅 回复超时了，再试一次？');

    } else if (errMsg.indexOf('无回复') >= 0 || !errMsg) {

      this._addMessage('ai', '😅 连接好像不太稳定，稍等一下重试好吗？');

    } else {

      this._addMessage('ai', '😅 ' + errMsg);

    }

    this._scrollToBottom();

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

  // 在对话中插入系统消息
  _addSystemMessage(msg) {
    var list = this.data.messages.slice();
    list.push({ role: 'ai', id: Date.now(), content: msg });
    this.setData({ messages: list });
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

          // 注入决策内参（v5.0）

          if (result.decision_memo) {

            report.decisionMemo = result.decision_memo;

          }

          if (result.decision_memo_detail) {

            report.decisionMemoDetail = result.decision_memo_detail;

          }

          if (result.prediction_stats) {

            report.predictionStats = result.prediction_stats;

          }

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

        { name: '浅睡+醒', value: 52, color: '#90A4AE' }

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

    var msg = { id, role, content, _showExperts: false };

    // 支持扩展字段（breathAction 等）

    if (extra) {

      if (extra.breathAction) msg.breathAction = true;

      if (extra.breathParams) msg.breathParams = extra.breathParams;

      if (extra.breathName) msg.breathName = extra.breathName;

      if (extra.breathTip) msg.breathTip = extra.breathTip;

      if (extra.experts) msg.experts = extra.experts;

    }

    const msgs = this.data.messages.concat([msg]);

    this.setData({ messages: msgs, msgId: id + 1 });

  },



  // 格式化专家会诊数据为前端渲染格式

  _formatExpertData(expertDetail) {

    if (!expertDetail || typeof expertDetail !== 'object') return null;

    var experts = [];

    var colors = ['#4A90E2','#5AB0FF','#7EC8E3','#6FCF97','#F2994A',

                  '#EB5757','#BB6BD9','#F2C94C','#56CCF2','#27AE60'];

    var icons = ['🧠','💡','🫁','🌙','🔬','⚠️','🧘','🏃','❤️','🥗'];

    var idx = 0;

    for (var name in expertDetail) {

      if (idx >= 10) break;

      var info = expertDetail[name];

      if (typeof info !== 'object') continue;

      var score = parseFloat(info.score) || 0;

      var scoreText = '';

      var scoreColor = '#4A90E2';

      if (score >= 0.8) { scoreText = '优秀'; scoreColor = '#27AE60'; }

      else if (score >= 0.6) { scoreText = '良好'; scoreColor = '#6FCF97'; }

      else if (score >= 0.4) { scoreText = '一般'; scoreColor = '#F2994A'; }

      else { scoreText = '偏低'; scoreColor = '#EB5757'; }



      var finding = '';

      var finding2 = '';

      if (info.findings && info.findings.length > 0) {

        finding = info.findings[0];

        if (info.findings.length > 1) {

          finding2 = info.findings[1];

        }

      } else if (info.risk_flags && info.risk_flags.length > 0) {

        finding = info.risk_flags[0];

      } else {

        // fallback: 基于评分和置信度生成简要描述

        var fallbackText = '评分 ' + scoreText + '，置信度 ' + Math.round((info.confidence || 0) * 100) + '%';

        if (score >= 0.8) fallbackText += '，各项指标良好';

        else if (score >= 0.6) fallbackText += '，轻度波动属正常范围';

        else if (score >= 0.4) fallbackText += '，部分指标偏弱需要关注';

        else fallbackText += '，存在明显改善空间';

        finding = fallbackText;

      }



      var confidencePct = '';

      if (info.confidence > 0) {

        confidencePct = Math.round(info.confidence * 100) + '%';

      }



      experts.push({

        name: name,

        specialty: info.specialty || '',

        score: score,

        scoreText: scoreText,

        scoreColor: scoreColor,

        finding: finding,

        finding2: finding2,

        color: colors[idx % colors.length],

        icon: icons[idx % icons.length],

        riskCount: info.risk_count || 0,

        confidence: info.confidence || 0,

        confidencePct: confidencePct,

      });

      idx++;

    }

    return { experts: experts };

  },



  // 展开/收拢专家会诊

  toggleExperts(e) {

    var idx = e.currentTarget.dataset.idx;

    var key = 'messages[' + idx + ']._showExperts';

    var msg = this.data.messages[idx];

    if (msg) {

      this.setData({ [key]: !msg._showExperts });

    }

  },



  // 点击呼吸引导入口 → 内嵌呼吸动画（不跳页面）

  invokeBreathing(e) {

    var idx = e.currentTarget.dataset.idx;

    var params = e.currentTarget.dataset.params;

    if (typeof params === 'string') {

      try { params = JSON.parse(params); } catch(er) {}

    }

    if (!params) params = {};



    var msgs = this.data.messages;

    if (idx === undefined || !msgs[idx]) return;



    // 展开呼吸动画状态

    msgs[idx]._breathActive = true;

    msgs[idx]._breathPhase = 'inhale';

    msgs[idx]._breathPhaseText = '吸气';

    msgs[idx]._breathCount = params.inhale || 4;

    msgs[idx]._breathScale = 0.6;

    msgs[idx]._breathOpacity = 0.5;

    msgs[idx]._breathProgress = 0;

    msgs[idx]._breathRound = 1;

    msgs[idx]._breathTotalRounds = params.rounds || 5;



    // 呼吸参数

    var inhale = params.inhale || 4;

    var hold = params.hold || 7;

    var exhale = params.exhale || 8;

    var totalRounds = params.rounds || 5;

    var _breathStartTime = Date.now();



    this.setData({ messages: msgs });



    // 呼吸计时器

    var self = this;

    var breathPhase = 'inhale';

    var breathCount = inhale;

    var breathRound = 1;

    var totalCycleMs = (inhale + hold + exhale) * 1000;



    var breathTimer = setInterval(function() {

      breathCount--;

      var msgs2 = self.data.messages;

      if (!msgs2[idx]) { clearInterval(breathTimer); return; }



      // 阶段切换

      if (breathCount <= 0) {

        if (breathPhase === 'inhale') {

          breathPhase = 'hold';

          breathCount = hold;

          msgs2[idx]._breathPhase = 'hold';

          msgs2[idx]._breathPhaseText = '屏住';

          msgs2[idx]._breathScale = 1.0;

          msgs2[idx]._breathOpacity = 1.0;

        } else if (breathPhase === 'hold') {

          breathPhase = 'exhale';

          breathCount = exhale;

          msgs2[idx]._breathPhase = 'exhale';

          msgs2[idx]._breathPhaseText = '呼气';

          msgs2[idx]._breathScale = 0.4;

          msgs2[idx]._breathOpacity = 0.3;

        } else if (breathPhase === 'exhale') {

          // 完成一轮

          breathRound++;

          if (breathRound > totalRounds) {

            clearInterval(breathTimer);

            msgs2[idx]._breathActive = false;

            msgs2[idx]._breathPhaseText = '✅ 完成';

            msgs2[idx].breathAction = false;  // 隐藏卡片

            self.setData({ messages: msgs2 });



            // 自动追加"做完了"消息

            self._sendMessage('做完了');

            return;

          }

          breathPhase = 'inhale';

          breathCount = inhale;

          msgs2[idx]._breathPhase = 'inhale';

          msgs2[idx]._breathPhaseText = '吸气';

          msgs2[idx]._breathScale = 0.6;

          msgs2[idx]._breathOpacity = 0.5;

          msgs2[idx]._breathRound = breathRound;

        }

      }



      // 更新进度

      var elapsed = Date.now() - _breathStartTime;

      var totalProgress = Math.min(100, Math.round((elapsed / (totalCycleMs * totalRounds)) * 100));



      msgs2[idx]._breathCount = breathCount;

      msgs2[idx]._breathProgress = totalProgress;

      self.setData({ messages: msgs2 });

    }, 1000);



    // 存timer引用用于停止

    msgs[idx]._breathTimer = breathTimer;

    this.setData({ messages: msgs });

  },



  // 停止内嵌呼吸

  stopInlineBreathing(e) {

    var idx = e.currentTarget.dataset.idx;

    var msgs = this.data.messages;

    if (msgs[idx] && msgs[idx]._breathTimer) {

      clearInterval(msgs[idx]._breathTimer);

    }

    if (msgs[idx]) {

      msgs[idx]._breathActive = false;

      msgs[idx].breathAction = false;

    }

    this.setData({ messages: msgs });

    this._sendMessage('先不做了');

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

    api.request('/api/timeline', { openid: openid, limit: 20 })

        .then(res => {

        const pts = res.points || [];

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

          const dpr = wx.getWindowInfo().pixelRatio;

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

      });

    },



  // ===== 动态快速回复 =====

  _getQuickReplies() {

    const now = new Date();

    const h = now.getHours();

    const last = wx.getStorageSync('latest_analysis_result');



    // 有时间相关推荐

    const timeTags = [];

    if (h >= 20 || h < 6) {

      timeTags.push('睡不着怎么办');

      timeTags.push('睡前放松方法');

    } else if (h >= 6 && h < 9) {

      timeTags.push('昨晚睡得好吗');

      timeTags.push('如何更有精神');

    } else if (h >= 12 && h < 14) {

      timeTags.push('午睡多久合适');

    }



    const baseTags = ['做一次睡眠评估', '怎样提高深睡', '半夜醒来怎么办'];



    let allTags = [];

    if (last && last.score) {

      allTags = [`昨晚${last.score}分怎么改善`, ...timeTags, ...baseTags];

    } else {

      allTags = [...timeTags, ...baseTags];

    }



    // 去重并限制5个

    return [...new Set(allTags)].slice(0, 5);

  },



  // ===== 动态欢迎消息 =====

  _getWelcomeMessage(serviceOk) {

    const now = new Date();

    const h = now.getHours();

    const last = wx.getStorageSync('latest_analysis_result');



    let timeEmoji = '🌙';

    if (h >= 6 && h < 12) { timeEmoji = '🌅'; }

    else if (h >= 12 && h < 18) { timeEmoji = '☀️'; }



    if (!serviceOk) {

      return timeEmoji + ' 你好！AI睡眠助手未能连接到后端服务，请先启动 `python deepseek_proxy.py`。';

    }



    if (last && last.score) {

      const score = last.score;

      const time = last.date || '昨晚';

      let comment = '';

      if (score >= 85) comment = '睡得很好！';

      else if (score >= 70) comment = '还不错～';

      else if (score >= 50) comment = '可以改善';

      else comment = '需要关注哦';

      return timeEmoji + ' 欢迎回来！上次睡眠评分 ' + score + ' 分（' + comment + '）';

    }



    return timeEmoji + ' 可以聊聊你的睡眠情况，我会给你专业的分析建议～';

  },

  // ===== 语音输入功能 =====
  _ensureRecorder() {
    if (!this._recorderManager) {
      this._recorderManager = wx.getRecorderManager();
      var self = this;
      this._recorderManager.onStop(function (res) {
        if (res.tempFilePath) self._uploadVoice(res.tempFilePath);
      });
      this._recorderManager.onError(function () {
        wx.showToast({ title: '录音失败', icon: 'none' });
        self.setData({ isRecording: false });
      });
    }
    return this._recorderManager;
  },
  toggleVoiceInput() {
    var show = !this.data.showVoiceInput;
    this.setData({ showVoiceInput: show });
    if (!show && this.data.isRecording) this._stopRecord();
  },
  startRecording() {
    var rec = this._ensureRecorder();
    var self = this;
    wx.getSetting({
      success: function (res) {
        if (!res.authSetting['scope.record']) {
          wx.authorize({
            scope: 'scope.record',
            success: function () {
              rec.start({ format: 'mp3', sampleRate: 16000, numberOfChannels: 1 });
              self.setData({ isRecording: true });
            },
            fail: function () { wx.showToast({ title: '需要麦克风权限', icon: 'none' }); }
          });
        } else {
          rec.start({ format: 'mp3', sampleRate: 16000, numberOfChannels: 1 });
          self.setData({ isRecording: true });
        }
      }
    });
  },
  stopRecording() { this._stopRecord(); },
  _stopRecord() {
    if (this._recorderManager) { try { this._recorderManager.stop(); } catch(e) {} }
    this.setData({ isRecording: false });
  },
  _uploadVoice(tempFilePath) {
    var self = this;
    var openid = '';
    try { var app = getApp(); openid = app.globalData.openid || ''; } catch(e) {}
    wx.showLoading({ title: '语音识别中...' });
    wx.uploadFile({
      url: api.API_BASE + '/api/voice-log',
      filePath: tempFilePath,
      name: 'voice_file',
      formData: { openid: openid, source: 'chat_page' },
      timeout: 30000,
      success: function (res) {
        wx.hideLoading();
        try {
          var data = JSON.parse(res.data);
          if (data.text) {
            self.setData({ inputText: data.text, showVoiceInput: false, isRecording: false });
            self.sendMessage();
          } else {
            wx.showToast({ title: '语音识别失败', icon: 'none' });
          }
        } catch(e) {
          if (res.data && res.data.length > 0) {
            self.setData({ inputText: res.data, showVoiceInput: false, isRecording: false });
            self.sendMessage();
          }
        }
      },
      fail: function () {
        wx.hideLoading();
        wx.showToast({ title: '上传失败, 请重试', icon: 'none' });
      }
    });
  },
});

// 快速话题生成器
function getQuickReplies(res) {
  // 如果有姬心脏主动对话
  if (res && res.active_conversation) {
    var msg = res.active_conversation.message || '';
    // 提取关键词作为话题卡片
    var cards = [msg];
    // 加上建议话题
    if (res.alerts && res.alerts.length > 0) {
      cards.push('查看我的睡眠变化');
    }
    cards.push('给我一些建议');
    cards.push('今天适合什么放松?');
    return cards;
  }
  return ['聊聊我的睡眠', '给我一些建议', '今天适合什么放松?'];
}

