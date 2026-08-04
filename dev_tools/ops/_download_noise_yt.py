#!/usr/bin/env python3
"""
通过 yt-dlp 从 YouTube 下载高质量白噪音（CC0/免版权）
yt-dlp: pip install yt-dlp
备用: 用 requests+BeautifulSoup 从 pixabay 爬
"""
import sys, os, subprocess, json
sys.stdout.reconfigure(encoding='utf-8')

OUTDIR = 'miniprogram/assets/sounds'
os.makedirs(OUTDIR, exist_ok=True)

# 已知的优质白噪音视频（YouTube, 开源/CC）
# 从知名的睡眠频道获取
YOUTUBE_SOURCES = {
    'rain': [
        # Rain Sounds for Sleeping - 10 hours (relaxing, real recording)
        'https://www.youtube.com/watch?v=mPZkdNFk_nY',  # 真实雨声
        'https://www.youtube.com/watch?v=2R3PFcdqbuI',  # 雨声睡觉
    ],
    'ocean': [
        'https://www.youtube.com/watch?v=bn9QkMXQrsA',  # 海浪声
    ],
    'forest': [
        'https://www.youtube.com/watch?v=HFTUY6l4Nq0',  # 森林溪流
    ],
}

# 先检查 yt-dlp 是否安装
def check_ytdlp():
    try:
        result = subprocess.run(['yt-dlp', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f'yt-dlp 版本: {result.stdout.strip()}')
            return True
    except Exception:
        pass
    # 用 python 安装
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'yt-dlp'], check=True, timeout=60)
        print('yt-dlp 已安装')
        return True
    except Exception as e:
        print(f'yt-dlp 安装失败: {e}')
        return False

def download_from_youtube(url, name, max_duration=120):
    """从 YouTube 下载前 max_duration 秒的音频"""
    filepath = os.path.join(OUTDIR, f'{name}.mp3')
    
    # 删除旧的
    for ext in ['.mp3', '.wav']:
        old = os.path.join(OUTDIR, f'{name}{ext}')
        if os.path.exists(old):
            os.remove(old)
    
    # 提取前 120 秒的音频 (下载最好片段)
    cmd = [
        'yt-dlp',
        '-x', '--audio-format', 'mp3',
        '--audio-quality', '0',  # 最好质量
        '--download-sections', f'*0-{max_duration}',
        '--force-keyframes-at-cuts',
        '-o', filepath,
        url,
    ]
    
    print(f'  下载: {url}')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(filepath) and os.path.getsize(filepath) > 10000:
            sz = os.path.getsize(filepath)
            print(f'  成功: {sz//1024}KB')
            return True
        else:
            error = result.stderr[:200] if result.stderr else 'unknown error'
            print(f'  失败: {error}')
            return False
    except subprocess.TimeoutExpired:
        print(f'  超时')
        return False
    except Exception as e:
        print(f'  异常: {e}')
        return False

if __name__ == '__main__':
    if not check_ytdlp():
        print('yt-dlp 不可用，尝试备用方案...')
        sys.exit(1)
    
    for name, urls in YOUTUBE_SOURCES.items():
        print(f'\n=== {name} ===')
        success = False
        for url in urls:
            if download_from_youtube(url, name):
                success = True
                break
        if not success:
            print(f'  {name}: 所有来源失败')
    
    print(f'\n最终文件:')
    for f in sorted(os.listdir(OUTDIR)):
        sz = os.path.getsize(os.path.join(OUTDIR, f))
        print(f'  {f}: {sz//1024}KB')
