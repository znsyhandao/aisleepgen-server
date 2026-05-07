# -*- coding: utf-8 -*-
"""Base class for all signal detectors."""


class SignalDetector:
    """Base detector with score-based competition."""
    
    protocol = None  # 子类重写
    
    def detect(self, message):
        """Return confidence 0.0-1.0 based on message matching."""
        return 0.0
    
    def get_keywords(self):
        """Return list of keywords for logging."""
        return []


def detect_intent(message, detectors=None):
    """Run all registered detectors, return winner by confidence.
    
    Returns:
        (protocol_name, confidence, matched_keywords)
    """
    if detectors is None:
        from . import ALL_DETECTORS
        detectors = ALL_DETECTORS
    
    best_protocol = None
    best_confidence = 0.0
    best_kw = []
    
    for d in detectors:
        conf = d.detect(message)
        if conf > best_confidence:
            best_confidence = conf
            best_protocol = d.protocol
            best_kw = d.get_keywords()
    
    return best_protocol, best_confidence, best_kw
