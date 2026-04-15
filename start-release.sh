#!/bin/bash
# 正式版启动脚本 (v1.0)
# 使用正式数据库和 Redis DB 0

cd "$(dirname "$0")"

export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
export CELERY_QUEUE_NAME="processing"

# 前端配置
export VITE_PORT="3000"
export VITE_API_PORT="8000"

echo "🚀 启动正式版后端 (8000)..."
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "🚀 启动正式版 Worker..."
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q processing &
WORKER_PID=$!

# 等待 Worker 启动完成
sleep 3

echo "🚀 预加载 faster-whisper 模型..."
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python scripts/preload_whisper_model.py tiny &

echo "🚀 启动正式版前端 (3000)..."
cd frontend && npm run dev -- --port 3000 &
FRONTEND_PID=$!

echo "✅ 正式版服务已启动"
echo "   后端 PID: $BACKEND_PID"
echo "   Worker PID: $WORKER_PID"
echo "   前端 PID: $FRONTEND_PID"
echo "   前端：http://localhost:3000"
echo "   后端：http://localhost:8000"

wait
