import unittest
import sys
import os
from src.aisleep.model.deepseek.official.DeepSeek_V3 import ModelConfig, DeepSeekModel
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM



# 必须先设置路径再尝试导入本地模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
print(f"Current working directory: {os.getcwd()}")

# 现在可以安全导入本地模块
try:
    from src.aisleep.model.deepseek.official.DeepSeek_V3 import DeepSeekModel, ModelConfig
except ImportError as e:
    print(f"导入失败，当前Python路径: {sys.path}")
    raise

class TestDeepSeekModel(unittest.TestCase):
    def setUp(self):
        self.config = ModelConfig()
        self.model = DeepSeekModel(self.config)
        # 添加分词器和HuggingFace模型
        model_path = 'E:/path/to/deepseek-v3-0324'
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.hf_model = AutoModelForCausalLM.from_pretrained(model_path)

    def test_model_initialization(self):
        """测试模型是否能正确初始化"""
        self.assertIsNotNone(self.model)
        self.assertEqual(self.model.config.hidden_size, 1024)  # 验证配置参数
        # Add these new test methods:
    def test_config_defaults(self):
        """验证默认配置值"""
        self.assertEqual(self.config.vocab_size, 32000)
        self.assertEqual(self.config.num_hidden_layers, 24)
        
    def test_model_forward_pass(self):
        """测试前向传播"""
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = self.model(input_ids)
        self.assertIsNotNone(outputs)
        self.assertTrue(hasattr(outputs, 'last_hidden_state'))
        
    def test_model_output_structure(self):
        """验证模型输出结构"""
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = self.model(input_ids)
        self.assertTrue(isinstance(outputs, tuple))
        self.assertEqual(len(outputs), 2)  # 假设输出是(last_hidden_state, pooler_output)
        
    def test_model_loading(self):
        """测试模型加载"""
        model = DeepSeekModel(self.config)
        self.assertIsNotNone(model)
        self.assertTrue(hasattr(model, 'forward'))
    def test_model_config(self):
        """测试模型配置"""
        # 测试模型配置是否正确加载
        self.assertEqual(self.model.config.vocab_size, 32000)
        self.assertEqual(self.model.config.hidden_size, 1024)
        self.assertEqual(self.model.config.num_hidden_layers, 24)
        self.assertEqual(self.model.config.num_attention_heads, 16)
        self.assertEqual(self.model.config.intermediate_size, 4096)
        

# ... 保留现有代码 ...


    def test_huggingface_tokenizer(self):
        """测试HuggingFace分词器"""
        text = "测试分词器功能"
        inputs = self.tokenizer(text, return_tensors="pt")
        self.assertEqual(inputs["input_ids"].shape[0], 1)  # 批大小为1
        self.assertGreater(inputs["input_ids"].shape[1], 0)  # 序列长度大于0

    def test_batch_processing(self):
        """测试批处理输入"""
        batch_size = 2
        seq_length = 10
        input_ids = torch.randint(0, self.config.vocab_size, (batch_size, seq_length))
        outputs = self.model(input_ids)
        self.assertEqual(outputs[0].shape, (batch_size, seq_length, self.config.hidden_size))

    def test_model_save_load(self):
        """测试模型保存和加载"""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            # 保存模型
            save_path = os.path.join(tmpdir, "test_model.bin")
            torch.save(self.model.state_dict(), save_path)
            
            # 加载模型
            new_model = DeepSeekModel(self.config)
            new_model.load_state_dict(torch.load(save_path))
            
            # 验证加载后的模型
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
            outputs = new_model(input_ids)
            self.assertIsNotNone(outputs)

# ... 保留文件末尾代码 ...



    def test_generation_capability(self):
        """测试模型生成能力"""
        input_ids = torch.randint(0, self.config.vocab_size, (1, 5))
        generated = self.model.generate(
            input_ids,
            max_length=20,
            do_sample=True
        )
        self.assertEqual(generated.shape[0], 1)  # 批大小为1
        self.assertEqual(generated.shape[1], 20)  # 生成长度

    def test_variable_length_input(self):
        """测试不同长度输入"""
        for length in [1, 10, 50, 100]:  # 测试不同长度
            input_ids = torch.randint(0, self.config.vocab_size, (1, length))
            outputs = self.model(input_ids)
            self.assertEqual(outputs[0].shape, (1, length, self.config.hidden_size))

    def test_special_tokens(self):
        """测试特殊token处理"""
        if hasattr(self.tokenizer, 'bos_token_id') and self.tokenizer.bos_token_id is not None:
            input_ids = torch.tensor([[self.tokenizer.bos_token_id]])
            outputs = self.model(input_ids)
            self.assertIsNotNone(outputs)

