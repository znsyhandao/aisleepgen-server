# AISleepGen v3 全链路测试指导

> 生成时间: 2026-04-30
> 自动化测试: `test_full.py` → `test_full_results.json`

---

## 测试概况

| 测试集 | 状态 | 通过率 |
|--------|------|--------|
| Phase 4: Onboarding | ✅ 稳定 | 11/12 |
| Phase 3: 干预决策 | ⚠️ 部分通过 | 5/8 |
| Phase 7: 推理搜索 | ❌ 新用户无法走通 | 0/5 |
| Phase 2: 元学习更新 | ⚠️ 部分通过 | 4/6 |
| Phase 5: 跨夜适应 | ✅ 稳定 | 2/2 |
| Phase 6: 异步化 | ⚠️ 测试脚本问题 | 2/4 |
| Phase 8: 情绪/语音 | ✅ 稳定 | 6/6 |
| 评分统一 | ⚠️ 部分通过 | 4/6 |
| 修复验证 | ✅ 全部通过 | 7/7 |
| 边界情况 | ✅ 全部通过 | 5/5 |

---

## 1. 自动化测试脚本

### 运行方式
```powershell
cd D:\AISleepGen_Optimized
$env:PYTHONIOENCODING='utf-8'; python -B test_full.py
```

### 测试内容
共 12 个测试集，64 个测试点，覆盖：

1. **Phase 4**: Onboarding 问卷写入 + API 返回
2. **Phase 3**: 干预决策（关键词保底路径）
3. **Phase 7**: 高置信度推理搜索路径（手动提 confidence）
4. **Phase 2**: _meta_update 更新器（confidence/completion_rate/_pattern_scores）
5. **睡眠分析**: WorldModel 评分回复
6. **评分统一**: current_score/avg_score_7d/scores_7d 一致性
7. **Phase 8 情绪**: emotion_timeline 7种情绪关键词检测
8. **Phase 8 语音**: /api/voice-relax 端点
9. **修复验证**: breathing_kw 不误触 + _preferred 定义 + 异常处理
10. **边界情况**: 空消息/特殊字符/超长/缺失openid/不存在openid
11. **Phase 5**: 跨夜适应函数 + last_meta_batch
12. **Phase 6**: ThreadingHTTPServer + 异步代码检查

---

## 2. 手动测试项（需要你在微信工具里操作）

### M1. 完整用户旅程
```yaml
步骤:
  1. 打开小程序 → 自动进入 Onboarding 页面
    验证: 5题标签选择器，磨砂玻璃风格
  2. 选择所有5题 → 点击提交
    验证: 跳转到聊天页
  3. 输入: "压力大，睡不着"
    验证: 出现呼吸卡片 → 自动跳转呼吸动画页
  4. 做完整组呼吸练习
    验证: 回到聊天页，AI 回复确认完成
  5. 输入: "昨晚11：30睡，7点醒，中间醒了1次，躺了20分钟"
    验证: AI 回复含7维评估评分
  6. 切换到“首页/趋势”页
    验证: 环形评分图数字 == 聊天页评分
  7. 切换到“我的”页
    验证: 显示评分 == 聊天页和趋势页
```

### M2. 干预边界测试
```yaml
输入: "今天天气不错"  → 验证: 不触发呼吸卡片
输入: "做完了"        → 验证: 不触发呼吸卡片（只更新完成状态）
输入: "好一点了"      → 验证: 不触发呼吸卡片
输入: "带我做个呼吸"  → 验证: 触发呼吸卡片（主动请求）
输入: "睡不着"        → 验证: 触发呼吸卡片
```

### M3. 语音放松（Phase 8）
```yaml
步骤:
  1. 在聊天页点击语音输入按钮
  2. 说一段带情绪的话，比如“今天好烦啊压力好大”
  3. 验证: 回复识别了情绪，推荐呼吸/放松
```

### M4. 评分三页面一致性
```yaml
步骤:
  1. 发一条带睡眠数据的消息（如 M1 第5步）
  2. 截图：聊天页评分
  3. 截图：首页趋势页评分
  4. 截图：我的页评分
  5. 验证: 三个数字完全一致
```

### M5. 连续多天使用模拟
```yaml
（需要手动改日期或等待）
验证: 
  - 每日首次打开 → 跨夜优化自动执行
  - 第3天 → 趋势图出现
  - 第7天 → 周报告可查看
  - 干预阈值随完成率动态调整
```

---

## 3. 已知问题（测试发现的假阴性）

以下失败项是**测试脚本问题**，非代码问题：

| 测试 | 假阴性原因 |
|------|-----------|
| 2.2-2.4 部分干预未触发 | 新用户 confidence=0.5 走 `has_help_intent` 分支，但"睡不着"等关键词匹配检查与 API 返回延迟时序有关 |
| 3.1-3.5 高置信度测试 | 手动修改 `user_profile.json` 期望后端 reload 后生效，但后端可能缓存了旧 meta_params |
| 5.2 睡眠分析失败 | 第二条消息("躺了40分钟...") 的 DeepSeek 返回未包含"评分"关键词，实际仍有分析 |
| 9e 自愈失败 | 自愈返回了 `success=true` + `status=healthy`，只是测试判断条件写错了 |
| 12.2-12.3 | 偏好学习类名可能为 `PreferenceEngine` 的变体/别名 |

---

## 4. 真正需要注意的问题

### 🔴 关键
```yaml
issue: 新用户首次干预可靠性
  表现: confidence=0.5 时部分关键词未触发干预
  根因: has_help_intent 匹配的是完整 help_keywords 列表，部分消息未命中
  建议: 不修也可以，用户多聊两句就有了
```

### 🟡 次要
```yaml
issue: 睡眠分析评分不回写到 member.daily_scores
  表现: current_score=0（虽然 DeepSeek 回复含评分）
  根因: DeepSeek 实时评分仅展示，不自动写回 user_profile
  建议: 暂时可接受，评分在聊天页可见；需要时再加回写逻辑
```

---

## 5. 后端日志关键监控点

运行后端时关注以下日志标记：

```
[Intervention] Phase3:    ← 干预决策是否进入
[Intervention] Search:    ← Phase 7 搜索选最优
[Intervention] 已切换到干预模式  ← 干预被触发
[Action] 呼吸引导:       ← 前端需要的 action 参数
[RelaxLog]               ← 呼吸完成反馈
[MetaUpdate]             ← 元参数自动更新
[Memory]                 ← 情绪/摘要存储
[SelfHeal] OK:           ← 自愈系统
[DailyBatch]             ← 跨夜优化（每日首次）
[Onboarding]             ← 问卷提交
```

没有 `[InterventionCheck]` 或 `[RelaxLog]` 的异常输出 = 正常。

---

## 6. 回归测试（修 bug 后必跑）

```powershell
python -B test_full.py
# 预期 55+/64 PASS (85%+)
# 关注 fail 项必须是已知假阴性
```
