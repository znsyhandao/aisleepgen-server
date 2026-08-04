# AISleepGen 沉浸式引导前端接入文档
> v15.0 | 15个循证减压场景 | 2026-05-06

---

## 一、整体流程

```
用户说"做个放松练习"
       │
       ▼
  POST /api/chat
       │
       ▼
  返回 { action: "4-7-8", meditation_protocol: "4-7-8", reply: "好,我们开始..." }
       │
       ▼
  前端检测 action ≠ null → 打开沉浸式引导界面
       │
       ▼
  GET /api/meditation-plan?protocol=4-7-8&duration=5
       │
       ▼
  返回 { protocol, protocol_name, steps: [{second, phase, instruction}] }
       │
       ▼
  前端渲染：进度圆环 + 逐条指令 + 计时器
       │
       ▼
  完成后 POST /api/intervention-complete { openid, protocol, duration }
```

---

## 二、核心 API

### 2.1 对话 → 触发引导

**POST /api/chat**

请求：
```json
{
    "openid": "wx_abc123",
    "message": "做个放松练习",
    "history": [
        {"role": "user", "content": "最近压力大"},
        {"role": "assistant", "content": "了解你的情况了"}
    ]
}
```

响应中的关键字段：
```json
{
    "reply": "好，我们开始……",
    "action": "4-7-8",
    "meditation_protocol": "4-7-8",
    "token_estimate": 45,
    "ai_score": 65.3,
    "companion": null
}
```

**前端逻辑：** 收到 `action != null` 时立即跳转沉浸式引导页，不再展示文字回复。

### 2.2 action → protocol 对照表

| action | protocol 名 | 类型 | 前端图标 |
|--------|-------------|------|---------|
| `4-7-8` | 4-7-8 呼吸法 | 呼吸 | lungs |
| `box_breathing` | 盒式呼吸(4-4-4-4) | 呼吸 | square |
| `breathing` | 正念呼吸 | 呼吸 | wind |
| `pursed_lip` | 缩唇呼吸 | 呼吸 | lips |
| `body_scan` | 身体扫描冥想 | 放松 | scan |
| `pmr` | 渐进肌肉放松 | 放松 | muscle |
| `autogenic` | 自律训练 | 放松 | feather |
| `safe_place` | 安全岛想象 | 意象 | island |
| `cloud_float` | 云端漂浮 | 意象 | cloud |
| `sound_bath` | 声音浴 | 意象 | music |
| `cognitive_unloading` | 认知卸荷 - 担忧日记 | 行为 | journal |
| `paradoxical_intention` | 矛盾意向 - 努力清醒 | 行为 | eye |
| `stimulus_control` | 刺激控制 - 重新建立床=睡觉 | 行为 | bed |
| `sleep_hygiene` | 睡眠卫生检查清单 | 行为 | checklist |
| `cognitive_restructuring` | 认知重构 - 挑战不合理信念 | 行为 | brain |

---

## 三、引导数据 API（核心！）

### POST /api/meditation-plan

请求：
```json
{
    "openid": "wx_abc123",
    "protocol": "4-7-8",
    "duration": 5
}
```

`duration` 单位分钟，默认5分钟。呼吸类建议3-5分钟，放松类建议5-10分钟。

#### 呼吸类响应示例（4-7-8 / box_breathing / breathing / pursed_lip）

```json
{
    "protocol": "4-7-8",
    "protocol_name": "4-7-8 呼吸法",
    "steps": [
        {"second": 0,   "phase": "breath", "cycle": 1, "instruction": "用鼻子吸气 4 秒"},
        {"second": 6,   "phase": "breath", "cycle": 1, "instruction": "屏住呼吸 7 秒"},
        {"second": 12,  "phase": "breath", "cycle": 1, "instruction": "用嘴巴缓缓呼气 8 秒"},
        {"second": 19,  "phase": "breath", "cycle": 2, "instruction": "用鼻子吸气 4 秒"},
        ...
    ],
    "total_duration": 300
}
```

**前端渲染：**
- 以 `second` 为时间轴，从 0 到 `total_duration`
- 圆环进度 = `current_time / total_duration`
- 当前指令 = 找到 `second <= current_time < next_second` 的 step
- 每个 `cycle` 数字可显示"第X轮"
- `phase` 可用于变色（吸气=蓝、屏息=紫、呼气=橙）

#### 身体扫描类响应示例（body_scan）

```json
{
    "protocol": "body_scan",
    "protocol_name": "身体扫描冥想",
    "steps": [
        {"second": 0,   "phase": "start",  "instruction": "轻轻闭上眼睛，感受呼吸"},
        {"second": 30,  "phase": "scan",   "area": "头顶",   "instruction": "把注意力带到头顶，感受这个区域"},
        {"second": 60,  "phase": "scan",   "area": "额头和眉毛", "instruction": "关注额头和眉毛之间的区域"},
        {"second": 90,  "phase": "scan",   "area": "眼睛和下巴", "instruction": "放松眼睛周围的肌肉，松开下巴"},
        ...
        {"second": 270, "phase": "finish", "instruction": "轻轻活动手指和脚趾，慢慢睁开眼睛"}
    ],
    "total_duration": 300
}
```

**前端渲染：** 每个 step 显示身体部位 `area`，可用人体图示高亮对应部位。

#### PMR 渐进肌肉放松

```json
{
    "protocol": "pmr",
    "protocol_name": "渐进式肌肉放松",
    "steps": [
        {"second": 0,   "phase": "tense", "instruction": "握紧双拳", "area": "手部"},
        {"second": 1,   "phase": "hold",  "instruction": "保持紧张...5, 4, 3, 2, 1"},
        {"second": 6,   "phase": "relax", "instruction": "松开双拳，感受放松的感觉"},
        {"second": 10,  "phase": "tense", "instruction": "耸肩到耳边", "area": "肩部"},
        ...
    ]
}
```

