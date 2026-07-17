#!/usr/bin/env bash
# check_workers.sh — v2.2.8 worker watchdog
#
# 触发: 每 5 分钟 (launchd 调度 com.video-clipper.worker-watchdog)
# 行为:
#   1. 检查 release/beta/mix worker 进程数 < 期望 → 自动 restart
#   2. 检查 worker uptime > 7 天 → 自动 restart (防 celery clock drift 累积)
#   3. 检查 uvicorn 8000/8030 端口无人监听 → 通知
#
# 期望 worker 数:
#   - release: 3 个 celery worker (--pool=solo, -Q processing) + 1 uvicorn :8000
#   - beta:    3 个 celery worker (--pool=solo, -Q processing_beta) + 1 uvicorn :8030
#   - mix:     1 个 celery worker (--pool=solo, -Q processing_mix)
#
# v2.2.8 升级 (2026-07-17):
#   - 修 7 天不重启 worker 导致 task 派发后丢失 (celery_queue redis 清空但 db 显示 running/0%)
#   - 加 auto restart (旧版只告警不拉起, 7 天没动作)
#   - 加 7 天 uptime 检查 (force restart 防止 clock drift 累积)
#   - 加 mix worker 监控 (v2.2.3+ 才有)
#   - 修 redis db 编号 (release=0, beta=1, mix 用 beta db 1)
#   - 修 list_workers 精确匹配 (旧 grep 'processing' 误匹配 processing_beta/mix, 多启 3 个)

set -uo pipefail

LOG_FILE="/tmp/video-clipper-worker-watchdog.log"
MAX_UPTIME_DAYS=7
WORKSPACE="/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper"
START_SCRIPT_BETA="$WORKSPACE/start-beta.sh"
START_SCRIPT_RELEASE="$WORKSPACE/start-release.sh"

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" | tee -a "$LOG_FILE"
}

notify() {
    local title="$1"
    local msg="$2"
    osascript -e "display notification \"$msg\" with title \"$title\" subtitle \"$WORKSPACE\"" 2>/dev/null || true
    logger -t video-clipper-watchdog "[$title] $msg" 2>/dev/null || true
    log "ALERT: [$title] $msg"
}

# 列出特定队列的 worker
# ps aux fields: $11=python $12=celery $13=-A $14=backend... $15=worker $16=--pool=solo $17=-Q $18=QUEUE_NAME
# 用 awk $18 == "processing" 精确匹配 (不是 substring, 避免 processing_beta/mix 误匹配)
list_workers_by_queue() {
    local queue="$1"
    ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk -v q="$queue" '$18 == q {print $2}'
}

# 检查 worker uptime 天数 (ETIMED 格式 "07-02:48:08" = 7天2小时48分, 转天数)
worker_uptime_days() {
    local pid=$1
    local etime
    etime=$(ps -p "$pid" -o etime= 2>/dev/null | xargs)
    if [ -z "$etime" ]; then
        echo 999
        return
    fi
    # etime 格式: [[DD-]hh:]mm:ss
    if [[ "$etime" == *-* ]]; then
        local days="${etime%%-*}"
        echo "$days"
    else
        echo 0
    fi
}

restart_group() {
    local group_name="$1"
    local queue_name="$2"
    local expected=$3
    local start_script="$4"

    local pids
    pids=$(list_workers_by_queue "$queue_name")
    local count=0
    if [ -n "$pids" ]; then
        count=$(echo "$pids" | wc -l | tr -d ' ')
    fi

    # 检查 1: 数量
    if [ "$count" -lt "$expected" ]; then
        log "WARN: $group_name workers=$count < expected=$expected, 启动 $start_script"
        notify "Worker Watchdog" "$group_name worker 数量不足 ($count/$expected), 自动重启"
        if [ -x "$start_script" ]; then
            "$start_script" >> "$LOG_FILE" 2>&1 &
        else
            log "ERROR: $start_script 不存在或不可执行"
        fi
        return
    fi

    # 检查 2: 任意 worker uptime > 7 天 → 杀全部 group 重启
    local need_restart=0
    for pid in $pids; do
        local days
        days=$(worker_uptime_days "$pid")
        if [ "$days" -ge "$MAX_UPTIME_DAYS" ]; then
            log "WARN: $group_name worker PID=$pid uptime=${days}d > ${MAX_UPTIME_DAYS}d, 强制重启"
            need_restart=1
        fi
    done

    if [ "$need_restart" -eq 1 ]; then
        notify "Worker Watchdog" "$group_name worker uptime 超过 ${MAX_UPTIME_DAYS} 天, 强制重启 (防 celery clock drift)"
        for pid in $pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
        sleep 2
        if [ -x "$start_script" ]; then
            "$start_script" >> "$LOG_FILE" 2>&1 &
        fi
    fi
}

