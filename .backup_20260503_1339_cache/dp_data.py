#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dp_data.py — AISleepGen 数据层入口
纯 re-export，所有实际功能在各个独立模块中。
"""
import os, sys as _sys
from datetime import datetime as _dt

_sys.path = [p for p in _sys.path if 'openclaw' not in p.lower()]
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['AISLEEPGEN_SKIP_MAIN'] = '1'

# 从各模块 re-export 所有符号
from profile_storage import (
    _get_default_profile, _load_all_profiles, _save_all_profiles,
    _backup_profile, _recover_from_backup,
    _load_user_profile, _save_user_profile, _atomic_write_profile,
    _update_user_profile, _safe_update_profile,
    _log_intervention, _handle_intervention_complete,
    _extract_features, _run_daily_batch_optimization,
    _store_feedback,
    USER_PROFILE_PATH, PROJECT_ROOT,
)
from self_learn import (
    _load_calibration, _save_calibration, _trigger_self_learn, _meta_update,
)
from ai_client import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
    load_deepseek_key, call_deepseek_api,
    get_world_model_analysis,
    _get_world_model, classify_scene, vertical_comparison,
    _HAS_DEEP_MODULE, _pref_engine, _world_model_instance,
)
from trend_layer import (
    _extract_trends, _build_history_context,
)
