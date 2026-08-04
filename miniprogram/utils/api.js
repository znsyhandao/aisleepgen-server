/**
 * API 服务模块
 * 连接本地DeepSeek代理服务器，支持多用户openid隔离
 */

// 开发者工具模式 → 自动切到 localhost
var isDevTools = false;
try {
  var _baseInfo = wx.getAppBaseInfoSync();
  isDevTools = _baseInfo.platform === 'devtools';
} catch(e) {}

const API_BASE = 'https://aisleepgen.com';

// 检查是否为预览模式（手机访问），自动获取局域网IP
var DEVICE_IP = '';
try {
  var devInfo = wx.getDeviceInfo();
  var winInfo = wx.getWindowInfo();
  var isMobile = (devInfo.platform !== 'devtools' && winInfo.windowWidth > 0);
  if (isMobile) {
    DEVICE_IP = '';
  }
} catch(e) {}
var AUDIO_BASE = DEVICE_IP ? ('http://' + DEVICE_IP + ':8888') : API_BASE;

/**
 * 获取当前用户的openid
 */
function _getOpenid() {
  try {
    var app = getApp();
    return app && app.globalData && app.globalData.openid ? app.globalData.openid : 'default';
  } catch(e) {
    return 'default';
  }
}

/**
 * 微信登录：用code换取openid
 * @param {string} code - wx.login获取的code
 * @returns {Promise<Object>} { openid }
 */
function wxLogin(code) {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/wx-login',
      method: 'POST',
      data: { code: code },
      header: { 'Content-Type': 'application/json' },
      timeout: 10000,
      success: function (res) {
        if (res.data && res.data.openid) {
          resolve(res.data);
        } else {
          reject(new Error('登录失败'));
        }
      },
      fail: function (err) {
        reject(err);
      }
    });
  });
}

/**
 * 通用请求包装：自动注入openid
 */
function _request(url, data, method, timeout) {
  var openid = _getOpenid();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: url,
      method: method || 'POST',
      data: data,
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': openid
      },
      timeout: timeout || 30000,
      success: function (res) {
        resolve(res.data);
      },
      fail: function (err) {
        reject(err);
      }
    });
  });
}

/**
 * 生成睡眠分析报告（调用DeepSeek API）
 * @param {Object} surveyData - 问卷数据
 * @returns {Promise} 分析报告
 */
function generateSleepReport(surveyData) {
  return _request(API_BASE + '/api/sleep-report', surveyData, 'POST', 60000);
}

/**
 * 生成冥想计划（调用DeepSeek API）
 * @param {Object} data - 用户状态数据
 * @returns {Promise} 冥想计划
 */
function generateMeditationPlan(data) {
  return _request(API_BASE + '/api/meditation-plan', data, 'POST', 30000);
}

/**
 * 检查服务器状态
 */
function checkServerStatus() {
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/health',
      method: 'GET',
      timeout: 5000,
      success: function (res) { resolve(res.data); },
      fail: function (err) { reject(err); }
    });
  });
}

/**
 * 检查AI服务健康状态
 * @returns {Promise<boolean>}
 */
function checkHealth() {
  return new Promise(function (resolve) {
    wx.request({
      url: API_BASE + '/health',
      method: 'GET',
      timeout: 3000,
      success: function () { resolve(true); },
      fail: function () { resolve(false); }
    });
  });
}

/**
 * 与AI对话
 * @param {string} message - 用户消息
 * @param {Array} history - 对话历史
 * @returns {Promise<string>} AI回复
 */
function chatWithAI(message, history, entrySource) {
  var openid = _getOpenid();
  var data = { message: message, history: history || [], openid: openid };
  if (entrySource) data.entry_source = entrySource;
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/chat',
      method: 'POST',
      data: data,
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': openid
      },
      timeout: 60000,
      success: function (res) {
        if (res.data && (res.data.reply || (typeof res.data === 'string' && res.data.length > 0))) {
          resolve(res.data);
        } else if (res.data && res.data.error) {
          // 后端返回了显式错误，展示给用户看而不是通用提示
          reject(new Error(res.data.error));
        } else {
          reject(new Error('AI无回复'));
        }
      },
      fail: function (err) {
        // 请求失败（网络不通/域名校验），尝试一次重连
        reject(err);
      }
    });
  });
}

