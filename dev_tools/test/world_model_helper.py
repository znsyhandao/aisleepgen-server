#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
world_model_helper.py - 世界模型回复提取器 v1.0

统一提取世界模型结构化JSON中的可读文本。
所有测试文件共享此模块。

用法:
  from world_model_helper import extract_reply_text
"""

import json

def extract_reply_text(resp):
    """
    Extract reply text from world model JSON or natural language response.
    
    世界模型返回结构:
    {
      "arousal": {"state": "sleeping", "confidence": 0.35, ...},
      "sleep": {"phase": "wake", ...},
      "render": {"instructions": {"tempo_bpm": 6.0, "text_speed": 0.85, ...}, ...}
    }
    
    也支持传统格式: {"reply": "...", "response": "...", etc}
    """
    if not isinstance(resp, dict):
        return json.dumps(resp, ensure_ascii=False)
    
    # First try traditional reply keys
    for key in ['reply', 'response', 'message', 'content', 'text', 'analysis']:
        val = resp.get(key)
        if isinstance(val, str) and len(val.strip()) > 5:
            return val
    
    # Build readable text from world model structure
    parts = []
    
    # Arousal state
    arousal = resp.get('arousal', {})
    if isinstance(arousal, dict):
        state = arousal.get('state', '')
        conf = arousal.get('confidence', 0)
        dist = arousal.get('distribution', {})
        if state:
            parts.append(f"arousal_state={state}")
        if conf:
            parts.append(f"confidence={conf:.2f}")
        if isinstance(dist, dict):
            top_state = max(dist, key=dist.get) if dist else ''
            if top_state:
                parts.append(f"top_state={top_state}({dist[top_state]:.2f})")
    
    # Sleep metrics
    sleep = resp.get('sleep', {})
    if isinstance(sleep, dict):
        phase = sleep.get('phase', '')
        deep = sleep.get('deep_pct', 0)
        rem = sleep.get('rem_pct', 0)
        latency = sleep.get('latency_min')
        if phase:
            parts.append(f"phase={phase}")
        if deep:
            parts.append(f"deep={deep}")
        if rem:
            parts.append(f"rem={rem}")
        if latency is not None:
            parts.append(f"latency={latency}")
    
    # Physiology
    phys = resp.get('physiology', {})
    if isinstance(phys, dict):
        hr = phys.get('hr')
        hrv = phys.get('hrv')
        stress = phys.get('stress')
        if hr: parts.append(f"hr={hr}")
        if hrv: parts.append(f"hrv={hrv}")
        if stress: parts.append(f"stress={stress}")
    
    # Render instructions (the actual output text content)
    render = resp.get('render', {})
    if isinstance(render, dict):
        instructions = render.get('instructions', {})
        if isinstance(instructions, dict):
            # The instructions that drive the audio/text output
            instr_parts = []
            for k in ['tempo_bpm', 'volume_db', 'text_speed', 'silence_s', 
                     'fade_in_s', 'scene', 'mode', 'action', 'text', 'prompt', 'advice']:
                v = instructions.get(k)
                if v is not None:
                    instr_parts.append(f"{k}={v}")
            if instr_parts:
                parts.extend(instr_parts)
        
        # Audio/text content
        for field in ['narration', 'description', 'analysis', 'advice', 'assessment']:
            val = render.get(field, '')
            if isinstance(val, str) and len(val) > 10:
                parts.append(val)
    
    # Suggestions or recommendations
    for field in ['suggestions', 'recommendations', 'actions']:
        val = resp.get(field, [])
        if isinstance(val, list) and val:
            parts.append('suggestions:' + ';'.join(str(v)[:50] for v in val))
    
    # Error/status info
    error = resp.get('error', resp.get('_error', ''))
    if error:
        parts.append(f"error={error}")
    status = resp.get('status', '')
    if status:
        parts.append(f"status={status}")
    
    if parts:
        return ' | '.join(parts)
    
    return json.dumps(resp, ensure_ascii=False)
