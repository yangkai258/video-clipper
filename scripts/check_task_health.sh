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

set -euo pipefail

LOG_FILE="/tmp/video-clipper-task-health.log"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_FILE"
}

# 找 venv 里的 python (跟 check_workers.sh 的 worker 行为保持一致)
PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

log "tick: running backend.services.task_health"
if ! cd "$PROJECT_ROOT" && "$PYTHON_BIN" -m backend.services.task_health >> "$LOG_FILE" 2>&1; then
    msg="video-clipper task_health 自身跑挂了, 看 $LOG_FILE"
    log "ERROR: $msg"
    osascript -e "display notification \"$msg\" with title \"video-clipper Task Health\"" 2>/dev/null || true
fi
