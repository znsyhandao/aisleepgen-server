# -*- coding: utf-8 -*-
from . import SignalDetector

_4_7_8_KEYWORDS = ['做', '开始', '引导', '练习', '怎么', '教我', '带我做', '做一下', '带带我', '来一下', '来一个', '做做']
_4_7_8_SPECIFIC = ['4-7-8', '478', '四七八', '放松练习']
_4_7_8_HARDCODE = ['放松']  # 通用放松词，低分


class Detector(SignalDetector):
    protocol = '4-7-8'
    
    def detect(self, msg):
        for kw in _4_7_8_SPECIFIC:
            if kw in msg:
                return 0.9
        for kw in _4_7_8_HARDCODE:
            if kw in msg:
                return 0.4
        for kw in _4_7_8_KEYWORDS:
            if kw in msg:
                return 0.3
        return 0.0
    
    def get_keywords(self):
        return _4_7_8_SPECIFIC + _4_7_8_HARDCODE + _4_7_8_KEYWORDS
