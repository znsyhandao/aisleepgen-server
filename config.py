#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
config.py — AISleepGen 统一配置层
所有路径/密钥/参数集中管理，消除散落硬编码。
"""
import os, json, datetime

# ============================================================
# 环境检测
# ============================================================
IS_HUAWEI_CLOUD = os.path.exists('/opt/aisleepgen/')
IS_LOCAL = not IS_HUAWEI_CLOUD

# ============================================================
# 路径（自动适应本地/云端）
# ============================================================
if IS_HUAWEI_CLOUD:
    BASE_DIR = '/opt/aisleepgen/'
    DATA_DIR = '/opt/aisleepgen/data/'
    LOG_DIR = '/opt/aisleepgen/logs/'
else:
    BASE_DIR = r'D:\AISleepGen_Optimized'
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    LOG_DIR = os.path.join(BASE_DIR, 'logs')

OUTPUT_DIR = os.path.join(BASE_DIR, 'wechat_posts')
FRONTIER_DIR = os.path.join(BASE_DIR, 'frontier_data')
BACKUP_DIR = os.path.join(BASE_DIR, '.surgical_backups')

# ============================================================
# 文件路径
# ============================================================
USER_PROFILE_FILE = os.path.join(DATA_DIR, 'user_profile.json')
USER_SURVEY_FILE = os.path.join(DATA_DIR, 'user_survey.json')
CONSENT_FILE = os.path.join(DATA_DIR, 'consent_records.json')
TOKEN_FILE = os.path.join(DATA_DIR, 'active_tokens.json')
RETRO_AUDIT_LOG = os.path.join(DATA_DIR, 'retro_audit_log.json')
FEEDBACK_DB = os.path.join(DATA_DIR, 'feedback_log.json')
AUDIT_LOG_DIR = os.path.join(DATA_DIR, 'audit_logs')
DECISION_TRACE_DIR = os.path.join(DATA_DIR, 'decision_traces')

# ============================================================
# API 密钥（从环境变量加载，兼容本地 config.json）
# ============================================================
def _load_config_json() -> dict:
    """从本地 config.json 加载配置（非华为云环境）"""
    cfg_path = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return {}

_config = _load_config_json()

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY') or _config.get('deepseek_api_key', '')
DEEPSEEK_BASE_URL = os.environ.get('DEEPSEEK_BASE_URL') or _config.get('deepseek_base_url', 'https://api.deepseek.com')

# 微信
WECHAT_APPID = os.environ.get('WECHAT_APPID') or _config.get('wechat_appid', '')
WECHAT_SECRET = os.environ.get('WECHAT_SECRET') or _config.get('wechat_secret', '')
WECHAT_API_KEY = os.environ.get('WECHAT_API_KEY') or _config.get('wechat_api_key', '')

# 邮件
SMTP_HOST = _config.get('smtp_host', '')
SMTP_PORT = _config.get('smtp_port', 465)
SMTP_USER = _config.get('smtp_user', '')
SMTP_PASS = _config.get('smtp_pass', '')

# Admin
ADMIN_KEY = os.environ.get('AISLEEPGEN_ADMIN_KEY', _config.get('admin_key', ''))

# 华为云专用
if IS_HUAWEI_CLOUD:
    HUAWEI_SKIN_PATH = '/opt/aiskinhealth/'

# ============================================================
# 模型参数
# ============================================================
DEEPSEEK_MODEL = 'deepseek-chat'
MAX_TOKENS = 4096
TEMPERATURE = 0.7

# ============================================================
# 系统常量
# ============================================================
TODAY = datetime.date.today().isoformat()
APP_VERSION = '20260601_1'

# ============================================================
# 工具函数
# ============================================================
def ensure_dirs() -> None:
    """确保所有需要的数据目录存在"""
    for d in [DATA_DIR, LOG_DIR, OUTPUT_DIR, BACKUP_DIR, AUDIT_LOG_DIR, DECISION_TRACE_DIR]:
        os.makedirs(d, exist_ok=True)

def get_today() -> str:
    """获取今天日期字符串"""
    return datetime.date.today().isoformat()
