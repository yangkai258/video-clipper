#!/bin/bash
# 正式版启动脚本 (v1.0)
# 使用正式数据库和 Redis DB 0

cd "$(dirname "$0")"

export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
export CELERY_QUEUE_NAME="processing"

echo "🚀 启动正式版后端 (8000)..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "🚀 启动正式版 Worker..."
python3 -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing &
WORKER_PID=$!

echo "✅ 正式版服务已启动"
echo "   后端 PID: $BACKEND_PID"
echo "   Worker PID: $WORKER_PID"
echo "   前端：http://localhost:3000"
echo "   后端：http://localhost:8000"

wait
