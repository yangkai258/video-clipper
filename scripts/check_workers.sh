#!/usr/bin/env bash
# check_workers.sh — 检查 worker 进程数, 不够就发通知
#
# 触发: 每 5 分钟 (由 launchd 调度)
# 行为: 检查 celery worker 进程数, 期望 >= 6 (1 main + 5 forkpool)
#        如果 < 6, 写日志 + 调 macOS 系统通知 + 写 systemd-style log
#        (不再自动重启 — 留给人判断, 因为可能是代码 bug, 重启没用)

set -euo pipefail

LOG_FILE="/tmp/video-clipper-worker-watchdog.log"
EXPECTED_MIN=6  # 1 main + 5 forkpool workers

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_FILE"
}

# 检查 beta worker (处理 processing_beta 队列)
beta_count=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | grep "processing_beta" | wc -l | tr -d ' ')
beta_ready=$(redis-cli -n 3 LLEN processing_beta 2>/dev/null | tr -d ' ')

log "watchdog tick: beta workers=$beta_count queue_depth=$beta_ready expected>=$EXPECTED_MIN"

if [ "$beta_count" -lt "$EXPECTED_MIN" ]; then
    msg="⚠️ video-clipper beta worker 死了! 当前进程数=$beta_count (期望>=$EXPECTED_MIN), 队列堆积=$beta_ready"
    log "ALERT: $msg"
    # macOS 桌面通知
    osascript -e "display notification \"$msg\" with title \"video-clipper Worker Watchdog\" subtitle \"beta 环境\"" 2>/dev/null || true
    # 写标准 log 方便聚合
    logger -t video-clipper-watchdog "$msg" 2>/dev/null || true
    # 不自动重启 — 让用户看 error_message 判断是代码 bug 还是资源问题
fi

# 检查 uvicorn 8030 端口
if ! lsof -i :8030 > /dev/null 2>&1; then
    msg="⚠️ video-clipper beta uvicorn 8030 端口无人监听"
    log "ALERT: $msg"
    osascript -e "display notification \"$msg\" with title \"video-clipper Worker Watchdog\" subtitle \"beta uvicorn\"" 2>/dev/null || true
fi