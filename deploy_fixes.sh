#!/bin/bash
# AISleepGen 修复部署脚本
# 将本地修复推送到 D70 生产服务器并重启

set -e

D70_HOST="82.156.208.245"
D70_USER="ubuntu"
D70_PATH="/opt/aisleepgen"

echo "=== 部署修复到 D70 ($D70_HOST) ==="

# 1. 推送更新的文件
echo "[1/4] 推送 deepseek_proxy.py..."
scp deepseek_proxy.py "$D70_USER@$D70_HOST:$D70_PATH/"

echo "[2/4] 推送 sleep_world_model.py..."
scp sleep_world_model.py "$D70_USER@$D70_HOST:$D70_PATH/"

# 2. 清理缓存
echo "[3/4] 清理缓存..."
ssh "$D70_USER@$D70_HOST" "find $D70_PATH -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null; find $D70_PATH -name '*.pyc' -delete"

# 3. 重启服务
echo "[4/4] 重启 deepseek_proxy..."
ssh "$D70_USER@$D70_HOST" "sudo supervisorctl restart aisleepgen 2>/dev/null || (sudo pkill -f deepseek_proxy.py; cd $D70_PATH && nohup python3 -u deepseek_proxy.py > /dev/null 2>&1 &)"

# 4. 验证
sleep 3
echo "[验证] 检查服务状态..."
ssh "$D70_USER@$D70_HOST" "ps aux | grep deepseek_proxy | grep -v grep | head -1"
curl -s "http://$D70_HOST:8090/health"

echo ""
echo "=== 部署完成 ==="
