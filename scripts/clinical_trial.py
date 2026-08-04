from meditation import MeditationGenerator  # 导入已有模块
from meditation_adapter import MeditationAnalyzer

class ClinicalTrialDesign:
    def __init__(self):
        self.design = {
            'study_type': "多中心随机双盲对照试验",
            'phases': {
                'screening': "2周筛选期",
                'intervention': "8周干预期",
                'followup': "4周随访期"
            },
            'arms': {
                'experimental': "AISleepGen精准方案组",
                'control': "标准CBT-I对照组",
                'placebo': "伪干预安慰剂组"
            },
            'primary_endpoints': [
                "PSQI睡眠质量指数变化",
                "多导睡眠图(PSG)的睡眠效率提升"
            ],
            'secondary_endpoints': [
                "血清IL-6水平变化",
                "HRV昼夜节律改善",
                "微生物组α多样性变化"
            ]
        }

    def generate_protocol(self):
        """生成符合CONSORT标准的试验方案"""
        return {
            'randomization': "分层随机(按基线PSQI和IL-6水平)",
            'blinding': {
                'participant': True,
                'assessor': True,
                'analyst': True
            },
            'sample_size': "每组至少50例(α=0.05, β=0.2)",
            'analysis_plan': "ITT和PP分析集"
        }
class OutcomeMetrics:
    def __init__(self):
        self.scales = {
            'PSQI': self._calc_psqi,
            'ISI': self._calc_isi,
            'HADS': self._calc_hads
        }

        self.meditation_metrics = MeditationAnalyzer()
    
    def quantify_improvement(self, baseline, post_treatment):
        """整合冥想效果评估"""
        results = {
            # ...原有睡眠和炎症指标...
            'meditation': self.meditation_metrics.evaluate(
                baseline.get('meditation'),
                post_treatment.get('meditation')
            )
        }
        return results
    @staticmethod
    def calculate_effect_size(pre: np.array, post: np.array) -> Dict:
        """计算多种效应量指标"""
        # Cohen's d
        pooled_std = np.sqrt((np.std(pre)**2 + np.std(post)**2)/2)
        cohen_d = (np.mean(post) - np.mean(pre)) / pooled_std
        
        # 响应率(Response Rate)
        rr = np.mean(post < pre) if np.mean(pre) > np.mean(post) else np.mean(post > pre)
        
        return {
            'cohen_d': cohen_d,
            'response_rate': rr,
            'nnt': 1/rr if rr > 0 else None  # 需治疗人数
        }
    
    def quantify_improvement(self, baseline: Dict, post_treatment: Dict) -> Dict:
        """计算多维度疗效指标
        Args:
            baseline: 包含基线期各项指标数据的字典，结构为{'psg': {'sleep_efficiency': float, ...}, 'blood': {'il6': float}}
            post_treatment: 包含治疗后各项指标数据的字典，结构与baseline相同
            
        Returns:
            包含以下结构的疗效指标字典:
            {
                'sleep': {
                    'efficiency': float,  # 睡眠效率效应量(Cohen's d)
                    'latency': float      # 睡眠潜伏期效应量
                },
                'inflammation': {
                    'il6': float          # 炎症因子IL-6变化效应量
                }
            }
        """
        return {
            'sleep': {
                'efficiency': self._calc_effect_size(
                    baseline['psg']['sleep_efficiency'],
                    post_treatment['psg']['sleep_efficiency']
                ),
                'latency': self._calc_effect_size(
                    baseline['psg']['sleep_latency'],
                    post_treatment['psg']['sleep_latency']
                )
            },
            'inflammation': {
                'il6': self._calc_effect_size(
                    baseline['blood']['il6'],
                    post_treatment['blood']['il6']
                )
            }
        }

    def _calc_effect_size(self, pre, post):
        """计算Cohen's d效应量"""
        return (pre - post) / ((pre + post) / 2) ** 0.5