# ... 保留文件末尾代码 ...



    def test_model_quantization(self):
        """测试模型量化"""
        quantized_model = torch.quantization.quantize_dynamic(
            self.model,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = quantized_model(input_ids)
        self.assertIsNotNone(outputs)

    def test_performance_benchmark(self):
        """测试性能基准"""
        import time
        input_ids = torch.randint(0, self.config.vocab_size, (1, 128))
        
        # 预热
        for _ in range(3):
            self.model(input_ids)
        
        # 正式测试
        start_time = time.time()
        for _ in range(10):
            self.model(input_ids)
        elapsed = time.time() - start_time
        
        print(f"\n平均推理时间: {elapsed/10:.4f}秒")
        self.assertLess(elapsed/10, 1.0)  # 假设1秒为合理阈值

    def test_invalid_input_handling(self):
        """测试异常输入处理"""
        with self.assertRaises(Exception):
            # 空输入
            self.model(torch.tensor([]))
        
        with self.assertRaises(Exception):
            # 超出词汇表范围的输入
            self.model(torch.tensor([[self.config.vocab_size + 1]]))

# ... 保留文件末尾代码 ...
    


    def test_onnx_export(self):
        """测试ONNX模型导出"""
        import onnxruntime
        with tempfile.TemporaryDirectory() as tmpdir:
            # 导出模型
            dummy_input = torch.randint(0, self.config.vocab_size, (1, 10))
            onnx_path = os.path.join(tmpdir, "model.onnx")
            torch.onnx.export(
                self.model,
                dummy_input,
                onnx_path,
                input_names=['input_ids'],
                output_names=['output'],
                dynamic_axes={'input_ids': {0: 'batch', 1: 'sequence'}}
            )
            
            # 验证ONNX模型
            ort_session = onnxruntime.InferenceSession(onnx_path)
            outputs = ort_session.run(None, {'input_ids': dummy_input.numpy()})
            self.assertIsNotNone(outputs)

    def test_multilingual_support(self):
        """测试多语言支持"""
        test_texts = [
            "Hello world",  # 英文
            "こんにちは世界",  # 日文
            "안녕하세요 세계"  # 韩文
        ]
        for text in test_texts:
            inputs = self.tokenizer(text, return_tensors="pt")
            outputs = self.model(inputs['input_ids'])
            self.assertIsNotNone(outputs)

    def test_long_text_handling(self):
        """测试长文本处理能力"""
        long_text = "测试" * 1000  # 生成长文本
        inputs = self.tokenizer(long_text, return_tensors="pt", truncation=True, max_length=512)
        outputs = self.model(inputs['input_ids'])
        self.assertEqual(outputs[0].shape[1], 512)  # 验证截断长度

# ... 保留文件末尾代码 ...


    def test_device_compatibility(self):
        """测试GPU/CPU兼容性"""
        devices = ['cpu']
        if torch.cuda.is_available():
            devices.append('cuda')
        
        for device in devices:
            model = DeepSeekModel(self.config).to(device)
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10)).to(device)
            outputs = model(input_ids)
            self.assertIsNotNone(outputs)

    def test_model_distillation(self):
        """测试模型蒸馏"""
        teacher_model = self.model
        student_config = ModelConfig(
            num_hidden_layers=12,  # 更小的学生模型
            hidden_size=768
        )
        student_model = DeepSeekModel(student_config)
        
        # 简单的蒸馏测试
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        with torch.no_grad():
            teacher_outputs = teacher_model(input_ids)
            student_outputs = student_model(input_ids)
        
        # 验证输出形状
        self.assertEqual(student_outputs[0].shape, (1, 10, student_config.hidden_size))

    def test_low_precision_inference(self):
        """测试低精度推理"""
        model = self.model.half()  # 转换为半精度
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10)).half()
        outputs = model(input_ids)
        self.assertIsNotNone(outputs)
        self.assertEqual(outputs[0].dtype, torch.float16)



    def test_model_pruning(self):
        """测试模型剪枝"""
        from torch.nn.utils import prune
        # 对线性层进行剪枝
        for name, module in self.model.named_modules():
            if isinstance(module, torch.nn.Linear):
                prune.l1_unstructured(module, name='weight', amount=0.2)
        
        # 验证剪枝后的推理
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = self.model(input_ids)
        self.assertIsNotNone(outputs)

    def test_fine_tuning(self):
        """测试模型微调"""
        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-5)
        criterion = torch.nn.CrossEntropyLoss()
        
        # 模拟训练步骤
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        labels = torch.randint(0, self.config.vocab_size, (1, 10))
        
        optimizer.zero_grad()
        outputs = self.model(input_ids)
        loss = criterion(outputs[0].view(-1, self.config.vocab_size), labels.view(-1))
        loss.backward()
        optimizer.step()
        
        # 验证微调后模型
        self.assertIsNotNone(outputs)

    def test_model_deployment(self):
        """测试模型部署"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import uvicorn
        
        app = FastAPI()
        
        @app.post("/predict")
        async def predict(input_ids: list):
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
        
        # 测试API
        client = TestClient(app)
        response = client.post("/predict", json={"input_ids": [100, 200, 300]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("output", response.json())



    def test_model_security(self):
        """测试模型安全性"""
        # 测试对抗样本处理
        adversarial_input = torch.rand(1, 10) * 1000  # 生成异常输入
        with torch.no_grad():
            outputs = self.model(adversarial_input.int())
        self.assertIsNotNone(outputs)

    def test_model_robustness(self):
        """测试模型鲁棒性"""
        # 测试不同噪声水平下的表现
        for noise_level in [0.1, 0.3, 0.5]:
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
            noisy_input = input_ids + noise_level * torch.randn_like(input_ids.float())
            outputs = self.model(noisy_input.int())
            self.assertIsNotNone(outputs)

    def test_model_interpretability(self):
        """测试模型解释性"""
        from captum.attr import IntegratedGradients
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        
        # 使用Integrated Gradients方法
        ig = IntegratedGradients(self.model)
        attributions = ig.attribute(input_ids.float(), target=0)
        
        # 验证解释结果
        self.assertEqual(attributions.shape, input_ids.shape)



    def test_model_fairness(self):
        """测试模型公平性"""
        # 测试不同性别/种族文本的处理差异
        test_texts = [
            "He is a doctor",
            "She is a nurse",
            "The man is a programmer",
            "The woman is a teacher"
        ]
        results = []
        for text in test_texts:
            inputs = self.tokenizer(text, return_tensors="pt")
            outputs = self.model(inputs['input_ids'])
            results.append(outputs[0].mean().item())
        
        # 验证不同组别的输出差异不超过阈值
        max_diff = max(results) - min(results)
        self.assertLess(max_diff, 0.5)  # 假设0.5为可接受差异阈值

    def test_privacy_protection(self):
        """测试模型隐私保护"""
        # 测试模型是否泄露敏感信息
        sensitive_text = "My credit card number is 1234-5678-9012-3456"
        inputs = self.tokenizer(sensitive_text, return_tensors="pt")
        outputs = self.model(inputs['input_ids'])
        
        # 验证输出中不包含原始敏感信息
        output_text = self.tokenizer.decode(outputs[0].argmax(-1)[0])
        self.assertNotIn("1234-5678-9012-3456", output_text)

    def test_continual_learning(self):
        """测试模型持续学习能力"""
        # 模拟持续学习场景
        original_output = self.model(torch.tensor([[100, 200, 300]]))
        
        # 微调模型
        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-5)
        for _ in range(3):  # 少量训练步骤
            optimizer.zero_grad()
            outputs = self.model(torch.tensor([[100, 200, 300]]))
            loss = outputs[0].mean()
            loss.backward()
            optimizer.step()
        
        # 验证模型仍能保持原有知识
        new_output = self.model(torch.tensor([[100, 200, 300]]))
        similarity = torch.cosine_similarity(
            original_output[0].flatten(), 
            new_output[0].flatten(), 
            dim=0
        )
        self.assertGreater(similarity, 0.8)  # 相似度阈值



    def test_energy_consumption(self):
        """测试模型能耗"""
        import time
        import psutil
        
        # 获取当前进程
        process = psutil.Process(os.getpid())
        
        # 记录初始能耗
        start_energy = process.cpu_times().user
        start_time = time.time()
        
        # 运行推理
        input_ids = torch.randint(0, self.config.vocab_size, (1, 128))
        for _ in range(10):
            self.model(input_ids)
            
        # 计算能耗
        elapsed = time.time() - start_time
        energy_used = process.cpu_times().user - start_energy
        
        print(f"\n平均能耗: {energy_used/elapsed:.4f} CPU秒/秒")
        self.assertLess(energy_used/elapsed, 2.0)  # 设置合理阈值

    def test_model_compression(self):
        """测试模型压缩率"""
        import tempfile
        import os
        
        # 原始模型大小
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "model.bin")
            torch.save(self.model.state_dict(), path)
            original_size = os.path.getsize(path)
            
        # 量化后模型大小
        quantized_model = torch.quantization.quantize_dynamic(
            self.model,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "quant_model.bin")
            torch.save(quantized_model.state_dict(), path)
            quantized_size = os.path.getsize(path)
            
        compression_rate = original_size / quantized_size
        print(f"\n模型压缩率: {compression_rate:.2f}x")
        self.assertGreater(compression_rate, 1.5)  # 期望压缩率

    def test_transfer_learning(self):
        """测试迁移学习能力"""
        # 冻结基础层
        for param in self.model.parameters():
            param.requires_grad = False
            
        # 添加新输出层
        new_head = torch.nn.Linear(self.config.hidden_size, 10)  # 假设新任务有10类
        self.model.add_module("new_head", new_head)
        
        # 测试微调
        optimizer = torch.optim.Adam(new_head.parameters(), lr=1e-4)
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        labels = torch.randint(0, 10, (1,))
        
        outputs = self.model(input_ids)[0]
        loss = torch.nn.functional.cross_entropy(new_head(outputs.mean(1)), labels)
        loss.backward()
        optimizer.step()
        
        self.assertIsNotNone(outputs)





    def test_edge_cases(self):
        """测试边缘案例"""
        # 测试空字符串
        inputs = self.tokenizer("", return_tensors="pt")
        outputs = self.model(inputs['input_ids'])
        self.assertIsNotNone(outputs)
        
        # 测试超长空格字符串
        long_space = " " * 1000
        inputs = self.tokenizer(long_space, return_tensors="pt", truncation=True, max_length=512)
        outputs = self.model(inputs['input_ids'])
        self.assertEqual(outputs[0].shape[1], min(len(long_space), 512))

    def test_memory_usage(self):
        """测试内存占用"""
        import tracemalloc
        tracemalloc.start()
        
        # 记录初始内存
        snapshot1 = tracemalloc.take_snapshot()
        
        # 执行推理
        input_ids = torch.randint(0, self.config.vocab_size, (1, 128))
        _ = self.model(input_ids)
        
        # 记录内存变化
        snapshot2 = tracemalloc.take_snapshot()
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        print("\n内存变化统计:")
        for stat in top_stats[:5]:
            print(stat)
            
        self.assertLess(stat.size_diff, 100*1024*1024)  # 内存增长应小于100MB

    def test_multi_threading(self):
        """测试多线程推理"""
        from concurrent.futures import ThreadPoolExecutor
        import threading
        
        results = []
        def inference_thread():
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
            outputs = self.model(input_ids)
            results.append(outputs)
            
        # 创建多个线程
        threads = []
        for _ in range(4):
            t = threading.Thread(target=inference_thread)
            threads.append(t)
            t.start()
            
        # 等待所有线程完成
        for t in threads:
            t.join()
            
        self.assertEqual(len(results), 4)
        for r in results:
            self.assertIsNotNone(r)

# ... 保留文件末尾代码 ...


    def test_serialization(self):
        """测试模型序列化/反序列化"""
        import pickle
        import io
        
        # 序列化模型
        buffer = io.BytesIO()
        torch.save(self.model.state_dict(), buffer)
        serialized = buffer.getvalue()
        
        # 反序列化
        buffer = io.BytesIO(serialized)
        new_model = DeepSeekModel(self.config)
        new_model.load_state_dict(torch.load(buffer))
        
        # 验证功能
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = new_model(input_ids)
        self.assertIsNotNone(outputs)

    def test_version_compatibility(self):
        """测试模型版本兼容性"""
        # 模拟旧版本模型
        old_config = ModelConfig(
            vocab_size=30000,
            hidden_size=768,
            num_hidden_layers=12
        )
        
        # 测试新模型加载旧配置
        try:
            model = DeepSeekModel(old_config)
            self.assertIsNotNone(model)
        except Exception as e:
            self.fail(f"版本兼容性测试失败: {str(e)}")

    def test_hot_update(self):
        """测试模型热更新"""
        # 创建两个不同配置的模型
        model1 = DeepSeekModel(self.config)
        new_config = ModelConfig(
            vocab_size=self.config.vocab_size,
            hidden_size=768,
            num_hidden_layers=12
        )
        model2 = DeepSeekModel(new_config)
        
        # 模拟热更新过程
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs1 = model1(input_ids)
        
        # 更新模型
        model1.load_state_dict(model2.state_dict(), strict=False)
        outputs2 = model1(input_ids)
        
        # 验证更新后模型仍能工作
        self.assertIsNotNone(outputs2)

# ... 保留文件末尾代码 ...


    def test_health_check(self):
        """测试模型服务健康检查"""
        # 模拟健康检查端点
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        
        app = FastAPI()
        
        @app.get("/health")
        async def health_check():
            try:
                # 简单推理验证模型状态
                _ = self.model(torch.tensor([[1, 2, 3]]))
                return {"status": "healthy"}
            except Exception:
                return {"status": "unhealthy"}
        
        client = TestClient(app)
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_performance_regression(self):
        """测试性能回归"""
        import time
        from statistics import mean
        
        # 基准性能数据
        baseline = 0.5  # 假设基准耗时0.5秒
        
        # 测试当前性能
        input_ids = torch.randint(0, self.config.vocab_size, (1, 128))
        times = []
        for _ in range(5):
            start = time.time()
            _ = self.model(input_ids)
            times.append(time.time() - start)
        
        current = mean(times)
        regression = (current - baseline) / baseline
        
        print(f"\n性能回归比例: {regression:.2%}")
        self.assertLess(regression, 0.1)  # 允许10%以内的性能回归

    def test_ab_testing_framework(self):
        """测试AB测试框架"""
        # 创建两个不同配置的模型
        model_a = DeepSeekModel(self.config)
        config_b = ModelConfig(
            hidden_size=768,
            num_hidden_layers=12
        )
        model_b = DeepSeekModel(config_b)
        
        # 测试相同输入下的输出差异
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        output_a = model_a(input_ids)[0]
        output_b = model_b(input_ids)[0]
        
        # 计算相似度
        similarity = torch.cosine_similarity(
            output_a.flatten(), 
            output_b.flatten(), 
            dim=0
        ).item()
        
        print(f"\n模型AB测试相似度: {similarity:.4f}")
        self.assertGreater(similarity, 0.7)  # 相似度阈值

# ... 保留文件末尾代码 ...


    def test_monitoring_metrics(self):
        """测试模型监控指标"""
        from prometheus_client import CollectorRegistry, Gauge
        
        # 创建监控指标
        registry = CollectorRegistry()
        latency_gauge = Gauge(
            'model_inference_latency', 
            '模型推理延迟(ms)',
            registry=registry
        )
        
        # 模拟监控数据收集
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        start_time = time.time()
        _ = self.model(input_ids)
        latency = (time.time() - start_time) * 1000
        
        # 记录指标
        latency_gauge.set(latency)
        
        # 验证指标
        metrics = registry.collect()
        self.assertGreater(len(metrics), 0)
        self.assertGreater(metrics[0].samples[0].value, 0)

    def test_canary_release(self):
        """测试灰度发布能力"""
        # 创建新旧两个模型版本
        old_model = DeepSeekModel(self.config)
        new_config = ModelConfig(
            hidden_size=768,
            num_hidden_layers=12
        )
        new_model = DeepSeekModel(new_config)
        
        # 模拟灰度发布(10%流量到新模型)
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        if random.random() < 0.1:  # 10%流量
            outputs = new_model(input_ids)
        else:
            outputs = old_model(input_ids)
            
        self.assertIsNotNone(outputs)

    def test_auto_rollback(self):
        """测试自动回滚机制"""
        # 创建正常模型和有问题的模型
        good_model = DeepSeekModel(self.config)
        bad_model = DeepSeekModel(self.config)
        
        # 模拟问题模型(故意设置错误参数)
        for param in bad_model.parameters():
            param.data.fill_(float('nan'))
            
        # 模拟自动回滚逻辑
        try:
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
            _ = bad_model(input_ids)
            current_model = good_model  # 触发回滚
        except Exception:
            current_model = good_model
            
        # 验证回滚后模型可用
        outputs = current_model(input_ids)
        self.assertIsNotNone(outputs)

# ... 保留文件末尾代码 ...


    def test_graceful_degradation(self):
        """测试服务降级功能"""
        # 模拟高负载情况
        original_model = self.model
        self.model = None  # 模拟模型不可用
        
        # 降级到简单模型
        from src.aisleep.model.simple_model import SimpleModel
        fallback_model = SimpleModel()
        
        # 验证降级后仍能工作
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = fallback_model(input_ids)
        self.assertIsNotNone(outputs)
        
        # 恢复原始模型
        self.model = original_model

    def test_rate_limiting(self):
        """测试流量控制"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI, Request
        from fastapi.middleware.rate_limit import RateLimitMiddleware
        
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, limit=10)  # 每秒10个请求
        
        @app.post("/predict")
        async def predict(request: Request, input_ids: list):
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
        
        # 测试限流
        client = TestClient(app)
        for _ in range(15):  # 超过限制
            response = client.post("/predict", json={"input_ids": [100, 200, 300]})
            if response.status_code != 200:
                self.assertEqual(response.status_code, 429)  # 验证限流响应
                break

    def test_multi_version_parallel(self):
        """测试多版本并行运行"""
        # 创建两个版本模型
        v1_model = DeepSeekModel(self.config)
        v2_config = ModelConfig(
            hidden_size=768,
            num_hidden_layers=12
        )
        v2_model = DeepSeekModel(v2_config)
        
        # 并行推理
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs_v1 = v1_model(input_ids)
        outputs_v2 = v2_model(input_ids)
        
        # 验证两个版本都能正常工作
        self.assertIsNotNone(outputs_v1)
        self.assertIsNotNone(outputs_v2)



    def test_model_caching(self):
        """测试模型缓存功能"""
        from src.aisleep.model.cache import ModelCache
        
        # 初始化缓存
        cache = ModelCache(max_size=2)
        
        # 测试缓存存储和检索
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        cache_key = tuple(input_ids[0].tolist())
        
        # 第一次计算并缓存
        outputs = self.model(input_ids)
        cache.set(cache_key, outputs)
        
        # 从缓存获取
        cached_outputs = cache.get(cache_key)
        self.assertIsNotNone(cached_outputs)
        self.assertTrue(torch.equal(outputs[0], cached_outputs[0]))

    def test_model_warmup(self):
        """测试模型预热效果"""
        import time
        
        # 冷启动测试
        start = time.time()
        _ = self.model(torch.randint(0, self.config.vocab_size, (1, 10)))
        cold_time = time.time() - start
        
        # 预热后测试
        for _ in range(3):
            _ = self.model(torch.randint(0, self.config.vocab_size, (1, 10)))
            
        start = time.time()
        _ = self.model(torch.randint(0, self.config.vocab_size, (1, 10)))
        warm_time = time.time() - start
        
        print(f"\n预热前后时间对比: 冷启动{cold_time:.4f}s vs 预热后{warm_time:.4f}s")
        self.assertLess(warm_time, cold_time)  # 预热后应更快

    def test_batch_optimization(self):
        """测试批处理优化效果"""
        import time
        from statistics import mean
        
        # 单条处理时间
        single_times = []
        for _ in range(5):
            start = time.time()
            _ = self.model(torch.randint(0, self.config.vocab_size, (1, 10)))
            single_times.append(time.time() - start)
        
        # 批量处理时间
        batch_size = 8
        batch_times = []
        for _ in range(5):
            start = time.time()
            _ = self.model(torch.randint(0, self.config.vocab_size, (batch_size, 10)))
            batch_times.append(time.time() - start)
        
        # 计算加速比
        speedup = mean(single_times)*batch_size / mean(batch_times)
        print(f"\n批处理加速比: {speedup:.2f}x")
        self.assertGreater(speedup, 1.5)  # 期望至少1.5倍加速

