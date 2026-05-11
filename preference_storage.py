"""
偏好存储层 — 独立、稳定、防覆盖
DeepSeek 负责语义分析，存储层负责安全持久化
"""

import json
import os
import shutil
from datetime import datetime
from typing import Dict, List, Optional


PREFERENCE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'user_preferences.json')
BACKUP_FILE = PREFERENCE_FILE + '.bak'


class PreferenceStorage:
    """偏好存储 — 独立文件，写前校验，自动备份"""
    
    def __init__(self):
        self.cache = None  # 内存缓存
    
    def load(self) -> Dict:
        """从文件加载偏好数据"""
        if self.cache is not None:
            return self.cache
        
        if os.path.exists(PREFERENCE_FILE):
            try:
                with open(PREFERENCE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.cache = data
                return data
            except:
                # 损坏文件，尝试用备份恢复
                if os.path.exists(BACKUP_FILE):
                    try:
                        with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        self.cache = data
                        print('[Preference] 从备份恢复')
                        return data
                    except:
                        pass
                print('[Preference] 文件损坏，重新初始化')
        
        return self._init_default()
    
    def save(self, preferences: Dict) -> bool:
        """安全保存偏好数据（写前校验）"""
        # 校验：必须包含必要字段
        if not isinstance(preferences, dict):
            print('[Preference] 保存失败：数据格式错误')
            return False
        
        # 校验：必须有category字段且有内容，或是刚初始化的空数据
        categories = preferences.get('categories', {})
        methods = preferences.get('methods', {})
        
        if categories or methods:
            # 有真实数据，检查合理性
            pass
        elif preferences.get('version') == 2:
            # 刚初始化的空数据，允许保存
            pass
        else:
            print('[Preference] 保存跳过：无有效数据')
            return False
        
        # 先备份旧文件
        if os.path.exists(PREFERENCE_FILE):
            try:
                shutil.copy2(PREFERENCE_FILE, BACKUP_FILE)
            except:
                pass
        
        # 写新文件
        try:
            with open(PREFERENCE_FILE + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(preferences, f, ensure_ascii=False, indent=2)
            os.replace(PREFERENCE_FILE + '.tmp', PREFERENCE_FILE)
            self.cache = preferences
            return True
        except Exception as e:
            print(f'[Preference] 保存失败: {e}')
            # 尝试恢复备份
            if os.path.exists(BACKUP_FILE):
                try:
                    shutil.copy2(BACKUP_FILE, PREFERENCE_FILE)
                except:
                    pass
            return False
    
    def _init_default(self) -> Dict:
        """初始化默认偏好数据"""
        self.cache = {
            'version': 2,
            'categories': {},
            'methods': {},
            'sentences': [],
            'inferred': [],
            'last_decay': '',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'updated_at': '',
        }
        return self.cache
    
    def get_stats(self) -> Dict:
        """获取偏好统计"""
        data = self.load()
        return {
            'categories_count': len(data.get('categories', {})),
            'methods_count': len(data.get('methods', {})),
            'sentences_count': len(data.get('sentences', [])),
            'has_data': bool(data.get('categories')) or bool(data.get('methods')),
        }


class PreferenceMerge:
    """偏好合并策略 — 解决空数据覆盖问题"""
    
    @staticmethod
    def merge(old: Dict, new: Dict) -> Dict:
        """合并新旧偏好，新数据覆盖旧数据，但空字段保留旧值"""
        if not new or not new.get('categories'):
            return old  # 新数据为空，保留旧的
        
        merged = dict(old)
        
        # 合并分类
        old_cats = old.get('categories', {})
        new_cats = new.get('categories', {})
        if new_cats:
            merged['categories'] = {**old_cats, **new_cats}
        
        # 合并方法
        old_methods = old.get('methods', {})
        new_methods = new.get('methods', {})
        if new_methods:
            merged['methods'] = {**old_methods, **new_methods}
        
        # 合并句子（取最新的20条）
        merged['sentences'] = (old.get('sentences', []) + new.get('sentences', []))[-20:]
        
        # 合并推断（取最新的10条）
        merged['inferred'] = (old.get('inferred', []) + new.get('inferred', []))[-10:]
        
        merged['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        merged['version'] = 2
        
        return merged
