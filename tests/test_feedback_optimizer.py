def test_feedback_optimization():
    optimizer = FeedbackOptimizer()
    
    # 测试信号质量优化
    params = {'filter_low': 0.5}
    feedback = {'rating': 2, 'notes': "信号噪声大"}
    optimized = optimizer.apply(params, feedback)
    
    assert optimized['filter_low'] > 1.0
    assert optimized['notch_filter'] is True


from transformers import AutoModelForCausalLM
model = AutoModelForCausalLM.from_pretrained("您的模型路径")
print(model.config)

from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained("您的模型路径")
print(tokenizer.special_tokens_map)