/**
 * 流式AI对话（SSE via wx.request task，逐token显示）
 * 需要微信小程序基础库 2.26+ 支持 enableChunked
 * @param {string} message - 用户消息
 * @param {Array} history - 对话历史
 * @param {function} onToken - 每收到一个token的回调(token字符串)
 * @returns {Promise<string>} 完整回复文本
 */
function chatWithAIStream(message, history, onToken) {
  var openid = _getOpenid();
  var data = { message: message, history: history || [], openid: openid };
  return new Promise(function (resolve, reject) {
    var fullText = '';
    var buffer = '';
    var chunkReceived = false;
    var fallbackTimer = setTimeout(function() {
      if (!chunkReceived && !fullText) {
        // 5秒无chunk → 回退到非流式请求
        var openid = _getOpenid();
        wx.request({
          url: API_BASE + '/api/chat',
          method: 'POST',
          data: data,
          header: {
            'Content-Type': 'application/json',
            'X-OpenID': openid
          },
          success: function (res2) {
            if (res2.data && res2.data.reply) {
              var fallbackText = res2.data.reply;
              if (onToken) onToken(fallbackText);
              resolve(fallbackText);
            } else {
              reject(new Error('AI无回复'));
            }
          },
          fail: function () {
            reject(new Error('请求失败'));
          }
        });
      }
    }, 5000);
    var task = wx.request({
      url: API_BASE + '/api/chat-sse',
      method: 'POST',
      data: data,
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': openid
      },
      enableChunked: true,
      timeout: 120000,
      success: function (res) {
        // enableChunked请求的success不包含完整data，onChunkReceived处理所有token
        // 如果onChunkReceived已经收到了[DONE]并resolve了，这个success不会重复触发
        // 但如果onChunkReceived没有触发（比如不支持chunked的旧库），尝试从res.data获取
        if (!fullText && res && res.data) {
          var text = typeof res.data === 'string' ? res.data : JSON.stringify(res.data);
          if (onToken) onToken(text);
          resolve(text);
        }
      },
      fail: function (err) {
        reject(err);
      }
    });
    
    task.onChunkReceived(function (chunkRes) {
      chunkReceived = true;
      if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; }
      if (chunkRes && chunkRes.data) {
        var decoder = new TextDecoder('utf-8');
        var text = decoder.decode(chunkRes.data);
        buffer += text;
        var parts = buffer.split('\n\n');
        buffer = parts.pop() || '';
        for (var i = 0; i < parts.length; i++) {
          var line = parts[i].trim();
          if (line.startsWith('data: ')) {
            var jsonStr = line.substring(6);
            if (jsonStr === '[DONE]') {
              if (fullText) { if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; } resolve(fullText); }
              else reject(new Error('AI无回复'));
              return;
            }
            try {
              var parsed = JSON.parse(jsonStr);
              if (parsed.token) {
                fullText += parsed.token;
                if (onToken) onToken(parsed.token);
              } else if (parsed.error) {
                if (fallbackTimer) { clearTimeout(fallbackTimer); fallbackTimer = null; } reject(new Error(parsed.error));
              }
            } catch (e) {}
          }
        }
      }
    });
  });
}


/**
 * 从对话历史生成睡眠报告
 * @param {Array} history - 完整对话历史
 * @returns {Promise<Object>} 报告数据
 */
function generateReportFromChat(history) {
  var openid = _getOpenid();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/chat-report',
      method: 'POST',
      data: { history: history, openid: openid },
      header: {
        'Content-Type': 'application/json',
        'X-OpenID': openid
      },
      timeout: 60000,
      success: function (res) {
        if (res.data && res.data.report) {
          resolve(res.data);
        } else {
          reject(new Error(res.data?.error || '生成失败'));
        }
      },
      fail: function (err) { reject(err); }
    });
  });
}

/**
 * 语音减压：分析情绪，推荐方案
 */
function voiceRelax(text) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/voice-relax', { text: text, openid: openid }, 'POST', 15000);
}

/**
 * 获取用户信息（画像/会员/统计）
 * @returns {Promise<Object>}
 */
function getUserProfile() {
  var openid = _getOpenid();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/user-profile?openid=' + encodeURIComponent(openid),
      method: 'GET',
      header: { 'X-OpenID': openid },
      timeout: 10000,
      success: function (res) { resolve(res.data); },
      fail: function (err) { reject(err); }
    });
  });
}

/**
 * 更新用户信息（昵称/头像等）
 * @param {Object} userInfo - { nickname, avatar_url, gender, age_range }
 * @returns {Promise<Object>}
 */
