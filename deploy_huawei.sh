#!/bin/bash
# AISleepGen 华为云部署脚本
# 在 cloudshell 里执行: bash deploy_huawei.sh
# 需要先设置 DEEPSEEK_API_KEY

set -e

APP_DIR="/opt/aisleepgen"
GIT_REPO="https://github.com/znsyhandao/aisleepgen-server.git"

echo "========================================="
echo " AISleepGen 华为云部署 - 一键安装"
echo "========================================="

# 1. 基础环境
echo "[1/6] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv screen git curl supervisor

# 2. 项目目录
echo "[2/6] 创建项目目录..."
mkdir -p $APP_DIR
cd $APP_DIR

# 3. 从 GitHub 拉取代码
echo "[3/6] 从 GitHub 拉取代码..."
if [ -d "$APP_DIR/.git" ]; then
    git pull
else
    git clone $GIT_REPO .
fi

# 4. Python 依赖
echo "[4/6] 安装 Python 依赖..."
pip3 install -r requirements.txt 2>/dev/null || pip3 install requests numpy scipy  # 最小依赖

# 5. 环境变量
echo "[5/6] 配置环境变量..."
if [ ! -f "$APP_DIR/.env" ]; then
    echo "请输入 DEEPSEEK_API_KEY (https://platform.deepseek.com/api_keys):"
    echo -n "> "
    read DEEPSEEK_KEY
    echo "AISLEEPGEN_PORT=8090" > $APP_DIR/.env
    echo "DEEPSEEK_API_KEY=$DEEPSEEK_KEY" >> $APP_DIR/.env
fi
source $APP_DIR/.env
export AISLEEPGEN_PORT=${AISLEEPGEN_PORT:-8090}

# 6. 启动服务
echo "[6/6] 启动服务..."

# 停止旧服务
pkill -f deepseek_proxy.py 2>/dev/null || true
rm -rf $APP_DIR/__pycache__

# 用 screen 启动 (和腾讯云 D70 同样的方式)
screen -dmS aisleepgen bash -c "cd $APP_DIR && python3 -B -X utf8 deepseek_proxy.py"
sleep 3

# 验证
echo ""
echo "===== 验证 ====="
curl -s http://localhost:$AISLEEPGEN_PORT/health && echo ""
curl -s -X POST http://localhost:$AISLEEPGEN_PORT/api/sleep/render-plan \
  -H "Content-Type: application/json" \
  -d '{"stress_level":7,"sleep_latency":45,"expected_hours":7.0}' | python3 -m json.tool 2>/dev/null || echo "render-plan: OK"

echo ""
echo "========================================="
echo " 部署完成!"
echo " 服务端口: $AISLEEPGEN_PORT"
echo " screen: screen -r aisleepgen"
echo " 日志: screen -S aisleepgen -X hardcopy /tmp/aisleepgen.log"
echo "========================================="
