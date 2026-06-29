#!/bin/bash
# 测试版启动脚本 (v1.1-beta)
# 使用独立数据库和 Redis，与正式版完全隔离

set -e

cd "$(dirname "$0")"

# === Git 分支切换 ===
TARGET_BRANCH="beta"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ "$CURRENT_BRANCH" != "$TARGET_BRANCH" ]; then
    echo "🔀 当前在 $CURRENT_BRANCH 分支，切到 $TARGET_BRANCH..."
    if ! git diff-index --quiet HEAD --; then
        echo "❌ 错误：工作区有未提交的改动，无法切分支"
        echo "   解决：先 git add + git commit，或者 git stash"
        echo "   查看：git status"
        exit 1
    fi
    git checkout "$TARGET_BRANCH"
    echo "✅ 已切到 $TARGET_BRANCH 分支"
fi

# ⚠️ 先清掉可能干扰的 .env 配置（避免默认值覆盖脚本里的 export）
unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME VITE_PORT VITE_API_PORT

# 测试版配置
export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db"
export CELERY_BROKER_URL="redis://localhost:6379/1"
export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
export CELERY_QUEUE_NAME="processing_beta"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_DOWNLOAD_TIMEOUT=60
export VITE_PORT="3030"
export VITE_API_PORT="8030"
# v2.1.51: 显式传入 version, 不依赖 git describe 分支拓扑歧义
# beta HEAD 当前指向 v2.1.50, 后续 commit 跑完会 bump 到 v2.1.51+
export VITE_APP_VERSION="v2.1.52"  # ponytail: v2.1.50->v2.1.52, 跟 main HEAD 896b733 同步 (P0/P1 修复后没 bump)

# === Sanity check ===
echo "============================================"
echo "  🧪 启动测试版 (Beta)"
echo "============================================"
echo "📦 数据库:    $DATABASE_URL"
echo "📡 Redis:     $CELERY_BROKER_URL"
echo "🛰️  队列:     $CELERY_QUEUE_NAME"
echo "🌐 前端端口:  $VITE_PORT"
echo "🔌 后端端口:  $VITE_API_PORT"
echo "============================================"

# 检查端口占用
if lsof -ti:8030 > /dev/null 2>&1; then
    echo "❌ 错误：8030 端口已被占用（可能已经有服务在跑）"
    echo "   解决：bash stop-beta.sh 或者 pkill -9 -f 'uvicorn.*8030'"
    exit 1
fi
if lsof -ti:3030 > /dev/null 2>&1; then
    echo "⚠️  警告：3030 端口已被占用（前端可能冲突）"
fi

# 检查数据库文件是否存在
DB_FILE=$(echo "$DATABASE_URL" | sed 's|.*///||')
if [ ! -f "$DB_FILE" ]; then
    echo "❌ 错误：数据库文件不存在：$DB_FILE"
    exit 1
fi
echo "✅ 数据库文件存在：$DB_FILE"

echo ""
echo "🚀 启动测试版后端 (8030)..."
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8030 > logs/backend_beta.log 2>&1 &
BACKEND_PID=$!

echo "🚀 启动测试版 Worker..."
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python -m celery -A backend.core.celery_app worker --loglevel=info --concurrency=5 -Q processing_beta > logs/celery_worker_beta.log 2>&1 &
WORKER_PID=$!

# 等待 Worker 启动完成
sleep 3

# === Sanity check: 验证 Worker 真的连上了对的 Redis db ===
# （之前用 nohup 启 worker 时没 export 环境变量，导致 worker 走 db 0 默认
#   而 uvicorn 把任务发到 db 1，任务卡 8 小时没人接）
WORKER_DB=$(grep -oE 'redis://[^/]+/[0-9]+' logs/celery_worker_beta.log | head -1 | grep -oE '/[0-9]+$')
EXPECTED_DB=$(echo "$CELERY_BROKER_URL" | grep -oE '/[0-9]+$')
if [ -n "$WORKER_DB" ] && [ -n "$EXPECTED_DB" ] && [ "$WORKER_DB" != "$EXPECTED_DB" ]; then
    echo ""
    echo "❌❌❌ 严重：Worker 连的 Redis db (${WORKER_DB}) 跟 uvicorn (${EXPECTED_DB}) 不一致！"
    echo "   任务会被发到 ${EXPECTED_DB}，但 Worker 永远从 ${WORKER_DB} 消费"
    echo "   原因：Worker 启动时 CELERY_BROKER_URL 没传进去（env 缺失）"
    echo "   修复：请用 bash start-beta.sh 启动（不要 nohup 手启）"
    echo ""
    pkill -9 -f 'celery.*processing_beta' 2>/dev/null
    exit 1
fi
echo "✅ Worker Redis db 校验通过：${WORKER_DB}"

echo "🚀 预加载 faster-whisper 模型..."
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python scripts/preload_whisper_model.py base > /dev/null 2>&1 &

echo "🚀 启动测试版前端 (3030)..."
cd frontend && npm run dev -- --config vite.config.beta.js --port 3030 > ../logs/frontend_beta.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "============================================"
echo "  ✅ 测试版服务已启动"
echo "============================================"
echo "   后端 PID: $BACKEND_PID (http://localhost:8030)"
echo "   Worker PID: $WORKER_PID"
echo "   前端 PID: $FRONTEND_PID (http://localhost:3030)"
echo ""
echo "📋 验证：在浏览器打开 http://localhost:3030"
echo "🛑 停止：pkill -9 -f 'uvicorn.*8030' ; pkill -9 -f 'celery.*processing_beta' ; pkill -9 -f 'vite.*3030'"
echo "============================================"

wait