# ... 保留文件末尾代码 ...


    def test_quantization_accuracy(self):
        """测试量化后的模型精度"""
        # 原始模型推理
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        original_outputs = self.model(input_ids)
        
        # 量化模型
        quantized_model = torch.quantization.quantize_dynamic(
            self.model,
            {torch.nn.Linear},
            dtype=torch.qint8
        )
        
        # 量化后推理
        quantized_outputs = quantized_model(input_ids)
        
        # 计算相似度
        similarity = torch.cosine_similarity(
            original_outputs[0].flatten(),
            quantized_outputs[0].flatten(),
            dim=0
        )
        print(f"\n量化前后输出相似度: {similarity.item():.4f}")
        self.assertGreater(similarity, 0.9)  # 相似度应大于0.9

    def test_memory_optimization(self):
        """测试内存占用优化"""
        import torch.utils.benchmark as benchmark
        
        # 优化前内存占用
        input_ids = torch.randint(0, self.config.vocab_size, (1, 128))
        mem_before = benchmark.utils.memory_usage(
            lambda: self.model(input_ids),
            num_runs=3
        )
        
        # 应用内存优化技术
        optimized_model = torch.jit.optimize_for_inference(
            torch.jit.script(self.model)
        )
        
        # 优化后内存占用
        mem_after = benchmark.utils.memory_usage(
            lambda: optimized_model(input_ids),
            num_runs=3
        )
        
        print(f"\n内存优化效果: {max(mem_before)/max(mem_after):.2f}x")
        self.assertLess(max(mem_after), max(mem_before))  # 优化后内存应更少

    def test_parallel_computation(self):
        """测试并行计算能力"""
        if torch.cuda.device_count() > 1:
            # 多GPU并行
            parallel_model = torch.nn.DataParallel(self.model)
            input_ids = torch.randint(0, self.config.vocab_size, (8, 10)).cuda()
            
            # 并行推理
            outputs = parallel_model(input_ids)
            self.assertEqual(outputs[0].shape, (8, 10, self.config.hidden_size))
        else:
            self.skipTest("需要多个GPU来测试并行计算")