**前端渲染：** 每对 tense→hold→relax 约10秒，高亮 `area` 部位。

#### 认知卸荷 / 担忧日记

```json
{
    "protocol": "cognitive_unloading",
    "protocol_name": "认知卸荷 - 担忧日记",
    "steps": [
        {"second": 0,   "phase": "think",  "instruction": "闭上眼睛，回想今天一直在想的事情"},
        {"second": 3,   "phase": "write",  "instruction": "在脑海里把那件事\"放在\"一个盒子里"},
        {"second": 8,   "phase": "affirm", "instruction": "告诉自己：\"明天再处理，现在不是时候\""},
        ...
    ]
}
```

> 这类场景步骤较短，每轮约30秒，可循环多次。

---

## 四、触发词大全（用户说什么会触发什么）

前端可用做**快捷入口按钮文案**：

| 按钮文案 | 触发协议 |
|---------|---------|
| 快速放松 | 4-7-8 |
| 盒式呼吸 | box_breathing |
| 身体扫描 | body_scan |
| 渐进放松 | pmr |
| 正念呼吸 | breathing |
| 缩唇呼吸 | pursed_lip |
| 自律训练 | autogenic |
| 安全岛 | safe_place |
| 云端漂浮 | cloud_float |
| 声音浴 | sound_bath |
| 担忧日记 ✨新 | cognitive_unloading |
| 努力清醒 ✨新 | paradoxical_intention |
| 重新建立床=睡觉 ✨新 | stimulus_control |
| 睡前检查 ✨新 | sleep_hygiene |
| 挑战坏想法 ✨新 | cognitive_restructuring |

---

## 五、配套 API

### 干预完成记录

**POST /api/intervention-complete**

```json
{
    "openid": "wx_abc123",
    "protocol": "4-7-8",
    "duration": 5,
    "completed": true,
    "rating": 4
}
```

返回：`{"status": "ok"}`

前端应在引导流程结束或用户手动退出时调用。

### 陪伴模式（可选）

适合"睡不着"场景的对话式引导，对比 meditation-plan 的固定步进，陪伴模式会根据用户反馈调整。

**POST /api/companion/start** — 启动陪伴模式
**POST /api/companion/update** — 用户反馈后获取下一步
**POST /api/companion/status** — 查当前状态
**POST /api/companion/stop** — 主动停止

---

## 六、错误处理

| HTTP 状态 | code | 含义 | 前端处理 |
|-----------|------|------|---------|
| 200 | - | 正常 | - |
| 200 | `error`: "rate_limit_exceeded" | 限流 | 展示"稍后再试" |
| 200 | `error`: "xxx" | 其他错误 | 兜底文字回复 |
| 500 | - | 服务器错误 | 展示"网络异常" |

---

## 七、前端最小实现建议

### 沉浸式引导页（5个核心组件）

```
┌─────────────────────┐
│  [< 返回]  4-7-8 呼吸  │  ← 协议名
├─────────────────────┤
│                     │
│      ╭─────╮        │
│      │ 3/9 │        │  ← 进度圆环（当前步/总步）
│      ╰─────╯        │
│                     │
│  用鼻子吸气 4 秒      │  ← 当前指令（大字，醒目）
│                     │
│  ● ● ● ○ ○ ○ ○ ○ ○  │  ← 步进点（已完成/未完成）
│                     │
│  第 2 轮 / 共 9 轮    │  ← 轮次计数
│                     │
│  [暂停]     [退出]    │  ← 控制按钮
└─────────────────────┘
```

### 关键交互
1. 进入页面立即开始计时，不额外点击"开始"
2. 每一步结束时用声音/振动提示
3. 退出时调用 `/api/intervention-complete`
4. 引导结束时自动弹出评分（1-5星）

---

## 八、16个协议触发一览（用于快捷面板）

前端聊天页入口下方可放3×5快捷网格：

```
┌──────┬──────┬──────┐
│ 快速  │ 盒式  │ 身体  │
│ 放松  │ 呼吸  │ 扫描  │
├──────┼──────┼──────┤
│ 渐进  │ 正念  │ 安全  │
│ 放松  │ 呼吸  │ 岛   │
├──────┼──────┼──────┤
│ 云端  │ 声音  │ 担忧  │
│ 漂浮  │ 浴   │ 日记  │
├──────┼──────┼──────┤
│ 努力  │ 刺激  │ 睡前  │
│ 清醒  │ 控制  │ 检查  │
├──────┼──────┼──────┤
│ 挑战  │      │      │
│ 想法  │      │      │
└──────┴──────┴──────┘
```

点击任意按钮 → `POST /api/chat { message: "做个X" }` → 拿到 action 后跳转引导页。

---

## 九、验证方法

```bash
# 1. 触发引导
curl -X POST http://localhost:8090/api/chat \
  -H "Content-Type: application/json" \
  -d '{"openid":"test","message":"做个放松练习","history":[]}'

# 2. 查看返回的 action 和 meditation_protocol
# 返回: {"reply":"好，我们开始...", "action":"4-7-8", ...}

# 3. 拉取引导步骤
curl -X POST http://localhost:8090/api/meditation-plan \
  -H "Content-Type: application/json" \
  -d '{"openid":"test","protocol":"4-7-8","duration":3}'
```

---

> **写完了。** 后端接口稳定，只需要前端按这份文档接入。需要我提供某个协议的具体步进数据示例，或者配合前端联调随时喊我。

---

## Update

前端代码已部署到 miniprogram/pages/meditation/ 和 miniprogram/pages/chat/chat.js。
