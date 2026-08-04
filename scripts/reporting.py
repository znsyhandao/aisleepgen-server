class ClinicalReportGenerator:
    def generate_pdf(self, results: Dict):
        """生成符合CONSORT标准的PDF报告"""
        doc = Document()
        
        # 1. 研究流程图
        self._add_flow_diagram(doc)
        
        # 2. 基线特征表
        self._add_baseline_table(doc, results['baseline'])
        
        # 3. 疗效分析结果
        self._add_efficacy_results(doc, results['primary_outcomes'])
        
        # 4. 安全性分析
        self._add_safety_analysis(doc, results['adverse_events'])
        
        doc.build()
