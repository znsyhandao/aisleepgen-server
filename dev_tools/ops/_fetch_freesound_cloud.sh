#!/bin/bash
# 终极方案: 从 Freesound 页面提取真实音频下载链接
# 手动指定已知 CC0 sound IDs，直接从页面取 preview URL
cd /opt/aisleepgen

# 直接用 wget 模拟浏览器下载已知 sound 页面，从中提取 preview 链接
# 不用 API，直接解析 HTML

function try_sound() {
    local name=$1
    local sound_id=$2
    local output="${name}.mp3"
    
    echo "Trying $name (sound $sound_id)..."
    
    # 第一步: 获取页面内容，提取 preview URL
    local page=$(wget -q -O - "https://freesound.org/people/none/sounds/${sound_id}/" --header="User-Agent: Mozilla/5.0" 2>/dev/null)
    local url=$(echo "$page" | grep -oP 'https://cdn.freesound.org/previews/[^"'"'"']+(?:mp3|ogg)' | head -1)
    
    if [ -z "$url" ]; then
        echo "  No preview URL found"
        # 尝试直接从 HTML 解析
        local alt_url=$(echo "$page" | grep -oP 'data-preview-url="[^"]+' | head -1 | sed 's/data-preview-url="//')
        if [ -n "$alt_url" ]; then
            url="$alt_url"
            echo "  Alt URL: $url"
        else
            echo "  Page snippet:"
            echo "$page" | grep -i 'preview\|download' | head -3
            return 1
        fi
    fi
    
    echo "  URL: $url"
    wget -q -O "$output" "$url" --header="User-Agent: Mozilla/5.0" 2>&1
    if [ -s "$output" ]; then
        echo "  OK: $(du -h "$output" | cut -f1)"
        return 0
    else
        rm -f "$output"
        echo "  FAIL"
        return 1
    fi
}

# 已知 CC0 白噪音 sound IDs (从 freesound 社区精选)
# 这些是高质量的自然录音
try_sound "rain"  "604026"  # Rain on window (klankbeeld)
try_sound "rain"  "609142"  # Garden rain
try_sound "ocean" "407420"  # Ocean waves
try_sound "ocean" "479838"  # Sea waves
try_sound "forest" "425782" # Forest ambience
try_sound "forest" "480547" # Night forest

# 如果 rain.mp3 还在用合成版的，就用雨声兜底
if [ ! -s "rain.mp3" ]; then
    ffmpeg -f lavfi -i "anoisesrc=d=30:c=pink:a=0.5&d=120:c=white:a=0.2" -filter_complex "amix=inputs=2:duration=longest" -ac 1 -ar 44100 rain.mp3 -y 2>/dev/null
    echo "  Fallback rain.mp3 generated"
fi

echo "=== Final ==="
for f in rain.mp3 ocean.mp3 forest.mp3; do
    if [ -f "$f" ]; then
        echo "$f: $(stat -c%s $f 2>/dev/null || echo 0) bytes"
    else
        echo "$f: MISSING"
    fi
done
