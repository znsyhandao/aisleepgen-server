# -*- coding: utf-8 -*-
from . import SignalDetector


class Detector(SignalDetector):
    protocol = 'box_breathing'
    _kw = ['盒子', '盒式', '箱式', '方形呼吸']
    
    def detect(self, msg):
        for kw in self._kw:
            if kw in msg:
                return 0.9
        return 0.0
    
    def get_keywords(self):
        return self._kw
