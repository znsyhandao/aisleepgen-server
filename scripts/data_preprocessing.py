from collections import Counter
import os
import json
import numpy as np
from tqdm import tqdm
from typing import List, Dict
from dataclasses import dataclass
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib import rcParams
import pandas as pd




@dataclass
class DataConfig:
    raw_data_dir: str = "data/raw"
    processed_dir: str = "data/processed"
    log_dir: str = "logs"  # Added log_dir with default value
    max_seq_length: int = 512
    batch_size: int = 32

class DataProcessor:
    def __init__(self, config: DataConfig):
        self.config = config
        self.report_dir = "reports"  # 新增报告输出目录
        os.makedirs(self.report_dir, exist_ok=True)

        # Initialize logger with config
        self.logger = self._setup_logger(config)
            # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows系统常用字体
        plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
        rcParams['font.size'] = 12  # 设置默认字体大小
        # Initialize analysis parameters
        self.epigenetic_clock = {
            "Horvath": {
                "CpG_sites": 353,
                "tissue_correction": True,
                "interpretation": {
                    "accelerated": ">1年",
                    "normal": "±1年",
                    "decelerated": "<-1年"
                }
            },
            "GrimAge": {
                "markers": ["DNAmPAI1", "DNAmCystatinC"],
                "mortality_prediction": True
            }
        }

        # 肠道菌群分析数据库
        self.gut_microbiota = {
            "protective": ["Faecalibacterium", "Bifidobacterium"],
            "risk": ["Enterococcus", "Clostridium"],
            "neuroactive": ["Lactobacillus", "Bacteroides"],
            "optimal_ratio": {
                "Firmicutes/Bacteroidetes": (0.8, 1.5)
            }
        }

        # 数字表型特征库
        self.digital_phenotyping = {
            "sleep": {
                "metrics": ["入睡潜伏期", "REM比例", "睡眠效率"],
                "wearables": ["Oura", "AppleWatch"]
            },
            "activity": {
                "patterns": ["步态变异", "昼夜节律", "运动强度"],
                "biomarkers": ["HRV", "皮肤电反应"]
            }
        }
         # 微生物代谢物数据库
        self.microbial_metabolites = {
            "neuroactive": {
                "SCFAs": ["乙酸", "丙酸", "丁酸"],
                "tryptophan": ["色氨酸", "5-HTP", "吲哚"],
                "optimal_ranges": {
                    "丁酸": (10, 20),  # μmol/g
                    "色氨酸": (5, 15)   # μg/ml
                }
            },
            "inflammatory": {
                "LPS": {"risk_threshold": 0.5},  # EU/ml
                "TMAO": {"risk_threshold": 6.0}  # μM
            }
        }

        # 单细胞转录组分析参数
        self.scRNA_seq = {
            "cell_types": {
                "microglia": ["P2RY12", "TMEM119"],
                "astrocytes": ["GFAP", "AQP4"],
                "neurons": ["SYT1", "RBFOX3"]
            },
            "pathways": {
                "neuroinflammation": ["IL1B", "TNF", "NFKB"],
                "synaptic_plasticity": ["BDNF", "ARC", "FOS"]
            }
        }

        # 环境暴露组分析
        self.exposome_analysis = {
            "chemical": ["PM2.5", "重金属", "双酚A"],
            "lifestyle": ["睡眠质量", "运动频率", "社交互动"],
            "biomarkers": {
                "重金属": {"hair": True, "blood": True},
                "双酚A": {"urine": True}
            }
        }



    def _setup_logger(self, config):
        """Configure production environment logger"""
        import logging
        # Create log directory if it doesn't exist
        os.makedirs(config.log_dir, exist_ok=True)
        
        logger = logging.getLogger('aisleep_prod')
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(f"{config.log_dir}/processing.log")
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s - %(message)s'
        ))
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    def omics_integration(self, file_path: str):
            """全组学整合分析"""
            with open(file_path, 'r', encoding='utf-8') as f:
                data = [json.loads(line) for line in f]
            
            print("\n=== 全组学整合分析报告 ===")
            
            # 1. 微生物代谢物分析
            if any('metabolites' in d for d in data):
                print("\n◆ 肠脑代谢物分析 ◆")
                butyrate = [d['metabolites']['butyrate'] 
                        for d in data if 'metabolites' in d]
                print(f"- 丁酸水平: {np.mean(butyrate):.1f} μmol/g (理想值10-20)")
                
                # 神经递质前体分析
                tryptophan = [d['metabolites'].get('tryptophan',0)
                            for d in data if 'metabolites' in d]
                print(f"- 色氨酸水平: {np.mean(tryptophan):.1f} μg/ml (理想值5-15)")

            # 2. 单细胞转录组分析
            if any('scRNA' in d for d in data):
                print("\n◆ 神经免疫细胞图谱 ◆")
                microglia_act = np.mean([
                    d['scRNA']['P2RY12']/d['scRNA']['TMEM119']
                    for d in data if 'scRNA' in d
                ])
                print(f"- 小胶质细胞激活指数: {microglia_act:.2f} (正常<1.5)")
                
                # 神经可塑性标记
                bdnf_exp = [d['scRNA'].get('BDNF',0) 
                        for d in data if 'scRNA' in d]
                print(f"- BDNF表达水平: {np.mean(bdnf_exp):.1f} TPM")

            # 3. 环境暴露评估
            if any('exposome' in d for d in data):
                print("\n◆ 环境暴露风险 ◆")
                heavy_metal = [d['exposome']['lead']+d['exposome']['cadmium']
                            for d in data if 'exposome' in d]
                print(f"- 重金属负荷: {np.mean(heavy_metal):.1f} μg/dL (安全<10)")
                
                # 空气污染暴露
                pm25_exp = [d['exposome'].get('PM2.5',0)
                        for d in data if 'exposome' in d]
                print(f"- 年度PM2.5暴露: {np.mean(pm25_exp):.1f} μg/m³ (WHO标准<5)")
                # 4. 风险预测与干预
                print("\n◆ 个性化健康管理 ◆")
                sample = data[0]  # 以第一个样本为例
                risk = self.predict_health_risk(sample)
                print(f"- 综合风险评分: {risk['composite']:.2f} (0-1范围)")
                print("- 推荐干预措施:")
                for item in self.generate_intervention(risk):
                    print(f"  • {item}")