start_mix_worker() {
    cd "$WORKSPACE" || return 1
    unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME
    export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_mix.db"
    export CELERY_BROKER_URL="redis://localhost:6379/0"
    export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
    export CELERY_QUEUE_NAME="processing_mix"
    nohup ./.venv/bin/celery -A backend.core.celery_app worker --pool=solo -Q processing_mix -n mix1 --max-tasks-per-child=10 >> "$LOG_FILE" 2>&1 < /dev/null &
}

# === 主检查 ===

# 1. Release worker (3 expected)
restart_group "release" "processing" 3 "$START_SCRIPT_RELEASE"

# 2. Beta worker (3 expected)
restart_group "beta" "processing_beta" 3 "$START_SCRIPT_BETA"

# 3. Mix worker (1 expected) — 没有 start 脚本, inline 启
mix_pids=$(list_workers_by_queue "processing_mix")
mix_count=0
if [ -n "$mix_pids" ]; then
    mix_count=$(echo "$mix_pids" | wc -l | tr -d ' ')
fi

if [ "$mix_count" -lt 1 ]; then
    log "WARN: mix workers=$mix_count < 1, inline 启"
    notify "Worker Watchdog" "mix worker 死了, 自动重启"
    start_mix_worker
elif [ "$mix_count" -gt 1 ]; then
    # v2.2.8 修复: 之前 grep 'processing' 误匹配导致多启, 现在多就杀多余留新
    log "WARN: mix workers=$mix_count > 1, 杀多余留最新"
    # 按 PID 升序, 留最大 (新启的 PID 一般更大, 简单可靠)
    # 不用 sort -k9 (etime 格式 "Fri05PM"/"10Jul26" 排序乱)
    pids_all=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk '$18 == "processing_mix" {print $2}')
    keep=$(echo "$pids_all" | sort -n | tail -1)
    # sed '$d' = 删最后一行, BSD head -n -1 不支持, 用 sed 替代
    drop=$(echo "$pids_all" | sort -n | sed '$d')
    for pid in $drop; do
        kill -9 "$pid" 2>/dev/null || true
    done
    log "  kept PID=$keep, killed: $drop"
fi

# mix uptime 检查 (跟 release/beta 一样的 7 天)
if [ "$mix_count" -ge 1 ]; then
    for pid in $mix_pids; do
        days=$(worker_uptime_days "$pid")
        if [ "$days" -ge "$MAX_UPTIME_DAYS" ]; then
            log "WARN: mix worker PID=$pid uptime=${days}d > ${MAX_UPTIME_DAYS}d, 强制重启"
            notify "Worker Watchdog" "mix worker uptime 超过 ${MAX_UPTIME_DAYS} 天, 强制重启"
            kill -9 "$pid" 2>/dev/null || true
            sleep 2
            start_mix_worker
            break
        fi
    done
fi

# 4. Uvicorn 端口检查 (端口无人监听 = 告警, 不自动重启 — uvicorn 跟 start 脚本绑一起启)
for port in 8000 8030; do
    if ! lsof -i ":$port" > /dev/null 2>&1; then
        notify "Worker Watchdog" "uvicorn 端口 $port 无人监听"
        log "ALERT: uvicorn :$port 无人监听"
    fi
done

# 5. tick log
release_count=$(list_workers_by_queue processing | wc -l | tr -d ' ')
beta_count=$(list_workers_by_queue processing_beta | wc -l | tr -d ' ')
mix_count_now=$(list_workers_by_queue processing_mix | wc -l | tr -d ' ')
uv8000=$(lsof -i :8000 -t 2>/dev/null | wc -l | tr -d ' ')
uv8030=$(lsof -i :8030 -t 2>/dev/null | wc -l | tr -d ' ')
log "tick done: release=$release_count beta=$beta_count mix=$mix_count_now uvicorn :8000=$uv8000 :8030=$uv8030"