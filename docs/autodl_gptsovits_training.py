# GPT-SoVITS 蔡引导音色克隆 — 一键部署脚本
# 在 AutoDL / 任意云GPU的 Jupyter Notebook 里运行

# ============================================================
# 第一步：环境安装
# ============================================================

!nvidia-smi  # 确认有GPU
print("GPU OK")

# 克隆GPT-SoVITS
!git clone https://github.com/RVC-Boss/GPT-SoVITS.git
%cd GPT-SoVITS

# 安装依赖
!pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple 2>&1 | tail -5

# 下载预训练模型
!python tools/download_models.py 2>&1 | tail -5

print("环境就绪")

# ============================================================
# 第二步：上传蔡引导的录音
# ============================================================

# 把蔡引导的6个音频文件上传到这个目录
# 在AutoDL里通过Jupyter的文件上传功能，传到 GPT-SoVITS/input_audio/
import os
os.makedirs("input_audio", exist_ok=True)
os.makedirs("output_model", exist_ok=True)

print("请将蔡引导的音频文件上传到 input_audio/ 目录")
print("支持格式: mp3, wav, m4a, aac")

# ============================================================
# 第三步：数据预处理 — 自动分割+转写
# ============================================================

import whisper
import json

# 加载Whisper模型（自动转写标注）
model = whisper.load_model("large-v3")

# 处理所有音频文件
audio_dir = "input_audio"
files = [f for f in os.listdir(audio_dir) if f.endswith(('.mp3','.wav','.m4a','.aac'))]

for fname in files:
    path = os.path.join(audio_dir, fname)
    print(f"转写: {fname}")
    result = model.transcribe(path, language="zh")
    segments = result["segments"]
    
    # 保存标注文件
    label_path = f"input_audio/{fname}.lab"
    full_text = " ".join([s["text"] for s in segments])
    # GPT-SoVITS 需要的标注格式：文件名|说话人|语言|文本
    with open(label_path, "w", encoding="utf-8") as f:
        for seg in segments:
            duration = seg["end"] - seg["start"]
            if duration > 2:  # 过滤太短的片段
                f.write(f"{fname}|guidance|ZH|{seg['text']}\n")
    
    print(f"  完成: {len(segments)}段, 总时长: {result['duration']:.1f}s")

print("预处理完成")
