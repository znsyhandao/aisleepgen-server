#!/usr/bin/env python
"""
快速ASR标注脚本：对raw_audio/caizhi_wav/下所有wav做语音识别
输出.list文件
"""
import os, json, sys

# conda env path fix
os.environ['PYTHONPATH'] = '/root/autodl-tmp/GPT-SoVITS/GPT_SoVITS:' + os.environ.get('PYTHONPATH', '')

wav_dir = '/root/autodl-tmp/GPT-SoVITS/raw_audio/caizhi_wav'
list_path = '/root/autodl-tmp/GPT-SoVITS/logs/caizhiming/caizhi_10.list'

# 尝试导入funasr
try:
    from funasr import AutoModel
    print("funasr available")
except ImportError:
    print("funasr not installed, trying pip install...")
    os.system("pip install funasr -q 2>/dev/null")
    from funasr import AutoModel

# 加载ASR模型
model = AutoModel(model="iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
                  vad_model="iic/speech_fsmn_vad_zh-cn-16k-common-pytorch",
                  punc_model="iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
                  disable_update=True)

lines = []
for f in sorted(os.listdir(wav_dir)):
    if not f.endswith('.wav'): continue
    fp = os.path.join(wav_dir, f)
    name = f.replace('.wav','')
    
    print(f"ASR: {f} ({os.path.getsize(fp)/1024/1024:.0f}MB)...")
    try:
        result = model.generate(input=fp)
        text = result[0]['text'] if result else ''
        print(f"  -> {text[:60]}...")
        line = f"{name}.wav|caizhiming|zh|{text}"
        lines.append(line)
    except Exception as e:
        print(f"  ERROR: {e}")
        lines.append(f"{name}.wav|caizhiming|zh|")

# 写.list
with open(list_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f"\nDone! {len(lines)} lines written to {list_path}")
with open(list_path, 'r', encoding='utf-8') as f:
    print(f.read())
