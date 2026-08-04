"""
extractor.py - 数据提取层
从对话文本提取睡眠数据 + 用户画像加载
职责单一：输入→结构化数据输出
"""

import re
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any


class DataExtractionResult:
    """提取结果的数据类，无逻辑"""
    def __init__(self, 
                 sleep_data: Dict,
                 user_message: str,
                 history: List,
                 openid: str,
                 user_profile: Dict,
                 current_data: Dict,
                 has_quantitative_now: bool):
        self.sleep_data = sleep_data
        self.user_message = user_message
        self.history = history
        self.openid = openid
        self.user_profile = user_profile
        self.current_data = current_data
        self.has_quantitative_now = has_quantitative_now


class DataExtractor:
    """从对话文本中提取所有结构化数据"""
    
    PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
    
    @classmethod
    def extract(cls, message: str, history: List, openid: str) -> DataExtractionResult:
        """主入口：从对话中提取所有数据"""
        # 1. 加载用户画像
        profile = cls._load_user_profile(openid)
        
        # 2. 从当前消息和全量文本提取睡眠数据
        current_data = cls._extract_sleep_data_from_text(message)
        all_text = message
        for msg in history:
            if isinstance(msg, dict) and msg.get('content'):
                all_text += ' ' + msg['content']
        full_data = cls._extract_sleep_data_from_text(all_text)
        
        # 3. 判断当前消息是否有定量数据
        has_now = bool(
            current_data and (
                current_data.get('bedtime') or
                current_data.get('wake_time') or
                current_data.get('total_duration') or
                (current_data.get('awake_times') and not current_data.get('awake_estimate')) or
                current_data.get('sleep_latency') or
                current_data.get('deep_sleep_percent') or
                current_data.get('rem_sleep_percent')
            )
        )
        
        return DataExtractionResult(
            sleep_data=full_data,
            user_message=message,
            history=history,
            openid=openid,
            user_profile=profile,
            current_data=current_data,
            has_quantitative_now=has_now,
        )
    
    @classmethod
    def _load_user_profile(cls, openid: str) -> Dict:
        """加载用户画像"""
        path = os.path.join(cls.PROFILE_DIR, 'user_profile.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                all_profiles = json.load(f)
            return all_profiles.get(openid, {})
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    @classmethod
    def _extract_sleep_data_from_text(cls, text: str) -> Dict:
        """从对话文本中提取睡眠相关数据（v2.0）"""
        # 直接从deepseek_proxy.py的_extract_sleep_data_from_text移植过来
        data = {}
        if not text:
            return data
        
        # 预处理：统一中英文标点
        text_clean = text.replace('：', ':').replace('～', '~').replace('；', ';').replace('，', ',').replace('。', '.').replace('？', '?').replace('！', '!')
        
        # ===== 第一阶段：精确表达式匹配 =====
        # 上床时间
        bed_match = None
        bed_patterns = [
            r'(?:上床|睡觉|入睡|躺下|就寝|闭眼).{0,10}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)',
            r'(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)\s*(?:睡|上床|躺下|才睡)',
            r'(?:昨晚|夜里|晚上).{0,5}?(\d{1,2})\s*[点时:：]?\s*(\d{0,2})\s*(?:分|半)\s*(?:睡|半)',
        ]
        for pat in bed_patterns:
            m = re.search(pat, text_clean)
            if m:
                bed_match = m
                break
        # 补充模式：XX:XX睡 / XX点睡 / XX点XX睡
        if not bed_match:
            _direct = re.search(r'(?:^|昨晚|夜里|晚上|睡觉|入睡).{0,3}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:睡|上床|躺下|才睡|入睡)', text_clean)
            if _direct:
                bed_match = _direct
            else:
                # 最宽松匹配: "23:00睡" "23点睡" "11点半睡的"
                _bare = re.search(r'(?:昨[晚]?|晚上)?\s*(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:睡|上床|躺下|才)', text_clean)
                if _bare:
                    bed_match = _bare
        if not bed_match:
            _more = re.search(r'(\d{1,2})\s*点多\s*(?:躺下|睡|上床)', text_clean)
            if _more:
                _h = int(_more.group(1))
                data['bedtime'] = f'{_h}:30'
                bed_match = _more
        
        # 翻来覆去到X点才睡着
        _toss = re.search(r'(?:翻来覆去|辗转反侧).{0,20}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)\s*(?:才|半)\s*(?:睡着|入睡)', text_clean)
        if _toss:
            _sh = int(_toss.group(1))
            _sm = int(_toss.group(2)) if _toss.group(2) else 0
            _at = text_clean[_toss.end():_toss.end()+4]
            if '半' in _at and _sm == 0:
                _sm = 30
            data['_fall_asleep_time'] = f'{_sh}:{_sm:02d}'
            if 'bedtime' in data:
                try:
                    _bt = data['bedtime']
                    _bh, _bm = map(int, _bt.split(':'))
                    _bed_total = _bh * 60 + _bm
                    _fall_total = _sh * 60 + _sm
                    if _fall_total < _bed_total:
                        _fall_total += 12 * 60
                    _latency = _fall_total - _bed_total
                    if 5 < _latency < 180:
                        data['sleep_latency'] = _latency
                except Exception:
                    pass
        if bed_match and not isinstance(bed_match, bool):
            h = int(bed_match.group(1))
            m = 0
            m_str = bed_match.group(2) if bed_match.group(2) else ''
            if m_str:
                m = int(m_str)
            after = text_clean[bed_match.end():bed_match.end()+4]
            if '半' in after and m == 0:
                m = 30
            ctx_before = text_clean[max(0, bed_match.start()-6):bed_match.start()]
            ctx_after = text_clean[bed_match.end():bed_match.end()+6]
            if '多' in ctx_before + ctx_after and m_str == '0':
                m = 30
            data['bedtime'] = f'{h}:{m:02d}'
        
        # 起床时间
        wake_patterns = [
            r'(?:起床|醒来|睁眼|醒了|睡到).{0,10}?(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)',
            r'(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)\s*(?:醒|起床|起来|睁眼|就醒|起)',
        ]
        wake_match = None
        for pat in wake_patterns:
            m = re.search(pat, text_clean)
            if m:
                wake_match = m
                break
        # 补充模式：XX点起 / XX:XX起
        if not wake_match:
            _direct = re.search(r'(\d{1,2})\s*[点时:：]\s*(\d{0,2})\s*(?:分|半)?\s*(?:起|起床|醒|醒来|睁眼)', text_clean)
            if _direct:
                wake_match = _direct
        if wake_match:
            h = int(wake_match.group(1))
            m = int(wake_match.group(2)) if wake_match.group(2) else 0
            after = text_clean[wake_match.end():wake_match.end()+4]
            if '半' in after and m == 0:
                m = 30
            data['wake_time'] = f'{h}:{m:02d}'
        
        # 睡眠时长
        dur_match = re.search(r'(?:睡[了]?|睡眠|只睡[了]?|睡了大概|睡了约|一共睡|睡了)\s*(?:大约|大概|约)?\s*(\d+(?:\...?\d+)?)\s*(?:~|到|至)\s*(\d+(?:\...?\d+)?)\s*(?:个)?\s*(?:小时|钟头|h)', text_clean)
        if dur_match:
            val = float(dur_match.group(1).replace('-','.').replace('~',''))
            val2 = dur_match.group(2)
            if val2:
                val2 = float(val2)
                val = (val + val2) / 2
            data['total_duration'] = round(val * 60)
            data['total_duration_source'] = 'explicit'
        
        # ===== 更多字段提取：压力、醒来次数、深睡等 =====
        
        # 单值时长（非区间，如 '睡了8小时' '大概睡了7.5小时'）
        if 'total_duration' not in data:
            single_dur = re.search(r'(?:睡了|只睡|睡眠|一共睡了)\s*(?:大概|大约|约)?\s*(\d+(?:[.-]\d+)?)\s*(?:个)?\s*(?:(?:小时|钟头|h)s?|min|分钟)', text_clean)
            if single_dur:
                v = float(single_dur.group(1))
                # 假设单位是小时（中文字段'hours'或'h'或没有单位）
                data['total_duration'] = round(v * 60)
                data['total_duration_source'] = 'explicit'
        
        # 压力
        stress_match = re.search(r'压力\s*(\d+)\s*(?:分|级|/10)', text_clean)
        if stress_match:
            data['stress_level'] = int(stress_match.group(1))
        
        # 醒来次数
        awake_match = re.search(r'(?:醒[了]?|醒过来|中间醒).{0,5}?(\d+)\s*(?:次|回|遍)', text_clean)
        if awake_match:
            data['awake_times'] = int(awake_match.group(1))
        
        # 中文数量词: '醒了两次' '醒了五六次' '醒了两三次'
        if 'awake_times' not in data:
            _cn_awake = re.search(r'(?:醒[了]?|醒过来|中间醒).{0,5}?([两])\s*(?:次|回|遍)', text_clean)
            if _cn_awake:
                data['awake_times'] = 2
            else:
                _cn_range = re.search(r'(?:醒[了]?|醒过来|中间醒).{0,5}?([一二两三四五六七八九十])([一二两三四五六七八九十]?)\s*(?:次|回|遍)', text_clean)
                if _cn_range:
                    _cd = {'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10}
                    _ns = [_cd.get(c, 0) for c in _cn_range.group(1) + (_cn_range.group(2) or '')]
                    _ns = [n for n in _ns if n > 0]
                    if _ns:
                        data['awake_times'] = max(_ns)
        
        # 深睡百分比
        deep_match = re.search(r'(?:深睡|深度睡眠).{0,5}?(\d+)\s*%', text_clean)
        if deep_match:
            data['deep_sleep_percent'] = int(deep_match.group(1))
        
        
        # 深睡时长（小时或分钟）
        deep_hr_match = re.search(r'(?:深睡|深度睡眠).{0,5}?(?:大概|约)?\s*(\d+(?:[.-]\d+)?)\s*(?:个)?\s*(?:小时|钟头|h)', text_clean)
        if deep_hr_match:
            v = float(deep_hr_match.group(1))
            if 'deep_sleep_percent' not in data:
                data['deep_sleep_percent'] = int(v / 8 * 100) if 'total_duration' in data else int(v / 7 * 100)
                data['_deep_hr_source'] = True
        
        # REM百分比
        rem_match = re.search(r'REM.{0,5}?(\d+)\s*%', text_clean)
        if rem_match:
            data['rem_sleep_percent'] = int(rem_match.group(1))
        
        # 入睡潜伏期
        latency_match = re.search(r'(?:入睡|睡着).{0,5}?(?:需要|花|要|用了|大概).{0,5}?(\d+)\s*(?:分钟|分|min)', text_clean)
        if latency_match:
            data['sleep_latency'] = int(latency_match.group(1))
        
        # 疼痛检测
        if re.search(r'(?:腰|背|颈|肩|腿|膝|关节|头痛).{0,5}?(?:疼|痛|酸|胀|不舒服)', text_clean):
            data['pain'] = True
            area_match = re.search(r'(?:腰|背|颈|肩|腿|膝|关节|头痛)', text_clean)
            if area_match:
                data['pain_area'] = area_match.group(0)
        
        # 鼾声检测
        if re.search(r'(?:打鼾|打呼|鼾声|呼噜)', text_clean):
            data['snore_related'] = True
        
        # 感觉/评价
        feeling_match = re.search(r'感觉?\s*(.{2,8}?)(?:[，。！？]|$)', text_clean[:30])
        if feeling_match:
            data['feeling'] = feeling_match.group(1)
        
        # 环境温度
        if re.search(r'(?:冷|冻|手脚冰凉|空调太低)', text_clean):
            data['environment_cold'] = True
        if re.search(r'(?:热|闷|出汗|空调太高)', text_clean):
            data['environment_hot'] = True
        
        # 入睡时间范围（没有精确时间但有"大概12点"）
        if 'bedtime' not in data:
            _range = re.search(r'大概\s*(\d{1,2})\s*点', text_clean)
            if _range:
                data['bedtime'] = f'{int(_range.group(1))}:00'
                data['bedtime_estimate'] = True
        
        if 'wake_time' not in data:
            _range = re.search(r'大概\s*(\d{1,2})\s*点\s*(?:起|醒)', text_clean)
            if _range:
                h = int(_range.group(1))
                if h < 12:
                    data['wake_time'] = f'{h}:00'
                    data['wake_estimate'] = True
        
        return data
