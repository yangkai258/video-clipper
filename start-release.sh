#!/bin/bash
# 正式版启动脚本 (v1.0)
# 使用正式数据库和 Redis DB 0

set -e

cd "$(dirname "$0")"

# === Git 分支切换 ===
TARGET_BRANCH="main"
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

# 正式版配置
export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db"
export CELERY_BROKER_URL="redis://localhost:6379/0"
export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
export CELERY_QUEUE_NAME="processing"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_DOWNLOAD_TIMEOUT=60
export VITE_PORT="3000"
export VITE_API_PORT="8000"
# v2.1.51: 显式传入 version
# main HEAD 实际没 tag (HEAD 在 v2.0 tag 之后 + 几个 fix), 走 v2.0 + 后续 fix
# 等下次正式 release 时 bump
export VITE_APP_VERSION="v2.1.53"  # v2.0->v2.1.53, 跟 beta 同步

# === Sanity check ===
echo "============================================"
echo "  🎬 启动正式版 (Release)"
echo "============================================"
echo "📦 数据库:    $DATABASE_URL"
echo "📡 Redis:     $CELERY_BROKER_URL"
echo "🛰️  队列:     $CELERY_QUEUE_NAME"
echo "🌐 前端端口:  $VITE_PORT"
echo "🔌 后端端口:  $VITE_API_PORT"
echo "============================================"

# 检查端口占用
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "❌ 错误：8000 端口已被占用（可能已经有服务在跑）"
    echo "   解决：bash stop-release.sh 或者 pkill -9 -f 'uvicorn.*8000'"
    exit 1
fi
if lsof -ti:3000 > /dev/null 2>&1; then
    echo "⚠️  警告：3000 端口已被占用（前端可能冲突）"
fi

# 检查数据库文件是否存在
DB_FILE=$(echo "$DATABASE_URL" | sed 's|.*///||')
if [ ! -f "$DB_FILE" ]; then
    echo "❌ 错误：数据库文件不存在：$DB_FILE"
    exit 1
fi
echo "✅ 数据库文件存在：$DB_FILE"

echo ""
echo "🚀 启动正式版后端 (8000)..."
# v2.2.1+: --workers 4 多 process 并发处理 upload chunk
# 旧单 worker: 1 个 chunk 慢 (SSD GC pause 200-500ms) 阻塞所有 6 个并发 chunk
# 新 4 worker: 4 个 event loop 独立, 1 个 worker 慢不影响其他
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4 > logs/backend_release.log 2>&1 &
BACKEND_PID=$!

echo "🚀 启动正式版 Worker..."
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python -m celery -A backend.core.celery_app worker --loglevel=info --pool=solo -Q processing > logs/celery_worker.log 2>&1 &
WORKER_PID=$!

# 等待 Worker 启动完成
sleep 3

# === Sanity check: 验证 Worker 真的连上了对的 Redis db ===
WORKER_DB=$(grep -oE 'redis://[^/]+/[0-9]+' logs/celery_worker.log | head -1 | grep -oE '/[0-9]+$')
EXPECTED_DB=$(echo "$CELERY_BROKER_URL" | grep -oE '/[0-9]+$')
if [ -n "$WORKER_DB" ] && [ -n "$EXPECTED_DB" ] && [ "$WORKER_DB" != "$EXPECTED_DB" ]; then
    echo ""
    echo "❌❌❌ 严重：Worker 连的 Redis db (${WORKER_DB}) 跟 uvicorn (${EXPECTED_DB}) 不一致！"
    echo "   原因：Worker 启动时 CELERY_BROKER_URL 没传进去（env 缺失）"
    echo "   修复：请用 bash start-release.sh 启动（不要 nohup 手启）"
    echo ""
    pkill -9 -f 'celery.*processing ' 2>/dev/null
    exit 1
fi
echo "✅ Worker Redis db 校验通过：${WORKER_DB}"

echo "🚀 预加载 faster-whisper 模型..."
/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/.venv/bin/python scripts/preload_whisper_model.py base > /dev/null 2>&1 &

echo "🚀 启动正式版前端 (3000)..."
cd frontend && rm -rf node_modules/.vite && npm run dev -- --port 3000 > ../logs/frontend_release.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo ""
echo "============================================"
echo "  ✅ 正式版服务已启动"
echo "============================================"
echo "   后端 PID: $BACKEND_PID (http://localhost:8000)"
echo "   Worker PID: $WORKER_PID"
echo "   前端 PID: $FRONTEND_PID (http://localhost:3000)"
echo ""
echo "📋 验证：在浏览器打开 http://localhost:3000"
echo "🛑 停止：pkill -9 -f 'uvicorn.*8000' ; pkill -9 -f 'celery.*processing' ; pkill -9 -f 'vite.*3000'"
echo "============================================"

wait