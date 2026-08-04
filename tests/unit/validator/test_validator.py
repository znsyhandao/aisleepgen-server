import unittest
from unittest.mock import patch
from data_validation import DataValidator

class TestDataValidator(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator()
        
    def test_normal_case(self):
        """测试正常数据"""
        data = [
            {
                "label": 5,
                "text": "normal text",
                "timestamp": "2023-06-15 12:00:00",
                "source": "production",
                "confidence": 0.8
            }
        ]
        report = self.validator.validate_output(data)
        self.assertEqual(report['quality_score'], 100)
        
    def test_edge_cases(self):
        """测试边界数据"""
        data = [
            {
                "label": 0,
                "text": "a" * 10,
                "timestamp": "2023-01-01 00:00:00",
                "source": "test",
                "confidence": 0
            },
            {
                "label": 10,
                "text": "a" * 512,
                "timestamp": "2023-12-31 23:59:59",
                "source": "test",
                "confidence": 1
            }
        ]
        report = self.validator.validate_output(data)
        self.assertTrue(report['passed'])
        
# ... 前面的测试代码保持不变 ...
# ... 前面的测试代码保持不变 ...

    def test_invalid_data(self):
        """测试无效数据"""
        data = [
            {
                "label": -1,  # 明确无效的值
                "text": "",   # 明确无效的值
                "timestamp": "invalid",  # 明确无效的格式
                "source": "",  # 明确无效的值
                "confidence": -0.1  # 明确无效的值
            }
        ]
        # 明确验证器应该抛出异常
        with self.assertRaises(ValueError):
            self.validator.validate_output(data)
        
    @patch('data_validation.DataValidator._check_basic_fields')
    def test_mocked_validation(self, mock_validate):
        """测试使用mock验证"""
        # 明确mock方法应该被调用
        mock_validate.return_value = None
        
        data = [{
            "label": 5, 
            "text": "test",
            "timestamp": "2023-01-01 00:00:00",
            "source": "test",
            "confidence": 0.5
        }]
        
        # 明确验证流程应该调用基本检查
        self.validator.validate_output(data)
        mock_validate.assert_called_once()




# ... 后面的测试代码保持不变 ...


# ... 后面的代码保持不变 ...


if __name__ == '__main__':
    unittest.main()

