"""
MAGI Client — Lightweight AISleepGen integration with M.A.G.I. Cluster

Deploy: copy this file alongside deepseek_proxy.py
Usage:
  from magi_client import magi_analyze
  result = magi_analyze(signal, query="sleep EEG")
  # Returns dict with fractal analysis, or None if MAGI is down

Zero dependencies beyond stdlib. Graceful degradation: if MAGI API
is unreachable, returns None without crashing.
"""
import json, time, urllib.request, urllib.error
from typing import Optional, Dict, List, Union

# MAGI API endpoint (Tencent Cloud: 82.156.208.245:8765)
# For same-server deployment, change to http://localhost:8765
MAGI_URL = 'http://82.156.208.245:8765'
TIMEOUT = 5  # seconds — fail fast, don't block user

def magi_analyze(signal: List[float], query: str = "sleep EEG analysis",
                 fs: float = 100.0) -> Optional[Dict]:
    """
    Send signal to MAGI cluster for fractal/stochastic analysis.
    
    Returns:
        Dict with analysis results, or None if MAGI is unreachable.
        Fields: fractal.hurst, fractal.complexity_index, stochastic.n_regimes,
                counterexample.h_constant_hypothesis, coordinator.confidence
    """
    if len(signal) < 100:
        # Pad short signals (e.g., weekly sleep scores) by linear repeat
        factor = 100 // len(signal) + 1
        signal = signal * factor
        signal = signal[:100]  # Trim to exactly 100
    
    data = json.dumps({'signal': signal, 'query': query, 'fs': fs}).encode()
    req = urllib.request.Request(f'{MAGI_URL}/analyze', data=data,
                                   headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=TIMEOUT)
        return json.loads(resp.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception):
        return None  # Graceful degradation

def magi_to_sleep_report(magi_result: Dict) -> str:
    """
    Convert MAGI analysis to a human-readable sleep report section.
    Returns formatted text ready to insert into the AI-generated report.
    """
    if not magi_result:
        return ""
    
    lines = ["\n## Fractal Analysis (MAGI Cluster)"]
    
    fractal = magi_result.get('fractal', {})
    h = fractal.get('hurst', 0.5)
    ci = fractal.get('complexity_index', 0)
    ptype = fractal.get('process_type', 'unknown')
    
    lines.append(f"- Hurst Exponent: H = {h:.3f}")
    if h > 0.80:
        lines.append("  Signal shows strong persistence — deep sleep patterns are consistent.")
    elif h > 0.65:
        lines.append("  Moderate persistence — sleep architecture is reasonably stable.")
    elif h > 0.50:
        lines.append("  Weak persistence — frequent transitions between sleep stages.")
    else:
        lines.append("  Anti-persistent — sleep pattern oscillates rapidly (possible arousal).")
    
    lines.append(f"- Signal Complexity: {ci:.1%}")
    if ci < 0.4:
        lines.append("  Low complexity — sleep signal is regular and well-structured.")
    elif ci < 0.6:
        lines.append("  Medium complexity — natural sleep with expected variability.")
    else:
        lines.append("  High complexity — fragmented or irregular sleep architecture.")
    
    stochastic = magi_result.get('stochastic', {})
    n_regimes = stochastic.get('n_regimes', 0)
    if n_regimes > 0:
        lines.append(f"- Detected {n_regimes} sleep regime transition(s)")
    
    counterexample = magi_result.get('counterexample', {})
    h_constant = counterexample.get('h_constant_hypothesis', '?')
    lines.append(f"- Fractal stability hypothesis: {h_constant}")
    
    return '\n'.join(lines) + '\n'
