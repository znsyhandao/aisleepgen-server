# -*- coding: utf-8 -*-
"""Add clinical validation report to AISleepGen
1. Backend: /api/clinical-report endpoint in deepseek_proxy.py
2. Frontend: profile page button + report page
"""
import py_compile
import os

# === Step 1: Add API endpoint to deepseek_proxy.py ===
FP = r"D:\AISleepGen_Optimized\deepseek_proxy.py"
with open(FP, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the handler routing section — add clinical-report route
old_route = "        elif path == '/api/goodnight':\n            self._handle_goodnight(data)"
new_route = "        elif path == '/api/goodnight':\n            self._handle_goodnight(data)\n        elif path == '/api/clinical-report':\n            self._handle_clinical_report(data)"

content = content.replace(old_route, new_route)

# Add the handler method — insert right after _handle_goodnight
# Find the end of _handle_goodnight  
old_end = "        self.wfile.write(json.dumps(push, ensure_ascii=False).encode('utf-8'))\n        print(f'[Goodnight] [{openid[:8]}...] \\u665a\\u5b89\\u63a8\\u9001\\u5df2\\u751f\\u6210')"

clinical_handler = """        self.wfile.write(json.dumps(push, ensure_ascii=False).encode('utf-8'))
        print(f'[Goodnight] [{openid[:8]}...] \\u665a\\u5b89\\u63a8\\u9001\\u5df2\\u751f\\u6210')

    def _handle_clinical_report(self, data):
        \"\"\"POST: \\u751f\\u6210\\u4e34\\u5e8a\\u9a8c\\u8bc1\\u62a5\\u544a\"\"\"
        self._set_headers()
        openid = self._get_openid(data)
        profile = _load_user_profile(openid)
        history = profile.get('history', [])
        
        # \\u62bd\\u53d6\\u8fd1\\u4e24\\u5468\\u7761\\u7720\\u6570\\u636e
        import time as ___t
        now = ___t.time()
        cutoff = now - 14 * 86400
        recent = [h for h in history if h.get('_ts', 0) > cutoff and h.get('wm_score', 0) > 0]
        
        # \\u8ba1\\u7b97\\u6307\\u6807
        scores = [h['wm_score'] for h in recent]
        sleep_times = []
        for h in recent:
            e = h.get('extracted', {}) or {}
            if isinstance(e, dict):
                lat = e.get('sleep_latency', 0) or 0
                dur = e.get('sleep_duration', 0) or 0
                deep = e.get('deep_sleep_pct', 0) or 0
                sleep_times.append({'latency': lat, 'duration': dur, 'deep': deep})
        
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        first_week = [s for i, s in enumerate(scores) if i < max(len(scores)//2, 3)]
        second_week = [s for i, s in enumerate(scores) if i >= max(len(scores)//2, 3)][-7:]
        avg_first = round(sum(first_week) / len(first_week), 1) if first_week else 0
        avg_second = round(sum(second_week) / len(second_week), 1) if second_week else 0
        improvement = round(avg_second - avg_first, 1)
        
        report = {
            'success': True,
            'user_id': openid[:8] + '...',
            'days_recorded': len(scores),
            'avg_score': avg_score,
            'avg_first_week': avg_first,
            'avg_second_week': avg_second,
            'improvement': improvement,
            'avg_latency_min': round(sum(t['latency'] for t in sleep_times) / len(sleep_times), 1) if sleep_times else 0,
            'avg_deep_pct': round(sum(t['deep'] for t in sleep_times) / len(sleep_times), 1) if sleep_times else 0,
            'daily_scores': [{'date': h.get('date', ''), 'score': h['wm_score']} for h in recent[-14:]],
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        }
        self.wfile.write(json.dumps(report, ensure_ascii=False).encode('utf-8'))
        print(f'[Clinical] [{openid[:8]}...] \\u4e34\\u5e8a\\u62a5\\u544a\\u5df2\\u751f\\u6210')"""

content = content.replace(old_end, clinical_handler)

with open(FP, 'w', encoding='utf-8') as f:
    f.write(content)

try:
    py_compile.compile(FP, doraise=True)
    print("deepseek_proxy.py: OK")
except py_compile.PyCompileError as e:
    print(f"ERROR in deepseek_proxy.py: {str(e)[:200]}")
    exit(1)

# === Step 2: Add button to profile page ===
PROFILE_WXML = r"D:\AISleepGen_Optimized\miniprogram\pages\profile\profile.wxml"
with open(PROFILE_WXML, 'r', encoding='utf-8') as f:
    pwxml = f.read()

# Add clinical report button after the history button
old_btn = """<view class="menu-item" bindtap="goToPage" data-page="history">
    <text class="menu-icon">📊</text>
    <text class="menu-text">历史记录</text>
    <text class="menu-arrow">›</text>
  </view>"""

new_btn = """<view class="menu-item" bindtap="goToPage" data-page="history">
    <text class="menu-icon">📊</text>
    <text class="menu-text">历史记录</text>
    <text class="menu-arrow">›</text>
  </view>
  <view class="menu-item" bindtap="goClinicalReport">
    <text class="menu-icon">🏥</text>
    <text class="menu-text">临床验证报告</text>
    <text class="menu-arrow">›</text>
  </view>"""

pwxml = pwxml.replace(old_btn, new_btn)

with open(PROFILE_WXML, 'w', encoding='utf-8') as f:
    f.write(pwxml)
print("profile.wxml: OK")

# === Step 3: Add handler in profile.js ===
PROFILE_JS = r"D:\AISleepGen_Optimized\miniprogram\pages\profile\profile.js"
with open(PROFILE_JS, 'r', encoding='utf-8') as f:
    pjs = f.read()

# Find the last function and add goClinicalReport
old_js_end = """  goToPage(e) {
    const url = e.currentTarget.dataset.page;
    wx.navigateTo({ url: '/' + url });
  }
});"""

new_js_end = """  goToPage(e) {
    const url = e.currentTarget.dataset.page;
    wx.navigateTo({ url: '/' + url });
  },

  // 临床验证报告
  goClinicalReport() {
    const that = this;
    wx.showLoading({ title: '生成报告中...' });
    wx.request({
      url: 'https://api.aisleepgen.com/api/clinical-report',
      method: 'POST',
      data: { openid: wx.getStorageSync('openid') || '' },
      success(res) {
        wx.hideLoading();
        if (res.data && res.data.success) {
          wx.navigateTo({
            url: '/pages/clinical-report/clinical-report?data=' + encodeURIComponent(JSON.stringify(res.data))
          });
        } else {
          wx.showToast({ title: '数据不足，请先记录睡眠', icon: 'none' });
        }
      },
      fail() {
        wx.hideLoading();
        wx.showToast({ title: '网络错误', icon: 'none' });
      }
    });
  }
});"""

pjs = pjs.replace(old_js_end, new_js_end)

with open(PROFILE_JS, 'w', encoding='utf-8') as f:
    f.write(pjs)
print("profile.js: OK")

# === Step 4: Create clinical-report page ===
CLINICAL_DIR = r"D:\AISleepGen_Optimized\miniprogram\pages\clinical-report"
os.makedirs(CLINICAL_DIR, exist_ok=True)

# clinical-report.js
with open(os.path.join(CLINICAL_DIR, 'clinical-report.js'), 'w', encoding='utf-8') as f:
    f.write("""Page({
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
""")

# clinical-report.wxml
with open(os.path.join(CLINICAL_DIR, 'clinical-report.wxml'), 'w', encoding='utf-8') as f:
    f.write("""<view class="page" wx:if="{{loaded && report}}">
  <view class="header">
    <text class="title">AISleepGen 临床验证报告</text>
    <text class="subtitle">{{report.generated_at}}</text>
  </view>

  <view class="card summary">
    <text class="card-title">📊 两周数据汇总</text>
    <view class="row">
      <text class="label">记录天数</text>
      <text class="value">{{report.days_recorded}} 天</text>
    </view>
    <view class="row">
      <text class="label">平均睡眠评分</text>
      <text class="value highlight">{{report.avg_score}} 分</text>
    </view>
    <view class="row">
      <text class="label">平均入睡时长</text>
      <text class="value">{{report.avg_latency_min}} min</text>
    </view>
    <view class="row">
      <text class="label">平均深睡比例</text>
      <text class="value">{{report.avg_deep_pct}}%</text>
    </view>
  </view>

  <view class="card comparison">
    <text class="card-title">📈 使用前后对比</text>
    <view class="row">
      <text class="label">前半周平均分</text>
      <text class="value">{{report.avg_first_week}} 分</text>
    </view>
    <view class="row">
      <text class="label">后半周平均分</text>
      <text class="value">{{report.avg_second_week}} 分</text>
    </view>
    <view class="improvement-badge" wx:if="{{report.improvement >= 0}}">
      <text>改善 {{report.improvement}} 分 🎉</text>
    </view>
    <view class="improvement-badge" wx:else>
      <text>波动中，继续记录</text>
    </view>
  </view>

  <view class="footer">
    <text class="footer-text">AISleepGen — 你的AI睡眠顾问</text>
    <button class="share-btn" open-type="share">分享报告</button>
  </view>
</view>

<view class="loading" wx:if="{{!loaded}}">
  <text>加载中...</text>
</view>
""")

# clinical-report.wxss
with open(os.path.join(CLINICAL_DIR, 'clinical-report.wxss'), 'w', encoding='utf-8') as f:
    f.write("""page { background: #0f0f23; color: #fff; font-family: -apple-system, PingFang SC, sans-serif; }
.page { padding: 20px; }
.header { text-align: center; margin-bottom: 24px; }
.title { font-size: 20px; font-weight: bold; color: #e8d8ff; }
.subtitle { font-size: 12px; color: #888; margin-top: 6px; display: block; }
.card { background: rgba(255,255,255,0.06); border-radius: 12px; padding: 16px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: bold; color: #8b7cb0; margin-bottom: 12px; display: block; }
.row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }
.label { font-size: 13px; color: #aaa; }
.value { font-size: 14px; color: #e8d8ff; font-weight: bold; }
.highlight { color: #7dd3fc; font-size: 16px; }
.improvement-badge { text-align: center; margin-top: 12px; }
.improvement-badge text { background: #059669; color: #fff; padding: 6px 16px; border-radius: 20px; font-size: 14px; font-weight: bold; }
.footer { text-align: center; margin-top: 24px; }
.footer-text { font-size: 11px; color: #666; display: block; margin-bottom: 12px; }
.share-btn { background: #7c5bbf; color: #fff; border-radius: 20px; font-size: 14px; padding: 8px 0; }
.loading { text-align: center; padding-top: 100px; color: #888; font-size: 14px; }
""")

# clinical-report.json
with open(os.path.join(CLINICAL_DIR, 'clinical-report.json'), 'w', encoding='utf-8') as f:
    f.write('{ "navigationBarTitleText": "临床验证报告", "usingComponents": {} }\n')

print("clinical-report page: OK")

# === Step 5: Register page in app.json ===
APPJSON = r"D:\AISleepGen_Optimized\miniprogram\app.json"
with open(APPJSON, 'r', encoding='utf-8') as f:
    appjson = f.read()

# Add clinical-report page to pages array (before the last page)
old_pages = '"pages/analytics/analytics"'
new_pages = '"pages/clinical-report/clinical-report",\n    "pages/analytics/analytics"'

appjson = appjson.replace(old_pages, new_pages)

with open(APPJSON, 'w', encoding='utf-8') as f:
    f.write(appjson)
print("app.json: OK")

print("\n=== ALL DONE ===")
