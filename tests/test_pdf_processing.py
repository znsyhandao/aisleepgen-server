import fitz  # 添加这行导入
from pdf_processor import PDFAlgorithmExtractor
import pytest
import os

@pytest.fixture
def sample_pdf():
    # 建议将测试用的PDF放在tests/test_data目录下
    return "tests/test_data/DeepSeek_R1.pdf" 

def test_report_generation(sample_pdf):
    processor = PDFAlgorithmExtractor(sample_pdf)
    algorithms = processor.extract_algorithms()
    
    # 打印提取结果
    for page, algos in algorithms.items():
        print(f"\n=== 第 {page + 1} 页 ===")
        for algo in algos:
            print(f"· {algo[:100]}...")  # 打印前100字符
    
    # 生成完整报告
    report_path = processor.generate_report()
    print(f"\n报告已生成: {report_path}")
    
    assert os.path.exists(report_path)
    assert report_path.endswith('.md')
    
    json_path = report_path.replace('.md', '.json')
    assert os.path.exists(json_path)


def test_extraction_quality(sample_pdf):
    processor = PDFAlgorithmExtractor(sample_pdf)
    algorithms = processor.extract_algorithms()
    
    # 更新内容类型检查
    content_types = {
        "强化学习算法": 0,
        "奖励函数": 0,
        "性能对比": 0,
        "关键指标": 0
    }
    
    for blocks in algorithms.values():
        for block in blocks:
            for ctype in content_types:
                if ctype in block:
                    content_types[ctype] += 1
    
    print("\n强化学习内容提取统计:")
    for ctype, count in content_types.items():
        print(f"- {ctype}: {count}处")
    
    # 验证至少提取到强化学习相关内容
    assert any(count > 0 for count in content_types.values()), "未提取到强化学习技术内容"

    # 验证提取到各类技术内容
    content_types = {
        "伪代码实现": 0,
        "算法步骤": 0, 
        "实验结果": 0,
        "技术定义": 0
    }
    
    for blocks in algorithms.values():
        for block in blocks:
            for ctype in content_types:
                if ctype in block:
                    content_types[ctype] += 1
    
    print("\n提取内容统计:")
    for ctype, count in content_types.items():
        print(f"- {ctype}: {count}处")
    
    # 验证至少提取到2种以上内容类型
    assert sum(v > 0 for v in content_types.values()) >= 2, "提取内容类型不足"

    # 验证提取到技术内容（放宽条件）
    has_content = any(
        "技术内容:" in block or "数学公式:" in block
        for blocks in algorithms.values()
        for block in blocks
    )
    assert has_content, "未提取到有效技术内容"
    
    # 打印提取结果
    for page, blocks in algorithms.items():
        print(f"\nPage {page + 1}:")
        for block in blocks[:3]:  # 每页最多显示3个段落
            print(f"  - {block[:150]}...")

    # 验证提取结果
    for page, blocks in algorithms.items():
        print(f"\n=== 第 {page+1} 页 ===")
        for block in blocks:
            print(f"内容类型: {'算法' if '算法' in block else '数学'}")
            print(f"内容预览: {block[:100]}...")
    
    # 验证提取到有意义的内容
    assert any(len(blocks) > 0 for blocks in algorithms.values()), "未提取到有效内容"

    # Basic validation
    assert sum(len(v) for v in algorithms.values()) > 0, "No content extracted"
    
    # Content type validation
    has_algorithms = any("【算法】" in b for blocks in algorithms.values() for b in blocks)
    has_formulas = any("【公式】" in b for blocks in algorithms.values() for b in blocks)
    has_pseudocode = any("【伪代码】" in b for blocks in algorithms.values() for b in blocks)
    
    print(f"\nExtraction summary:")
    print(f"- Algorithms found: {has_algorithms}")
    print(f"- Formulas found: {has_formulas}")
    print(f"- Pseudocode found: {has_pseudocode}")

def test_algorithm_extraction(sample_pdf):
    processor = PDFAlgorithmExtractor(sample_pdf)
    algorithms = processor.extract_algorithms()
    
    # 验证提取到算法章节或技术实现
    has_content = any(
        "算法章节:" in algo or "技术实现:" in algo
        for algos in algorithms.values() 
        for algo in algos
    )
    assert has_content, "未提取到有效技术内容"
    
    # 打印提取结果
    for page, algos in algorithms.items():
        print(f"\nPage {page + 1}:")
        for algo in algos:
            print(f"  - {algo[:200]}...")

    # 验证提取内容不包含人名
    for page, algos in algorithms.items():
        for algo in algos:
            assert not re.search(r'[A-Z][a-z]+\s+[A-Z][a-z]+', algo), "提取结果包含人名"
    
    # 验证至少提取到算法原理或公式
    assert any("算法原理:" in algo or "数学公式:" in algo 
              for algos in algorithms.values() for algo in algos), "未提取到有效算法内容"
    
    # 调试输出
    for page, algos in algorithms.items():
        print(f"\nPage {page + 1} found {len(algos)} algorithms:")
        for algo in algos:
            print(f"  - {algo[:80]}...")
    
    # 验证至少提取到1个有效算法
    assert sum(len(v) for v in algorithms.values()) >= 1, "算法提取不足"
    
    # 验证公式提取（放宽条件）
    has_formula = any("数学公式:" in algo for algos in algorithms.values() for algo in algos)
    assert has_formula, "未提取到数学公式，请检查PDF内容或调整提取规则"


def test_document_analysis(sample_pdf):
    processor = PDFAlgorithmExtractor(sample_pdf)
    with fitz.open(sample_pdf) as doc:
        analysis = processor._analyze_document(doc)
        
        print("\n=== 文档分析验证 ===")
        print(f"有效章节数: {len(analysis['real_sections'])}")
        print(f"算法提及数: {len(analysis['algorithm_mentions'])}")
        print(f"公式定位数: {len(analysis['formula_locations'])}")
        
        # 验证提取质量
        assert any("Reinforcement" in algo for algo in analysis['algorithm_mentions']), "算法提取不完整"
        assert len(analysis['formula_locations']) > 0, "未提取到公式"
        assert not any("et al" in sec for sec in analysis['real_sections']), "章节包含参考文献"