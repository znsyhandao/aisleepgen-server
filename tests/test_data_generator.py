import matplotlib.pyplot as plt
from data_generator import BioSynthGenerator
import tensorflow as tf
import numpy as np
from scipy.integrate import solve_ivp
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_signal_generation():
    print("Initializing BioSynthGenerator...")
    generator = BioSynthGenerator()
    
    # 生成包含REM和NREM阶段的睡眠数据
    stages = {
        'nrem1': (0, 60),
        'nrem2': (60, 180),
        'rem': (180, 240),
        'stress': (200, 201)  # 应激事件
    }
    print("Generating physiological rhythm data...")
    data = generator.generate_physiological_rhythm(stages=stages)

    print(f"Generated data shape: {data.shape}")
    print(f"Data columns: {list(data.columns)}")
    
    
    # 可视化
    plt.figure(figsize=(12, 8))
    for i, col in enumerate(data.columns, 1):
        plt.subplot(3, 1, i)
        plt.plot(data.index, data[col])
        plt.title(col.upper())
    plt.tight_layout()
    plt.savefig('physiological_signals.png')
    print("Saved plot to physiological_signals.png")


class HPAAxisModel:
    def __init__(self):
        self.crh = 0
        self.acth = 0
        self.cortisol = 0
        
    def update(self, stress_input, dt=0.1):
        # 微分方程模拟HPA轴
        d_crh = 0.5*stress_input - 0.2*self.crh
        d_acth = 0.3*self.crh - 0.4*self.acth
        d_cortisol = 0.7*self.acth - 0.1*self.cortisol
        
        self.crh += d_crh * dt
        self.acth += d_acth * dt
        self.cortisol += d_cortisol * dt
        return self.cortisol


def coupled_oscillator(theta, phi, dt=0.01):
    # 丘脑-皮层耦合模型
    omega_theta, omega_phi = 1.0, 0.5
    K, G = 0.2, 0.3
    
    d_theta = omega_theta + K*np.sin(phi - theta)
    d_phi = omega_phi + G*np.sin(theta - phi)
    
    return theta + d_theta*dt, phi + d_phi*dt


def generate_head_motion(duration, sample_rate):
    # 分形布朗运动模拟头部运动
    t = np.arange(0, duration, 1/sample_rate)
    motion = np.zeros_like(t)
    for h in [0.6, 0.7, 0.8]:  # 不同Hurst指数
        motion += fractional_brownian_motion(t, h)
    return motion / 3


def test_physiological_constraints():
    # 测试不同年龄/BMI下的生理信号特征
    young_normal = BioSynthGenerator(age=25, bmi=21)
    elderly_overweight = BioSynthGenerator(age=65, bmi=27)
    
    # 测试梯度
    test_input = tf.random.normal((1, 1024))
    with tf.GradientTape() as tape:
        tape.watch(test_input)
        output = young_normal.generate_physiological_rhythm()
        loss = tf.reduce_mean(output**2)
    
    grads = tape.gradient(loss, young_normal.trainable_variables)
    grad_ok = all(g is not None for g in grads)
    print("所有梯度存在:", grad_ok)

    data_young = young_normal.generate_physiological_rhythm()
    data_elderly = elderly_overweight.generate_physiological_rhythm()
    
    # 验证年龄相关变化
    assert data_young['hrv'].std() > data_elderly['hrv'].std() * 1.2
    # 验证BMI相关变化
    assert (data_elderly['gsr'].max() - data_elderly['gsr'].min() > 
           data_young['gsr'].max() - data_young['gsr'].min())


def test_gan_augmentation():
    base_gen = BioSynthGenerator()
    pipeline = AugmentationPipeline(base_gen)
    
    # 生成原始数据
    original = base_gen.generate_physiological_rhythm()
    
    # 数据增强
    augmented = pipeline.augment(original)
    
    # 验证数据分布
    assert len(augmented) > len(original)
    assert 18 <= augmented['age'].min() <= 68
    assert 18 <= augmented['bmi'].mean() <= 28
    
    # 可视化增强效果
    plt.figure(figsize=(10,6))
    plt.scatter(augmented['age'], augmented['hrv_std'], alpha=0.3)
    plt.xlabel('Age')
    plt.ylabel('HRV Variability')
    plt.savefig('augmentation_effect.png')

# 在文件末尾添加
if __name__ == "__main__":
    print("=== 开始生理信号生成测试 ===")
    test_signal_generation()
    print("=== 测试完成 ===")