# ... existing code ...

    def multiomics_analysis(self, file_path: str):
        """多组学整合分析"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = [json.loads(line) for line in f]
        
        print("\n=== 多组学整合分析报告 ===")
        
        # 1. 表观遗传分析
        if any('methylation' in d for d in data):
            print("\n◆ 表观遗传时钟分析 ◆")
            ages = [d['methylation']['horvath_age'] - d['age'] 
                   for d in data if 'methylation' in d and 'age' in d]
            if ages:
                print(f"- 表观遗传年龄偏差: {np.mean(ages):.1f}岁")
                print(f"- 甲基化加速状态: {sum(a>1 for a in ages)/len(ages):.1%}")

        # 2. 肠道菌群分析
        if any('microbiome' in d for d in data):
            print("\n◆ 肠-脑轴评估 ◆")
            ratios = [d['microbiome']['f_b_ratio'] 
                     for d in data if 'microbiome' in d and 'f_b_ratio' in d['microbiome']]
            if ratios:
                print(f"- 厚壁菌/拟杆菌比率: {np.mean(ratios):.2f} (理想值0.8-1.5)")
            
            # 神经活性菌分析
            neuro_bacteria = [
                sum(d['microbiome'].get(b,0) 
                   for b in self.gut_microbiota["neuroactive"])
                for d in data if 'microbiome' in d
            ]
            if neuro_bacteria:
                print(f"- 神经活性菌占比: {np.mean(neuro_bacteria):.1%}")

        # 3. 数字表型分析
        if any('wearable' in d for d in data):
            print("\n◆ 数字生物标记物 ◆")
            sleep_eff = [d['wearable']['sleep_efficiency'] 
                        for d in data if 'wearable' in d and 'sleep_efficiency' in d['wearable']]
            if sleep_eff:
                print(f"- 平均睡眠效率: {np.mean(sleep_eff):.1%} (临床阈值>85%)")
            
            # 活动模式分析 - 添加字段存在性检查
            circadian_data = [
                (d['wearable']['daytime_activity'] - d['wearable']['night_activity'])
                for d in data if 'wearable' in d 
                and 'daytime_activity' in d['wearable'] 
                and 'night_activity' in d['wearable']
            ]
            if circadian_data:
                circadian_rhythm = np.mean(circadian_data)
                print(f"- 昼夜活动差异: {circadian_rhythm:.1f} (正常>2000步)")


# ... existing code ...

    def omics_integration(self, file_path: str):
            """全组学整合分析"""
            with open(file_path, 'r', encoding='utf-8') as f:
                data = [json.loads(line) for line in f]
            
            print("\n=== 全组学整合分析报告 ===")
            
            # 1. 微生物代谢物分析
            if any('metabolites' in d for d in data):
                print("\n◆ 肠脑代谢物分析 ◆")
                butyrate = [d['metabolites']['butyrate'] 
                        for d in data if 'metabolites' in d and 'butyrate' in d['metabolites']]
                if butyrate:
                    print(f"- 丁酸水平: {np.mean(butyrate):.1f} μmol/g (理想值10-20)")
                
                tryptophan = [d['metabolites'].get('tryptophan',0)
                            for d in data if 'metabolites' in d]
                if tryptophan:
                    print(f"- 色氨酸水平: {np.mean(tryptophan):.1f} μg/ml (理想值5-15)")

            # 2. 单细胞转录组分析
            if any('scRNA' in d for d in data):
                print("\n◆ 神经免疫细胞图谱 ◆")
                microglia_data = [
                    (d['scRNA']['P2RY12'], d['scRNA']['TMEM119'])
                    for d in data if 'scRNA' in d 
                    and 'P2RY12' in d['scRNA'] 
                    and 'TMEM119' in d['scRNA']
                ]
                if microglia_data:
                    microglia_act = np.mean([p/t for p,t in microglia_data])
                    print(f"- 小胶质细胞激活指数: {microglia_act:.2f} (正常<1.5)")
                
                bdnf_exp = [d['scRNA'].get('BDNF',0) 
                        for d in data if 'scRNA' in d]
                if bdnf_exp:
                    print(f"- BDNF表达水平: {np.mean(bdnf_exp):.1f} TPM")

            # 3. 环境暴露评估 (增强健壮性)
            if any('exposome' in d for d in data):
                print("\n◆ 环境暴露风险 ◆")
                # 重金属分析 - 处理可能缺失的字段
                heavy_metal = [
                    d['exposome'].get('lead',0) + d['exposome'].get('cadmium',0)
                    for d in data if 'exposome' in d
                ]
                if heavy_metal:
                    print(f"- 重金属负荷: {np.mean(heavy_metal):.1f} μg/dL (安全<10)")
                
                pm25_exp = [d['exposome'].get('PM2.5',0)
                        for d in data if 'exposome' in d]
                if pm25_exp:
                    print(f"- 年度PM2.5暴露: {np.mean(pm25_exp):.1f} μg/m³ (WHO标准<5)")
    
    def _setup_logger(self, config):
        """配置生产环境日志"""
        import logging
        # Create log directory if it doesn't exist
        os.makedirs(config.log_dir, exist_ok=True)
        logger = logging.getLogger('aisleep_prod')
        logger.setLevel(logging.INFO)
        
        # 文件日志
        file_handler = logging.FileHandler(f"{config.log_dir}/processing.log")
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        
        # 控制台日志
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(
            '%(levelname)s - %(message)s'
        ))
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        file_handler = logging.FileHandler(f"{config.log_dir}/processing.log")

        return logger

    def run_pipeline(self):
        """增强版数据处理流程"""
        self.logger.info("启动数据处理流程")
        try:
            if not self.check_data_structure():
                raise ValueError("原始数据目录结构不符合要求")
            
            for split in ["train", "valid", "test"]:
                self.logger.info(f"开始处理 {split} 数据...")

                print(f"\n开始处理 {split} 数据...")
                raw_data = self.load_raw_data(f"{split}.json")
                processed = self.batch_processing(raw_data)
                self.save_processed_data(processed, f"{split}_processed.json")
                self.multiomics_analysis(f"data/processed/{split}_processed.json")  # 使用多组学分析
                self.omics_integration(f"data/processed/{split}_processed.json")  # 使用全组学分析
        except Exception as e:
            self.logger.error(f"流程执行失败: {str(e)}")
            raise

    def advanced_analysis(self, file_path: str):
        """多维度深度分析"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = [json.loads(line) for line in f]
        
        print("\n=== 神经心理整合分析报告 ===")
        
        # 1. 神经环路分析
        print("\n◆ 脑网络功能评估 ◆")
        if any('fmri' in d for d in data):
            dmn_connectivity = np.mean([d['fmri']['dmn'] for d in data if 'fmri' in d])
            print(f"- 默认模式网络连接强度: {dmn_connectivity:.2f} (正常>0.5)")
        
        # 2. 分子水平分析
        if any('biomarkers' in d for d in data):
            print("\n◆ 分子标记物分析 ◆")
            il6_levels = [d['biomarkers']['il6'] for d in data if 'biomarkers' in d]
            print(f"- 炎症因子IL-6: {np.mean(il6_levels):.1f} pg/ml (正常<3)")
        
        # 3. 个性化治疗建议
        print("\n◆ 精准医疗方案 ◆")
        for d in data[:2]:  # 分析前2个典型样本
            if 'eeg' in d and 'assessment' in d:
                print(f"\n样本ID: {d.get('id','未知')}")
                
                # 神经调节方案
                if d['eeg']['beta'] > 25:
                    print("- 高频神经振荡异常 → 推荐θ波tACS调节")
                
                # 心理干预方案
                if d['assessment'].get('PHQ-9',0) > 15:
                    print("- 重度抑郁 → 联合方案:")
                    print("  ⚕ 早晨光照治疗(10,000lux × 30分钟)")
                    print("  🧠 计算机化认知训练(每周3次)")
                    print("  🎵 个性化音乐处方(基于HRV实时调节)")



    def clinical_evaluation(self, file_path: str):
        """综合临床评估报告"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = [json.loads(line) for line in f]
        
        # 生成多维度评估报告
        print("\n=== 综合临床评估报告 ===")
        
        # 1. 心理量表分析
        if any('assessment' in d for d in data):
            print("\n◆ 标准化心理测量 ◆")
            for tool, config in self.assessment_tools.items():
                if tool in data[0].get('assessment', {}):
                    scores = [d['assessment'][tool] for d in data if 'assessment' in d]
                    avg_score = np.mean(scores)
                    print(f"- {tool}: 平均分={avg_score:.1f} ({config['interpretation'](avg_score)})")

        # 2. 神经生理分析
        if any('eeg' in d for d in data):
            print("\n◆ 神经电生理特征 ◆")
            beta_alpha_ratio = np.mean([
                d['eeg']['beta']/(d['eeg']['alpha']+1e-6) 
                for d in data if 'eeg' in d
            ])
            print(f"- β/α波比率: {beta_alpha_ratio:.2f} ({'异常' if beta_alpha_ratio>2 else '正常'})")

        # 3. 生成治疗建议
        print("\n◆ 循证治疗建议 ◆")
        for d in data[:3]:  # 分析前3个样本
            if 'label' in d:
                label = self.clinical_labels.get(d['label'], {})
                if label.get('name') == "抑郁状态":
                    print("- 抑郁干预方案:")
                    print("  ⚕ tDCS: 左侧DLPFC，1.5mA × 20分钟")
                    print("  ♫ 音乐治疗: 432Hz钢琴曲 + 阿尔法波诱导")
                    print("  📊 监测指标: PHQ-9每周评估 + HRV日记录")

# ... existing code ...


        # 将show_stats改为实例方法
    def show_stats(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = [json.loads(line) for line in f]
        
        print(f"\n文件统计: {file_path}")
        print(f"- 总样本数: {len(data)}")
        print(f"- 平均文本长度: {sum(len(d['text']) for d in data)/len(data):.1f}")
        
        # 标签分布统计
        from collections import Counter  # 添加导入
        label_dist = Counter(d['label'] for d in data)
        print("- 标签分布:", dict(label_dist))
        
    def check_data_structure(self) -> bool:
        """检查原始数据目录结构是否正确"""
        required_files = ["train.json", "valid.json", "test.json"]
        missing_files = [
            f for f in required_files 
            if not os.path.exists(os.path.join(self.config.raw_data_dir, f))
        ]
        if missing_files:
            print(f"缺少必要文件: {missing_files}")
            print(f"请确保在 {self.config.raw_data_dir} 目录下存在以下文件: {required_files}")
        return not missing_files
    
    # ... 保留其他方法不变 ...

    
# ... existing code ...

    def load_raw_data(self, file_name: str) -> List[Dict]:
        """加载单个原始数据文件"""
        file_path = os.path.join(self.config.raw_data_dir, file_name)
        try:
            with open(file_path, "r", encoding='utf-8') as f:
                data = []
                for line in f:
                    try:
                        sample = json.loads(line)
                        if not all(k in sample for k in ["text", "label"]):  # 验证必要字段
                            raise ValueError(f"样本缺少必要字段: {sample}")
                        data.append(sample)
                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误(行将被跳过): {str(e)}")
                        continue
                return data
        except FileNotFoundError:
            raise FileNotFoundError(f"数据文件不存在: {file_path}")

# ... existing code ...


    
    def preprocess_sample(self, sample: Dict) -> Dict:
        """预处理单个样本"""
        # 这里添加你的预处理逻辑
        processed = {
            "text": sample["text"][:self.config.max_seq_length],
            "label": sample.get("label", -1)
        }
        return processed


    def batch_processing(self, samples: List[Dict]) -> List[Dict]:
        """批量处理数据"""
        if not samples:  # 添加空数据检查
            print("警告: 输入数据为空")
            return []
        return [self.preprocess_sample(s) for s in tqdm(samples, desc="数据处理进度")]  # 添加进度条描述

    def run_pipeline(self):
        """增强版数据处理流程"""
        self.logger.info("启动数据处理流程")
        try:
            if not self.check_data_structure():
                raise ValueError("原始数据目录结构不符合要求")
            
            for split in ["train", "valid", "test"]:

                print(f"\n开始处理 {split} 数据...")
                raw_data = self.load_raw_data(f"{split}.json")
                processed = self.batch_processing(raw_data)
                self.save_processed_data(processed, f"{split}_processed.json")
                self.show_stats(f"data/processed/{split}_processed.json")  # 改为调用实例方法
                print(f"{split} 数据处理完成，保存到: data/processed/{split}_processed.json")
                # 在处理完成后添加报告生成
                output_file = f"data/processed/{split}_processed.json"
                self.generate_visual_report(output_file)
                
        except Exception as e:
            self.logger.error(f"流程执行失败: {str(e)}")
            raise

    def save_processed_data(self, data: List[Dict], file_name: str):
        """保存处理后的数据"""
            # 确保路径存在
        os.makedirs(self.config.processed_dir, exist_ok=True)
        output_path = os.path.join(self.config.processed_dir, file_name)
        print(f"正在保存文件到: {os.path.abspath(output_path)}")  # 添加调试信息

        try:
            with open(output_path, "w", encoding='utf-8', errors='strict') as f:
                for item in data:
                    json_str = json.dumps(item, ensure_ascii=False)
                    f.write(json_str + "\n")
        except Exception as e:
            print(f"保存文件时出错: {str(e)}")
            raise

    

# ... existing code ...

    def analyze_label_distribution(self, file_path):  # Add self parameter
        """分析标签分布"""
        from collections import Counter
        labels = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                labels.append(data['label'])
        
        print(f"\n标签分布分析: {file_path}")
        print(f"- 总样本数: {len(labels)}")
        print(f"- 标签分布: {dict(Counter(labels))}")
        print(f"- 唯一标签数: {len(set(labels))}")

    def generate_visual_report(self, file_path: str):
        """生成可视化PDF报告 - 增强版"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = [json.loads(line) for line in f]
        
        report_name = os.path.join(self.report_dir, 
                                f"visual_report_{os.path.basename(file_path)}.pdf")
        
        try:
            # 确保报告目录存在且可写
            os.makedirs(self.report_dir, exist_ok=True)
            
            # 检查文件是否被占用
            if os.path.exists(report_name):
                try:
                    os.remove(report_name)
                except PermissionError:
                    print(f"警告: 无法删除旧报告文件 {report_name}")
                    return

            with PdfPages(report_name) as pdf:
                # 1. 标签分布可视化
                self._plot_label_distribution(data, pdf)
                
                # 2. 生物标记物分布
                if any('biomarkers' in d for d in data):
                    self._plot_biomarkers(data, pdf)
                    
                # 3. 睡眠效率分布
                if any('wearable' in d for d in data):
                    self._plot_sleep_metrics(data, pdf)
                
            print(f"可视化报告已生成: {report_name}")
            
        except PermissionError as e:
            self.logger.error(f"无法写入报告文件: {str(e)}")
            print(f"错误: 请关闭可能正在使用的报告文件 {report_name}")
        except Exception as e:
            self.logger.error(f"生成报告失败: {str(e)}")
            raise



    def _plot_label_distribution(self, data, pdf):
        """绘制标签分布图 - 专业版"""
        labels = [d['label'] for d in data]
        label_counts = {k:v for k,v in sorted(Counter(labels).items(), key=lambda x: x[0])}
        
        plt.figure(figsize=(12, 6))
        ax = sns.barplot(x=list(label_counts.keys()), y=list(label_counts.values()))
        
        # 添加专业标注
        plt.title('样本标签分布统计', fontsize=14, pad=20)
        plt.xlabel('临床诊断分类', fontsize=12)
        plt.ylabel('样本数量 (n)', fontsize=12)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        # 在柱子上方添加数值标签
        for p in ax.patches:
            ax.annotate(f"{int(p.get_height())}", 
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha='center', va='center', 
                    xytext=(0, 5), 
                    textcoords='offset points',
                    fontsize=10)
        
        # 更新图例说明，包含所有标签
        clinical_labels = {
            0: "健康对照",
            1: "抑郁状态", 
            2: "焦虑状态",
            3: "神经炎症",
            4: "睡眠障碍",
            5: "环境暴露"
        }
        legend_text = "临床分类说明:\n" + "\n".join(
            [f"{k}:{v}" for k,v in clinical_labels.items() if k in label_counts]
        )
        
        plt.text(0.02, 0.95, 
                legend_text,
                transform=ax.transAxes,
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10)
        
        pdf.savefig(bbox_inches='tight')
        plt.close()

    def _plot_biomarkers(self, data, pdf):
        """绘制生物标记物图表 - 专业版"""
        biomarkers = {
            'IL-6 (pg/ml)': [d['biomarkers']['il6'] for d in data if 'biomarkers' in d],
            'BDNF (TPM)': [d.get('scRNA', {}).get('BDNF', 0) for d in data]
        }
        
        plt.figure(figsize=(14, 7))
        
        # 使用专业配色
        palette = sns.color_palette("husl", len(biomarkers))
        
        # 绘制分布图并添加临床参考线
        for i, (name, values) in enumerate(biomarkers.items()):
            if values:
                sns.kdeplot(values, label=name, fill=True, color=palette[i], alpha=0.6)
        
        # 添加临床阈值参考线
        plt.axvline(x=3, color='r', linestyle='--', label='IL-6临床阈值(3pg/ml)')
        plt.axvline(x=1.5, color='b', linestyle=':', label='BDNF参考值(1.5TPM)')
        
        # 专业格式设置
        plt.title('神经炎症生物标记物分布密度', fontsize=14)
        plt.xlabel('浓度/表达量', fontsize=12)
        plt.ylabel('概率密度', fontsize=12)
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.grid(True, linestyle='--', alpha=0.6)
        
        # 添加统计说明
        stats_text = "\n".join([
            f"{name}: n={len(values)}, μ={np.mean(values):.2f}±{np.std(values):.2f}"
            for name, values in biomarkers.items() if values
        ])
        plt.text(0.98, 0.95, stats_text, 
                transform=plt.gca().transAxes,
                ha='right', va='top',
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10)
        
        pdf.savefig(bbox_inches='tight')
        plt.close()

    def _plot_sleep_metrics(self, data, pdf):
        """绘制睡眠指标图表 - 专业版"""
        sleep_data = {
            '睡眠效率(%)': [d['wearable']['sleep_efficiency']*100 for d in data if 'wearable' in d],
            'REM比例(%)': [d['wearable'].get('rem_ratio', 0)*100 for d in data if 'wearable' in d]
        }
        
        plt.figure(figsize=(12, 7))
        
        # 专业箱线图设置
        flierprops = dict(marker='o', markersize=8, 
                        markerfacecolor='none', markeredgecolor='red')
        boxprops = dict(linestyle='-', linewidth=1.5)
        
        sns.boxplot(data=pd.DataFrame(sleep_data), 
                palette="Set2",
                flierprops=flierprops,
                boxprops=boxprops)
        
        # 添加临床参考区域
        plt.axhspan(85, 100, color='green', alpha=0.1, label='健康范围')
        plt.axhline(y=85, color='green', linestyle='--', linewidth=1)
        
        # 专业标注
        plt.title('睡眠质量指标分布 (箱线图)', fontsize=14)
        plt.ylabel('百分比值 (%)', fontsize=12)
        plt.grid(axis='y', linestyle=':', alpha=0.7)
        plt.legend(loc='upper right')
        
        # 添加样本量说明
        plt.text(0.02, 0.95, 
                f"总样本量: n={len(data)}\n绿色虚线: 临床健康阈值(85%)", 
                transform=plt.gca().transAxes,
                bbox=dict(facecolor='white', alpha=0.8),
                fontsize=10)
        
        pdf.savefig(bbox_inches='tight')
        plt.close()

    def predict_health_risk(self, sample: Dict) -> Dict:
        """多维度健康风险预测"""
        risk_scores = {
            'neuro_inflammation': 0,
            'sleep_disorder': 0,
            'aging_acceleration': 0
        }
        
        # 1. 神经炎症风险评估
        if 'biomarkers' in sample:
            il6 = sample['biomarkers'].get('il6', 0)
            risk_scores['neuro_inflammation'] = min(1.0, il6 / 10)  # IL-6水平标准化
        
        # 2. 睡眠障碍风险评估
        if 'wearable' in sample:
            sleep_eff = sample['wearable'].get('sleep_efficiency', 1)
            risk_scores['sleep_disorder'] = max(0, (0.85 - sleep_eff) * 6.67)  # 低于85%开始计分
        
        # 3. 衰老加速评估
        if 'methylation' in sample and 'age' in sample:
            age_gap = sample['methylation']['horvath_age'] - sample['age']
            risk_scores['aging_acceleration'] = min(1.0, max(0, age_gap / 5))
        
        # 综合风险评分
        risk_scores['composite'] = 0.4 * risk_scores['neuro_inflammation'] + \
                                0.3 * risk_scores['sleep_disorder'] + \
                                0.3 * risk_scores['aging_acceleration']
        
        return risk_scores

    def generate_intervention(self, risk_scores: Dict) -> List[str]:
        """生成个性化干预方案"""
        interventions = []
        
        # 神经炎症干预
        if risk_scores['neuro_inflammation'] > 0.6:
            interventions.extend([
                "抗炎饮食方案(Omega-3/姜黄素)",
                "低频经颅磁刺激(每周3次)"
            ])
        elif risk_scores['neuro_inflammation'] > 0.3:
            interventions.append("益生菌补充(特定菌株)")
        
        # 睡眠干预
        if risk_scores['sleep_disorder'] > 0.7:
            interventions.extend([
                "CBT-I认知行为治疗",
                "褪黑素缓释剂型"
            ])
        elif risk_scores['sleep_disorder'] > 0.4:
            interventions.append("光照节律调节")
        
        # 抗衰老干预
        if risk_scores['aging_acceleration'] > 0.5:
            interventions.extend([
                "NAD+前体补充",
                "间歇性禁食(16:8)"
            ])
        
        # 基础建议
        if not interventions:
            interventions.append("维持当前健康监测")
        
        return interventions
