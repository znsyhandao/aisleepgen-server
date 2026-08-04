#!/bin/bash
export PATH=$PATH:/home/ubuntu/.local/bin
cd /opt/aisleepgen

echo "=== Download rain ==="
yt-dlp -x --audio-format mp3 --audio-quality 0 --download-sections "*0-120" --force-keyframes-at-cuts -o "rain_temp.mp3" "https://www.youtube.com/watch?v=mPZkdNFk_nY" 2>&1
ls -la rain_temp.mp3 2>&1 || echo "rain fail"

echo "=== Download ocean ==="
yt-dlp -x --audio-format mp3 --audio-quality 0 --download-sections "*0-120" --force-keyframes-at-cuts -o "ocean_temp.mp3" "https://www.youtube.com/watch?v=bn9QkMXQrsA" 2>&1
ls -la ocean_temp.mp3 2>&1 || echo "ocean fail"

echo "=== Download forest ==="
yt-dlp -x --audio-format mp3 --audio-quality 0 --download-sections "*0-120" --force-keyframes-at-cuts -o "forest_temp.mp3" "https://www.youtube.com/watch?v=HFTUY6l4Nq0" 2>&1
ls -la forest_temp.mp3 2>&1 || echo "forest fail"

echo "=== Done ==="
ls -la *.mp3 2>/dev/null
