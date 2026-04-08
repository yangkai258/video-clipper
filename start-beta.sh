#!/bin/bash
# 测试版启动脚本 (v1.1-beta)
# 使用独立数据库和 Redis，与正式版完全隔离

cd "$(dirname "$0")"

export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
export CELERY_QUEUE_NAME="processing_beta"

echo "🚀 启动测试版后端 (8030)..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8030 &
BACKEND_PID=$!

echo "🚀 启动测试版 Worker..."
python3 -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing_beta &
WORKER_PID=$!

echo "✅ 测试版服务已启动"
echo "   后端 PID: $BACKEND_PID"
echo "   Worker PID: $WORKER_PID"
echo "   前端：http://localhost:3030"
echo "   后端：http://localhost:8030"

wait