function updateUserProfile(userInfo) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/update-profile', {
    user_info: userInfo,
    openid: openid
  }, 'POST', 10000);
}

/**
 * 提交初始问卷（含 meta_params 先验初始化）
 * @param {Object} survey - 问卷答案
 * @returns {Promise<Object>}
 */
function submitOnboardingSurvey(survey) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/update-profile', {
    onboarding_survey: survey,
    openid: openid
  }, 'POST', 10000);
}

/**
 * 获取睡眠统计
 * @returns {Promise<Object>}
 */
function getSleepStats() {
  var openid = _getOpenid();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/sleep-stats?openid=' + encodeURIComponent(openid),
      method: 'GET',
      header: { 'X-OpenID': openid },
      timeout: 10000,
      success: function (res) { resolve(res.data); },
      fail: function (err) { reject(err); }
    });
  });
}

/**
 * 获取历史记录列表
 * @param {number} page
 * @param {number} pageSize
 * @returns {Promise<Object>}
 */
function getHistory(page, pageSize) {
  var openid = _getOpenid();
  page = page || 1;
  pageSize = pageSize || 20;
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/history?openid=' + encodeURIComponent(openid) + '&page=' + page + '&page_size=' + pageSize,
      method: 'GET',
      header: { 'X-OpenID': openid },
      timeout: 10000,
      success: function (res) { resolve(res.data); },
      fail: function (err) { reject(err); }
    });
  });
}

/**
 * 提交用户反馈
 * @param {string} message
 * @param {number} rating (1-5)
 * @returns {Promise<Object>}
 */
function submitFeedback(message, rating) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/feedback', {
    message: message,
    rating: rating || 5,
    openid: openid
  }, 'POST', 10000);
}

/**
 * 导出数据
 * @param {string} format 'json' or 'csv'
 * @returns {Promise<Object>}
 */
function exportData(format) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/data-export', {
    format: format || 'json',
    openid: openid
  }, 'POST', 30000);
}

/**
 * 主动管家检测
 */
function butlerCheck() {
  var openid = _getOpenid();
  console.log('[API] butlerCheck openid:', openid);
  return _request(API_BASE + '/api/butler-check', { openid: openid }, 'POST', 10000);
}

/**
 * 商业智能/行业动态
 */
function getBizIntel(query) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/biz-intel', { openid: openid, query: query || '' }, 'POST', 10000);
}

/**
 * 标记简报已读
 */
function markBriefRead() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/mark-brief-read', { openid: openid }, 'POST', 5000);
}

/**
 * 晚安推送（个性化睡前建议）
 */
function goodnight() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/goodnight', { openid: openid }, 'POST', 10000);
}

/**
 * 获取情绪时间线
 */
function getEmotionTimeline() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/emotion-timeline', { openid: openid }, 'POST', 10000);
}

/**
 * 获取对话摘要
 */
function getConversationSummaries() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/conversation-summaries', { openid: openid }, 'POST', 10000);
}

/**
 * 触发后端自我诊断+修复
 */
function selfHeal() {
  return _request(API_BASE + '/api/self-heal', {}, 'POST', 10000);
}


/**
 * 订阅消息（用户授权后保存订阅关系）
 * @param {Array} templateIds - 用户同意的模板ID列表
 * @param {string} type - 订阅类型（sleep_tip / daily_brief / alert）
 * @returns {Promise<Object>}
 */
function subscribeMsg(templateIds, type) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/subscribe-msg', {
    openid: openid,
    template_ids: templateIds,
    type: type || 'sleep_tip',
  }, 'POST', 10000);
}

/**
 * 获取/设置推送偏好
 * @param {Object} settings - 推送设置（可选，不传则获取）
 * @returns {Promise<Object>}
 */
function getPushSettings() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/push-settings', {
    openid: openid,
    action: 'get',
  }, 'POST', 10000);
}

function updatePushSettings(settings) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/push-settings', {
    openid: openid,
    action: 'set',
    settings: settings,
  }, 'POST', 10000);
}

/**
 * 获取待推送消息
 * @returns {Promise<Object>} { push: [...], count: number }
 */
function getPendingPush() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/pending-push', {
    openid: openid,
    action: 'get',
  }, 'POST', 10000);
}

/**
 * 标记推送已读
 */
function markPushRead(pushId) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/pending-push', {
    openid: openid,
    action: 'read',
    push_id: pushId,
  }, 'POST', 5000);
}

/**
 * 标记推送已接受
 */