# ... 保留文件末尾代码 ...


    def test_elastic_scaling(self):
        """测试模型弹性伸缩能力"""
        from src.aisleep.model.scaling import ModelScaler
        
        # 初始化伸缩器
        scaler = ModelScaler(min_instances=1, max_instances=5)
        
        # 模拟负载变化
        for load in [0.3, 0.8, 1.5, 0.2]:
            current_instances = scaler.adjust(load)
            self.assertGreaterEqual(current_instances, 1)
            self.assertLessEqual(current_instances, 5)
            
            # 验证实例状态
            for instance in scaler.instances:
                self.assertTrue(instance.is_healthy())

    def test_auto_scaling(self):
        """测试自动扩缩容机制"""
        from src.aisleep.model.scaling import AutoScaler
        
        # 初始化自动扩缩容
        autoscaler = AutoScaler(
            cpu_threshold=0.7,
            memory_threshold=0.8
        )
        
        # 模拟高负载
        autoscaler.monitor(cpu_usage=0.9, memory_usage=0.6)
        self.assertEqual(autoscaler.current_instances, 2)  # 应扩容
        
        # 模拟低负载
        autoscaler.monitor(cpu_usage=0.3, memory_usage=0.4)
        self.assertEqual(autoscaler.current_instances, 1)  # 应缩容

    def test_load_balancing(self):
        """测试负载均衡"""
        from src.aisleep.model.load_balancer import LoadBalancer
        
        # 初始化3个模型实例
        instances = [DeepSeekModel(self.config) for _ in range(3)]
        lb = LoadBalancer(instances)
        
        # 模拟10个请求
        for i in range(10):
            input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
            instance = lb.get_instance()
            outputs = instance(input_ids)
            self.assertIsNotNone(outputs)
            
        # 验证请求分布
        request_counts = lb.get_request_counts()
        self.assertTrue(max(request_counts) - min(request_counts) <= 2)  # 最大差异不超过2

