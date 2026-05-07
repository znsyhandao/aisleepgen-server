# -*- coding: utf-8 -*-
from . import SignalDetector

# All 12 remaining detectors (one-liner each)
_CONFIGS = [
    ('pursed_lip', ['缩唇']),
    ('autogenic', ['自律', '暗示', '沉重', '温暖']),
    ('safe_place', ['安全岛', '安全的地方', '安全']),
    ('cloud_float', ['云端', '漂浮', '云']),
    ('sound_bath', ['声音浴', '颂钵', '大提琴', '声音']),
    ('cognitive_unloading', ['担忧', '担心', '写下', '卸荷', '认知卸荷', '写下来']),
    ('paradoxical_intention', ['矛盾', '清醒', '努力', '睁眼', '保持清醒']),
    ('stimulus_control', ['刺激控制', '睡不着就起来', '20分钟规则']),
    ('sleep_hygiene', ['卫生', '检查', '清单', '环境', '睡前准备', '习惯']),
    ('cognitive_restructuring', ['认知', '信念', '挑战', '想法', '灾难化', '重构']),
    ('body_scan', ['身体扫描', '扫描']),
    ('pmr', ['肌肉', 'pmr', '渐进']),
]

for _proto, _kw in _CONFIGS:
    _locals = {}
    exec(f'''class Detector(SignalDetector):
    protocol = '{_proto}'
    _kw = {_kw!r}
    def detect(self, msg):
        for kw in self._kw:
            if kw in msg:
                return 0.85
        return 0.0
    def get_keywords(self):
        return self._kw
''', globals(), _locals)
    _cls = _locals['Detector']
    _cls.__name__ = f'Detector_{_proto}'
    _cls.__module__ = __name__
    globals()[f'Detector_{_proto}'] = _cls
    del _cls, _locals

del _CONFIGS, _proto, _kw
