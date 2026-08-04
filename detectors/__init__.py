# -*- coding: utf-8 -*-
"""Signal detector package.
每个检测器独立存活，按注册顺序竞争。置信度高的胜出。"""
from .base import SignalDetector, detect_intent

# Import all detector classes
from .detector_4_7_8 import Detector as _d_478
from .detector_box import Detector as _d_box
from .detector_breathing import Detector as _d_breathing
from .detector_others import (
    Detector_pursed_lip,
    Detector_autogenic,
    Detector_safe_place,
    Detector_cloud_float,
    Detector_sound_bath,
    Detector_cognitive_unloading,
    Detector_paradoxical_intention,
    Detector_stimulus_control,
    Detector_sleep_hygiene,
    Detector_cognitive_restructuring,
    Detector_body_scan,
    Detector_pmr,
)

# Registration order = competition priority
# More specific detectors first, generic ones last
ALL_DETECTORS = [
    # 呼吸类（高特异性）
    _d_box(),
    _d_breathing(),
    _d_478(),
    # 专有场景
    Detector_pursed_lip(),
    Detector_autogenic(),
    Detector_body_scan(),
    Detector_pmr(),
    # 意象类
    Detector_safe_place(),
    Detector_cloud_float(),
    Detector_sound_bath(),
    # 认知行为类
    Detector_cognitive_unloading(),
    Detector_paradoxical_intention(),
    Detector_stimulus_control(),
    Detector_sleep_hygiene(),
    Detector_cognitive_restructuring(),
]

__all__ = ['SignalDetector', 'detect_intent', 'ALL_DETECTORS']