# ... 保留文件末尾代码 ...

    def test_adversarial_defense(self):
        """测试对抗攻击防御能力"""
        from torchattacks import PGD
        
        # 创建对抗攻击
        attack = PGD(self.model, eps=0.3, alpha=0.1, steps=10)
        
        # 生成对抗样本
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        adversarial_input = attack(input_ids.float(), input_ids)
        
        # 验证模型输出稳定性
        normal_output = self.model(input_ids)
        adv_output = self.model(adversarial_input.int())
        similarity = torch.cosine_similarity(
            normal_output[0].flatten(),
            adv_output[0].flatten(),
            dim=0
        )
        print(f"\n对抗样本相似度: {similarity.item():.4f}")
        self.assertGreater(similarity, 0.7)  # 相似度应大于0.7

    def test_explainability_enhancement(self):
        """测试可解释性增强"""
        from captum.attr import LayerIntegratedGradients
        from captum.attr import visualization as viz
        
        # 准备解释方法
        lig = LayerIntegratedGradients(self.model, self.model.embeddings)
        
        # 获取解释
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        attributions = lig.attribute(input_ids.float(), target=0)
        
        # 可视化验证
        fig = viz.visualize_text(
            viz.VisualizationDataRecord(
                attributions[0].sum(dim=1),
                torch.softmax(self.model(input_ids)[0], dim=-1)[0],
                [str(i) for i in input_ids[0].tolist()],
                "Input",
                "Explanation",
                "Label",
                attributions[0].sum()
            )
        )
        self.assertIsNotNone(fig)  # 验证可视化生成成功

    def test_monitoring_alert(self):
        """测试监控告警机制"""
        from src.aisleep.monitoring import AlertManager
        
        # 初始化告警系统
        alert_manager = AlertManager(
            latency_threshold=500,  # 500ms
            error_rate_threshold=0.1  # 10%
        )
        
        # 模拟异常情况
        alert_manager.check_metrics(latency=600, error_rate=0.15)
        self.assertTrue(alert_manager.should_alert())  # 应触发告警
        
        # 模拟正常情况
        alert_manager.check_metrics(latency=300, error_rate=0.05)
        self.assertFalse(alert_manager.should_alert())  # 不应触发告警

