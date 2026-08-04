import sys
sys.path.append('D:/AISleepGen')
from data_generator import SpectralAttention
import tensorflow as tf
# Set GPU memory growth at the very start
gpus = tf.config.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
    except RuntimeError as e:
        print(e)  # Memory growth must be set before GPUs are initialized
import psutil
import time
from tensorflow.python.framework import ops

def monitor_memory():
    """监控内存使用情况"""
    process = psutil.Process()
    while True:
        mem = process.memory_info().rss / 1024 / 1024
        print(f"内存使用: {mem:.2f}MB")
        time.sleep(0.5)
def clear_tf_memory():
    """清理TensorFlow占用的内存"""
    tf.keras.backend.clear_session()
    ops.reset_default_graph()

# ... SpectralAttention 类定义之后 ...

def test_spectral_attention():
    """测试SpectralAttention层的功能"""
    # 清理内存
    clear_tf_memory()
    # 1. 测试层初始化
    layer = SpectralAttention(frame_length=128)  # 设置与输入长度匹配的frame_length
    input_data = tf.random.normal((32, 128))  # 模拟32个样本，128个特征
    
    # 2. 测试build方法
    try:
        layer.build(input_data.shape)
        print("[OK] build方法测试通过")
    except Exception as e:
        print(f"[FAIL] build方法失败: {str(e)}")
    
    # 3. 测试call方法
    try:
        output = layer(input_data)
        if output.shape == input_data.shape:
            print("[OK] call方法输出形状正确")
        else:
            print(f"[FAIL] call方法输出形状错误: 期望{input_data.shape}, 实际{output.shape}")
            
        # 检查权重是否被正确应用
        weights_sum = tf.reduce_sum(layer.attention_weights)
        if abs(weights_sum.numpy() - 1.0) < 1e-6:  # softmax后权重和应为1
            print("[OK] 注意力权重归一化正确")
        else:
            print(f"[FAIL] 注意力权重归一化错误: 和为{weights_sum.numpy()}")
            
    except Exception as e:
        print(f"[FAIL] call方法失败: {str(e)}")
    
    # 4. 测试梯度计算
    with tf.GradientTape() as tape:
        output = layer(input_data)
        loss = tf.reduce_mean(output)
    try:
        grads = tape.gradient(loss, layer.trainable_variables)
        if all(g is not None for g in grads):
            print("[OK] 梯度计算正确")
        else:
            print("[FAIL] 梯度计算错误: 存在None梯度")
    except Exception as e:
        print(f"[FAIL] 梯度计算失败: {str(e)}")
    
    # 5. 测试序列化/反序列化
    try:
        config = layer.get_config()
        new_layer = SpectralAttention.from_config(config)
        print("[OK] 序列化/反序列化测试通过")
    except Exception as e:
        print(f"[FAIL] 序列化/反序列化失败: {str(e)}")

# 可以在这里添加其他测试函数
if __name__ == "__main__":
    test_spectral_attention()