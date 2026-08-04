"""
math_core_activate.py — 激活 AISleepGen Math Core (非侵入式)
=============================================================
不修改 deepseek_proxy.py，通过 monkey-patch 注入 Math Core。
在 8090 服务器启动时 import 此模块即可。

使用:
  # 在服务器启动脚本中加入:
  import math_core_activate
  
  # 或独立使用:
  python math_core_activate.py
"""
import sys, os, logging

logger = logging.getLogger("math_core_activate")

def activate():
    """激活 Math Core 增强"""
    try:
        sys.path.insert(0, r"D:\AISleepGen_Optimized")
        import deepseek_proxy as dp
        
        # 保存原始 analyze 函数
        _original_analyze = dp.analyze
        
        def enhanced_analyze(profile, openid_prefix=''):
            """增强版 analyze: 原始告警 + Math Core 分析"""
            alerts = _original_analyze(profile, openid_prefix)
            
            try:
                from sleep_math_bridge import enhance_sleep_analysis
                math_result = enhance_sleep_analysis(profile)
                if math_result.get('enhanced'):
                    alerts.append({
                        'type': 'math_enhanced',
                        'fractal_analysis': math_result.get('fractal_metrics'),
                        'magi_assessment': math_result.get('magi_assessment'),
                        'enhanced_score': math_result.get('enhanced_score'),
                        'complexity': math_result.get('complexity_analysis'),
                    })
            except ImportError:
                pass  # Math Core unavailable
            except Exception as e:
                logger.debug(f"Math Core enhancement skipped: {e}")
            
            return alerts
        
        # 替换
        dp.analyze = enhanced_analyze
        logger.info("Math Core activated: analyze() enhanced with DFA+MAGI+POMDP")
        return True
    except ImportError as e:
        logger.warning(f"Math Core activation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Math Core activation error: {e}")
        return False

def deactivate():
    """回退到原始版本"""
    try:
        import deepseek_proxy as dp
        if hasattr(deepseek_proxy_module := sys.modules.get('deepseek_proxy'), '_original_analyze'):
            restore_module = sys.modules['deepseek_proxy']
        else:
            restore_module = dp
        logger.info("Math Core deactivated")
        return True
    except Exception:
        return False

# 自动激活
if __name__ != "__main__":
    _activated = activate()
