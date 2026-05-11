cd ~/aisleepgen

# 下载所有缺失的核心依赖
curl -sL -o asyncio_server.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/asyncio_server.py"
curl -sL -o dp_router.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/dp_router.py"
curl -sL -o cognitive_belief.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/cognitive_belief.py"
curl -sL -o chat_prompt_builder.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/chat_prompt_builder.py"
curl -sL -o dp_data.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/dp_data.py"
curl -sL -o experiment_log.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/experiment_log.py"
curl -sL -o async_pipeline.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/async_pipeline.py"
curl -sL -o profile_storage.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/profile_storage.py"
curl -sL -o fallback_replies.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/fallback_replies.py"
curl -sL -o body_context.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/body_context.py"
curl -sL -o prediction_engine.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/prediction_engine.py"
curl -sL -o neural_extractor.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/neural_extractor.py"
curl -sL -o decision_explainer.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/decision_explainer.py"
curl -sL -o sleep_coach.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/sleep_coach.py"
curl -sL -o pomdp_learner.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/pomdp_learner.py"
curl -sL -o sleep_world_model.py "https://raw.githubusercontent.com/znsyhandao/aisleepgen-server/main/sleep_world_model.py"

# 验证所有文件
echo "=== 已下载的文件 ==="
for f in asyncio_server.py dp_router.py cognitive_belief.py chat_prompt_builder.py dp_data.py experiment_log.py async_pipeline.py profile_storage.py fallback_replies.py body_context.py prediction_engine.py neural_extractor.py decision_explainer.py sleep_coach.py pomdp_learner.py sleep_world_model.py; do
    if [ -f "$f" ]; then
        size=$(wc -c < "$f")
        echo "  $f: ${size} bytes"
    else
        echo "  $f: MISSING!"
    fi
done

echo ""
echo "如果所有文件都存在，启动新服务:"
echo "  screen -S sleep -X quit; sleep 1"
echo "  screen -dmS sleep bash -c 'cd ~/aisleepgen && python3 -B -X utf8 asyncio_server.py'"
echo "  sleep 3; curl -s http://localhost:8090/health"
