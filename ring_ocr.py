"""
ring_ocr.py — 手环睡眠截图OCR引擎

主模式：
  Mode A: EasyOCR 真实文本识别（通用，不限于华为）
  Mode B: 手动输入的已知数值（回退/验证）

EasyOCR 在华为运动健康 App 截图上自动识别：
  睡眠评分、深睡/浅睡/REM时长、心率、HRV、睡/醒时间
"""

import numpy as np
from PIL import Image
import os, json, re, io

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SLEEP_RECORD_DIR = os.path.join(PROJECT_ROOT, "sleep_record")

# EasyOCR 全局懒加载
_EASYOCR_READER = None

def _get_ocr_reader():
    global _EASYOCR_READER
    if _EASYOCR_READER is None:
        try:
            import easyocr
            _EASYOCR_READER = easyocr.Reader(['ch_sim', 'en'], gpu=False)
            print("[RingOCR] EasyOCR reader initialized (CPU mode)")
        except Exception as e:
            print(f"[RingOCR] EasyOCR init failed: {e}")
    return _EASYOCR_READER

class RingDataExtractor:
    def __init__(self):
        self._cache = {}
    
    def extract_known_values(self, date: str = None) -> dict:
        """返回从截图中手动读取的已知数值（回退/验证用）"""
        data = {
            "date": date or "2026-05-05",
            "bedtime": "23:24",
            "waketime": "06:35",
            "total_sleep_min": 431,   # 7h11m
            "awake_min": 59,
            "deep_sleep_min": 175,    # 2h55m
            "light_sleep_min": 186,   # 3h6m
            "rem_min": 51,
            "heart_rate_avg": 60,
            "heart_rate_range": "55-65",
            "sleep_score": 91,
            "hrv": None,
            "respiratory_rate": None,
            "spo2": None,
            "movement_index": None,
            "source": "manual_read_from_screenshot"
        }
        return data

    def extract_with_easyocr(self, image_input) -> dict:
        """Mode A: EasyOCR 真实文本识别（主力模式）
        
        Args:
            image_input: 图片路径(str) 或图片字节(bytes)
        
        Returns:
            dict: 结构化睡眠数据
        """
        reader = _get_ocr_reader()
        if reader is None:
            return {"status": "ocr_not_available", "source": "easyocr"}
        
        try:
            if isinstance(image_input, str):
                if not os.path.exists(image_input):
                    return {"status": "file_not_found"}
                result = reader.readtext(image_input)
            elif isinstance(image_input, bytes):
                # 从字节读取
                img = Image.open(io.BytesIO(image_input))
                # 转 numpy 再转 PIL 给 easyocr（其内部用 numpy）
                arr = np.array(img.convert('RGB'))
                result = reader.readtext(arr)
            else:
                return {"status": "invalid_input", "source": "easyocr"}
        except Exception as e:
            return {"status": "ocr_failed", "error": str(e)[:100], "source": "easyocr"}
        
        # 提取所有文本行
        texts = [item[1] for item in result]
        print(f"[RingOCR] EasyOCR extracted {len(texts)} text blocks")
        for t in texts[:30]:
            print(f"  > {t}")
        
        parsed = self._parse_ocr_texts(texts)
        parsed["source"] = "easyocr"
        parsed["status"] = "parsed"
        return parsed

    def _parse_ocr_texts(self, texts: list) -> dict:
        """从OCR文本行中提取结构化睡眠数据"""
        data = {"source": "easyocr"}
        full = " ".join(texts)
        
        # 1. 睡眠评分 — "评分N" 或 "N分"（独立词）
        score_pat = re.search(r'[^\d](\d{2,3})\s*分(?!钟)', full)
        if not score_pat:
            score_pat = re.search(r'评分[：:\s]*(\d{2,3})', full)
        if score_pat:
            data["sleep_score"] = int(score_pat.group(1))
        
        # 2. 深睡时长 (优先匹配"X小时Y分钟"完整格式)
        deep_pat = re.search(r'(?:深睡|深度睡眠).{0,10}?(\d+)\s*(?:小时|时)\s*(\d+)\s*(?:分钟|分)', full)
        if deep_pat:
            data["deep_sleep_min"] = int(deep_pat.group(1)) * 60 + int(deep_pat.group(2))
        else:
            deep_pat2 = re.search(r'(?:深睡|深度睡眠).{0,10}?(\d+)\s*分', full)
            if deep_pat2:
                data["deep_sleep_min"] = int(deep_pat2.group(1))
        
        # 3. 浅睡时长
        light_pat = re.search(r'(?:浅睡|浅度睡眠).{0,10}?(\d+)\s*(?:小时|时)\s*(\d+)\s*(?:分钟|分)', full)
        if light_pat:
            data["light_sleep_min"] = int(light_pat.group(1)) * 60 + int(light_pat.group(2))
        else:
            light_pat2 = re.search(r'(?:浅睡|浅度睡眠).{0,10}?(\d+)\s*分', full)
            if light_pat2:
                data["light_sleep_min"] = int(light_pat2.group(1))
        
        # 4. REM时长
        rem_pat = re.search(r'(?:REM|快速眼动|做梦).{0,10}?(\d+)\s*(?:小时|时)\s*(\d+)\s*(?:分钟|分)', full)
        if rem_pat:
            data["rem_min"] = int(rem_pat.group(1)) * 60 + int(rem_pat.group(2))
        else:
            rem_pat2 = re.search(r'(?:REM|快速眼动|做梦).{0,10}?(\d+)\s*分', full)
            if rem_pat2:
                data["rem_min"] = int(rem_pat2.group(1))
        
        # 5. 总睡眠时长
        total_pat = re.search(r'(?:睡眠时长|总时长|夜间睡眠).{0,10}?(\d+)\s*(?:小时|时)\s*(\d+)\s*(?:分钟|分)', full)
        if total_pat:
            data["total_sleep_min"] = int(total_pat.group(1)) * 60 + int(total_pat.group(2))
        
        # 6. 清醒次数
        awake_cnt = re.search(r'清醒次数.{0,10}?(\d+)次', full)
        if awake_cnt:
            data["awake_count"] = int(awake_cnt.group(1))
        
        # 7. 平均心率
        hr_pat = re.search(r'(?:平均心率|心率).{0,10}?(\d{2,3})\s*(?:次|bpm|次\/分)', full)
        if hr_pat:
            data["heart_rate_avg"] = int(hr_pat.group(1))
        
        # 8. HRV
        hrv_pat = re.search(r'(?:HRV|心率变异性).{0,10}?(\d{2,3})\s*(?:ms|毫秒)', full)
        if hrv_pat:
            data["hrv"] = int(hrv_pat.group(1))
        
        # 9. 血氧
        spo2_pat = re.search(r'(?:血氧|SpO2).{0,10}?(\d{2,3})\s*%', full)
        if spo2_pat:
            data["spo2"] = int(spo2_pat.group(1))
        
        # 10. 呼吸率
        resp_pat = re.search(r'(?:呼吸率|呼吸频率).{0,10}?(\d{2})\s*(?:次|bpm)', full)
        if resp_pat:
            data["respiratory_rate"] = int(resp_pat.group(1))
        
        # 11. 入睡/醒来时间
        bed_pat = re.search(r'(?:入睡|上床).{0,10}?(\d{1,2})[:\-](\d{2})', full)
        if bed_pat:
            data["bedtime"] = f"{int(bed_pat.group(1))}:{bed_pat.group(2)}"
        wake_pat = re.search(r'(?:醒来|起床).{0,10}?(\d{1,2})[:\-](\d{2})', full)
        if wake_pat:
            data["waketime"] = f"{int(wake_pat.group(1))}:{wake_pat.group(2)}"
        
        # 12. 深睡连续性
        continuity = re.search(r'深睡连续性.{0,10}?(\d{2,3})分', full)
        if continuity:
            data["deep_continuity"] = int(continuity.group(1))
        
        return data
    
    def extract_auto(self, image_path: str) -> dict:
        """纯图像处理自动提取（不依赖OCR引擎）
        
        从截图的颜色分布/像素位置提取特征
        """
        if not os.path.exists(image_path):
            return {"status": "file_not_found"}
        
        img = Image.open(image_path)
        arr = np.array(img)
        h, w = arr.shape[:2]
        
        result = {"status": "auto_extracted", "image_size": f"{w}x{h}"}
        
        # =============== 1. 顶部睡眠摘要区 (0~900px) ===============
        top = arr[:min(900, h)]
        top_gray = np.mean(top, axis=2)
        
        # 找标尺图中的色块 - 华为健康的深睡(深蓝)浅睡(浅蓝)REM(紫)区域
        # 从右侧睡眠阶段时间条提取颜色比例
        right_bar = arr[100:800, w-100:w-20]  # 右侧的阶段时间条
        
        # 定义颜色范围
        deep_blue = (right_bar[:,:,2] > 150) & (right_bar[:,:,1] < 100) & (right_bar[:,:,0] < 80)
        light_blue = (right_bar[:,:,1] > 150) & (right_bar[:,:,2] > 180) & (right_bar[:,:,0] < 100)
        purple = (right_bar[:,:,0] > 100) & (right_bar[:,:,2] > 100) & (right_bar[:,:,1] < 80)
        
        total_pixels = right_bar.shape[0] * right_bar.shape[1]
        if total_pixels > 0:
            result["_stage_blue_pct"] = float(np.mean(deep_blue))
            result["_stage_lightblue_pct"] = float(np.mean(light_blue))
            result["_stage_purple_pct"] = float(np.mean(purple))
        
        # =============== 2. 中部心率区 (900~2000px) ===============
        mid = arr[900:min(2000, h), :w//2]
        mid_gray = np.mean(mid, axis=2)
        
        # 找白色背景上的深色数值卡片
        # 心率卡片通常在左边，白色背景上有大数字
        card_rows = np.sum(mid_gray < 100, axis=1)  # 深色像素行投影
        text_line_count = int(np.sum(card_rows > 20))
        result["_text_lines_detected"] = text_line_count
        
        # =============== 3. 底部评分区 (2000~2700px) ===============
        bot = arr[2000:min(2700, h)]
        bot_gray = np.mean(bot, axis=2)
        
        # 评分大圆在中央
        center_y, center_x = bot.shape[0]//3, bot.shape[1]//2
        Y, X = np.ogrid[:bot.shape[0], :bot.shape[1]]
        circle = (X - center_x)**2 + (Y - center_y)**2 <= 80**2
        circle_brightness = np.mean(bot_gray[circle])
        result["_score_circle_brightness"] = float(circle_brightness)
        
        # 评分附近的数字区域（用亮度变化检测）
        score_region = bot_gray[center_y-50:center_y+50, center_x-80:center_x+80]
        result["_score_region_std"] = float(np.std(score_region))
        
        return result
    
    def format_for_pomdp(self, ring_data: dict = None) -> dict:
        """将手环数据格式化为POMDP观测"""
        if ring_data is None:
            ring_data = self.extract_known_values()
        
        parts = ["[手环传感器]"]
        if ring_data.get("total_sleep_min"):
            parts.append(f"睡眠{ring_data['total_sleep_min']}分钟")
        if ring_data.get("deep_sleep_min"):
            parts.append(f"深睡{ring_data['deep_sleep_min']}分钟")
        if ring_data.get("light_sleep_min"):
            parts.append(f"浅睡{ring_data['light_sleep_min']}分钟")
        if ring_data.get("rem_min"):
            parts.append(f"REM{ring_data['rem_min']}分钟")
        if ring_data.get("awake_min"):
            parts.append(f"清醒{ring_data['awake_min']}分钟")
        if ring_data.get("heart_rate_avg"):
            parts.append(f"心率{ring_data['heart_rate_avg']}bpm")
        if ring_data.get("hrv"):
            parts.append(f"HRV{ring_data['hrv']}ms")
        if ring_data.get("sleep_score"):
            parts.append(f"评分{ring_data['sleep_score']}")
        
        text = ", ".join(parts)
        
        # 计算评分调整值
        score_adj = 0
        if ring_data.get("sleep_score", 0) > 80:
            score_adj += 5
        if ring_data.get("deep_sleep_min", 0) > 120:
            score_adj += 3
        if ring_data.get("awake_min", 0) > 40:
            score_adj -= 3
        if ring_data.get("total_sleep_min", 0) > 420:
            score_adj += 2
        if ring_data.get("hrv") and ring_data["hrv"] > 30:
            score_adj += 2
        
        return {
            "text": text,
            "score_adjustment": score_adj,
            "data": ring_data
        }

def get_ring_extractor():
    return RingDataExtractor()

if __name__ == "__main__":
    ext = RingDataExtractor()
    
    # 模式A：自动提取（验证型，不依赖OCR）
    img_path = os.path.join(SLEEP_RECORD_DIR, "woman_measurement_from_ring_20260505night.jpg")
    if os.path.exists(img_path):
        auto = ext.extract_auto(img_path)
        print("Auto-extract results:")
        for k, v in auto.items():
            if k.startswith("_"):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")
    
    # 模式B：已知数值
    print("\nKnown ring data:")
    known = ext.extract_known_values()
    print(json.dumps(known, indent=2, ensure_ascii=False))
    
    # POMDP格式化
    print("\nPOMDP observation:")
    obs = ext.format_for_pomdp()
    print(f"  Text: {obs['text']}")
    print(f"  Score adjustment: {obs['score_adjustment']}")
