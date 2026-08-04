#!/usr/bin/env python3
"""
meditation_content.py — 眠小兔原创冥想内容库
后端数据层：按系列/集数返回冥想文案
"""
import json, os

# ===== 系列索引 =====
SERIES_INDEX = {
    "art": {
        "name": "🎨 艺术冥想系列",
        "description": "以经典艺术创作为载体，通过视觉感知引导深度冥想",
        "items": [
            {"id": "art_01", "title": "空间艺术冥想", "duration": 900},
            {"id": "art_02", "title": "印象当下冥想", "duration": 900},
            {"id": "art_03", "title": "去符号化冥想", "duration": 720},
            {"id": "art_04", "title": "滴画冥想", "duration": 900},
            {"id": "art_05", "title": "帕瓦罗蒂·人的探索冥想", "duration": 1080},
            {"id": "art_06", "title": "抽象表现冥想", "duration": 900},
        ]
    },
    "ni_zan": {
        "name": "🖌️ 倪瓒画作感悟系列",
        "description": "从元代画家倪瓒的画作中感悟宁静与无常",
        "items": [
            {"id": "niz_01", "title": "培养内心的宁静冥想", "duration": 900},
            {"id": "niz_02", "title": "拥抱无常冥想", "duration": 900},
        ]
    },
    "plant": {
        "name": "🌿 植物冥想系列",
        "description": "借植物隐喻，引导内在力量的觉察与生长",
        "items": [
            {"id": "pl_01", "title": "植物生命力冥想", "duration": 900},
            {"id": "pl_02", "title": "松树慎独适应力冥想", "duration": 900},
            {"id": "pl_03", "title": "迷迭香安神冥想", "duration": 720},
            {"id": "pl_04", "title": "雪松掌控力冥想", "duration": 900},
            {"id": "pl_05", "title": "鸢尾信念冥想", "duration": 720},
            {"id": "pl_06", "title": "香荚兰沁人心脾冥想", "duration": 720},
            {"id": "pl_07", "title": "三色堇思绪冥想", "duration": 720},
            {"id": "pl_08", "title": "紫罗兰谦逊温柔冥想", "duration": 720},
            {"id": "pl_09", "title": "莲花净世冥想", "duration": 900},
            {"id": "pl_10", "title": "车前草修复创伤冥想", "duration": 900},
            {"id": "pl_11", "title": "艾草解毒冥想", "duration": 720},
            {"id": "pl_12", "title": "洋甘菊减压安神冥想", "duration": 720},
            {"id": "pl_13", "title": "西番莲镇静冥想", "duration": 720},
            {"id": "pl_14", "title": "薄荷清神醒脑冥想", "duration": 600},
            {"id": "pl_15", "title": "玫瑰美好抗压冥想", "duration": 900},
            {"id": "pl_16", "title": "芸香恩典降临辟邪冥想", "duration": 720},
        ]
    },
    "cognitive": {
        "name": "🧠 认知冥想系列",
        "description": "哲学思辨引导，破除认知偏差",
        "items": [
            {"id": "cog_01", "title": "空的冥想（上）", "duration": 1200},
            {"id": "cog_02", "title": "空的冥想（下）", "duration": 1200},
        ]
    },
    "story": {
        "name": "📖 故事治愈冥想系列",
        "description": "用真实故事包裹疗愈引导",
        "items": [
            {"id": "st_01", "title": "和西安美院学生做邻居（上集）", "duration": 900},
            {"id": "st_02", "title": "和西安美院学生做邻居（中集）", "duration": 900},
            {"id": "st_03", "title": "和西安美院学生做邻居（下集）", "duration": 900},
        ]
    },
    "walk": {
        "name": "🚶 行走冥想系列",
        "description": "在场景中行走，在行走中冥想",
        "items": [
            {"id": "wk_01", "title": "湖边行走冥想", "duration": 900},
            {"id": "wk_02", "title": "山中行走冥想", "duration": 900},
            {"id": "wk_03", "title": "桥上行走冥想", "duration": 720},
            {"id": "wk_04", "title": "公园行走冥想", "duration": 900},
            {"id": "wk_05", "title": "故宫行走冥想", "duration": 1200},
            {"id": "wk_06", "title": "北京胡同行走冥想", "duration": 1200},
            {"id": "wk_07", "title": "书店行走冥想", "duration": 900},
            {"id": "wk_08", "title": "雨后初晴的秦岭行走冥想", "duration": 1200},
        ]
    },
    "ocean": {
        "name": "🌊 海洋冥想系列",
        "description": "以水为媒，引导深层放松",
        "items": [
            {"id": "oc_01", "title": "水的形象化冥想", "duration": 900},
            {"id": "oc_02", "title": "海浪之声冥想", "duration": 900},
        ]
    },
    "color_breath": {
        "name": "🌈 色彩呼吸冥想系列",
        "description": "借助色彩想象，引导呼吸调节",
        "items": [
            {"id": "cb_01", "title": "星期五蓝色冥想", "duration": 720},
        ]
    },
    "tea": {
        "name": "🍵 午茶冥想系列",
        "description": "茶香中的正念冥想",
        "items": [
            {"id": "tea_01", "title": "周末早茶冥想", "duration": 900},
            {"id": "tea_02", "title": "周末下午茶冥想", "duration": 900},
        ]
    },
    "present": {
        "name": "⏳ 活在当下三部曲冥想系列",
        "description": "深度沉浸于当下的力量",
        "items": [
            {"id": "pr_01", "title": "深度沉浸当下冥想", "duration": 900},
            {"id": "pr_02", "title": "避开未来陷阱活在当下冥想", "duration": 900},
        ]
    },
    "anxiety": {
        "name": "😰 焦虑消解冥想系列",
        "description": "针对不同焦虑源的专业消解方案",
        "items": [
            {"id": "ax_01", "title": "反洗脑成功学冥想", "duration": 1200},
            {"id": "ax_02", "title": "反洗脑成功学冥想第二集", "duration": 1200},
            {"id": "ax_03", "title": "缓解职业焦虑梯度冥想", "duration": 1080},
            {"id": "ax_04", "title": "缓解孤独冥想", "duration": 900},
            {"id": "ax_05", "title": "焦虑消解冥想第十三集", "duration": 900},
            {"id": "ax_06", "title": "缓解人工智能带来的焦虑的冥想", "duration": 1200},
            {"id": "ax_07", "title": "觉知力与平等心冥想", "duration": 900},
            {"id": "ax_08", "title": "焦虑消解冥想第一集", "duration": 900},
            {"id": "ax_09", "title": "焦虑消解冥想第二集", "duration": 900},
            {"id": "ax_10", "title": "焦虑消解冥想第三集", "duration": 900},
            {"id": "ax_11", "title": "焦虑消解冥想第五集", "duration": 900},
            {"id": "ax_12", "title": "焦虑消解冥想第十四集", "duration": 900},
            {"id": "ax_13", "title": "缓解恐慌冥想", "duration": 900},
            {"id": "ax_14", "title": "缓解家长暴躁冥想", "duration": 900},
            {"id": "ax_15", "title": "普通也很快乐冥想", "duration": 720},
            {"id": "ax_16", "title": "联结内在权威冥想", "duration": 900},
            {"id": "ax_17", "title": "消解负罪感冥想", "duration": 900},
        ]
    },
    "skill": {
        "name": "💡 软能力提升冥想系列",
        "description": "冥想不只是放松，更是训练洞察力与分辨力",
        "items": [
            {"id": "sk_01", "title": "休止巡航提升洞察力冥想", "duration": 900},
            {"id": "sk_02", "title": "学习艺术提升洞察力冥想第二集", "duration": 900},
            {"id": "sk_03", "title": "建构工具箱提升洞察力冥想第一集", "duration": 900},
            {"id": "sk_04", "title": "建构工具箱提升洞察力冥想第二集", "duration": 900},
            {"id": "sk_05", "title": "建构工具箱提升洞察力冥想第三集", "duration": 900},
            {"id": "sk_06", "title": "建构工具箱提升洞察力冥想第四集", "duration": 900},
            {"id": "sk_07", "title": "建构工具箱提升洞察力冥想第五集", "duration": 900},
            {"id": "sk_08", "title": "建构工具箱提升洞察力冥想第六集", "duration": 900},
            {"id": "sk_09", "title": "建构工具箱提升洞察力冥想第七集", "duration": 900},
            {"id": "sk_10", "title": "破解软瘾冥想", "duration": 1080},
            {"id": "sk_11", "title": "移除感知过滤器提升洞察力冥想", "duration": 900},
            {"id": "sk_12", "title": "提升分辨力冥想", "duration": 900},
            {"id": "sk_13", "title": "观察训练提升洞察力冥想", "duration": 900},
        ]
    },
    "energy": {
        "name": "⚡ 能量冥想系列",
        "description": "唤醒内在能量，摆脱倦怠",
        "items": [
            {"id": "en_01", "title": "动力提升冥想", "duration": 900},
            {"id": "en_02", "title": "挖掘能量情绪之泉冥想", "duration": 900},
            {"id": "en_03", "title": "补充能量冥想第一集", "duration": 900},
            {"id": "en_04", "title": "补充能量冥想第二集", "duration": 900},
        ]
    },
    "tension": {
        "name": "😌 缓解紧张冥想系列",
        "description": "快速释放身体和精神的紧张",
        "items": [
            {"id": "ts_01", "title": "自律放松冥想", "duration": 720},
            {"id": "ts_02", "title": "真如呼吸冥想", "duration": 720},
        ]
    },
    "positive": {
        "name": "🌟 积极冥想系列",
        "description": "积极心理引导",
        "items": [
            {"id": "po_01", "title": "改变的力量冥想", "duration": 900},
        ]
    },
    "zen": {
        "name": "☯️ 禅宗冥想系列",
        "description": "源自禅宗的止观修行",
        "items": [
            {"id": "zn_01", "title": "拴住那猴子冥想", "duration": 900},
            {"id": "zn_02", "title": "止心猿意马冥想", "duration": 900},
            {"id": "zn_03", "title": "静坐调和功夫冥想", "duration": 1200},
        ]
    },
    "special": {
        "name": "🔮 特殊功能冥想系列",
        "description": "针对性解决特定问题",
        "items": [
            {"id": "sp_01", "title": "抗疲劳冥想", "duration": 900},
            {"id": "sp_02", "title": "潜意识治愈冥想", "duration": 1200},
            {"id": "sp_03", "title": "脑内啡指数冥想", "duration": 720},
        ]
    },
    "happiness": {
        "name": "🌼 破除幸福执念冥想系列",
        "description": "跳出幸福陷阱，回归本真",
        "items": [
            {"id": "hp_01", "title": "工作幸福冥想", "duration": 900},
            {"id": "hp_02", "title": "跳出幸福陷阱冥想", "duration": 900},
            {"id": "hp_03", "title": "呼吸联结冥想", "duration": 720},
            {"id": "hp_04", "title": "提升抗压能力冥想第一集", "duration": 900},
            {"id": "hp_05", "title": "提升抗压能力冥想第二集", "duration": 900},
            {"id": "hp_06", "title": "解离大法冥想", "duration": 900},
            {"id": "hp_07", "title": "自我富足冥想", "duration": 720},
            {"id": "hp_08", "title": "降低沮丧杀伤力冥想", "duration": 900},
        ]
    },
    "classic": {
        "name": "📜 经典冥想系列",
        "description": "传承自东西方冥想传统的经典技法",
        "items": [
            {"id": "cl_01", "title": "内观之metta冥想", "duration": 1200},
            {"id": "cl_02", "title": "咒语冥想", "duration": 900},
            {"id": "cl_03", "title": "安全岛冥想", "duration": 720},
            {"id": "cl_04", "title": "开放式监控冥想", "duration": 900},
            {"id": "cl_05", "title": "引导能量冥想", "duration": 900},
            {"id": "cl_06", "title": "想象正能量冥想", "duration": 720},
            {"id": "cl_07", "title": "身体意识冥想", "duration": 720},
            {"id": "cl_08", "title": "道教冥想", "duration": 1080},
            {"id": "cl_09", "title": "释放负能量冥想", "duration": 720},
        ]
    },
    "sleep": {
        "name": "💤 助眠冥想系列",
        "description": "专项解决入睡困难的冥想全集",
        "items": [
            {"id": "sl_01", "title": "云隐喻冥想", "duration": 900},
            {"id": "sl_02", "title": "释放愤怒冥想", "duration": 900},
            {"id": "sl_03", "title": "睡眠焦虑消解冥想", "duration": 1200},
            {"id": "sl_04", "title": "消解孤独冥想", "duration": 900},
            {"id": "sl_05", "title": "自生冥想", "duration": 720},
            {"id": "sl_06", "title": "海绵冥想", "duration": 720},
            {"id": "sl_07", "title": "放松身心冥想", "duration": 720},
            {"id": "sl_08", "title": "漂浮冥想", "duration": 720},
            {"id": "sl_09", "title": "消除无望冥想", "duration": 900},
            {"id": "sl_10", "title": "创造意象冥想", "duration": 900},
            {"id": "sl_11", "title": "缓解强迫症冥想", "duration": 1080},
            {"id": "sl_12", "title": "缓解压力和愈合冥想", "duration": 900},
            {"id": "sl_13", "title": "冲突解决放松冥想", "duration": 900},
            {"id": "sl_14", "title": "缓解PTSD冥想", "duration": 1200},
            {"id": "sl_15", "title": "沉入梦乡冥想", "duration": 900},
            {"id": "sl_16", "title": "情绪麻木修复冥想", "duration": 900},
            {"id": "sl_17", "title": "可视化冥想", "duration": 900},
            {"id": "sl_18", "title": "深度睡眠冥想", "duration": 1200},
            {"id": "sl_19", "title": "数数冥想", "duration": 600},
            {"id": "sl_20", "title": "向下移动的冥想", "duration": 720},
            {"id": "sl_21", "title": "神经语言学程序的冥想", "duration": 900},
            {"id": "sl_22", "title": "叹气式的深呼吸冥想", "duration": 600},
            {"id": "sl_23", "title": "生物反馈方法的冥想", "duration": 900},
            {"id": "sl_24", "title": "内心的平静冥想", "duration": 720},
            {"id": "sl_25", "title": "舒缓胃部焦虑冥想", "duration": 720},
        ]
    },
    "cockpit": {
        "name": "🚗 智能座舱专用冥想系列",
        "description": "驾驶场景下的专业心理辅助",
        "items": [
            {"id": "cp_01", "title": "专注力提升冥想", "duration": 600},
            {"id": "cp_02", "title": "克服不安冥想", "duration": 600},
            {"id": "cp_03", "title": "心亡为忙冥想", "duration": 600},
            {"id": "cp_04", "title": "生生不息冥想", "duration": 600},
            {"id": "cp_05", "title": "脱敏冥想第一集", "duration": 720},
            {"id": "cp_06", "title": "脱敏冥想第二集", "duration": 720},
            {"id": "cp_07", "title": "脱敏冥想第三集", "duration": 720},
            {"id": "cp_08", "title": "驾驶预处理冥想", "duration": 600},
            {"id": "cp_09", "title": "路怒消解冥想", "duration": 600},
            {"id": "cp_10", "title": "轻松状态冥想", "duration": 600},
            {"id": "cp_11", "title": "音乐精神减压放松冥想第一集", "duration": 900},
            {"id": "cp_12", "title": "音乐精神减压放松冥想第二集", "duration": 900},
        ]
    },
    "immune": {
        "name": "🛡️ 免疫冥想系列",
        "description": "通过意念引导增强免疫功能",
        "items": [
            {"id": "im_01", "title": "增强免疫冥想", "duration": 900},
            {"id": "im_02", "title": "激活免疫意象冥想", "duration": 900},
            {"id": "im_03", "title": "词典想象法免疫冥想", "duration": 900},
        ]
    },
    "slow": {
        "name": "🐌 慢冥想系列",
        "description": "在快时代中，训练「慢」的觉察力",
        "items": [
            {"id": "sw_01", "title": "心灵之旅冥想", "duration": 900},
            {"id": "sw_02", "title": "创建慢发现之眼冥想第一集", "duration": 900},
            {"id": "sw_03", "title": "创建慢发现之眼冥想第二集", "duration": 900},
            {"id": "sw_04", "title": "创建慢发现之眼冥想第三集", "duration": 900},
            {"id": "sw_05", "title": "创建慢发现之眼冥想第四集", "duration": 900},
        ]
    },
    "focus": {
        "name": "🎯 提升专注力冥想系列",
        "description": "吐纳与专注力训练",
        "items": [
            {"id": "fc_01", "title": "吐纳提升专注力冥想", "duration": 720},
        ]
    },
    "new_concept": {
        "name": "🌀 新概念冥想系列",
        "description": "用「三」「反」「流」「感」「隐」等抽象概念重塑冥想体验",
        "items": [
            {"id": "nc_01", "title": "三冥想", "duration": 720},
            {"id": "nc_02", "title": "偶联冥想", "duration": 720},
            {"id": "nc_03", "title": "反冥想", "duration": 720},
            {"id": "nc_04", "title": "纤维冥想", "duration": 720},
            {"id": "nc_05", "title": "抚概念空间冥想", "duration": 900},
            {"id": "nc_06", "title": "感冥想", "duration": 720},
            {"id": "nc_07", "title": "流冥想", "duration": 720},
            {"id": "nc_08", "title": "肤概念空间冥想", "duration": 900},
            {"id": "nc_09", "title": "间概念空间冥想", "duration": 900},
            {"id": "nc_10", "title": "隐概念空间冥想", "duration": 900},
            {"id": "nc_11", "title": "超冥想", "duration": 720},
        ]
    },
    "sutra": {
        "name": "📿 佛经冥想系列",
        "description": "以经典佛经为引的深度冥想",
        "items": [
            {"id": "su_01", "title": "心经冥想系列", "duration": 1200},
            {"id": "su_02", "title": "道德经冥想", "duration": 1200},
            {"id": "su_03", "title": "金刚经冥想系列", "duration": 1200},
            {"id": "su_04", "title": "佛说入胎经冥想·胚芽源起冥想", "duration": 900},
        ]
    },
}