# ... 保留文件末尾代码 ...


    def test_deployment_config(self):
        """测试模型部署配置"""
        # 验证部署所需的最小资源配置
        min_memory = self.model.get_min_memory_requirement()
        self.assertGreaterEqual(min_memory, 4)  # 至少4GB内存
        
        min_cpu = self.model.get_min_cpu_requirement()
        self.assertGreaterEqual(min_cpu, 2)  # 至少2个CPU核心

    def test_input_validation(self):
        """测试输入验证逻辑"""
        # 测试无效输入处理
        invalid_inputs = [
            None,
            "invalid_string",
            torch.tensor([[-1]]),  # 超出词汇表范围
            torch.tensor([[self.config.vocab_size + 1]])  # 超出词汇表范围
        ]
        
        for inp in invalid_inputs:
            with self.assertRaises(ValueError):
                self.model.validate_input(inp)

    def test_output_postprocessing(self):
        """测试输出后处理"""
        # 模拟模型原始输出
        raw_output = torch.rand(1, 10, self.config.hidden_size)
        
        # 测试不同后处理方法
        processed = self.model.postprocess_output(raw_output, method="softmax")
        self.assertAlmostEqual(processed.sum().item(), 1.0, delta=1e-5)  # softmax归一化
        
        processed = self.model.postprocess_output(raw_output, method="sigmoid")
        self.assertTrue(torch.all(processed >= 0) and torch.all(processed <= 1))  # sigmoid范围

