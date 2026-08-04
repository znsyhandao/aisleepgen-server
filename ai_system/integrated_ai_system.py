#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成AI系统 - 统一世界模型与产品化引擎

位置: D:\AISleepGen\ai_system\integrated_ai_system.py
这是AI系统的核心后端，与前端部署目录分离
"""

import sqlite3
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import threading
import logging
import random
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 数据目录
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================================
# 数据模型定义
# ============================================================================

@dataclass
class UserFeedback:
    """用户反馈数据模型"""
    session_id: str
    user_id: str
    rating: int  # 1-5星
    helpful_comment: str = ""
    unhelpful_comment: str = ""
    sleep_quality: Optional[int] = None  # 1-10分
    completion_status: str = "completed"  # completed, interrupted, skipped
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

@dataclass 
class UserProfile:
    """用户个性化档案"""
    user_id: str
    preferred_guide_types: List[str] = None
    optimal_session_length: int = 15  # 分钟
    best_time_of_day: str = "evening"  # morning, afternoon, evening
    sensitivity_level: str = "medium"  # low, medium, high
    historical_ratings: List[int] = None
    stress_patterns: Dict[str, Any] = None
    environmental_preferences: Dict[str, Any] = None
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if self.preferred_guide_types is None:
            self.preferred_guide_types = ["breathing", "body_scan"]
        if self.historical_ratings is None:
            self.historical_ratings = []
        if self.stress_patterns is None:
            self.stress_patterns = {}
        if self.environmental_preferences is None:
            self.environmental_preferences = {}
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at

@dataclass
class EnvironmentData:
    """环境数据模型"""
    temperature: float
    humidity: float
    uv_index: float
    air_quality: int
    noise_level: float
    light_intensity: float
    location: str
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()

# ============================================================================
# 集成AI系统主类
# ============================================================================

class IntegratedAISystem:
    """集成AI系统 - 统一世界模型与产品化引擎"""
    
    def __init__(self, db_name="ai_system.db"):
        # 数据库路径放在data目录下
        self.db_path = os.path.join(DATA_DIR, db_name)
        
        # 和风天气API配置（来自世界模型）
        self.HEWEATHER_CONFIG = {
            'api_key': '8789e31ababa4c97ad8b5f36bb15d7eb',
            'base_url': 'https://devapi.qweather.com/v7/',
            'default_location': '101010100',
            'android_restrictions': {
                'enabled': False,
                'package_name': '',
                'sha1_fingerprint': ''
            }
        }
        
        # 初始化所有组件
        self._init_database()
        self._load_insight_rules()
        self._setup_audio_library()
        
        logger.info(f"[RUN] 集成AI系统初始化完成 - 数据库: {self.db_path}")
    
        self._setup_audio_library()
        
        logger.info(f"[RUN] 集成AI系统初始化完成 - 数据库: {self.db_path}")
    
    def _load_insight_rules(self):
        """加载洞察规则（从数据库或配置文件）"""
        try:
            # 这里可以加载个性化推荐规则
            # 目前先使用默认规则
            self.insight_rules = {
                'mood_mapping': {
                    'stressed': 'breathing',
                    'anxious': 'relaxation', 
                    'tired': 'nature',
                    'focused': 'focus'
                },
                'time_mapping': {
                    'morning': 'breathing',
                    'afternoon': 'focus',
                    'evening': 'relaxation',
                    'night': 'nature'
                },
                'session_length_rules': {
                    'beginner': 10,
                    'intermediate': 15,
                    'advanced': 20
                }
            }
            logger.info("[OK] 洞察规则加载完成")
        except Exception as e:
            logger.error(f"[FAIL] 加载洞察规则失败: {e}")
            self.insight_rules = {}


    def _init_database(self):
        """初始化集成数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 用户反馈表（产品化引擎）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                helpful_comment TEXT,
                unhelpful_comment TEXT,
                sleep_quality INTEGER CHECK (sleep_quality >= 1 AND sleep_quality <= 10),
                completion_status TEXT DEFAULT 'completed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 用户档案表（产品化引擎）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                preferred_guide_types TEXT,
                optimal_session_length INTEGER DEFAULT 15,
                best_time_of_day TEXT DEFAULT 'evening',
                sensitivity_level TEXT DEFAULT 'medium',
                historical_ratings TEXT,
                stress_patterns TEXT,
                environmental_preferences TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 环境数据表（世界模型）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS environment_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                temperature REAL,
                humidity REAL,
                uv_index REAL,
                air_quality INTEGER,
                noise_level REAL,
                light_intensity REAL,
                location TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 会话记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS session_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                guide_type TEXT,
                session_length INTEGER,
                environment_data TEXT,
                user_profile_snapshot TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("[OK] 集成数据库初始化完成")
    

    
    def _setup_audio_library(self):
        """设置音频库 - 现在指向aisleepgen-netlify的audio目录"""
        # 音频文件在aisleepgen-netlify/audio目录下
        netlify_audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                        'aisleepgen-netlify', 'audio')
        
        self.audio_library = {
            'breathing': [
                'inhale-tone.mp3', 'exhale-tone.mp3', 'hold-tone.mp3'
            ],
            'relaxation': [
                'deep-breathing.mp3', 'anxiety-relief.mp3', 
                'sleep-meditation.mp3', 'white-noise.mp3'
            ],
            'nature': [
                'rain-sounds.mp3', 'ocean-waves.mp3', 'nature-ambience.mp3'
            ],
            'focus': [
                'focus-enhancement.mp3', 'piano-music.mp3'
            ]
        }
        
        # 验证音频文件存在
        for category, files in self.audio_library.items():
            existing_files = []
            for file in files:
                file_path = os.path.join(netlify_audio_dir, file)
                if os.path.exists(file_path):
                    existing_files.append(file)
                else:
                    logger.warning(f"[WARN]  音频文件不存在: {file_path}")
            self.audio_library[category] = existing_files
    
    def get_system_health_report(self):
        """获取系统健康报告"""
        try:
            # 检查数据库连接
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM user_feedback")
            feedback_count = cursor.fetchone()[0]
            conn.close()
            
            # 检查API连接
            env_data = self.fetch_environment_data()
            
            return {
                'status': 'healthy',
                'database': 'connected',
                'api_connection': 'active' if env_data else 'inactive',
                'feedback_count': feedback_count,
                'audio_files': {k: len(v) for k, v in self.audio_library.items()},
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def generate_intelligent_recommendation(self, user_id, context):
        """生成智能推荐"""
        try:
            # 获取环境数据
            env_data = self.fetch_environment_data()
            
            # 基于上下文和环境数据生成推荐
            mood = context.get('mood', 'relaxed')
            time_of_day = context.get('time_of_day', 'evening')
            
            # 使用洞察规则
            guide_type = self.insight_rules['mood_mapping'].get(mood, 'breathing')
            
            # 根据时间调整推荐
            if time_of_day in self.insight_rules['time_mapping']:
                guide_type = self.insight_rules['time_mapping'][time_of_day]
            
            # 确定会话长度
            session_length = self.insight_rules['session_length_rules'].get('intermediate', 15)
            
            # 选择音频文件
            available_audio = self.audio_library.get(guide_type, [])
            audio_file = random.choice(available_audio) if available_audio else 'default.mp3'
            
            recommendation = {
                'guide_type': guide_type,
                'session_length': session_length,
                'audio_file': audio_file,
                'environment': {
                    'temperature': env_data.temperature if env_data else 22,
                    'humidity': env_data.humidity if env_data else 50
                },
                'user_context': context,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"[TARGET] 为用户 {user_id} 生成推荐: {guide_type} ({session_length}分钟)")
            return recommendation
            
        except Exception as e:
            logger.error(f"生成推荐失败: {e}")
            # 返回默认推荐
            return {
                'guide_type': 'breathing',
                'session_length': 15,
                'audio_file': 'inhale-tone.mp3',
                'environment': {'temperature': 22, 'humidity': 50},
                'user_context': context,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def collect_user_feedback(self, feedback):
        """收集用户反馈"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO user_feedback 
                (session_id, user_id, rating, helpful_comment, unhelpful_comment, 
                 sleep_quality, completion_status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                feedback.session_id,
                feedback.user_id,
                feedback.rating,
                feedback.helpful_comment,
                feedback.unhelpful_comment,
                feedback.sleep_quality,
                feedback.completion_status,
                feedback.created_at
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"[NOTE] 收集用户反馈: 用户 {feedback.user_id}, 评分 {feedback.rating}")
            return True
            
        except Exception as e:
            logger.error(f"收集反馈失败: {e}")
            return False
    
    def fetch_environment_data(self):
        """获取环境数据（世界模型）"""
        try:
            # 这里可以集成真实的环境数据API
            # 目前返回模拟数据
            return EnvironmentData(
                temperature=random.randint(15, 30),
                humidity=random.randint(30, 80),
                air_quality=random.randint(1, 5),
                noise_level=random.uniform(20, 60),
                light_intensity=random.uniform(100, 1000),
                location="Beijing"
            )
        except Exception as e:
            logger.error(f"获取环境数据失败: {e}")
            return None

def demo_integrated_system():
    """演示集成系统功能"""
    print("[RUN] 集成AI系统演示 - 新的文件结构")
    print("=" * 70)
    print("位置: D:\\AISleepGen\\ai_system\\integrated_ai_system.py")
    print("这是AI系统的核心后端，与前端部署目录分离")
    print()
    
    # 初始化集成系统
    ai_system = IntegratedAISystem()
    
    # 演示环境数据获取
    print("1. 环境数据获取（世界模型）...")
    env_data = ai_system.fetch_environment_data()
    print(f"   温度: {env_data.temperature}°C")
    print(f"   湿度: {env_data.humidity}%")
    
    # 演示用户反馈收集
    print("\n2. 用户反馈收集（产品化引擎）...")
    feedback = UserFeedback(
        session_id="demo_session_001",
        user_id="demo_user",
        rating=4,
        helpful_comment="新的文件结构更清晰"
    )
    ai_system.collect_user_feedback(feedback)
    print("   [OK] 反馈收集完成")
    
    # 演示智能推荐
    print("\n3. 智能推荐生成...")
    recommendation = ai_system.generate_intelligent_recommendation("demo_user", {})
    print(f"   推荐类型: {recommendation['guide_type']}")
    print(f"   会话长度: {recommendation['session_length']}分钟")
    
    print("\n" + "=" * 70)
    print("🎉 新的文件结构演示完成!")
    print("\n优化后的结构:")
    print("• ai_system/ - AI核心后端")
    print("• aisleepgen-netlify/ - 纯前端部署")
    print("• 清晰的职责分离")

if __name__ == "__main__":
    demo_integrated_system()