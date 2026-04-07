#!/bin/bash

# Video Clipper 启动脚本

set -e

echo "🎬 Video Clipper 启动脚本"
echo "========================="

# 检查 Redis
echo "📦 检查 Redis..."
if ! command -v redis-cli &> /dev/null; then
    echo "❌ Redis 未安装，请先安装 Redis"
    exit 1
fi

if ! redis-cli ping &> /dev/null; then
    echo "⚠️  Redis 未运行，尝试启动..."
    redis-server --daemonize yes
    sleep 2
fi
echo "✅ Redis 运行中"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "🐍 创建 Python 虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
echo "📦 安装 Python 依赖..."
pip install -q -r requirements.txt

# 初始化数据库
echo "🗄️  初始化数据库..."
python -c "from backend.core.database import init_db; init_db()"

# 启动 Celery Worker
echo "👷 启动 Celery Worker..."
celery -A backend.core.celery_app worker --loglevel=info --concurrency=2 -Q celery,processing &
CELERY_PID=$!
echo "✅ Celery Worker PID: $CELERY_PID"

# 等待 Celery 启动
sleep 3

# 启动 FastAPI
echo "🚀 启动 FastAPI 后端..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "✅ FastAPI 后端 PID: $BACKEND_PID"

echo ""
echo "========================="
echo "✅ 后端服务已启动！"
echo "📡 API: http://localhost:8000"
echo "📚 Docs: http://localhost:8000/docs"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""

# 等待用户中断
trap "kill $CELERY_PID $BACKEND_PID 2>/dev/null; echo '服务已停止'; exit 0" INT

wait
