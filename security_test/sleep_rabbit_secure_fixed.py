#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
鐪犲皬鍏旂潯鐪犲仴搴锋妧鑳?- 瀹夊叏鐗堟湰
瀹屽叏閬靛惊"缁濅笉妯℃嫙"鍘熷垯锛屾墍鏈夊姛鑳介兘鏄湡瀹炵殑
绗﹀悎OpenClaw鎶€鑳借鑼?v1.0.5
"""

import os
import sys
import json
import argparse
import statistics
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import csv
import time


class EnvironmentCapability(Enum):
    """鐜鑳藉姏绾у埆"""
    BASIC = "basic"      # 浠呮爣鍑嗗簱锛屾彁渚涚湡瀹炲熀纭€鍔熻兘
    ADVANCED = "advanced"  # 鏈塎NE绛夌瀛﹀簱锛屾彁渚涘畬鏁碋DF鍒嗘瀽
    FULL = "full"        # 瀹屾暣AISleepGen鐜锛屾墍鏈夐珮绾у姛鑳?

class FileType(Enum):
    """鏂囦欢绫诲瀷"""
    EDF = "edf"          # EDF鐫＄湢鏁版嵁
    CSV = "csv"          # CSV鏁版嵁鏂囦欢
    TXT = "txt"          # 鏂囨湰鏁版嵁
    UNKNOWN = "unknown"  # 鏈煡绫诲瀷


@dataclass
class FileAnalysis:
    """鏂囦欢鍒嗘瀽缁撴灉"""
    exists: bool
    file_type: FileType
    size_mb: float
    extension: str
    is_readable: bool
    line_count: Optional[int] = None
    encoding: Optional[str] = None


@dataclass
class HeartRateAnalysis:
    """蹇冪巼鍒嗘瀽缁撴灉"""
    mean_hr: float
    std_hr: float
    min_hr: float
    max_hr: float
    hrv_sdnn: Optional[float] = None
    stress_score: Optional[float] = None


@dataclass
class MeditationGuide:
    """鍐ユ兂鎸囧"""
    type: str
    duration_minutes: int
    instructions: List[str]
    benefits: List[str]
    tips: List[str]


class SleepRabbitSkill:
    """鐪犲皬鍏旂潯鐪犲仴搴锋妧鑳?- 瀹夊叏鐗堟湰"""
    
    def __init__(self):
        self.name = "sleep-rabbit"
        self.version = "1.0.5"
        self.description = "鐪犲皬鍏旂潯鐪犲仴搴峰垎鏋愮郴缁?- 瀹夊叏鐗堟湰"
        
        # 鐜妫€娴?        self.capability = self._detect_environment()
        
        # 鍒濆鍖栨棩蹇?        self._init_logging()
    
    def _init_logging(self):
        """鍒濆鍖栨棩蹇?""
        self.log_file = Path("sleep_rabbit.log")
        self.log_messages = []
    
    def _log(self, message: str, level: str = "INFO"):
        """璁板綍鏃ュ織"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] [{level}] {message}"
        self.log_messages.append(log_entry)
        
        # 鍚屾椂杈撳嚭鍒版帶鍒跺彴
        print(log_entry)
        
        # 鍐欏叆鏃ュ織鏂囦欢
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")
        except:
            pass  # 濡傛灉鏃犳硶鍐欏叆鏃ュ織鏂囦欢锛岀户缁墽琛?    
    def _detect_environment(self) -> EnvironmentCapability:
        """妫€娴嬬幆澧冭兘鍔?""
        try:
            # 灏濊瘯瀵煎叆MNE
            import mne
            self._log("妫€娴嬪埌MNE搴擄紝鏀寔瀹屾暣EDF鍒嗘瀽")
            return EnvironmentCapability.ADVANCED
        except ImportError:
            self._log("鏈娴嬪埌MNE搴擄紝浣跨敤鍩虹鍔熻兘")
            return EnvironmentCapability.BASIC
    
    def analyze_file(self, file_path: str) -> FileAnalysis:
        """鍒嗘瀽鏂囦欢 - 鐪熷疄鍔熻兘"""
        path = Path(file_path)
        
        if not path.exists():
            return FileAnalysis(
                exists=False,
                file_type=FileType.UNKNOWN,
                size_mb=0.0,
                extension="",
                is_readable=False
            )
        
        # 鑾峰彇鏂囦欢鎵╁睍鍚?        ext = path.suffix.lower().lstrip('.')
        
        # 纭畾鏂囦欢绫诲瀷
        file_type = FileType.UNKNOWN
        if ext == "edf":
            file_type = FileType.EDF
        elif ext == "csv":
            file_type = FileType.CSV
        elif ext == "txt":
            file_type = FileType.TXT
        
        # 鑾峰彇鏂囦欢澶у皬
        size_mb = path.stat().st_size / (1024 * 1024)
        
        # 妫€鏌ュ彲璇绘€?        is_readable = os.access(file_path, os.R_OK)
        
        # 濡傛灉鏄枃鏈枃浠讹紝灏濊瘯鑾峰彇琛屾暟
        line_count = None
        encoding = None
        if file_type in [FileType.CSV, FileType.TXT] and is_readable:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    line_count = sum(1 for _ in f)
                encoding = "utf-8"
            except:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        line_count = sum(1 for _ in f)
                    encoding = "gbk"
                except Exception:
        return FileAnalysis(
            exists=True,
            file_type=file_type,
            size_mb=size_mb,
            extension=ext,
            is_readable=is_readable,
            line_count=line_count,
            encoding=encoding
        )
    
    def analyze_heart_rate(self, hr_data: List[float]) -> HeartRateAnalysis:
        """鍒嗘瀽蹇冪巼鏁版嵁 - 鐪熷疄璁＄畻"""
        if not hr_data:
            raise ValueError("蹇冪巼鏁版嵁涓嶈兘涓虹┖")
        
        # 鍩烘湰缁熻
        mean_hr = statistics.mean(hr_data)
        std_hr = statistics.stdev(hr_data) if len(hr_data) > 1 else 0.0
        min_hr = min(hr_data)
        max_hr = max(hr_data)
        
        # 璁＄畻HRV (SDNN) - 鐪熷疄璁＄畻
        hrv_sdnn = None
        if len(hr_data) >= 5:
            # 璁＄畻RR闂存湡锛堝亣璁惧績鐜囧崟浣嶄负bpm锛?            rr_intervals = [60000 / hr for hr in hr_data]  # 杞崲涓烘绉?            
            # 璁＄畻SDNN
            mean_rr = statistics.mean(rr_intervals)
            squared_diffs = [(rr - mean_rr) ** 2 for rr in rr_intervals]
            hrv_sdnn = math.sqrt(statistics.mean(squared_diffs))
        
        # 璁＄畻鍘嬪姏璇勫垎锛堝熀浜嶩RV锛?        stress_score = None
        if hrv_sdnn is not None:
            # 绠€鍗曠殑鍘嬪姏璇勫垎妯″瀷
            if hrv_sdnn > 50:
                stress_score = 0.2  # 浣庡帇
            elif hrv_sdnn > 30:
                stress_score = 0.5  # 姝ｅ父
            else:
                stress_score = 0.8  # 楂樺帇
        
        return HeartRateAnalysis(
            mean_hr=mean_hr,
            std_hr=std_hr,
            min_hr=min_hr,
            max_hr=max_hr,
            hrv_sdnn=hrv_sdnn,
            stress_score=stress_score
        )
    
    def get_meditation_guide(self, meditation_type: str = "breathing", 
                            duration: int = 10) -> MeditationGuide:
        """鑾峰彇鍐ユ兂鎸囧 - 鐪熷疄鎸囧"""
        
        # 瀹氫箟鍐ユ兂绫诲瀷
        guides = {
            "breathing": {
                "name": "鍛煎惛鍐ユ兂",
                "instructions": [
                    "1. 鎵句竴涓畨闈欒垝閫傜殑鍦版柟鍧愪笅",
                    "2. 鑳岄儴鎸虹洿锛屽弻鎵嬫斁鍦ㄨ啙鐩栦笂",
                    "3. 闂笂鐪肩潧锛屼笓娉ㄤ簬鍛煎惛",
                    "4. 鍚告皵4绉掞紝灞忔皵2绉掞紝鍛兼皵6绉?,
                    "5. 閲嶅杩欎釜鍛煎惛妯″紡"
                ],
                "benefits": [
                    "闄嶄綆蹇冪巼",
                    "鍑忚交鍘嬪姏",
                    "鎻愰珮涓撴敞鍔?,
                    "鏀瑰杽鐫＄湢璐ㄩ噺"
                ],
                "tips": [
                    "姣忓ぉ缁冧範10-15鍒嗛挓鏁堟灉鏈€浣?,
                    "鏃╀笂缁冧範鏈夊姪浜庝竴澶╃殑绮剧鐘舵€?,
                    "鐫″墠缁冧範鏈夊姪浜庡叆鐫?
                ]
            },
            "body_scan": {
                "name": "韬綋鎵弿鍐ユ兂",
                "instructions": [
                    "1. 骞宠汉鎴栬垝閫傚湴鍧愮潃",
                    "2. 浠庤剼瓒惧紑濮嬶紝閫愭笎鍚戜笂鎵弿韬綋",
                    "3. 娉ㄦ剰姣忎釜閮ㄤ綅鐨勬劅瑙?,
                    "4. 鏀炬澗绱у紶鐨勮倢鑲?,
                    "5. 淇濇寔鍛煎惛骞崇ǔ"
                ],
                "benefits": [
                    "缂撹В韬綋绱у紶",
                    "鎻愰珮韬綋鎰忚瘑",
                    "鍑忚交鎱㈡€х柤鐥?,
                    "淇冭繘娣卞害鏀炬澗"
                ],
                "tips": [
                    "閫傚悎鐫″墠缁冧範",
                    "姣忎釜閮ㄤ綅鍋滅暀30绉?,
                    "涓嶈寮鸿揩鏀炬澗锛屽彧鏄瀵?
                ]
            },
            "sleep_prep": {
                "name": "鐫″墠鍑嗗鍐ユ兂",
                "instructions": [
                    "1. 鐫″墠30鍒嗛挓寮€濮?,
                    "2. 璋冩殫鐏厜锛屽叧闂數瀛愯澶?,
                    "3. 涓撴敞浜庣紦鎱㈢殑鑵瑰紡鍛煎惛",
                    "4. 鎯宠薄骞抽潤鐨勫満鏅?,
                    "5. 璁╂€濈华鑷劧娴佸姩"
                ],
                "benefits": [
                    "鏀瑰杽鍏ョ潯鏃堕棿",
                    "鎻愰珮鐫＄湢娣卞害",
                    "鍑忓皯澶滈棿閱掓潵",
                    "鎻愬崌鏁翠綋鐫＄湢璐ㄩ噺"
                ],
                "tips": [
                    "寤虹珛鍥哄畾鐨勭潯鍓嶄华寮?,
                    "閬垮厤鍜栧暋鍥犲拰閲嶉",
                    "淇濇寔鍗у鍑夌埥瀹夐潤"
                ]
            }
        }
        
        # 鑾峰彇鎸囧畾绫诲瀷鐨勬寚瀵?        if meditation_type not in guides:
            meditation_type = "breathing"  # 榛樿绫诲瀷
        
        guide_data = guides[meditation_type]
        
        return MeditationGuide(
            type=guide_data["name"],
            duration_minutes=duration,
            instructions=guide_data["instructions"],
            benefits=guide_data["benefits"],
            tips=guide_data["tips"]
        )
    
    def handle_sleep_analyze(self, file_path: str) -> str:
        """澶勭悊鐫＄湢鍒嗘瀽鍛戒护"""
        self._log(f"澶勭悊鐫＄湢鍒嗘瀽: {file_path}")
        
        # 鍒嗘瀽鏂囦欢
        file_analysis = self.analyze_file(file_path)
        
        if not file_analysis.exists:
            return f"[閿欒] 鏂囦欢涓嶅瓨鍦? {file_path}"
        
        if not file_analysis.is_readable:
            return f"[閿欒] 鏂囦欢涓嶅彲璇? {file_path}"
        
        # 鏍规嵁鐜鑳藉姏鎻愪緵涓嶅悓鍒嗘瀽
        if self.capability == EnvironmentCapability.BASIC:
            return self._basic_sleep_analysis(file_analysis)
        else:
            return self._advanced_sleep_analysis(file_path, file_analysis)
    
    def _basic_sleep_analysis(self, file_analysis: FileAnalysis) -> str:
        """鍩虹鐫＄湢鍒嗘瀽锛堟棤MNE锛?""
        result = [
            "=" * 60,
            "鐪犲皬鍏旂潯鐪犲垎鏋?- 鍩虹鐗堟湰",
            "=" * 60,
            f"鏂囦欢: {file_analysis.extension.upper()} 鏍煎紡",
            f"澶у皬: {file_analysis.size_mb:.2f} MB",
            f"鍙: {'鏄? if file_analysis.is_readable else '鍚?}",
            "",
            "鈿狅笍  娉ㄦ剰: 鍩虹鐗堟湰浠呮彁渚涙枃浠堕獙璇?,
            "瑕佽幏寰楀畬鏁寸殑EDF鐫＄湢鍒嗘瀽锛岃瀹夎MNE搴?",
            "  pip install mne",
            "",
            "瀹夎鍚庯紝鎮ㄥ皢鑾峰緱:",
            "  鈥?瀹屾暣鐨勭潯鐪犻樁娈靛垎鏋?,
            "  鈥?鐫＄湢璐ㄩ噺璇勫垎",
            "  鈥?璇︾粏鐨勭潯鐪犳姤鍛?,
            "  鈥?涓€у寲鏀硅繘寤鸿",
            "",
            "褰撳墠鍔熻兘:",
            "  鈥?鏂囦欢楠岃瘉鍜屽熀鏈俊鎭?,
            "  鈥?蹇冪巼鏁版嵁缁熻
