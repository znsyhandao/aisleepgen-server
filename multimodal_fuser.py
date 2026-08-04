# -*- coding: utf-8 -*-
"""
multimodal_fuser.py — 多模态融合引擎 v1.0
项目代号：哪吒 Phase 1-2

职责：
1. 聚合音频分析、睡眠皮肤、手环截图OC的三路信号
2. 每条数据标注置信度等级
3. 输出结构化文本块，供 deepseek_proxy _handle_chat 注入 prompt

不依赖任何外部 ML 模型，纯统计+物理规则。
"""

import json, os, re
from datetime import datetime, timedelta

# ============ 配置 ============
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = r'F:\sleep_record'
SLEEP_SKIN_DB = os.path.join(PROJECT_ROOT, 'sleep-skin image database')
SKIN_FEATURES_FILE = os.path.join(SLEEP_SKIN_DB, 'skin_features.json')
FACE_HISTORY_FILE = os.path.join(PROJECT_ROOT, 'face_history.json')

# ============ 置信度等级 ============
CONF_HIGH = "可信度高"       # 有客观设备/音频数据支撑
CONF_MEDIUM = "基于数据"     # 有自述或部分数据
CONF_LOW = "基于推测"        # 无数据，仅模型推断
CONF_NONE = "数据不足"       # 无数据可用


# ===================== 动态置信度系统 =====================

def _dynamic_confidence(label, score_value, thresholds):
    """
    根据数值动态分配置信度等级
    
    Args:
        label: 信号名称（如"睡眠安静度"）
        score_value: 实际数值（如 0.82 = 82%）
        thresholds: 阈值字典，如 {'high': 0.8, 'medium': 0.65}
    
    Returns:
        (level_str, confidence_str)
    """
    if score_value is None:
        return ('', CONF_NONE)
    if score_value >= thresholds.get('high', 0.8):
        return ('高', CONF_HIGH)
    elif score_value >= thresholds.get('medium', 0.65):
        return ('中', CONF_MEDIUM)
    else:
        return ('低', CONF_LOW)


# ===================== 音频分析聚合 =====================