class StatisticalAnalysis:
    def __init__(self):
        self.methods = {
            'primary': {
                'analysis': "混合效应模型(MMRM)",
                'variables': "分组*时间交互效应",
                'covariates': ["基线值", "研究中心"]
            },
            'secondary': {
                'mediation': "路径分析(微生物组-炎症-睡眠改善)",
                'subgroup': "基于表观遗传年龄分层"
            }
        }

    def analyze_rct_data(self, dataset):
        """执行主要统计分析流程"""
        # 使用statsmodels实现
        import statsmodels.api as sm
        import statsmodels.formula.api as smf
        
        model = smf.mixedlm(
            "sleep_efficiency ~ group * time + baseline_value",
            data=dataset,
            groups=dataset['center']
        )
        return model.fit()
class ClinicalTrial:
    def __init__(self):
        # 分层随机化实现
        self.stratification_factors = ['PSQI', 'IL6']

        self.meditation = MeditationGenerator()        
        
    def randomize_patient(self, baseline_data: Dict) -> str:
        """基于基线数据的分层随机化"""
        strata = []
        for factor in self.stratification_factors:
            value = baseline_data.get(factor, 0)
            strata.append(f"{factor[:3]}{int(value//10)}")  # 如PSQ2, IL1
        
        # 哈希生成随机种子
        random_seed = hash(tuple(strata)) % 1000
        np.random.seed(random_seed)

                # 调用已有冥想模块
        if 'meditation_type' in baseline_data:
            return self.meditation.assign_group(baseline_data)
        return np.random.choice(['experimental', 'control', 'placebo'])
        
     