# ===== 系列标签（用于手环数据推荐）=====
SERIES_TAGS = {
    "sleep": ["助眠冥想系列", "活在当下三部曲冥想系列", "海洋冥想系列", "经典冥想系列"],
    "anxiety": ["焦虑消解冥想系列", "破除幸福执念冥想系列", "缓解紧张冥想系列"],
    "focus": ["提升专注力冥想系列", "软能力提升冥想系列", "认知冥想系列"],
    "energy": ["能量冥想系列", "积极冥想系列", "特殊功能冥想系列"],
    "stress": ["焦虑消解冥想系列", "智能座舱专用冥想系列", "缓解紧张冥想系列", "午茶冥想系列"],
    "immune": ["免疫冥想系列"],
    "general": ["艺术冥想系列", "植物冥想系列", "故事治愈冥想系列", "行走冥想系列",
                 "倪瓒画作感悟系列", "禅宗冥想系列", "新概念冥想系列", "慢冥想系列",
                 "佛经冥想系列", "色彩呼吸冥想系列"],
}

# ===== 场景背景音映射 =====
SERIES_AMBIENT = {
    "艺术冥想系列": "ambient_classical",
    "倪瓒画作感悟系列": "ambient_guqin",
    "植物冥想系列": "ambient_forest",
    "认知冥想系列": "ambient_silence",
    "故事治愈冥想系列": "ambient_tea",
    "行走冥想系列": "ambient_wind",
    "海洋冥想系列": "ambient_ocean",
    "色彩呼吸冥想系列": "ambient_rainbow",
    "午茶冥想系列": "ambient_tea",
    "活在当下三部曲冥想系列": "ambient_calm",
    "焦虑消解冥想系列": "ambient_rain",
    "软能力提升冥想系列": "ambient_classical",
    "能量冥想系列": "ambient_sunrise",
    "缓解紧张冥想系列": "ambient_calm",
    "积极冥想系列": "ambient_sunrise",
    "禅宗冥想系列": "ambient_guqin",
    "特殊功能冥想系列": "ambient_calm",
    "破除幸福执念冥想系列": "ambient_wind",
    "经典冥想系列": "ambient_silence",
    "助眠冥想系列": "ambient_night",
    "智能座舱专用冥想系列": "ambient_drive",
    "免疫冥想系列": "ambient_forest",
    "慢冥想系列": "ambient_calm",
    "提升专注力冥想系列": "ambient_water",
    "新概念冥想系列": "ambient_space",
    "佛经冥想系列": "ambient_guqin",
}