# ... 保留文件末尾代码 ...


    def test_api_documentation(self):
        """测试API文档完整性"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import json
        
        app = FastAPI()
        
        @app.post("/predict")
        async def predict(input_ids: list):
            """预测接口文档测试"""
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
        
        # 获取OpenAPI文档
        client = TestClient(app)
        schema = client.get("/openapi.json").json()
        
        # 验证文档关键字段
        self.assertIn("paths", schema)
        self.assertIn("/predict", schema["paths"])
        self.assertIn("post", schema["paths"]["/predict"])
        self.assertIn("description", schema["paths"]["/predict"]["post"])

    def test_io_format_compatibility(self):
        """测试输入输出格式兼容性"""
        # 测试不同格式输入
        input_formats = [
            [1, 2, 3],  # 列表格式
            {"input_ids": [1, 2, 3]},  # 字典格式
            "1,2,3"  # 字符串格式
        ]
        
        for inp in input_formats:
            try:
                if isinstance(inp, str):
                    # 字符串格式特殊处理
                    input_ids = list(map(int, inp.split(",")))
                elif isinstance(inp, dict):
                    input_ids = inp["input_ids"]
                else:
                    input_ids = inp
                    
                outputs = self.model(torch.tensor([input_ids]))
                self.assertIsNotNone(outputs)
            except Exception as e:
                self.fail(f"输入格式{type(inp)}处理失败: {str(e)}")

    def test_stress_performance(self):
        """测试模型服务压力性能"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        import threading
        
        app = FastAPI()
        
        @app.post("/predict")
        async def predict(input_ids: list):
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
        
        client = TestClient(app)
        
        # 模拟并发请求
        results = []
        def make_request():
            response = client.post("/predict", json={"input_ids": [100, 200, 300]})
            results.append(response.status_code)
            
        threads = []
        for _ in range(100):  # 100个并发请求
            t = threading.Thread(target=make_request)
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        # 验证成功率
        success_rate = sum(1 for code in results if code == 200) / len(results)
        print(f"\n压力测试成功率: {success_rate:.2%}")
        self.assertGreaterEqual(success_rate, 0.95)  # 95%成功率阈值

