#!/bin/bash
# 启动 Redis 容器（正式版 + 测试版）

cd "$(dirname "$0")"

echo "🐳 启动 Redis 容器..."
echo ""

# 启动正式版 Redis
if docker ps | grep -q vc-redis-release; then
  echo "✅ 正式版 Redis 已运行 (6379)"
else
  echo "🚀 启动正式版 Redis..."
  docker run -d --name vc-redis-release \
    -p 6379:6379 \
    -v $(pwd)/redis_release_data:/data \
    redis:7-alpine
  echo "✅ 正式版 Redis 已启动"
fi

# 启动测试版 Redis
if docker ps | grep -q vc-redis-beta; then
  echo "✅ 测试版 Redis 已运行 (6380)"
else
  echo "🚀 启动测试版 Redis..."
  docker run -d --name vc-redis-beta \
    -p 6380:6379 \
    -v $(pwd)/redis_beta_data:/data \
    redis:7-alpine
  echo "✅ 测试版 Redis 已启动"
fi

echo ""
echo "📊 Redis 状态:"
docker ps --filter "name=vc-redis" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

echo ""
echo "✅ Redis 已就绪"
echo "  正式版：localhost:6379"
echo "  测试版：localhost:6380"