# 在DataProcessor类中添加以下方法

    def dynamic_monitoring(self, data_path: str, interval_days: int = 7):
        """动态监测与干预优化系统"""
        # 1. 加载历史数据
        history = self.load_history(data_path)
        
        # 2. 生成趋势分析
        trends = self.analyze_trends(history)
        
        # 3. 优化干预方案
        optimized_plan = self.optimize_intervention(trends)
        
        return optimized_plan

    def load_history(self, data_path: str) -> List[Dict]:
        """加载历史监测数据"""
        history = []
        for filename in sorted(os.listdir(data_path)):
            if filename.startswith("monitoring_") and filename.endswith(".json"):
                with open(os.path.join(data_path, filename), 'r') as f:
                    data = json.load(f)
                    history.append(data)
        return history

    def analyze_trends(self, history: List[Dict]) -> Dict:
        """多维度趋势分析"""
        trends = {
            'neuro_inflammation': [],
            'sleep_quality': [],
            'cognitive_function': []
        }
        
        for record in history:
            # 神经炎症趋势
            if 'biomarkers' in record:
                trends['neuro_inflammation'].append(record['biomarkers'].get('il6', 0))
            
            # 睡眠质量趋势
            if 'wearable' in record:
                trends['sleep_quality'].append(record['wearable'].get('sleep_efficiency', 0))
            
            # 认知功能趋势
            if 'assessment' in record:
                trends['cognitive_function'].append(record['assessment'].get('cognitive_score', 0))
        
        return trends

    def optimize_intervention(self, trends: Dict) -> Dict:
        """基于趋势的干预方案优化"""
        plan = {
            'current': [],
            'adjusted': []
        }
        
        # 神经炎症干预调整
        il6_trend = np.array(trends['neuro_inflammation'])
        if len(il6_trend) > 2 and np.polyfit(range(len(il6_trend)), il6_trend, 1)[0] > 0.5:
            plan['adjusted'].append("升级抗炎方案: 增加IL-6抑制剂剂量")
        
        # 睡眠干预调整
        sleep_trend = np.array(trends['sleep_quality'])
        if len(sleep_trend) > 2 and np.mean(sleep_trend[-3:]) < 0.7:
            plan['adjusted'].append("强化睡眠干预: 增加CBT-I频次")
        
        # 认知干预调整
        cog_trend = np.array(trends['cognitive_function'])
        if len(cog_trend) > 2 and np.polyfit(range(len(cog_trend)), cog_trend, 1)[0] < -1:
            plan['adjusted'].append("新增认知训练: 每日30分钟双任务训练")
        
        if not plan['adjusted']:
            plan['current'] = ["维持现有干预方案"]
        
        return plan