class MixedModelAnalysis:
    def __init__(self):
        self.model_spec = """
        sleep_efficiency ~ group + time + group:time + 
                          baseline_PSQI + (1|center)
        """
    
    def fit_model(self, data: pd.DataFrame) -> Dict:
        """带自动修正的模型拟合流程
        Args:
            data: 包含中心分组和基线PSQI的数据框
        Returns:
            包含以下键的字典:
            - final_model: 拟合后的模型结果
            - diagnostics: 模型诊断结果
            - applied_corrections: 应用的修正方法
            - bio_data: 生物反馈数据(如果存在EEG数据)
        """
        try:
            model = smf.mixedlm(
                self.model_spec,
                data=data,
                groups=data['center'],
                re_formula="~1"
            )
            result = model.fit()
            
            # 诊断与自动修正
            diag = self._check_assumptions(result)
            if not diag['normality']['passed']:
                result = self._apply_transform(result, data)
            if not diag['homoscedasticity']['passed']:
                result = self._apply_weights(result, data)
                
            # 生物数据处理
            bio_data = None
            if 'eeg' in data.columns:
                from meditation_adapter import process_biofeedback
                bio_data = process_biofeedback(data)
                
            return {
                'final_model': result,
                'diagnostics': diag,
                'applied_corrections': {
                    'transformed': not diag['normality']['passed'],
                    'weighted': not diag['homoscedasticity']['passed']
                },
                'bio_data': bio_data
            }
            
        except Exception as e:
            warnings.warn(f"模型拟合失败: {str(e)}")
            raise
    def _check_assumptions(self, model):
        """验证模型假设，返回包含检验结果的字典"""
        # 残差正态性检验 (Shapiro-Wilk)
        _, norm_p = stats.shapiro(model.resid)
        
        # 异方差性检验 (Breusch-Pagan)
        _, het_p = sms.het_breuschpagan(model.resid, model.model.exog)
        
        return {
            'normality': {
                'passed': norm_p >= 0.05,
                'p_value': norm_p,
                'test': 'Shapiro-Wilk'
            },
            'homoscedasticity': {
                'passed': het_p >= 0.05,
                'p_value': het_p,
                'test': 'Breusch-Pagan'
            }
        }

    def _apply_transform(self, model, data):
        """应用Box-Cox变换处理非正态性"""
        from scipy import stats
        transformed, _ = stats.boxcox(data['sleep_efficiency'] + 0.1)  # 确保正值
        
        new_data = data.copy()
        new_data['sleep_efficiency'] = transformed
        return smf.mixedlm(
            self.model_spec,
            data=new_data,
            groups=new_data['center']
        ).fit()

    def _apply_weights(self, model, data):
        """应用逆方差加权处理异方差"""
        weights = 1 / (model.resid**2 + 1e-6)  # 避免除零
        return smf.mixedlm(
            self.model_spec,
            data=data,
            groups=data['center'],
            weights=weights
        ).fit()


    def _apply_transform(self, model, data):
        """应用Box-Cox变换处理非正态性"""
        from scipy import stats
        transformed = stats.boxcox(data['sleep_efficiency'])
        new_data = data.copy()
        new_data['sleep_efficiency'] = transformed[0]
        
        return smf.mixedlm(
            self.model_spec,
            data=new_data,
            groups=new_data['center']
        ).fit()

    def _apply_weights(self, model, data):
        """应用逆方差加权处理异方差"""
        weights = 1 / model.resid**2
        return smf.mixedlm(
            self.model_spec,
            data=data,
            groups=data['center'],
            weights=weights
        ).fit()

    
    def _check_normality(self, model):
        """残差正态性检验与可视化"""
        from scipy import stats
        _, pval = stats.shapiro(model.resid)
        return {
            'shapiro_p': pval,
            'is_normal': pval > 0.05,
            'plot': self._plot_qq(model.resid)
        }
    
    def _calc_vif(self, model):
        """计算方差膨胀因子"""
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        exog = model.model.exog
        return [variance_inflation_factor(exog, i) for i in range(exog.shape[1])]
    
    def _interpret_coefficients(self, model):
        """临床意义解释"""
        coef = model.params
        return {
            'group_effect': f"实验组改善{coef['group[T.experimental]']:.2f}分(P={model.pvalues['group[T.experimental]']:.3f})",
            'time_effect': f"每周期改善{coef['time']:.2f}分",
            'interaction': "有显著交互效应" if model.pvalues['group:time'] < 0.05 else "无交互效应"
        }

    
    def _check_assumptions(self, model):
        """全面验证混合模型假设"""
        # 1. 残差正态性检验
        _, norm_p = stats.shapiro(model.resid)
        
        # 2. 异方差性检验
        _, het_p = stats.levene(
            model.resid[:len(model.resid)//2],
            model.resid[len(model.resid)//2:]
        )
        
        # 3. 自相关检验
        acf = sm.tsa.acf(model.resid, nlags=5)
        
        # 4. 异常值检测
        influence = model.get_influence()
        cooks = influence.cooks_distance[0]
        
        # 生成诊断报告
        return {
            'assumptions': {
                'normality': {
                    'passed': norm_p > 0.05,
                    'p_value': norm_p,
                    'plot': self._plot_qq(model.resid)
                },
                'homoscedasticity': {
                    'passed': het_p > 0.05,
                    'p_value': het_p,
                    'plot': self._plot_resid_fitted(model)
                },
                'autocorrelation': {
                    'passed': all(abs(x) < 0.3 for x in acf[1:]),
                    'acf_values': acf,
                    'plot': self._plot_acf(model.resid)
                }
            },
            'outliers': {
                'count': sum(cooks > 4/len(cooks)),
                'indices': np.where(cooks > 4/len(cooks))[0].tolist()
            }
        }

    def _plot_qq(self, residuals):
        """生成Q-Q图"""
        fig = sm.qqplot(residuals, line='45')
        plt.close()
        return fig

    def _plot_resid_fitted(self, model):
        """残差-拟合值图"""
        fig, ax = plt.subplots()
        ax.scatter(model.fittedvalues, model.resid)
        ax.axhline(y=0, color='r', linestyle='--')
        plt.close()
        return fig

    def _plot_acf(self, residuals):
        """自相关函数图"""
        fig = sm.graphics.tsa.plot_acf(residuals)
        plt.close()
        return fig

    
