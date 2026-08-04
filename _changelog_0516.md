# 2026-05-16

## 07:34-07:39 OpenClaw gateway自杀分析
...

## 09:33-09:50 突变动力学修复 —— 🅱 + 🅰 实战

### 🅱 面部分析接入主站（完成）
**评估（避免重复造轮子）：**
- face_analyzer.analyze() 是纯函数，zero side effects，直接 import 即可
- face_proxy (8091独立服务器) 是**重复轮子**——它只做了 HTTP 壳 + import face_analyzer
- 删掉重复方案：直接在 dp_router 末尾加 3 个路由 `/api/sleep-from-face`, `/api/sleep-from-face-feedback`, `/api/sleep-data-stats`

**突变动力学修复 — 死代码+字段名漂移：**
1. `ensemble_model_v1.json` 字段名是 `scale_mean` 不是 `scaler_mean`（训练和预测脚本各自维护，版本不一致）
2. `_predict()` 硬编码 `pca` 变量引用，但 v1/v3 模型都没有 `pca_components` 字段 → 死代码路径
3. 残留的第57行 `raw = np.array([ridge, lasso, pca])` 覆盖了 if/else 的正确逻辑
4. 所有 `except: pass` 升级为 `except Exception as e: print(...)`（3处）

**结果：** 今早照片 `IMG_20260516_073301.jpg` 成功预测评分 3.8

### 🅰 音频上传路由（完成）
**评估：** 已有 `/api/audio/analyze` 和 `/api/audio/status`，缺上传入口
- 加 `/api/audio/upload` 路由，接收 base64 wav/m4a → 写 `sleep_record/`
- 43个m4a录音（500MB+各）无法全量转换（不需要），上传路由针对短片段设计
- pydub 在 Python 3.13 下不兼容（audioop 被移除），m4a→wav 转换降级为前端处理

### 工具链改进
- pre_op.py 修复 UnicodeEncodeError（GBK终端emoji爆炸）
- pre_op.py 修复语法错误（`not ok` 不支持写法）
- dp_router 增加 132 行新代码（4个路由），语法验证通过

## 代办
- [ ] ffmpeg 安装 + 后端 m4a→wav 转换（pydub 不可用，需另寻方案）
- [ ] 面部分析 ensemble 模型重训练（v1 太旧，特征漂移风险）
- [ ] EDF 失眠数据集下载验证（Mendeley DOI: 3hx58k232n.3）
