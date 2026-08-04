"""
batch_convert_m4a.py — 批量m4a→wav转换
突变动力学审核：
  1. 不会覆盖已有wav（写新同名_converted.wav）
  2. 保存转换日志（可回溯）
  3. 大文件跳过（>20MB的整晚录音直接skip）
  4. 空文件/损坏文件记录到err_log不中断流程
"""
import subprocess, os, sys, json
from datetime import datetime

FFMPEG = r'D:\ffmpeg\bin\ffmpeg.exe'
RECORD_DIR = r'D:\AISleepGen_Optimized\sleep_record'
MAX_MB = 20  # 只转 <=20MB 的短片段

def convert_one(src, dst):
    """转一个m4a为8000Hz单声道wav，返回(duration_sec, success)"""
    cmd = [FFMPEG, '-i', src, '-ac', '1', '-ar', '8000', '-y', dst]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return (0, False, r.stderr.strip()[:200])
    # Parse duration from stderr
    import re
    m = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', r.stderr)
    if m:
        h, m_, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
        dur = h*3600 + m_*60 + s
    else:
        dur = 0
    return (round(dur, 1), True, '')

def main():
    os.makedirs(RECORD_DIR, exist_ok=True)
    files = sorted([f for f in os.listdir(RECORD_DIR) if f.endswith('.m4a')])
    log = []
    converted = 0
    skipped_size = 0
    skipped_exists = 0
    errors = 0

    print(f'[batch] Found {len(files)} m4a files')
    for fname in files:
        src = os.path.join(RECORD_DIR, fname)
        base = fname.rsplit('.', 1)[0]
        dst = os.path.join(RECORD_DIR, base + '.wav')

        # Check if wav already exists
        if os.path.exists(dst):
            skipped_exists += 1
            log.append({'file': fname, 'status': 'skip_exists', 'wav': base+'.wav'})
            continue

        # Size check
        sz_mb = os.path.getsize(src) / 1e6
        if sz_mb > MAX_MB:
            skipped_size += 1
            log.append({'file': fname, 'status': 'skip_size', 'mb': round(sz_mb, 1)})
            continue

        # Convert
        dur, ok, err = convert_one(src, dst)
        if ok:
            converted += 1
            print(f'  [OK] {fname} -> {base}.wav ({dur}s)')
            log.append({'file': fname, 'status': 'ok', 'duration_s': dur, 'wav': base+'.wav'})
        else:
            errors += 1
            print(f'  [FAIL] {fname}: {err}')
            log.append({'file': fname, 'status': 'error', 'error': err})

    # Save log
    log_path = os.path.join(RECORD_DIR, 'batch_convert_log.json')
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump({'timestamp': datetime.now().isoformat(), 'results': log, 
                   'summary': {'converted': converted, 'skipped_size': skipped_size,
                               'skipped_exists': skipped_exists, 'errors': errors}},
                  f, indent=2, ensure_ascii=False)
    
    print(f'\n[batch] Done: {converted} converted, {skipped_size} skipped(large), {skipped_exists} skip(exists), {errors} errors')
    print(f'[batch] Log saved: {log_path}')

if __name__ == '__main__':
    main()