function markPushAccepted(pushId) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/pending-push', {
    openid: openid,
    action: 'accepted',
    push_id: pushId,
  }, 'POST', 5000);
}


/**
 * 启动陪伴模式
 * @param {string} protocol - 引导协议 (4-7-8 / breathing_light / body_scan)
 * @param {string} message - 用户说的内容
 * @returns {Promise<Object>}
 */
function startCompanion(protocol, message) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/companion/start', {
    openid: openid,
    protocol: protocol || '4-7-8',
    message: message || '',
  }, 'POST', 10000);
}

/**
 * 更新陪伴状态
 * @param {Object} feedback - { movement_detected: bool, time_elapsed: number, user_cancel: bool }
 * @returns {Promise<Object>}
 */
function updateCompanion(feedback) {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/companion/update', {
    openid: openid,
    feedback: feedback || {},
  }, 'POST', 10000);
}

/**
 * 获取陪伴状态
 * @returns {Promise<Object>}
 */
function getCompanionStatus() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/companion/status', {
    openid: openid,
  }, 'POST', 5000);
}

/**
 * 停止陪伴
 */
function stopCompanion() {
  var openid = _getOpenid();
  return _request(API_BASE + '/api/companion/stop', {
    openid: openid,
  }, 'POST', 5000);
}

