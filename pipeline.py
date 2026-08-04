# -*- coding: utf-8 -*-
"""
自动采集管线 v1 — Run daily to collect sleep photos + audio
Cron建议: 早8:30 (处理昨晚数据), 晚22:00 (提醒睡前准备)
"""
import os, json, subprocess, sys, tempfile
from datetime import datetime

PROJECT = r'D:\AISleepGen_Optimized'
RECORD = os.path.join(PROJECT, 'sleep_record')
ANALYZED = os.path.join(RECORD, 'analyzed')
SKIN_DB = os.path.join(PROJECT, 'sleep-skin image database')
FEATURES = os.path.join(PROJECT, 'sleep-skin features')
SCRIPTS = os.path.join(PROJECT, 'scripts')
FFMPEG = r'D:\ffmpeg\bin\ffmpeg.exe'
PYTHON = sys.executable

def get_today():
    return datetime.now().strftime('%Y%m%d')

def get_yesterday():
    from datetime import timedelta
    return (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

def step_label(msg):
    t = datetime.now().strftime('%H:%M:%S')
    print(f'[{t}] {msg}')

def run_py(script, *args):
    cmd = [PYTHON, script] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print(f'  STDOUT: {r.stdout[-300:]}')
        print(f'  STDERR: {r.stderr[-300:]}')
        raise RuntimeError(f'Script failed: {script}, exit={r.returncode}')
    return r.stdout

def scan_new_m4a():
    """查找昨晚（前一天22点后）到今早的新m4a"""
    today = get_today()
    yesterday = get_yesterday()
    targets = []
    for f in sorted(os.listdir(RECORD)):
        if not f.endswith('.m4a'): continue
        # 文件名格式: YYYYMMDD_HHMMSS.m4a
        if f.startswith(today) or f.startswith(yesterday):
            targets.append(f)
    return targets

def analyze_audio(target_files):
    """批量分析新m4a（跳过头10分钟）"""
    from sleep_audio_analyzer import SleepAudioAnalyzer
    ana = SleepAudioAnalyzer()
    results = []
    for fname in target_files:
        fp = os.path.join(RECORD, fname)
        sz_mb = os.path.getsize(fp) / 1e6
        skip = 600 if sz_mb > 100 else 0
        step_label(f'分析音频: {fname} ({sz_mb:.0f}MB, skip={skip}s)')
        try:
            result = ana.analyze_file(fp, skip_seconds=skip)
            result['date'] = fname[:8]
            result['source'] = fname
            out = os.path.join(ANALYZED, fname.replace('.m4a', '_analysis.json'))
            with open(out, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            results.append(result)
            s, m, st = result['snore'], result['movement'], result['stability']
            step_label(f'  OK: {result["duration_hours"]:.1f}h snore={s["snore_pct"]:.0f}% mov={m["total_movement_min"]:.0f}m')
        except Exception as e:
            step_label(f'  FAIL: {e}')
    return results

def extract_skin_features(photo_dir):
    """提取新照片的皮肤特征 — 调用 v9 特征提取"""
    v9_script = os.path.join(SCRIPTS, 'extract_skin_features_v9.py')
    if os.path.exists(v9_script):
        step_label(f'提取皮肤特征: {photo_dir}')
        run_py(v9_script)
    else:
        step_label(f'[WARN] v9特征提取脚本未找到: {v9_script}')
        step_label('[WARN] 照片已保存但未提取特征，后续手动处理')

def update_model():
    """更新跨夜变化模型"""
    cn_pipeline = os.path.join(PROJECT, 'cross_night_pipeline.py')
    if os.path.exists(cn_pipeline):
        step_label('更新跨夜模型...')
        output = run_py(cn_pipeline, 'update')
        for line in output.split('\n'):
            if 'R=' in line or 'RMSE' in line:
                print(f'  {line}')

def save_pipeline_log(log_data):
    log_path = os.path.join(RECORD, 'pipeline_log.json')
    if os.path.exists(log_path):
        with open(log_path, encoding='utf-8') as f: logs = json.load(f)
    else:
        logs = []
    logs.append(log_data)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(logs[-90:], f, ensure_ascii=False, indent=2)

# ===== Main =====
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'evening'
    log = {'timestamp': datetime.now().isoformat(), 'mode': mode}
    
    if mode == 'morning':
        # 早晨处理: 分析昨晚音频 + 今天早上的照片
        step_label('=== 早晨管线启动 ===')
        
        # 1. 分析新音频
        new_m4a = scan_new_m4a()
        log['new_m4a'] = len(new_m4a)
        step_label(f'发现 {len(new_m4a)} 个新音频')
        
        if new_m4a:
            audio_results = analyze_audio(new_m4a)
            log['audio_ok'] = len(audio_results)
        
        # 2. 提取皮肤特征（如果有新照片）
        today = get_today()
        today_dir = os.path.join(SKIN_DB, today)
        yesterday_dir = os.path.join(SKIN_DB, get_yesterday())
        for d in [today_dir, yesterday_dir]:
            if os.path.isdir(d) and len(os.listdir(d)) > 0:
                step_label(f'发现照片目录: {d}')
                extract_skin_features(d)
                log['photos_dir'] = d
        
        # 3. 更新模型
        update_model()
        log['model_updated'] = True
    
    elif mode == 'evening':
        # 晚间提醒
        step_label('=== 晚间准备提醒 ===')
        print()
        print('  ⏰ 睡前准备清单:')
        print('  1. 打开手机相机 → 自拍（正面光充足）')
        print('  2. 开始整夜录音（在睡前放置在床头）')
        print('  3. 关灯睡觉 🌙')
        print()
        step_label('管线待命中...')
        log['notes'] = 'evening_reminder'
    
    save_pipeline_log(log)
    step_label(f'管线完成 [{mode}]')

if __name__ == '__main__':
    main()
