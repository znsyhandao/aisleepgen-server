class DataQualityControl:
    def run_checks(self, trial_data: Dict) -> Dict:
        """执行全套数据质控"""
        checks = {
            'missing_data': self._check_missing_values(trial_data),
            'outliers': self._detect_outliers(trial_data),
            'protocol_deviations': self._find_deviations(trial_data)
        }
        
        # 动态生成质控报告
        report = {
            'pass_rate': np.mean([c['passed'] for c in checks.values()]),
            'critical_issues': [
                k for k,v in checks.items() 
                if not v['passed'] and v['severity'] == 'critical'
            ]
        }
        return report
