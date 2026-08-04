import pytest
from aisleep.reporting.generator import MedicalReportGenerator

@pytest.fixture
def test_db():
    # 创建测试数据库mock
    pass

def test_medical_recommendations(test_db):
    report_gen = MedicalReportGenerator(test_db)
    
    # 测试未审核情况
    with pytest.raises(ValueError):
        report_gen._get_rem_notes({'rem_percent': 10})
    
    # 通过审核后测试
    report_gen.review_system.approved_notes.add('rem_notes')
    assert "REM睡眠不足" in report_gen._get_rem_notes({'rem_percent': 10})
