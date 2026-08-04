#!/bin/bash
# 从 Pixabay 免费音乐下载白噪音
# Pixabay 服务器在国内可达（腾讯云镜像）
cd /opt/aisleepgen

echo "=== Download from pixabay ==="

# 雨声 - 直接从 pixabay 搜索页提取
# 用已知的免费白噪音ID
# 实际上: pixabay.com/music/ 下有很多免费白噪音

# 直接用已知的下载链接（从pixabay公开页面提取）
echo "Rain..."
wget -q -O rain.mp3 "https://cdn.pixabay.com/audio/2025/05/07/audio_1512f0b8c5.mp3" 2>/dev/null
if [ -s rain.mp3 ]; then echo "  rain OK ($(stat -c%s rain.mp3) bytes)"; else rm -f rain.mp3; fi

echo "Ocean..."
wget -q -O ocean.mp3 "https://cdn.pixabay.com/audio/2023/03/20/audio_2f40e4931a.mp3" 2>/dev/null
if [ -s ocean.mp3 ]; then echo "  ocean OK ($(stat -c%s ocean.mp3) bytes)"; else rm -f ocean.mp3; fi

echo "Forest..."
wget -q -O forest.mp3 "https://cdn.pixabay.com/audio/2023/03/29/audio_f6d14d7d34.mp3" 2>/dev/null
if [ -s forest.mp3 ]; then echo "  forest OK ($(stat -c%s forest.mp3) bytes)"; else rm -f forest.mp3; fi

echo "Night..."
wget -q -O night.mp3 "https://cdn.pixabay.com/audio/2024/01/17/audio_088eac02c1.mp3" 2>/dev/null
if [ -s night.mp3 ]; then echo "  night OK ($(stat -c%s night.mp3) bytes)"; else rm -f night.mp3; fi

# 列出所有
echo "=== Results ==="
for f in rain.mp3 ocean.mp3 forest.mp3 night.mp3; do
    if [ -f "$f" ] && [ -s "$f" ]; then
        echo "  $f: $(du -h $f | cut -f1)"
    fi
done
