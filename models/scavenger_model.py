# scavenger_model.py
import tensorflow as tf
from tensorflow.keras import layers, models
import numpy as np

class ScavengerEfficiencyModel:
    """基于 Transformer 的清道夫效率模型"""
    
    def __init__(self, input_dims: dict):
        """初始化模型"""
        self.input_dims = input_dims
        self.model = self._build_model()
        
    def _build_model(self):
        """构建模型架构"""
        # 输入层
        inputs = {}
        for sensor, dim in self.input_dims.items():
            inputs[sensor] = layers.Input(shape=(dim,), name=f"{sensor}_input")
        
        # 特征嵌入
        embeddings = []
        for sensor, input_tensor in inputs.items():
            embedding = layers.Dense(64, activation='relu')(input_tensor)
            embedding = layers.Reshape((1, 64))(embedding)  # 添加序列维度
            embeddings.append(embedding)
        
        # 融合所有嵌入
        fused = layers.Concatenate(axis=1)(embeddings)
        
        # Transformer 编码器
        transformer = layers.MultiHeadAttention(num_heads=4, key_dim=64)(
            fused, fused, fused
        )
        transformer = layers.LayerNormalization()(transformer)
        transformer = layers.Dense(128, activation='relu')(transformer)
        transformer = layers.GlobalAveragePooling1D()(transformer)
        
        # 预测头
        output = layers.Dense(64, activation='relu')(transformer)
        output = layers.Dense(32, activation='relu')(output)
        output = layers.Dense(1, activation='sigmoid')(output)
        output = layers.Lambda(lambda x: x * 100)(output)  # 缩放到 0-100
        
        # 构建模型
        model = models.Model(inputs=inputs, outputs=output)
        model.compile(
            optimizer='adam',
            loss='mse',
            metrics=['mae']
        )
        
        return model
        
    def train(self, train_data, val_data, epochs=50, batch_size=32):
        """训练模型"""
        history = self.model.fit(
            train_data,
            validation_data=val_data,
            epochs=epochs,
            batch_size=batch_size
        )
        return history
        
    def predict(self, data):
        """预测清道夫效率"""
        return self.model.predict(data)
        
    def save(self, path):
        """保存模型"""
        self.model.save(path)
        
    @classmethod
    def load(cls, path):
        """加载模型"""
        model = tf.keras.models.load_model(path)
        instance = cls({})
        instance.model = model
        return instance
