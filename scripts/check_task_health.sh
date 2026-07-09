#!/usr/bin/env bash
# check_task_health.sh — task-level watchdog (complements check_workers.sh)
#
# check_workers.sh  = 进程层 (worker 还活着没)
# check_task_health = task  层 (task 还正常推进没)
# 两个交叉: 进程死 + task 卡 = 真正卡死, 自动标 failed
#
# 触发: 每 5 分钟 (由 launchd 调度)
# 行为: 调 backend.services.task_health.check_stuck_tasks
#       - mode 1: started_at 空 + created_at > 5min  -> no_worker_pickup
#       - mode 2: progress_changed_at > 30min 没动  -> no_progress_update
#       真卡死的标 failed, project 改 pending (用户可重试)
#       跑双 db (release + beta) — 双环境共享 watchdog
#         release: data/video_clipper.db (default)
#         beta:    data/video_clipper_beta.db (跟 8030 端口 beta worker 走同 db)

set -euo pipefail

LOG_FILE="/tmp/video-clipper-task-health.log"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_FILE"
}

# 找 venv 里的 python (跟 check_workers.sh 的 worker 行为保持一致)
PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

# 跑双 db (默认 release + beta) — 切 DATABASE_URL 让 backend.services.task_health 选 db
for db_label in release beta; do
    if [ "$db_label" = "release" ]; then
        db_path="$PROJECT_ROOT/data/video_clipper.db"
    else
        db_path="$PROJECT_ROOT/data/video_clipper_beta.db"
    fi
    if [ ! -f "$db_path" ]; then
        log "skip: $db_label db 不存在 ($db_path)"
        continue
    fi

    log "tick [$db_label]: running backend.services.task_health"
    # ⚠️ 不能用 DATABASE_URL=... python -m ... 因为环境变量同步不进去
    # 用一个临时 wrapper 脚本注入 env 然后调 backend.services.task_health
    # 简单做法: 改 export DATABASE_URL 然后跑
    if ! export DATABASE_URL="sqlite+aiosqlite:///$db_path" \
        && cd "$PROJECT_ROOT" \
        && "$PYTHON_BIN" -m backend.services.task_health >> "$LOG_FILE" 2>&1; then
        msg="video-clipper task_health [$db_label] 自身跑挂了, 看 $LOG_FILE"
        log "ERROR: $msg"
        osascript -e "display notification \"$msg\" with title \"video-clipper Task Health\"" 2>/dev/null || true
    fi
done
