/**
 * API 服务模块
 * 连接本地DeepSeek代理服务器，支持多用户openid隔离
 */

// 开发者工具模式 → 自动切到 localhost
var isDevTools = false;
try {
  var _sys = wx.getSystemInfoSync();
  isDevTools = _sys.platform === 'devtools';
} catch(e) {}

const API_BASE = isDevTools ? 'http://localhost:8090' : 'https://neonotebook.tail55f441.ts.net:8090';

// 检查是否为预览模式（手机访问），自动获取局域网IP
var DEVICE_IP = '';
try {
  var sys = wx.getSystemInfoSync();
  if (sys.platform !== 'devtools') {
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
function chatWithAI(message, history) {
  var openid = _getOpenid();
  return new Promise(function (resolve, reject) {
    wx.request({
      url: API_BASE + '/api/chat',
      method: 'POST',
      data: { message: message, history: history || [], openid: openid },
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

module.exports = {
  API_BASE: API_BASE,
  AUDIO_BASE: AUDIO_BASE,
  wxLogin: wxLogin,
  generateSleepReport: generateSleepReport,
  generateMeditationPlan: generateMeditationPlan,
  checkHealth: checkHealth,
  chatWithAI: chatWithAI,
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
};
