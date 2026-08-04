from aisleep.config import validate_config

# 测试用例1：正常配置
valid_config = {
    'monitor_interval': 5,
    'hardware_timeout': 10.0
}

# 测试用例2：缺少必需字段
missing_key_config = {
    'monitor_interval': 5
    # 缺少 hardware_timeout
}

# 测试用例3：类型错误
wrong_type_config = {
    'monitor_interval': "5",  # 应该是int
    'hardware_timeout': 10.0
}

# 测试用例4：部分类型错误
partial_wrong_type_config = {
    'monitor_interval': 5,
    'hardware_timeout': "10.0"  # 应该是int或float
}

def test_validation(config, case_name):
    print(f"\n测试用例: {case_name}")
    print(f"配置内容: {config}")
    try:
        validate_config(config)
        print("✅ 验证通过")
    except Exception as e:
        print(f"❌ 验证失败: {str(e)}")

# 执行所有测试
test_validation(valid_config, "正常配置")
test_validation(missing_key_config, "缺少必需字段")
test_validation(wrong_type_config, "类型错误(monitor_interval)")
test_validation(partial_wrong_type_config, "类型错误(hardware_timeout)")


# 添加边界值测试用例
boundary_test_configs = [
    ({'monitor_interval': 0, 'hardware_timeout': 0.0}, "零值测试"),
    ({'monitor_interval': 1, 'hardware_timeout': 0.001}, "极小值测试"),
    ({'monitor_interval': 999999, 'hardware_timeout': 999999.0}, "极大值测试")
]

# 在执行所有测试后添加：
for config, name in boundary_test_configs:
    test_validation(config, f"边界值测试 - {name}")