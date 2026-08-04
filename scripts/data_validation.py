from datetime import datetime

class DataValidator:
    def __init__(self, config_path='validation_rules.json'):
        self.config_path = config_path
        self.last_modified = 0
        self.config_version = 0
        self._backup_rules = None  # 新增配置备份
        self._load_rules()
        
    def _validate_config(self, config):
        """验证配置有效性"""
        required_sections = ['thresholds', 'consistency_rules']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"配置缺少必要部分: {section}")
        
        # 验证阈值配置
        thresholds = config['thresholds']
        required_thresholds = ['max_label_ratio', 'short_text_ratio']
        for key in required_thresholds:
            if key not in thresholds:
                raise ValueError(f"阈值配置缺少: {key}")
                
        return True

    def _load_rules(self):
        """支持验证和回滚的规则加载方法"""
        try:
            modified_time = os.path.getmtime(self.config_path)
            with open(self.config_path, 'r', encoding='utf-8') as f:
                new_rules = json.load(f)
            
            # 验证新配置
            self._validate_config(new_rules)
            
            # 备份当前配置
            self._backup_rules = getattr(self, 'rules', None)
            
            # 应用新配置
            self.rules = new_rules
            self.thresholds = self.rules.get('thresholds', {})
            self.last_modified = modified_time
            
        except Exception as e:
            print(f"配置加载失败: {str(e)}")
            # 回滚到备份配置或默认配置
            if self._backup_rules:
                self.rules = self._backup_rules
            else:
                self.rules = {
                    'thresholds': {
                        'max_label_ratio': 0.6,
                        'short_text_ratio': 0.3,
                        'min_text_length': 10,
                        'max_text_length': 512
                    },
                    'consistency_rules': {
                        'label_text_mismatch': ['优秀', '完美', '极好']
                    }
                }
            self.thresholds = self.rules.get('thresholds', {})
            raise  # 重新抛出异常以便上层处理

    
    def _check_basic_fields(self, data, report):
        # 基本字段检查实现
        if not isinstance(data, list):
            report['passed'] = False
            report['violations'].append("数据必须是列表")
    
    def _validate_item(self, item):
        """验证单个数据项的有效性"""
        try:
            # 检查label范围
            if not 0 <= item.get('label', -1) <= 10:
                return False
                
            # 检查text非空
            if not isinstance(item.get('text', ''), str) or len(item['text']) == 0:
                return False
                
            # 检查timestamp格式
            datetime.strptime(item.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                
            # 检查source非空
            if not isinstance(item.get('source', ''), str) or len(item['source']) == 0:
                return False
                
            # 检查confidence范围
            if not 0 <= item.get('confidence', -1) <= 1:
                return False
                
            return True
        except (ValueError, TypeError):
            return False

    def validate_sampled_output(self, data, sample_ratio=0.1):
        """验证采样数据"""
        if not 0 < sample_ratio <= 1:
            raise ValueError("采样比例必须在(0,1]范围内")
        
        report = self.validate_output(data)
        self._add_sampling_note(data, sample_ratio, report)
        
        # 添加采样数据特有的检查
        if len(data) > 1000:  # 大数据量时才检查分布
            self._check_distributions(data, report)
            self._check_advanced_rules(data, report)
        
        return report


    def _add_sampling_note(self, data, sample_ratio, report):
        """添加采样信息到报告"""
        report['sampling_info'] = {
            'original_size': len(data) / sample_ratio,
            'sample_size': len(data),
            'sample_ratio': sample_ratio,
            'note': '结果基于随机采样估算'
        }


    def _load_rules(self, config_path):
        """增强规则加载方法"""
        default_rules = {
            'thresholds': {
                'max_label_ratio': 0.6,
                'short_text_ratio': 0.3,
                'min_text_length': 10,
                'max_text_length': 512
            },
            'consistency_rules': {
                'label_text_mismatch': ['优秀', '完美', '极好'],
                'required_fields': ['label', 'text', 'timestamp', 'source', 'confidence']
            }
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_rules = json.load(f)
                return {**default_rules, **user_rules}  # 合并默认和用户规则
        except:
            return default_rules

    def _check_missing_fields(self, data, report):
        """检查必填字段是否缺失"""
        required_fields = self.rules['consistency_rules'].get('required_fields', [])
        missing_counts = {field:0 for field in required_fields}
        
        for item in data:
            if not isinstance(item, dict):
                continue
            for field in required_fields:
                if field not in item or item[field] is None:
                    missing_counts[field] += 1
        
        for field, count in missing_counts.items():
            if count > 0:
                report['quality_score'] -= 2
                report['violations'].append(f"字段缺失: {field} (缺失{count}次)")

    # ... 前面的代码保持不变 ...
    def _check_field_completeness(self, data, report):
        """检查字段完整性"""
        required_fields = self.rules['consistency_rules'].get('required_fields', [])
        missing_count = 0
        
        for item in data:
            if not isinstance(item, dict):
                continue
            for field in required_fields:
                if field not in item or item[field] is None:
                    missing_count += 1
        
        total_fields = len(data) * len(required_fields)
        if total_fields > 0:
            completeness = 100 - (missing_count / total_fields * 100)
            report['details']['field_completeness'] = round(completeness)
            if missing_count > 0:
                report['warnings'].append(f"字段缺失: 共缺失{missing_count}个字段")

    def _check_value_validity(self, data, report):
        """检查值有效性"""
        invalid_count = 0
        
        for item in data:
            if not isinstance(item, dict):
                continue
            if not self._validate_item(item):
                invalid_count += 1
        
        if len(data) > 0:
            validity = 100 - (invalid_count / len(data) * 100)
            report['details']['value_validity'] = round(validity)
            if invalid_count > 0:
                report['violations'].append(f"无效数据: 共发现{invalid_count}条无效记录")


    def _check_consistency(self, data, report):
        """检查数据一致性"""
        # 1. 标签-文本一致性检查
        consistency_result = self._check_label_text_consistency(data)
        if not consistency_result[0]:
            report['details']['consistency'] -= 10
            report['warnings'].append(f"标签-文本不一致: {consistency_result[1]}")

        # 2. 时间戳有效性检查
        time_result = self._check_timestamp_validity(data)
        if not time_result[0]:
            report['details']['consistency'] -= 10
            report['violations'].append(f"时间戳问题: {time_result[1]}")

        # 3. 置信度与标签一致性检查
        confidence_result = self._check_confidence_consistency(data)
        if not confidence_result[0]:
            report['details']['consistency'] -= 5
            report['warnings'].append(f"置信度异常: {confidence_result[1]}")

    def _check_confidence_consistency(self, data):
        """检查置信度与标签的一致性"""
        low_confidence_count = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            confidence = item.get('confidence', 0)
            label = item.get('label', -1)
            
            # 高标签值但低置信度视为不一致
            if label >= 8 and confidence < 0.7:
                low_confidence_count += 1
                
        return (low_confidence_count == 0,
               f"发现{low_confidence_count}个高标签低置信度的样本")

# ... 保持现有代码不变 ...
    def _check_distributions(self, data, report):
        """实现详细的分布质量检查"""
        # 1. 标签分布检查
        label_score = 100
        label_result = self._check_label_balance(data)
        if not label_result[0]:
            label_score -= 30
            report['warnings'].append(f"标签分布异常: {label_result[1]}")
        
        # 2. 文本长度分布检查
        length_score = 100
        text_result = self._check_text_length_distribution(data)
        if not text_result[0]:
            length_score -= 30
            report['warnings'].append(f"文本长度分布异常: {text_result[1]}")
        
        # 3. 计算分布质量综合评分
        report['details']['distribution_quality'] = round((label_score + length_score) / 2)

# ... 保持现有代码不变 ...
    def _load_rules(self, config_path):
        """增强规则加载方法，支持完整配置验证"""
        default_rules = {
            'thresholds': {
                'max_label_ratio': 0.6,
                'short_text_ratio': 0.3,
                'min_text_length': 10,
                'max_text_length': 512,
                'confidence_threshold': 0.7  # 新增置信度阈值
            },
            'consistency_rules': {
                'label_text_mismatch': ['优秀', '完美', '极好'],
                'required_fields': ['label', 'text', 'timestamp', 'source', 'confidence'],
                'field_rules': {  # 新增字段级验证规则
                    'label': {'min': 0, 'max': 10},
                    'text': {'min_length': 1, 'max_length': 512},
                    'confidence': {'min': 0, 'max': 1}
                }
            },
            'scoring': {  # 新增评分配置
                'weights': {
                    'field_completeness': 0.3,
                    'value_validity': 0.4,
                    'distribution_quality': 0.2,
                    'consistency': 0.1
                },
                'passing_score': 80
            }
        }
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_rules = json.load(f)
                # 深度合并默认和用户规则
                return self._deep_merge(default_rules, user_rules)
        except Exception as e:
            print(f"加载规则文件失败，使用默认规则: {str(e)}")
            return default_rules

    def _deep_merge(self, default, custom):
        """深度合并两个字典"""
        result = default.copy()
        for key, value in custom.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _validate_item(self, item):
        """基于配置规则验证单个数据项"""
        try:
            field_rules = self.rules['consistency_rules'].get('field_rules', {})
            
            # 检查label
            label = item.get('label')
            if not field_rules.get('label', {}).get('min', -1) <= label <= field_rules.get('label', {}).get('max', 11):
                return False
                
            # 检查text
            text = item.get('text', '')
            min_len = field_rules.get('text', {}).get('min_length', 1)
            max_len = field_rules.get('text', {}).get('max_length', 513)
            if not isinstance(text, str) or not min_len <= len(text) <= max_len:
                return False
                
            # 检查timestamp格式
            datetime.strptime(item.get('timestamp', ''), '%Y-%m-%d %H:%M:%S')
                
            # 检查source
            if not isinstance(item.get('source', ''), str) or len(item['source']) == 0:
                return False
                
            # 检查confidence
            confidence = item.get('confidence')
            if not field_rules.get('confidence', {}).get('min', -1) <= confidence <= field_rules.get('confidence', {}).get('max', 2):
                return False
                
            return True
        except (ValueError, TypeError):
            return False


# ... 保持现有代码不变 ...

    def validate_output(self, data):
        report = {
            'quality_score': 100,  # 初始分数
            'passed': True,
            'violations': [],
            'warnings': [],
            'details': {
                'field_completeness': 100,
                'value_validity': 100,
                'distribution_quality': 100,
                'consistency': 100
            }
        }
        
        # 1. 基本字段检查
        self._check_basic_fields(data, report)
        
        # 2. 字段完整性检查
        self._check_field_completeness(data, report)
        
        # 3. 值有效性检查
        self._check_value_validity(data, report)
        
        # 4. 分布质量检查（大数据量时）
        if len(data) > 1000:
            self._check_distributions(data, report)
        
        # 5. 数据一致性检查
        self._check_consistency(data, report)
        
        # 计算最终质量分数
        self._calculate_final_score(report)
        return report

    def _calculate_final_score(self, report):
        """计算最终质量分数"""
        weights = {
            'field_completeness': 0.3,
            'value_validity': 0.4, 
            'distribution_quality': 0.2,
            'consistency': 0.1
        }
        
        # 加权计算
        total = sum(report['details'][k] * weights[k] for k in weights)
        report['quality_score'] = round(total)
        report['passed'] = report['quality_score'] >= 80  # 合格线80分

    

    # ... 后面的代码保持不变 ...


    def _check_distributions(self, data, report):
        """实现分布检查"""
        # 标签分布检查
        label_result = self._check_label_balance(data)  # Remove second argument
        if not label_result[0]:
            report['quality_score'] -= 3
            report['warnings'].append(f"标签分布异常: {label_result[1]}")
            
        # 文本长度分布检查
        text_result = self._check_text_length_distribution(data)  # Also update this call
        if not text_result[0]:
            report['quality_score'] -= 3
            report['warnings'].append(f"文本长度分布异常: {text_result[1]}")

# ... existing code ...

    def _check_label_balance(self, data):
        """检查标签分布均衡性"""
        from collections import Counter
        labels = [d['label'] for d in data if isinstance(d, dict)]
        if not labels:
            return (True, "无有效数据")
            
        counter = Counter(labels)
        total = sum(counter.values())
        max_ratio_actual = max(counter.values()) / total
        return (max_ratio_actual <= self.thresholds['max_label_ratio'], 
                f"最大类别占比{max_ratio_actual:.1%} (样本数:{total})")

    def _check_text_length_distribution(self, data):
        """检查文本长度分布"""
        lengths = [len(d['text']) for d in data if isinstance(d, dict)]
        if not lengths:
            return (True, "无有效文本数据")
            
        short_ratio = sum(1 for l in lengths if l < 50) / len(lengths)
        avg_length = sum(lengths) / len(lengths)
        return (short_ratio <= self.thresholds['short_text_ratio'],
                f"基于{len(lengths)}个样本: 短文本占比{short_ratio:.1%} 平均长度{avg_length:.1f}字符")

# ... rest of the code ...


# ... existing code ...

    def _check_advanced_rules(self, data, report):
        """实现高级规则检查"""
        # 标签-文本一致性检查
        mismatch_words = self.rules['consistency_rules'].get('label_text_mismatch', [])
        consistency_result = self._check_label_text_consistency(data, mismatch_words)  # Add self.
        if not consistency_result[0]:
            report['quality_score'] -= 2
            report['warnings'].append(f"标签-文本不一致: {consistency_result[1]}")
            
        # 时间戳有效性检查
        time_result = self._check_timestamp_validity(data)  # Also update this call
        if not time_result[0]:
            report['quality_score'] -= 2
            report['violations'].append(f"时间戳问题: {time_result[1]}")

# ... existing code ...

    def _check_label_text_consistency(self, data, mismatch_words=None):
        """检查标签与文本内容的逻辑一致性"""
        if mismatch_words is None:
            mismatch_words = self.rules['consistency_rules'].get('label_text_mismatch', [])
            
        inconsistencies = 0
        for d in data:
            if not isinstance(d, dict):
                continue
            text = d.get('text', '')
            label = d.get('label', -1)
            
            if label in [0,1] and any(word in text.lower() for word in mismatch_words):
                inconsistencies += 1
                
        return (inconsistencies == 0,
               f"发现{inconsistencies}个标签与文本内容不一致的样本")

    def _check_timestamp_validity(self, data):
        """检查时间戳的有效性和逻辑"""
        from datetime import datetime
        now = datetime.now()
        invalid_timestamps = 0
        future_timestamps = 0
        
        for d in data:
            if not isinstance(d, dict) or 'timestamp' not in d:
                continue
                
            try:
                ts = datetime.strptime(d['timestamp'], '%Y-%m-%d %H:%M:%S')
                if ts > now:
                    future_timestamps += 1
            except:
                invalid_timestamps += 1
                
        return (invalid_timestamps + future_timestamps == 0,
               f"无效时间戳:{invalid_timestamps} 未来时间戳:{future_timestamps}")

# ... rest of the code ...


# 更新辅助函数以支持采样数据


# 保留原有的辅助函数，但修改为使用实例阈值和规则