# ... 保留文件末尾代码 ...


    def test_api_versioning(self):
        """测试API版本控制"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI, Header
        
        app = FastAPI()
        
        @app.post("/v1/predict")
        async def predict_v1(input_ids: list):
            """V1版本API"""
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
            
        @app.post("/v2/predict")
        async def predict_v2(input_ids: list, x_version: str = Header("v2")):
            """V2版本API"""
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist(), "version": x_version}
        
        # 测试版本API
        client = TestClient(app)
        v1_response = client.post("/v1/predict", json={"input_ids": [100, 200, 300]})
        v2_response = client.post("/v2/predict", json={"input_ids": [100, 200, 300]}, headers={"X-Version": "v2"})
        
        self.assertEqual(v1_response.status_code, 200)
        self.assertEqual(v2_response.status_code, 200)
        self.assertIn("version", v2_response.json())

    def test_data_validation(self):
        """测试数据校验"""
        # 测试输入数据校验
        with self.assertRaises(ValueError):
            self.model.validate_input_data(None)
            
        # 测试输出数据校验
        invalid_output = torch.rand(1, 10, self.config.hidden_size) * float('inf')  # 生成非法输出
        with self.assertRaises(ValueError):
            self.model.validate_output_data(invalid_output)

    def test_internationalization(self):
        """测试国际化支持"""
        test_cases = [
            ("Hello world", "en"),  # 英文
            ("こんにちは世界", "ja"),  # 日文
            ("안녕하세요 세계", "ko")  # 韩文
        ]
        
        for text, lang in test_cases:
            inputs = self.tokenizer(text, return_tensors="pt")
            outputs = self.model(inputs['input_ids'])
            
            # 验证语言识别
            detected_lang = self.model.detect_language(outputs[0])
            self.assertEqual(detected_lang, lang)

# ... 保留文件末尾代码 ...


    def test_config_hot_reload(self):
        """测试配置热加载功能"""
        from src.aisleep.config import ConfigManager
        
        # 初始化配置管理器
        config_manager = ConfigManager(config_path="config.yaml")
        original_value = config_manager.get("model.max_length")
        
        # 模拟配置更新
        new_config = {"model": {"max_length": original_value + 10}}
        config_manager.update_config(new_config)
        
        # 验证配置热加载
        self.assertEqual(config_manager.get("model.max_length"), original_value + 10)
        self.assertTrue(config_manager.is_config_loaded())

    def test_log_auditing(self):
        """测试日志审计功能"""
        from src.aisleep.logging import AuditLogger
        import io
        
        # 初始化内存日志处理器
        log_stream = io.StringIO()
        logger = AuditLogger(stream=log_stream)
        
        # 记录审计日志
        logger.log("test_user", "predict", {"input": "test"})
        log_content = log_stream.getvalue()
        
        # 验证日志内容
        self.assertIn("test_user", log_content)
        self.assertIn("predict", log_content)
        self.assertIn("input", log_content)

    def test_access_control(self):
        """测试权限控制系统"""
        from fastapi.testclient import TestClient
        from fastapi import FastAPI, Depends, HTTPException
        from fastapi.security import APIKeyHeader
        
        app = FastAPI()
        api_key_header = APIKeyHeader(name="X-API-Key")
        
        def get_api_key(api_key: str = Depends(api_key_header)):
            if api_key != "valid_key":
                raise HTTPException(status_code=403, detail="Invalid API Key")
            return api_key
        
        @app.post("/predict")
        async def predict(input_ids: list, api_key: str = Depends(get_api_key)):
            input_tensor = torch.tensor([input_ids])
            with torch.no_grad():
                outputs = self.model(input_tensor)
            return {"output": outputs[0].tolist()}
        
        # 测试权限控制
        client = TestClient(app)
        
        # 无效API Key测试
        response = client.post("/predict", json={"input_ids": [1,2,3]}, headers={"X-API-Key": "invalid"})
        self.assertEqual(response.status_code, 403)
        
        # 有效API Key测试
        response = client.post("/predict", json={"input_ids": [1,2,3]}, headers={"X-API-Key": "valid_key"})
        self.assertEqual(response.status_code, 200)

# ... 保留文件末尾代码 ...


    def test_multi_tenant_isolation(self):
        """测试多租户隔离"""
        from src.aisleep.model.multitenant import MultiTenantModel
        
        # 初始化多租户模型
        mt_model = MultiTenantModel()
        
        # 添加不同租户的模型
        tenant1_model = DeepSeekModel(self.config)
        tenant2_model = DeepSeekModel(self.config)
        mt_model.add_tenant("tenant1", tenant1_model)
        mt_model.add_tenant("tenant2", tenant2_model)
        
        # 验证隔离性
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs1 = mt_model.predict("tenant1", input_ids)
        outputs2 = mt_model.predict("tenant2", input_ids)
        
        # 验证不同租户输出不同
        self.assertFalse(torch.equal(outputs1[0], outputs2[0]))

    def test_auto_recovery(self):
        """测试服务自动恢复"""
        from src.aisleep.model.recovery import ModelRecovery
        
        # 初始化恢复管理器
        recovery = ModelRecovery(self.model)
        
        # 模拟模型崩溃
        def faulty_predict(_):
            raise RuntimeError("模拟崩溃")
            
        original_predict = self.model.predict
        self.model.predict = faulty_predict
        
        # 验证自动恢复
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        outputs = recovery.predict(input_ids)
        self.assertIsNotNone(outputs)
        
        # 恢复原始方法
        self.model.predict = original_predict

    def test_health_assessment(self):
        """测试健康度综合评估"""
        from src.aisleep.model.health import HealthEvaluator
        
        # 初始化评估器
        evaluator = HealthEvaluator(self.model)
        
        # 运行评估
        report = evaluator.evaluate()
        
        # 验证评估结果
        self.assertIn("latency", report)
        self.assertIn("throughput", report)
        self.assertIn("error_rate", report)
        self.assertGreater(report["health_score"], 0.7)  # 健康度阈值

# ... 保留文件末尾代码 ...
    def test_integrated_monitoring(self):
        """测试监控告警集成"""
        from src.aisleep.monitoring import MonitoringSystem
        from prometheus_client import CollectorRegistry
        
        # 初始化监控系统
        registry = CollectorRegistry()
        monitoring = MonitoringSystem(registry)
        
        # 模拟监控数据
        input_ids = torch.randint(0, self.config.vocab_size, (1, 10))
        start_time = time.time()
        _ = self.model(input_ids)
        latency = (time.time() - start_time) * 1000
        
        # 记录指标
        monitoring.record_latency(latency)
        monitoring.record_success()
        
        # 验证指标收集
        metrics = registry.collect()
        self.assertGreater(len(metrics), 0)

if __name__ == '__main__':
    unittest.main()
