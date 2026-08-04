# 好奇心驱动的探索机制

## 核心原理

传统的强化学习依赖**外部奖励**（赢棋得1分，输棋扣1分）。但在现实世界中，奖励非常稀疏。好奇心机制能解决这个问题：**在没有外部奖励时，AI也能产生内在的动力去学习。**

### 基于预测误差的好奇心

核心公式：

$$
\mathbf{z}_{k+1} = \mathbf{z}_k + (1-\lambda) r_\theta(\mathbf{z}_k; \mathbf{x}) + \beta \varepsilon_k
$$

其中 $\varepsilon_k \sim \mathcal{N}(0, I)$ 是高斯噪声，$\lambda \in [0,1)$ 控制阻尼系数，$\beta \geq 0$ 控制噪声强度。

### 不动点残差

模型收敛性的度量：

$$
\| f_\theta(\mathbf{z}; \mathbf{x}) - \mathbf{z} \|
$$

当残差趋近于 0 时，说明模型收敛到了吸引子（attractor）。

### 双曲时间编码

$$
\text{weights} = \tanh(\alpha \cdot (1 - \frac{t}{T}))
$$

其中 $t=0$ 是入睡点，$t=T$ 是最晚时间点。

## 实验结果

在 Sudoku-Extreme 测试集上：

| 方法 | 准确率 |
|------|--------|
| Feedforward 42层 | 2.6% |
| 权重绑定 + 深度缩放 | 32.6% |
| 分段在线训练 | 74.7% |
| **EqR（本文方法）** | **99.8%** |