module.exports = {
  API_BASE: API_BASE,
  AUDIO_BASE: AUDIO_BASE,
  wxLogin: wxLogin,
  generateSleepReport: generateSleepReport,
  generateMeditationPlan: generateMeditationPlan,
  checkHealth: checkHealth,
  chatWithAI: chatWithAI,
  chatWithAIStream: chatWithAIStream,
  generateReportFromChat: generateReportFromChat,
  voiceRelax: voiceRelax,
  getUserProfile: getUserProfile,
  updateUserProfile: updateUserProfile,
  submitOnboardingSurvey: submitOnboardingSurvey,
  getSleepStats: getSleepStats,
  getHistory: getHistory,
  submitFeedback: submitFeedback,
  exportData: exportData,
  butlerCheck: butlerCheck,
  getBizIntel: getBizIntel,
  markBriefRead: markBriefRead,
  goodnight: goodnight,
  getEmotionTimeline: getEmotionTimeline,
  getConversationSummaries: getConversationSummaries,
  selfHeal: selfHeal,
  subscribeMsg: subscribeMsg,
  getPushSettings: getPushSettings,
  updatePushSettings: updatePushSettings,
  getPendingPush: getPendingPush,
  markPushRead: markPushRead,
  markPushAccepted: markPushAccepted,
  startCompanion: startCompanion,
  updateCompanion: updateCompanion,
  getCompanionStatus: getCompanionStatus,
  stopCompanion: stopCompanion,
  
  // ===== v7.2 新API =====
  
  /**
   * 获取图表数据（趋势线/饼图/柱状图/热力图/雷达图）
   * @returns {Promise<Object>} chart data
   */
  getChartData: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/chart/data', { openid: openid }, 'POST', 15000);
  },

  /**
   * 睡前预判：预测今晚睡眠质量
   * @returns {Promise<Object>} prediction + report_text
   */
  getSiegePredict: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/siege/predict', { openid: openid }, 'POST', 15000);
  },

  /**
   * 睡眠诊断书
   * @returns {Promise<Object>} diagnosis + card_text
   */
  getSiegeDiagnosis: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/siege/diagnosis', { openid: openid }, 'POST', 15000);
  },

  /**
   * 睡眠快照（预判+诊断一次调用）
   * @returns {Promise<Object>} prediction + diagnosis
   */
  getSiegeSnapshot: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/siege/snapshot', { openid: openid }, 'POST', 20000);
  },

  /**
   * 自动睡眠日记
   * @returns {Promise<Object>} diary + short_text
   */
  getAutoDiary: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/diary/auto', { openid: openid }, 'POST', 15000);
  },

  /**
   * 三层记忆检索
   * @returns {Promise<Object>} recall_text
   */
  getMemoryRecall: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/memory/recall', { openid: openid }, 'POST', 10000);
  },

  /**
   * 记忆睡前整理
   * @returns {Promise<Object>} consolidate result
   */
  consolidateMemory: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/memory/consolidate', { openid: openid }, 'POST', 10000);
  },

  /**
   * Agent感知：查看当前情境信号
   * @returns {Promise<Object>} signals + actions
   */
  getAgentPerceive: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/agent/perceive', { openid: openid }, 'POST', 10000);
  },

  /**
   * 运行一次Agent循环
   * @returns {Promise<Object>} cycle result
   */
  runAgentCycle: function() {
    return _request(API_BASE + '/api/agent/cycle', {}, 'POST', 30000);
  },

  /**
   * 音频分析
   * @param {string} wavPath - 可选，指定WAV文件路径
   * @returns {Promise<Object>} audio result + pomdp observation
   */
  analyzeAudio: function(wavPath) {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/audio/analyze', {
      openid: openid,
      wav_path: wavPath || null,
    }, 'POST', 30000);
  },

  /**
   * 手环数据提取
   * @param {string} mode - 'auto' 或 'known'
   * @returns {Promise<Object>} ring data + pomdp observation
   */
  extractRingData: function(mode) {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/ring/extract', {
      openid: openid,
      mode: mode || 'known',
    }, 'POST', 10000);
  },

  /**
   * 多源数据融合
   * @returns {Promise<Object>} assimilated data
   */
  assimilateSleepData: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/sleep/assimilate', { openid: openid }, 'POST', 30000);
  },

  /**
   * 增强版早间推送（预览不发送）
   * @returns {Promise<Object>} enhanced morning content
   */
  getEnhancedMorning: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/push/enhanced/morning', { openid: openid }, 'POST', 15000);
  },

  /**
   * 增强版晚间推送（预览不发送）
   * @returns {Promise<Object>} enhanced evening content
   */
  getEnhancedEvening: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/push/enhanced/evening', { openid: openid }, 'POST', 15000);
  },

  getBandInsight: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/band-insight', { openid: openid }, 'POST', 10000);
  },

  /**
   * 通用请求（用于沉浸式引导等新功能）
   */
  request: function(path, data) {
    var openid = _getOpenid();
    data = data || {};
    data.openid = data.openid || openid;
    return _request(API_BASE + path, data, 'POST', 30000);
  },

  // ===== 支付 & 会员系统 =====

  /**
   * 获取定价信息
   * @returns {Promise<Object>} { pricing, recommend_rules }
   */
  getPricing: function() {
    var openid = _getOpenid();
    return new Promise(function (resolve, reject) {
      wx.request({
        url: API_BASE + '/api/pricing',
        method: 'GET',
        timeout: 10000,
        success: function (res) { resolve(res.data); },
        fail: function (err) { reject(err); }
      });
    });
  },

  /**
   * 创建支付订单
   * @param {string} tier - 'pro' 或 'unlimited'
   * @param {string} period - 'month' | 'quarter' | 'year'
   * @returns {Promise<Object>} { success, prepay_id, pay_params, tier, period, price }
   */
  createOrder: function(tier, period) {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/create-order', {
      openid: openid,
      tier: tier,
      period: period,
    }, 'POST', 15000);
  },

  /**
   * AI智能推荐会员方案
   * @returns {Promise<Object>} { should_recommend, tier, message, price, icon }
   */
  getTierRecommendation: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/recommend-tier', {
      openid: openid,
    }, 'POST', 10000);
  },

  /**
   * 获取预测验证统计 (v5.0)
   * @returns {Promise<Object>} { success, stats: { verified_count, verification_rate, ... } }
   */
  getPredictionStats: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/prediction-stats', {
      openid: openid,
    }, 'POST', 10000);
  },

  isiStatus: function() {
    var openid = _getOpenid();
    return _request(API_BASE + '/api/sleep/isi-status', { openid: openid }, 'POST', 10000);
  },

  isiSubmit: function(data) {
    var openid = _getOpenid();
    data.openid = data.openid || openid;
    return _request(API_BASE + '/api/sleep/isi-submit', data, 'POST', 10000);
  },
};

// ===== 算法实验室 (Nexus 进化引擎注入算法) =====
/**
 * 获取注入算法列表
 * @returns {Promise<Object>} { success, count, algos: [{algo, file, func}] }
 */
function listAlgos() {
  return _request(API_BASE + '/api/sleep/algo-list', {}, 'POST', 15000);
}

/**
 * 运行注入算法
 * @param {string} algo - 算法名
 * @param {Object} args - 参数 (可选)
 * @returns {Promise<Object>} { success, algo, result, error }
 */
function runAlgo(algo, args) {
  return _request(API_BASE + '/api/sleep/algo-run', { algo: algo, args: args || {} }, 'POST', 60000);
}

module.exports.listAlgos = listAlgos;
module.exports.runAlgo = runAlgo;
