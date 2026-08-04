# Auto-deploy script for server
# Run: bash _server_deploy.sh

cd ~/aisleepgen

echo "[SERVER] Downloading files..."
curl -sL -o deepseek_proxy.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/deepseek_proxy.py"
curl -sL -o tier_recommender.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/tier_recommender.py"

echo "[SERVER] Verifying files..."
ls -la deepseek_proxy.py tier_recommender.py

echo "[SERVER] Stopping old service..."
pkill -f deepseek_proxy.py 2>/dev/null
sleep 1

echo "[SERVER] Cleaning cache..."
rm -rf __pycache__

echo "[SERVER] Starting new service..."
screen -dmS sleep bash -c 'cd ~/aisleepgen && python3 -B -X utf8 deepseek_proxy.py'
sleep 3

echo "[SERVER] Verifying API..."
curl -s http://localhost:8090/health
echo ""
curl -s -X POST http://localhost:8090/api/recommend-tier -H "Content-Type: application/json" -d '{"openid":"test123"}'
echo ""
echo "[SERVER] DONE"