# 在DataProcessor类中添加以下方法

    def generate_doctor_dashboard(self, patient_data: Dict, output_path: str = None):
        """生成医生审核界面HTML报告"""
        from jinja2 import Template
        
        # 1. 准备数据
        risk_scores = self.predict_health_risk(patient_data)
        interventions = self.generate_intervention(risk_scores)
        
        # 2. 创建HTML模板
        template_str = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI睡眠健康管理报告</title>
            <style>
                .dashboard { font-family: 'Microsoft YaHei'; margin: 20px; }
                .panel { border: 1px solid #ddd; border-radius: 5px; padding: 15px; margin-bottom: 20px; }
                .risk-meter { height: 20px; background: linear-gradient(to right, #4CAF50, #FFC107, #F44336); }
                .intervention-card { background: #f5f5f5; padding: 10px; margin: 5px 0; border-left: 4px solid #2196F3; }
            </style>
        </head>
        <body>
            <div class="dashboard">
                <h1>患者健康管理报告</h1>
                
                <div class="panel">
                    <h2>风险评分</h2>
                    <div class="risk-meter" style="width: {{ risk_scores.composite*100 }}%"></div>
                    <p>综合风险评分: {{ "%.2f"|format(risk_scores.composite) }} (0-1范围)</p>
                </div>
                
                <div class="panel">
                    <h2>推荐干预措施</h2>
                    {% for item in interventions %}
                    <div class="intervention-card">{{ item }}</div>
                    {% endfor %}
                </div>
                
                <div class="panel">
                    <h2>关键指标趋势</h2>
                    <img src="{{ trend_plot }}" alt="指标趋势图" style="max-width: 100%;">
                </div>
            </div>
        </body>
        </html>
        """
        
        # 3. 生成趋势图
        trend_plot = self._generate_trend_plot(patient_data)
        
        # 4. 渲染报告
        template = Template(template_str)
        html_report = template.render(
            risk_scores=risk_scores,
            interventions=interventions,
            trend_plot=trend_plot
        )
        
        # 5. 保存或返回报告
        if output_path:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_report)
            print(f"医生审核界面已生成: {output_path}")
        return html_report

    def _generate_trend_plot(self, data: Dict) -> str:
        """生成Base64编码的趋势图"""
        import io
        import base64
        
        # 示例数据 - 实际应从数据库或历史记录获取
        time_points = ['Week1', 'Week2', 'Week3', 'Week4']
        metrics = {
            '睡眠效率': [0.75, 0.78, 0.82, 0.85],
            'IL-6水平': [8.5, 7.2, 6.8, 5.9]
        }
        
        plt.figure(figsize=(10, 5))
        for name, values in metrics.items():
            plt.plot(time_points, values, marker='o', label=name)
        
        plt.title('关键指标变化趋势')
        plt.ylabel('数值')
        plt.legend()
        plt.grid(True, linestyle='--', alpha=0.6)
        
        # 转换为Base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close()
        buf.seek(0)
        return "data:image/png;base64," + base64.b64encode(buf.read()).decode('utf-8')

    def interactive_review(self, patient_id: str):
        """启动交互式医生审核界面"""
        try:
            import tkinter as tk
            from tkinter import ttk
            
            # 创建主窗口
            root = tk.Tk()
            root.title(f"患者审核 - ID: {patient_id}")
            
            # 1. 基本信息面板
            info_frame = ttk.LabelFrame(root, text="患者概况", padding=10)
            info_frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(info_frame, text="姓名: 张某某").grid(row=0, column=0, sticky=tk.W)
            ttk.Label(info_frame, text="年龄: 45岁").grid(row=1, column=0, sticky=tk.W)
            ttk.Label(info_frame, text="主诉: 失眠伴日间疲劳").grid(row=2, column=0, sticky=tk.W)
            
            # 2. 风险指标面板
            risk_frame = ttk.LabelFrame(root, text="风险指标", padding=10)
            risk_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 风险进度条
            ttk.Label(risk_frame, text="神经炎症风险:").grid(row=0, column=0)
            ttk.Progressbar(risk_frame, length=200, value=65).grid(row=0, column=1)
            
            ttk.Label(risk_frame, text="睡眠障碍风险:").grid(row=1, column=0)
            ttk.Progressbar(risk_frame, length=200, value=80).grid(row=1, column=1)
            
            # 3. 干预方案面板
            action_frame = ttk.LabelFrame(root, text="干预方案", padding=10)
            action_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            interventions = [
                "CBT-I认知行为治疗(每周2次)",
                "光照治疗(早晨30分钟)",
                "褪黑素缓释片(睡前3mg)"
            ]
            
            for i, item in enumerate(interventions):
                cb = ttk.Checkbutton(action_frame, text=item)
                cb.grid(row=i, column=0, sticky=tk.W)
                cb.state(['selected'])
            
            # 4. 审核操作按钮
            btn_frame = ttk.Frame(root)
            btn_frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Button(btn_frame, text="通过审核", command=lambda: self._approve(patient_id)).pack(side=tk.RIGHT)
            ttk.Button(btn_frame, text="修改方案", command=lambda: self._modify(patient_id)).pack(side=tk.RIGHT, padx=5)
            ttk.Button(btn_frame, text="拒绝", command=lambda: self._reject(patient_id)).pack(side=tk.RIGHT)
            
            root.mainloop()
            
        except ImportError:
            print("警告: 未安装tkinter，无法启动图形界面")

    def _approve(self, patient_id):
        """审核通过处理"""
        print(f"患者 {patient_id} 方案已审核通过")
        self.logger.info(f"Approved plan for patient {patient_id}")

    def _modify(self, patient_id):
        """修改方案处理"""
        print(f"患者 {patient_id} 方案需要修改")
        self.logger.info(f"Modify plan for patient {patient_id}")

    def _reject(self, patient_id):
        """拒绝处理"""
        print(f"患者 {patient_id} 方案被拒绝")
        self.logger.info(f"Rejected plan for patient {patient_id}")

# 在DataProcessor类中添加/修改以下方法

    def generate_meditation_program(self, patient_profile: Dict) -> Dict:
        """升级版冥想方案生成 - 基于多维度生物标记物"""
        program = {
            'type': "",
            'protocols': [],
            'evidence': {}
        }
        
        # 神经炎症标记驱动方案
        il6_level = patient_profile.get('biomarkers', {}).get('il6', 0)
        if il6_level > 7:
            program.update({
                'type': "抗炎冥想协议",
                'protocols': [
                    "迷走神经激活呼吸(6次/分钟)",
                    "身体扫描+热成像反馈",
                    "引导式慈悲冥想(针对神经炎症)"
                ],
                'evidence': {
                    'mechanism': "降低IL-6和TNF-α水平",
                    'duration': "30分钟/天",
                    'studies': ["PMID: 33494025", "PMID: 35692347"]
                }
            })
        
        # 睡眠结构优化方案
        elif patient_profile.get('sleep_efficiency', 0) < 0.8:
            program.update({
                'type': "睡眠架构优化冥想",
                'protocols': [
                    "渐进式肌肉放松+生物反馈",
                    "θ波诱导音频(4-7Hz)",
                    "睡眠时间知觉训练"
                ],
                'evidence': {
                    'mechanism': "增加慢波睡眠比例",
                    'duration': "睡前20分钟",
                    'studies': ["PMID: 36171234"]
                }
            })
        
        # 默认正念方案
        else:
            program.update({
                'type': "精准正念协议",
                'protocols': [
                    "基于HRV的实时呼吸引导",
                    "开放式监测冥想",
                    "注意力锚定训练"
                ],
                'evidence': {
                    'mechanism': "增强前额叶-杏仁核功能连接",
                    'duration': "20分钟/天",
                    'studies': ["PMID: 34856015"]
                }
            })

        # 新增动态参数计算
        dynamic_params = {
            'intensity': self._calc_intensity(
                patient_data.get('stress_score', 0),
                patient_data.get('hrv', 0)
            ),
            'duration': self._calc_duration(
                patient_data.get('sleep_latency', 0),
                patient_data.get('rem_ratio', 0)
            )
        }
        program['dynamic_parameters'] = dynamic_params    
            
        # 添加神经调控参数
        program['neurofeedback'] = {
            'eeg_target': "增强前额叶θ波(4-8Hz)" if il6_level > 5 else "抑制β波(15-30Hz)",
            'hrv_threshold': "LF/HF < 0.5" if patient_profile.get('stress_score',0)>0.6 else "自由调节"
        }
        
        return program

    def cbti_sleep_program(self, patient_data: Dict) -> Dict:
        """CBT-I 2.0 - 整合多组学数据"""
        program = {
            'components': [],
            'precision_metrics': {}
        }
        
        # 基于表观遗传年龄调整睡眠限制
        epigenetic_gap = patient_data.get('methylation',{}).get('horvath_age',0) - patient_data.get('age',0)
        if epigenetic_gap > 3:
            restriction = max(5, 7 - epigenetic_gap*0.3)
            program['components'].append({
                'name': "表观遗传优化睡眠限制",
                'protocol': f"卧床时间限制为{restriction}小时(考虑表观年龄{epigenetic_gap}岁差异)"
            })
        
        # 微生物组指导的刺激控制
        if patient_data.get('microbiome',{}).get('f_b_ratio',0) > 1.8:
            program['components'].append({
                'name': "菌群平衡光照方案",
                'protocol': "早晨5000lux光照45分钟(调节肠道菌群昼夜节律)"
            })
        
        # 神经可塑性认知重构
        if patient_data.get('scRNA',{}).get('BDNF',0) < 2.0:
            program['components'].append({
                'name': "BDNF增强认知训练",
                'exercises': [
                    "双重任务工作记忆训练",
                    "情境模拟暴露疗法"
                ]
            })
        
        # 精准化指标追踪
        program['precision_metrics'] = {
            'target_sleep_architecture': {
                'REM': "20-25%",
                'SWS': "15-20% (表观遗传调整)" if epigenetic_gap > 2 else "标准范围"
            },
            'biomarker_targets': {
                'IL-6': "<3pg/ml",
                'HRV': "RMSSD >50ms"
            }
        }
        
        return program

    def integrate_mindbody_programs(self, patient_data: Dict) -> Dict:
        """整合方案3.0 - 神经科学驱动"""
        program = {
            'morning': self._generate_morning_routine(patient_data),
            'daytime': self._generate_daytime_protocols(patient_data),
            'evening': self._generate_sleep_preparation(patient_data),
            'monitoring': self._setup_biomarker_monitoring(patient_data)
        }
        
        # 添加神经可塑性增强方案
        if patient_data.get('scRNA',{}).get('BDNF',0) < 3.0:
            program['neuroplasticity'] = {
                'protocol': "间歇性θ爆发刺激(iTBS)到左侧DLPFC",
                'schedule': "每周3次，持续4周",
                'combo': "同步进行双重任务训练"
            }
        
        return program

    def _generate_morning_routine(self, data: Dict) -> Dict:
        """生成基于生物标记的晨间方案"""
        routine = {
            'light_therapy': {
                'intensity': "10,000 lux" if data.get('wearable',{}).get('sleep_efficiency',0)<0.85 else "5,000 lux",
                'duration': "45分钟" if data.get('biomarkers',{}).get('il6',0)>5 else "30分钟"
            },
            'movement': "瑜伽流(针对HPA轴调节)" if data.get('stress_score',0)>0.6 else "功能性训练"
        }
        
        # 添加微生物组优化建议
        if data.get('microbiome',{}).get('f_b_ratio',0) > 2.0:
            routine['probiotics'] = {
                'strains': "Bifidobacterium longum 1714",
                'timing': "空腹服用"
            }
        
        return routine

    def _setup_biomarker_monitoring(self, data: Dict) -> List[Dict]:
        """设置多模态生物标记物监测方案"""
        monitors = []
        
        # 炎症监测
        if data.get('biomarkers',{}).get('il6',0) > 3:
            monitors.append({
                'marker': "IL-6",
                'method': "居家指尖血检测",
                'frequency': "每周2次"
            })
        
        # 睡眠监测
        monitors.append({
            'marker': "睡眠架构",
            'device': "EEG头带+Oura环",
            'metrics': ["REM潜伏期", "慢波睡眠比例"]
        })
        
        # 微生物组监测
        if data.get('microbiome',{}).get('f_b_ratio',0) > 1.8:
            monitors.append({
                'marker': "肠道菌群",
                'test': "粪便SCFA分析",
                'frequency': "每月1次"
            })
        
        return monitors

    # 修改interactive_review方法，添加方案修改功能
    def interactive_review(self, patient_id: str):
        """启动交互式医生审核界面"""
        try:
            import tkinter as tk
            from tkinter import ttk, simpledialog
            
            # 创建主窗口
            root = tk.Tk()
            root.title(f"患者审核 - ID: {patient_id}")
            
            # 存储当前干预方案
            current_interventions = [
                "CBT-I认知行为治疗(每周2次)",
                "光照治疗(早晨30分钟)",
                "褪黑素缓释片(睡前3mg)"
            ]
            
            # 1. 基本信息面板
            info_frame = ttk.LabelFrame(root, text="患者概况", padding=10)
            info_frame.pack(fill=tk.X, padx=5, pady=5)
            
            ttk.Label(info_frame, text="姓名: 张某某").grid(row=0, column=0, sticky=tk.W)
            ttk.Label(info_frame, text="年龄: 45岁").grid(row=1, column=0, sticky=tk.W)
            ttk.Label(info_frame, text="主诉: 失眠伴日间疲劳").grid(row=2, column=0, sticky=tk.W)
            
            # 2. 风险指标面板
            risk_frame = ttk.LabelFrame(root, text="风险指标", padding=10)
            risk_frame.pack(fill=tk.X, padx=5, pady=5)
            
            # 风险进度条
            ttk.Label(risk_frame, text="神经炎症风险:").grid(row=0, column=0)
            ttk.Progressbar(risk_frame, length=200, value=65).grid(row=0, column=1)
            
            ttk.Label(risk_frame, text="睡眠障碍风险:").grid(row=1, column=0)
            ttk.Progressbar(risk_frame, length=200, value=80).grid(row=1, column=1)
            
            # 3. 干预方案面板
            action_frame = ttk.LabelFrame(root, text="干预方案", padding=10)
            action_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            for i, item in enumerate(current_interventions):
                cb = ttk.Checkbutton(action_frame, text=item)
                cb.grid(row=i, column=0, sticky=tk.W)
                cb.state(['selected'])
            
            # 4. 审核操作按钮框架 (新增这部分)
            btn_frame = ttk.Frame(root)
            btn_frame.pack(fill=tk.X, padx=5, pady=5)
            
            def modify_plan():
                """修改干预方案"""
                # ... 原有修改方案代码 ...
            
            def update_interventions_display():
                """更新界面显示的干预方案"""
                # ... 原有更新代码 ...
            
            # 添加操作按钮 (修复错误)
            ttk.Button(btn_frame, text="通过审核", command=lambda: self._approve(patient_id)).pack(side=tk.RIGHT)
            ttk.Button(btn_frame, text="修改方案", command=modify_plan).pack(side=tk.RIGHT, padx=5)
            ttk.Button(btn_frame, text="拒绝", command=lambda: self._reject(patient_id)).pack(side=tk.RIGHT)
            
            root.mainloop()
            
        except ImportError:
            print("警告: 未安装tkinter，无法启动图形界面")


    # 修改_modify方法，支持实际方案修改
    def _modify(self, patient_id):
        """修改方案处理 - 增强版"""
        # 这里可以添加将修改后的方案保存到数据库的逻辑
        print(f"患者 {patient_id} 方案已更新")
        self.logger.info(f"Modified plan for patient {patient_id}")

    # 修改_reject方法，支持实际拒绝逻辑
    def _reject(self, patient_id):
        """拒绝处理 - 增强版"""
        # 这里可以添加拒绝方案的逻辑
        print(f"患者 {patient_id} 方案已拒绝")
        self.logger.info(f"Rejected plan for patient {patient_id}")


    def validate_protocol(self, patient_id: str, protocol_type: str) -> Dict:
        """疗效验证核心逻辑"""
        # 1. 加载患者历史数据
        history = self.load_clinical_history(patient_id)
        
        # 2. 计算关键指标变化
        metrics = {
            'sleep_efficiency': self._calc_improvement(history, 'wearable.sleep_efficiency'),
            'il6_level': self._calc_reduction(history, 'biomarkers.il6'),
            'phq9_score': self._calc_reduction(history, 'assessment.PHQ-9')
        }
        
        # 3. 生成循证报告
        return {
            'effect_size': {k: f"{v:.1%}" for k,v in metrics.items()},
            'clinical_significance': self._assess_significance(metrics),
            'recommendation': self._generate_recommendation(metrics)
        }

    # 在DataProcessor类中添加
    class RealTimeMonitor:
        def __init__(self):
            self.wearable_apis = {
                'oura': self._connect_oura,
                'apple_health': self._connect_apple_health
            }
        
        def stream_biometrics(self, device_type: str) -> Generator:
            """实时数据流处理"""
            while True:
                raw_data = self.wearable_apis[device_type]()
                yield self._preprocess_stream(raw_data)
# 在DataProcessor类中添加
        def validate_clinical_protocol(self, trial_data: Dict):
            """临床验证主流程"""
            # 1. 数据质控
            qc_report = self._run_quality_control(trial_data)
            
            # 2. 疗效分析
            outcome_analyzer = OutcomeMetrics()
            efficacy = outcome_analyzer.quantify_improvement(
                trial_data['baseline'],
                trial_data['post_treatment']
            )
            
            # 3. 统计检验
            stats = StatisticalAnalysis()
            model_results = stats.analyze_rct_data(trial_data)
            
            # 4. 生成报告
            return {
                'quality_control': qc_report,
                'efficacy_metrics': efficacy,
                'statistical_results': model_results.summary(),
                'clinical_significance': self._interpret_results(model_results)
            }


# 在__main__中更新测试数据
if __name__ == "__main__":
    config = DataConfig()
    processor = DataProcessor(config)
        # 添加临床标签定义
    processor.clinical_labels = {
        0: {"name": "健康状态", "intervention": "维持健康生活方式"},
        1: {"name": "抑郁状态", "intervention": "抗抑郁治疗"},
        2: {"name": "焦虑状态", "intervention": "认知行为疗法"},
        3: {"name": "神经炎症", "intervention": "抗炎治疗"}
    }

    # 更全面的测试数据集
    test_data = {
        "train_processed.json": [
            # 完整数据样本
            {"text": "完整样本", "label": 0, 
             "methylation": {"horvath_age": 35}, "age": 30,
             "microbiome": {"f_b_ratio": 1.1, "Lactobacillus": 0.15},
             "wearable": {"sleep_efficiency": 0.9, "daytime_activity": 8000, "night_activity": 500},
             "metabolites": {"butyrate": 15, "tryptophan": 10},
             "scRNA": {"P2RY12": 1.2, "TMEM119": 0.8, "BDNF": 5.5},
             "exposome": {"lead": 3, "cadmium": 2, "PM2.5": 4.5}
            },
            # 缺失部分字段的样本
            {"text": "部分数据样本", "label": 1, 
             "methylation": {"horvath_age": 50}, "age": 45,
             "wearable": {"sleep_efficiency": 0.82}
            },
            # 边缘值样本
            {"text": "边缘值样本", "label": 2,
             "microbiome": {"f_b_ratio": 2.5},
             "metabolites": {"butyrate": 5},
             "exposome": {"lead": 15, "cadmium": 8}
            }
        ],
        "valid_processed.json": [
            # 神经炎症样本
            {"text": "神经炎症样本", "label": 3,
             "scRNA": {"P2RY12": 0.5, "TMEM119": 0.3, "IL1B": 8.2},
             "biomarkers": {"il6": 8.5},
             "eeg": {"beta": 28, "alpha": 10}
            },
            # 健康对照样本
            {"text": "健康对照", "label": 0,
             "microbiome": {"f_b_ratio": 1.0, "Bifidobacterium": 0.25},
             "metabolites": {"butyrate": 18},
             "wearable": {"sleep_efficiency": 0.95}
            }
        ],
        "test_processed.json": [
            # 极端睡眠数据
            {"text": "失眠患者", "label": 4,
             "wearable": {"sleep_efficiency": 0.65, "daytime_activity": 3000, "night_activity": 2500},
             "assessment": {"PHQ-9": 18}
            },
            # 环境暴露样本
            {"text": "高污染暴露", "label": 5,
             "exposome": {"PM2.5": 25, "lead": 12},
             "methylation": {"horvath_age": 55}, "age": 40
            }
        ]
    }

    # 创建测试目录结构
    os.makedirs("data/processed", exist_ok=True)
    for filename, data in test_data.items():
        with open(f"data/processed/{filename}", "w", encoding='utf-8') as f:
            for item in data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # 增强测试流程
    print("\n=== 增强系统测试 ===")
    test_cases = [
        ("完整数据分析", lambda: processor.multiomics_analysis("data/processed/train_processed.json")),
        ("神经炎症分析", lambda: processor.advanced_analysis("data/processed/valid_processed.json")),
        ("环境暴露评估", lambda: processor.omics_integration("data/processed/test_processed.json")),
        ("临床评估", lambda: processor.clinical_evaluation("data/processed/valid_processed.json"))
    ]

    for name, test_func in test_cases:
        print(f"\n▶ 执行测试用例: {name}")
        try:
            test_func()
        except Exception as e:
            print(f"测试失败: {str(e)}")
        else:
            print("✓ 测试通过")

# ... existing code ...


    # 执行测试
    print("\n=== 开始系统测试 ===")
    for filename in test_data.keys():
        print(f"\n测试文件: {filename}")
        processor.analyze_label_distribution(f"data/processed/{filename}")
        processor.multiomics_analysis(f"data/processed/{filename}")
        processor.omics_integration(f"data/processed/{filename}")

    processor = DataProcessor(config)
    processor.run_pipeline()  # 会自动生成可视化报告

    # 执行测试流程
    print("\n=== 增强系统测试 ===")
    test_cases = [
        ("完整数据分析", lambda: processor.multiomics_analysis("data/processed/train_processed.json")),
        ("神经炎症分析", lambda: processor.advanced_analysis("data/processed/valid_processed.json")),
        ("环境暴露评估", lambda: processor.omics_integration("data/processed/test_processed.json")),
        ("临床评估", lambda: processor.clinical_evaluation("data/processed/valid_processed.json"))
    ]
    # 从测试数据中提取一个样本作为演示数据
    patient_data = test_data["train_processed.json"][0]  # 使用第一个样本
    # 生成HTML报告
    processor.generate_doctor_dashboard(patient_data, "reports/doctor_review.html")

    # 启动交互界面
    processor.interactive_review("PATIENT_123")


    patient_data = test_data["valid_processed.json"][0]  # 使用神经炎症样本
    program = processor.integrate_mindbody_programs(patient_data)

    # 输出专业方案
    print("\n=== 神经科学整合方案 ===")
    print(f"晨间方案: {program['morning']['light_therapy']}")
    print(f"日间协议: {program['daytime']['movement']}")
    print("\n生物标记监测:")
    for monitor in program['monitoring']:
        print(f"- {monitor['marker']}: {monitor.get('method','')}")
