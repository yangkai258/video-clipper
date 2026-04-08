#!/bin/bash
# 一键启动正式版和测试版

cd "$(dirname "$0")"

echo "🚀 启动 Video Clipper 双版本..."
echo ""

# 启动正式版
echo "=== 正式版 v1.0 ==="
./start-release.sh &
RELEASE_PID=$!

sleep 5

# 启动测试版
echo ""
echo "=== 测试版 v1.1-beta ==="
./start-beta.sh &
BETA_PID=$!

echo ""
echo "✅ 两个版本已启动"
echo ""
echo "访问地址："
echo "  正式版：http://localhost:3000"
echo "  测试版：http://localhost:3030"
echo ""
echo "按 Ctrl+C 停止所有服务"

wait
