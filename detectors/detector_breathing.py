# -*- coding: utf-8 -*-
from . import SignalDetector


class Detector(SignalDetector):
    protocol = 'breathing'
    _kw = ['呼吸', '正念', '深呼吸']
    _fallback = ['做', '放松']  # 跟4-7-8重叠，但4-7-8先注册就优先
    
    def detect(self, msg):
        for kw in self._kw:
            if kw in msg:
                return 0.85
        return 0.0
    
    def get_keywords(self):
        return self._kw