def _get_latest_audio_analysis():
    """获取最新的整夜音频分析结果"""
    try:
        analyzed_dir = os.path.join(SLEEP_RECORD_DIR, 'analyzed')
        if not os.path.exists(analyzed_dir):
            return None

        # 只取原始录分析（不含 tmp 和 analysis_ 前缀的重新编码文件）
        analysis_files = [
            f for f in os.listdir(analyzed_dir) 
            if f.endswith('_analysis.json') 
            and 'tmp' not in f 
            and 'analysis_' not in f
            and not f.startswith('_')
            and f.count('_') >= 1  # 至少 YYYYMMDD_HHMMSS 格式
        ]
        if not analysis_files:
            return None

        # 优先选整夜录音（total_minutes >= 180 或 quiet_pct 有意义的）
        # 如果有多条，选日期最新的
        valid_analyses = []
        for f in analysis_files:
            try:
                with open(os.path.join(analyzed_dir, f), 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                total_min = d.get('total_minutes', 0) or 0
                quiet_pct = d.get('quiet_pct', None)
                # 整夜录音：至少 3 小时 OR 有安静比数据
                if total_min >= 180 or (quiet_pct is not None and quiet_pct > 0):
                    valid_analyses.append((f, total_min, quiet_pct))
            except:
                pass
        
        if not valid_analyses:
            return None
        
        # 按 total_minutes 降序排序，取最长录音
        valid_analyses.sort(key=lambda x: x[1], reverse=True)
        latest = valid_analyses[0][0]
        with open(os.path.join(analyzed_dir, latest), 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取关键信号
        result = {
            'date': data.get('date', ''),
            'total_minutes': data.get('total_minutes', 0),
            'quiet_pct': data.get('quiet_pct', 0),
            'active_count': data.get('active_count', 0),
            'total_active_min': data.get('total_active_min', 0),
            'longest_quiet_min': data.get('longest_quiet_min', 0),
            'max_signal_db': data.get('max_signal_db', 0),
            'active_blocks': data.get('active_blocks', []),
            'source': 'audio_analyzer',
            'file': latest,
        }
        return result
    except Exception as e:
        print(f'[Multimodal] audio analysis error: {e}')
        return None


def _get_latest_audio_file_info():
    """检查 sleep_record 下最新的 m4a/wav 文件"""
    try:
        audio_files = []
        if os.path.exists(SLEEP_RECORD_DIR):
            for f in os.listdir(SLEEP_RECORD_DIR):
                if f.endswith(('.m4a', '.wav')) and not f.startswith('_'):
                    audio_files.append(f)
        if not audio_files:
            return None
        latest = sorted(audio_files, reverse=True)[0]
        # 解析文件名中的日期
        match = re.match(r'(\d{8})_', latest)
        date_str = match.group(1) if match else None
        return {
            'file': latest,
            'date': date_str,
            'size_mb': round(os.path.getsize(os.path.join(SLEEP_RECORD_DIR, latest)) / (1024*1024), 1),
        }
    except Exception as e:
        print(f'[Multimodal] audio file info error: {e}')
        return None


def _assess_audio_quality(analysis):
    """从音频分析结果中推断睡眠质量（动态置信度）"""
    if not analysis:
        return None, CONF_NONE

    signals = []
    pct = (analysis.get('quiet_pct') or 0) / 100.0
    
    # 1. 安静比例 → 深睡充足度（阈值：>=0.8高, >=0.65中）
    if analysis.get('total_minutes', 0) >= 180:
        level, conf = _dynamic_confidence('睡眠安静度', pct, {'high': 0.8, 'medium': 0.65})
        if level:
            desc = f"整夜安静比例{pct*100:.0f}%"
            if level == '高':
                desc += "，睡眠环境良好"
            elif level == '低':
                desc += "，体动频繁，可能影响睡眠质量"
            signals.append(('睡眠安静度', level, desc, conf))
    
    # 2. 活跃段模式 → 夜醒连续性（夜醒次数，越少越好）
    active_count = analysis.get('active_count', 0)
    if active_count > 0:
        # 动态阈值：<=2次高, <=5次中
        if active_count <= 2:
            signals.append(('夜醒模式', '平稳', f"夜醒{active_count}次，共{analysis.get('total_active_min', 0)}分钟", CONF_HIGH))
        elif active_count <= 5:
            signals.append(('夜醒模式', '偏多', f"夜醒{active_count}次，共{analysis.get('total_active_min', 0)}分钟", CONF_MEDIUM))
        else:
            signals.append(('夜醒模式', '频繁', f"夜醒{active_count}次，可能影响睡眠连续性", CONF_LOW))
    
    # 3. 最长安静段 → 能否进入深睡（>=90分钟高，>=45分钟中）
    longest = analysis.get('longest_quiet_min', 0)
    if longest >= 90:
        signals.append(('深睡窗口', '充足', f"最长安静段{longest}分钟，具备进入深睡的条件", CONF_HIGH))
    elif longest >= 45:
        signals.append(('深睡窗口', '一般', f"最长安静段{longest}分钟", CONF_MEDIUM))
    elif longest > 0:
        signals.append(('深睡窗口', '偏短', f"最长安静段仅{longest}分钟，可能难进入深睡", CONF_LOW))

    # 4. 整体信号质量评估（total_active_min 占总时长比例）
    total = analysis.get('total_minutes', 0)
    active_min = analysis.get('total_active_min', 0)
    if total > 0:
        active_pct = active_min / total
        if active_pct < 0.01:
            signals.append(('体动总量', '极低', f"整晚体动仅{active_min}分钟，睡眠非常平稳", CONF_HIGH))
        elif active_pct < 0.05:
            signals.append(('体动总量', '低', f"整晚体动{active_min}分钟", CONF_HIGH))
        elif active_pct < 0.15:
            signals.append(('体动总量', '中', f"整晚体动{active_min}分钟", CONF_MEDIUM))
        else:
            signals.append(('体动总量', '高', f"整晚体动{active_min}分钟，占{active_pct*100:.0f}%", CONF_LOW))

    return signals, CONF_HIGH


# ===================== 睡眠皮肤分析聚合 =====================

def _get_latest_skin_data():
    """获取最近 3 天的皮肤分析记录（睡前 vs 醒后）"""
    try:
        with open(FACE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        
        records = history.get('default', [])
        if not records:
            return None, CONF_NONE
        
        # 按时间排序
        records.sort(key=lambda r: r.get('ts', ''), reverse=True)
        
        # 分离睡前和醒后
        bedtime = [r for r in records if r.get('mode') == 'bedtime']
        wakeup = [r for r in records if r.get('mode') == 'wakeup']
        
        latest_bedtime = bedtime[0] if bedtime else None
        latest_wakeup = wakeup[0] if wakeup else None
        
        if not latest_bedtime or not latest_wakeup:
            return None, CONF_NONE
        
        # 计算变化
        fatigue_change = None
        if latest_bedtime and latest_wakeup:
            bf = latest_bedtime.get('fatigue', 0)
            wf = latest_wakeup.get('fatigue', 0)
            fatigue_change = round(wf - bf, 1)
        
        result = {
            'bedtime_fatigue': latest_bedtime.get('fatigue') if latest_bedtime else None,
            'wakeup_fatigue': latest_wakeup.get('fatigue') if latest_wakeup else None,
            'fatigue_change': fatigue_change,
            'bedtime_ts': latest_bedtime.get('ts', '') if latest_bedtime else '',
            'wakeup_ts': latest_wakeup.get('ts', '') if latest_wakeup else '',
            'total_records': len(records),
        }
        
        # 趋势：最近 7 天的变化
        recent_seven = [r for r in records if r.get('ts', '')[:10] >= (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')]
        bedtime_seven = [r for r in recent_seven if r.get('mode') == 'bedtime']
        wakeup_seven = [r for r in recent_seven if r.get('mode') == 'wakeup']
        if len(bedtime_seven) >= 3:
            result['bedtime_trend'] = round(bedtime_seven[0]['fatigue'] - bedtime_seven[-1]['fatigue'], 1)
        if len(wakeup_seven) >= 3:
            result['wakeup_trend'] = round(wakeup_seven[0]['fatigue'] - wakeup_seven[-1]['fatigue'], 1)
        
        return result, CONF_HIGH
    except Exception as e:
        print(f'[Multimodal] skin data error: {e}')
        return None, CONF_NONE


def _assess_skin_quality(skin_data):
    """从皮肤变化推断睡眠质量（动态置信度）"""
    if not skin_data:
        return None, CONF_NONE
    
    signals = []
    
    fatigue_change = skin_data.get('fatigue_change')
    
    if fatigue_change is not None:
        if fatigue_change <= -0.2:
            signals.append(('皮肤恢复', '良好', f"睡前面部疲劳{skin_data['bedtime_fatigue']}→醒后{skin_data['wakeup_fatigue']}，疲劳度下降，睡眠恢复较好", CONF_HIGH))
        elif fatigue_change <= 0:
            signals.append(('皮肤恢复', '一般', f"睡前面部疲劳{skin_data['bedtime_fatigue']}→醒后{skin_data['wakeup_fatigue']}，未见明显疲劳累积", CONF_MEDIUM))
        elif fatigue_change <= 0.5:
            signals.append(('皮肤恢复', '偏弱', f"醒后面部疲劳评分上升{fatigue_change}点", CONF_MEDIUM))
        else:
            signals.append(('皮肤恢复', '弱', f"醒后面部疲劳评分上升{fatigue_change}点，提示睡眠恢复不足", CONF_LOW))
    
    # 趋势判断
    bedtime_trend = skin_data.get('bedtime_trend')
    wakeup_trend = skin_data.get('wakeup_trend')
    if bedtime_trend is not None and wakeup_trend is not None:
        diff = abs(bedtime_trend) + abs(wakeup_trend)
        if diff < 0.3:
            signals.append(('面部趋势', '稳定', f"近7天面部疲劳度变化小", CONF_MEDIUM))
        elif diff >= 1.0:
            signals.append(('面部趋势', '波动', f"近7天面部疲劳度波动{diff:.1f}点", CONF_MEDIUM))
    
    return signals, CONF_MEDIUM


# ===================== 手环截图 OCR 聚合 =====================

def _get_latest_ocr_data():
    """获取最近的天花板截图OCR数据（如果有）"""
    try:
        ocr_file = os.path.join(SLEEP_SKIN_DB, 'sleep_huawei_data.json')
        if not os.path.exists(ocr_file):
            return None, CONF_NONE
        
        with open(ocr_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list) and data:
            latest = data[-1]
            result = {
                'date': latest.get('date', ''),
                'deep_pct': latest.get('deep_pct'),
                'total_sleep': latest.get('total_sleep'),
                'sleep_score': latest.get('sleep_score'),
                'source': 'huawei_ocr',
            }
            return result, CONF_MEDIUM
        return None, CONF_NONE
    except Exception as e:
        print(f'[Multimodal] OCR data error: {e}')
        return None, CONF_NONE


# ===================== 融合主函数 =====================

def build_multimodal_context():
    """
    融合三条数据线，输出一段结构化上下文文本（供注入 prompt）
    
    返回格式：
    === 多模态数据 ===
    📊 音频分析（可信度高）
    · 安静比 82% · 夜醒 2 次 · 最长深睡窗口 65分钟
    
    📐 皮肤分析（基于数据）
    · 醒后面部疲劳 +0.3 · 趋势稳定
    
    🗣 手环OCR（基于数据）
    · 深睡 22% · 睡眠评分 78
    
    📊 置信度加权：
    · 音频分析：最稳定的数据源，仅次手环
    · 皮肤分析：可作为辅助，但受光线影响
    · 手环数据：最精确但需用户截图
    
    如果没有数据，返回空字符串。
    """
    parts = []
    
    # 1. 音频分析
    audio_analysis = _get_latest_audio_analysis()
    audio_file = _get_latest_audio_file_info()
    
    if audio_analysis:
        signals, conf = _assess_audio_quality(audio_analysis)
        if signals:
            audio_lines = ["📊 音频分析（可信度高）"]
            for label, level, detail, _ in signals:
                audio_lines.append(f"· {label}: {level} — {detail}")
            audio_source = audio_analysis.get('file', audio_file.get('file', '')) if audio_file else audio_analysis.get('file', '')
            if audio_source:
                # 从文件名提取日期 (YYYYMMDD)
                import re as _re
                _m = _re.match(r'(\d{4})(\d{2})(\d{2})_', audio_source)
                if _m:
                    audio_lines.append(f"· 录音日期: {_m.group(1)}年{_m.group(2)}月{_m.group(3)}日")
                else:
                    audio_lines.append(f"· 数据来源: {audio_source}")
            parts.append('\n'.join(audio_lines))
    elif audio_file:
        # 有录音文件但未分析
        parts.append(f"📊 音频分析（基于数据）\n· 最近录音: {audio_file['file']} (未分析)")
    else:
        parts.append("📊 音频分析（数据不足）\n· 暂无整夜录音数据")

    # 2. 皮肤分析
    skin_data, skin_conf = _get_latest_skin_data()
    if skin_data and skin_data.get('bedtime_fatigue') is not None:
        signals, _ = _assess_skin_quality(skin_data)
        skin_prefix = "📐 皮肤分析（可信度高）" if skin_data.get('total_records', 0) >= 10 else "📐 皮肤分析（基于数据）"
        skin_lines = [skin_prefix]
        skin_lines.append(f"· 记录数: {skin_data['total_records']}天")
        if signals:
            for label, level, detail, _ in signals:
                skin_lines.append(f"· {label}: {level} — {detail}")
        parts.append('\n'.join(skin_lines))
    else:
        parts.append("📐 皮肤分析（数据不足）")

    # 3. 手环OCR
    ocr_data, ocr_conf = _get_latest_ocr_data()
    if ocr_data:
        ocr_lines = ["🗣 手环数据分析（基于数据）"]
        if ocr_data.get('deep_pct') is not None:
            ocr_lines.append(f"· 深睡比例: {ocr_data['deep_pct']}%")
        if ocr_data.get('sleep_score') is not None:
            ocr_lines.append(f"· 睡眠评分: {ocr_data['sleep_score']}")
        if ocr_data.get('total_sleep') is not None:
            ocr_lines.append(f"· 总时长: {ocr_data['total_sleep']}分钟")
        parts.append('\n'.join(ocr_lines))
    else:
        parts.append("🗣 手环数据分析（数据不足）\n· 建议截图华为睡眠报告上传")
    
    # 4. 置信度总评
    confidence_summary = (
        "--- 置信度参考 ---\n"
        "📊 音频分析: 最稳定的客观数据。安静比和体动量可信度高，夜醒计数受算法影响可能有误报\n"
        "📐 皮肤分析: 辅助信号。受拍摄光线、角度、早晚环境差异影响，趋势比绝对值更可信\n"
        "🗣 手环数据: 最精确但需用户授权。当前暂不可用\n"
        "⚠️ 结合三点：当音频+皮肤信号方向一致时，结论置信度显著提升"
    )
    parts.append(confidence_summary)
    
    return "\n\n".join(parts)


def summarize_multimodal():
    """精简版：一句话概括当前所有可用数据状态"""
    audio = _get_latest_audio_analysis()
    skin, _ = _get_latest_skin_data()
    ocr, _ = _get_latest_ocr_data()
    
    stats = []
    if audio:
        stats.append(f"音频{audio.get('quiet_pct', '?')}%安静")
    if skin:
        chg = skin.get('fatigue_change', '?')
        stats.append(f"皮肤{'+' if chg != '?' and chg and chg > 0 else ''}{chg}")
    if ocr:
        stats.append(f"手环深睡{ocr.get('deep_pct', '?')}%")
    
    return " · ".join(stats) if stats else "暂无多模态数据"


# ===================== 趋势发现（跨夜数据关联） =====================

def _load_audio_trend(days=7):
    """从 analyzed/ 加载最近几天的音频分析趋势"""
    try:
        analyzed_dir = os.path.join(SLEEP_RECORD_DIR, 'analyzed')
        if not os.path.exists(analyzed_dir):
            return []
        
        entries = []
        for f in os.listdir(analyzed_dir):
            if not f.endswith('_analysis.json') or 'tmp' in f:
                continue
            try:
                with open(os.path.join(analyzed_dir, f), 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                total = d.get('total_minutes', 0) or 0
                quiet = d.get('quiet_pct', None)
                if total >= 180 and quiet is not None:
                    # Extract date from filename
                    date_str = f[:8] if f[:8].isdigit() else ''
                    entries.append({
                        'date': date_str,
                        'quiet_pct': quiet,
                        'active': d.get('active_count', 0),
                        'longest': d.get('longest_quiet_min', 0),
                    })
            except:
                continue
        
        entries.sort(key=lambda x: x['date'], reverse=True)
        # Limit to most recent `days`
        return entries[:days]
    except Exception as e:
        print(f'[Trend] audio error: {e}')
        return []


def _load_skin_trend(days=7):
    """从 face_history 加载最近几天的皮肤疲劳趋势"""
    try:
        with open(FACE_HISTORY_FILE, 'r', encoding='utf-8') as f:
            history = json.load(f)
        records = history.get('default', [])
        wakeup_records = [r for r in records if r.get('mode') == 'wakeup']
        wakeup_records.sort(key=lambda r: r.get('ts', ''), reverse=True)
        return wakeup_records[:days]
    except Exception as e:
        print(f'[Trend] skin error: {e}')
        return []


def build_trend_context(days=7):
    """
    分析近 N 天的数据趋势，输出一句可注入 prompt 的趋势总结
    
    返回格式：一句中文（空字符串 = 数据不足）
    """
    audio = _load_audio_trend(days)
    skin = _load_skin_trend(days)
    
    parts = []
    
    # 音频趋势
    if len(audio) >= 2:
        quiet_vals = [a['quiet_pct'] for a in audio if a['quiet_pct']]
        active_vals = [a['active'] for a in audio]
        
        if len(quiet_vals) >= 2:
            first_q, last_q = quiet_vals[-1], quiet_vals[0]
            diff_q = round(last_q - first_q, 1)
            if diff_q <= -5:
                parts.append(f"音频安静比在下降（{first_q}%→{last_q}%）")
            elif diff_q >= 5:
                parts.append(f"音频安静比在上升（{first_q}%→{last_q}%）")
        
        if len(active_vals) >= 2:
            first_a, last_a = active_vals[-1], active_vals[0]
            diff_a = last_a - first_a
            if diff_a >= 5:
                parts.append(f"夜醒次数在增加（{first_a}→{last_a}次/晚）")
            elif diff_a <= -5:
                parts.append(f"夜醒次数在减少（{first_a}→{last_a}次/晚）")
    
    # 皮肤趋势
    if len(skin) >= 2:
        fatigue_vals = [s.get('fatigue', 0) or 0 for s in skin]
        first_f, last_f = fatigue_vals[-1], fatigue_vals[0]
        diff_f = round(last_f - first_f, 1)
        if diff_f <= -0.5:
            parts.append(f"醒后面部疲劳在改善（下降{diff_f}点）")
        elif diff_f >= 0.5:
            parts.append(f"醒后面部疲劳在恶化（上升{diff_f}点）")
    
    if parts:
        trend = "【趋势发现】近{day}天数据趋势：{detail}".format(day=days, detail='；'.join(parts))
        return f"\n\n{trend}\n"
    
    return ""


# 导出 build_trend_context 供 __all__
__all__ = ['build_multimodal_context', 'summarize_multimodal', 'build_trend_context']