# ===== 环境音描述 =====
AMBIENT_DESCRIPTIONS = {
    "ambient_ocean": {"name": "🌊 海浪", "desc": "舒缓的海浪拍岸声", "prompt": "柔和的海浪声，有节奏地拍打着沙滩，偶尔有海鸥鸣叫"},
    "ambient_rain": {"name": "☔ 雨声", "desc": "细雨落在树叶上的白噪音", "prompt": "持续的细雨声，轻柔地落在树叶和地面上，远处有隐约的雷声"},
    "ambient_forest": {"name": "🌲 森林", "desc": "鸟鸣与微风穿过树林", "prompt": "清晨的森林，微风穿过树叶，远处有鸟鸣和溪流声"},
    "ambient_night": {"name": "🌙 夜晚", "desc": "夏夜的虫鸣与微风", "prompt": "宁静的夏夜，蟋蟀和青蛙的叫声，偶有微风拂过"},
    "ambient_fire": {"name": "🔥 篝火", "desc": "木柴燃烧的噼啪声", "prompt": "温暖的篝火，木柴燃烧的噼啪声，火苗跳跃的微弱声响"},
    "ambient_wind": {"name": "🍃 微风", "desc": "轻柔的风穿过山谷", "prompt": "持续而轻柔的风声，穿过山谷和林间"},
    "ambient_water": {"name": "💧 溪流", "desc": "山涧溪流的潺潺声", "prompt": "清澈的山涧溪流，水流撞击石头的潺潺声"},
    "ambient_calm": {"name": "🧘 宁静", "desc": "纯粹安静的背景", "prompt": "极低频率的白噪音，几乎无声，只有最微弱的空气振动"},
    "ambient_silence": {"name": "🤫 静默", "desc": "完全的静谧", "prompt": "完全的安静，只有最细微的呼吸声"},
    "ambient_tea": {"name": "🍵 茶室", "desc": "茶室的安静氛围", "prompt": "安静的茶室氛围，偶有茶壶水沸的咕嘟声"},
    "ambient_guqin": {"name": "🎵 古琴", "desc": "中国古琴的悠远琴音", "prompt": "遥远的古琴声，单音悠长，在空间中回荡"},
    "ambient_classical": {"name": "🎻 轻古典", "desc": "低音量钢琴背景", "prompt": "轻柔的古典钢琴，音量极低，几乎是氛围音乐"},
    "ambient_sunrise": {"name": "🌅 日出", "desc": "清晨的第一缕阳光", "prompt": "清晨的氛围，鸟鸣渐起，阳光温暖，万物复苏"},
    "ambient_drive": {"name": "🚗 车内", "desc": "车内空调的平稳风声", "prompt": "车内空调的平稳风声，引擎低沉的嗡嗡声"},
    "ambient_rainbow": {"name": "🌈 色彩", "desc": "柔和的色彩氛围", "prompt": "柔和的氛围音，像色彩在空气中流动"},
    "ambient_space": {"name": "🌌 太空", "desc": "深邃的太空氛围", "prompt": "深邃而空旷的氛围音，低频持续，像在太空中漂浮"},
}

def get_series_list():
    """获取所有系列列表"""
    result = []
    for key, val in SERIES_INDEX.items():
        result.append({
            "id": key,
            "name": val["name"],
            "description": val["description"],
            "count": len(val["items"]),
            "ambient": SERIES_AMBIENT.get(val["name"], "ambient_calm"),
        })
    return result

def get_series_items(series_id):
    """获取某个系列的所有冥想"""
    series = SERIES_INDEX.get(series_id)
    if not series:
        return None
    ambient_key = SERIES_AMBIENT.get(series["name"], "ambient_calm")
    ambient = AMBIENT_DESCRIPTIONS.get(ambient_key, {})
    return {
        "series": series,
        "ambient": ambient,
        "items": series["items"],
    }

def get_recommendation_by_mood(mood):
    """根据情绪推荐系列"""
    tags = SERIES_TAGS.get(mood, ["general"])
    result = []
    for tag in tags:
        for key, val in SERIES_INDEX.items():
            if val["name"] == tag:
                result.append({
                    "id": key,
                    "name": val["name"],
                    "count": len(val["items"]),
                    "ambient": SERIES_AMBIENT.get(val["name"], "ambient_calm"),
                })
    return result
