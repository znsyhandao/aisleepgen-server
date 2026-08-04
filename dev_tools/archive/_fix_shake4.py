# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:\AISleepGen_Optimized')

with open(r'D:\AISleepGen_Optimized\miniprogram\pages\meditation\meditation.js', 'r', encoding='utf-8') as f:
    c = f.read()

# Change timer from 1s to 1s still, but only update progress display every 3 ticks
# The key: separate DOM-updating data from non-updating data
# Use currentStepIndex for instruction (changes rarely)
# Use a less frequent set for progress bar

old_timer = '''    this._timer = setInterval(function() {
      var ct = self.data.currentTime + 1;
      var total = self.data.totalDuration;
      if (total <= 0) { self.complete(); return; }

      var pct = Math.min(Math.round(ct / total * 100), 100);
      var remain = Math.max(total - ct, 0);

      // 更新进度（每秒更新）
      self.setData({
        currentTime: ct,
        progress: pct / 100,
        remaining: remain,
        ringPercent: pct,
        ringAngle: Math.round(pct * 3.6)
      });

      // 更新当前步骤（每秒检查）
      self._updateCurrentStep(ct);

      // 更新步进点（每5秒刷新一次）
      self._tickCount++;
      if (self._tickCount % 5 === 0) {
        self.setData({
          visibleDots: self._calcDots(self.data.currentStepIndex, self.data.steps)
        });
      }

      if (ct >= total) {
        self.complete();
      }
    }, 1000);'''

new_timer = '''    this._timer = setInterval(function() {
      var ct = self.data.currentTime + 1;
      var total = self.data.totalDuration;
      if (total <= 0) { self.complete(); return; }

      var pct = Math.min(Math.round(ct / total * 100), 100);
      var remain = Math.max(total - ct, 0);

      self._tickCount++;

      // 步骤变更检测（每次都要，但只setData当步骤变了）
      var steps = self.data.steps;
      if (steps && steps.length > 0) {
        var idx = 0;
        for (var i = steps.length - 1; i >= 0; i--) {
          if (ct >= steps[i].second) { idx = i; break; }
        }
        if (idx !== self.data.currentStepIndex) {
          var update = { currentStepIndex: idx };
          if (steps[idx] && steps[idx].cycle) { update.currentCycle = steps[idx].cycle; }
          update.visibleDots = self._calcDots(idx, steps);
          self.setData(update);
          wx.vibrateShort({ type: 'light' }).catch(function() {});
        }
      }

      // 进度更新：每3秒刷一次（减少setData频率）
      if (self._tickCount % 3 === 0) {
        self.setData({
          currentTime: ct,
          remaining: remain,
          ringPercent: pct
        });
      }

      if (ct >= total) {
        self.complete();
      }
    }, 1000);'''

if old_timer in c:
    c = c.replace(old_timer, new_timer)
    with open(r'D:\AISleepGen_Optimized\miniprogram\pages\meditation\meditation.js', 'w', encoding='utf-8') as f:
        f.write(c)
    print('Timer logic replaced: progress every 3s, step change on-demand')
else:
    print('OLD TIMER NOT FOUND - checking current timer code')
    idx = c.find('this._timer = setInterval')
    if idx > 0:
        print(c[idx:idx+800])
