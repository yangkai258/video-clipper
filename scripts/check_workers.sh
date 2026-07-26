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

# v2.2.23: 拿 worker 实际 CELERY_BROKER_URL (从 ps eww 读 env)
# macOS 没 /proc/PID/environ, 用 ps eww -p PID 拿完整 env
# 返 broker 字符串 (例 redis://localhost:6379/0), 失败返 ""
worker_actual_broker() {
    local pid="$1"
    if [ -z "$pid" ]; then
        echo ""
        return
    fi
    # ps eww 输出 "PID ... ENV1=val1 ENV2=val2 ..."
    # macOS tr 拆空格 (broker url 没空格)
    ps eww -p "$pid" 2>/dev/null | tr ' ' '\n' | grep "^CELERY_BROKER_URL=" | head -1 | cut -d= -f2-
}

# v2.2.23: 拿 worker 实际 CELERY_QUEUE_NAME
worker_actual_queue() {
    local pid="$1"
    if [ -z "$pid" ]; then
        echo ""
        return
    fi
    ps eww -p "$pid" 2>/dev/null | tr ' ' '\n' | grep "^CELERY_QUEUE_NAME=" | head -1 | cut -d= -f2-
}

# v2.2.23: 检查 worker broker 一致性, 不一致返 0 (need restart), 一致返 1
# 用法: if worker_broker_mismatch "$pid" "redis://localhost:6379/0" "processing_mix"; then
worker_broker_mismatch() {
    local pid="$1"
    local expected_broker="$2"
    local expected_queue="$3"
    local actual_broker
    local actual_queue
    actual_broker=$(worker_actual_broker "$pid")
    actual_queue=$(worker_actual_queue "$pid")
    if [ "$actual_broker" != "$expected_broker" ] || [ "$actual_queue" != "$expected_queue" ]; then
        return 0  # 不一致
    fi
    return 1  # 一致
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
    # v2.2.37: 启 release + beta 各 1 个 mix worker (跟 uvicorn 模式一致)
    # 之前只启 release 1 个 (db=0/processing_mix), beta 模式混剪派发到 db=0 但 uvicorn 8030 在 beta 端,
    # worker 查 release 切片 db 找不到 beta 资源库 ID → 0 match → fail.
    # 修: dispatch 跟 env 走 (v2.2.37 mix_dispatch._resolve_*), worker 也按 uvicorn 模式启.
    cd "$WORKSPACE" || return 1
    unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME

    # release mix worker (跟 release uvicorn :8000 一致, db=0/processing_mix, 查 release 切片 db)
    export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db"
    export CELERY_BROKER_URL="redis://localhost:6379/0"
    export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
    export CELERY_QUEUE_NAME="processing_mix"
    nohup ./.venv/bin/celery -A backend.core.celery_app worker --pool=solo -Q processing_mix -n mix1 --max-tasks-per-child=10 >> "$LOG_FILE" 2>&1 < /dev/null &

    # beta mix worker (跟 beta uvicorn :8030 一致, db=1/processing_mix_beta, 查 beta 切片 db)
    unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME
    export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db"
    export CELERY_BROKER_URL="redis://localhost:6379/1"
    export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
    export CELERY_QUEUE_NAME="processing_mix_beta"
    nohup ./.venv/bin/celery -A backend.core.celery_app worker --pool=solo -Q processing_mix_beta -n mix_beta1 --max-tasks-per-child=10 >> "$LOG_FILE" 2>&1 < /dev/null &
}

# v2.2.10: inline 启 release worker (跟 start_mix_worker 同款)
# 解决: start-release.sh 要切 main + 端口检查, 经常因 uncommitted 改动 / 端口占用 拒绝跑
# watchdog 调它等于没调. 直接 inline 启 worker (uvicorn --reload 已经在跑不需要重启)
start_release_workers() {
    cd "$WORKSPACE" || return 1
    unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME
    export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper.db"
    export CELERY_BROKER_URL="redis://localhost:6379/0"
    export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
    export CELERY_QUEUE_NAME="processing"
    for n in 1 2 3; do
        nohup ./.venv/bin/celery -A backend.core.celery_app worker --pool=solo -Q processing -n release$n --max-tasks-per-child=10 >> "$LOG_FILE" 2>&1 < /dev/null &
    done
}

start_beta_workers() {
    cd "$WORKSPACE" || return 1
    unset DATABASE_URL CELERY_BROKER_URL CELERY_RESULT_BACKEND CELERY_QUEUE_NAME
    export DATABASE_URL="sqlite+aiosqlite:///./data/video_clipper_beta.db"
    export CELERY_BROKER_URL="redis://localhost:6379/1"
    export CELERY_RESULT_BACKEND="redis://localhost:6379/1"
    export CELERY_QUEUE_NAME="processing_beta"
    for n in 1 2 3; do
        nohup ./.venv/bin/celery -A backend.core.celery_app worker --pool=solo -Q processing_beta -n beta$n --max-tasks-per-child=10 >> "$LOG_FILE" 2>&1 < /dev/null &
    done
}

# v2.2.10: 端口有 uvicorn 在跑就用 inline 启 worker (避免 start-*.sh 因切 branch/端口冲突 拒绝跑)
# uvicorn 监听 -> inline 启 worker (uvicorn --reload 已经在跑不需要重启)
# uvicorn 没监听 -> 调 start-*.sh 完整启动 (大修/第一次启动)
_should_inline_workers() {
    local port=$1
    lsof -nP -iTCP:$port -sTCP:LISTEN -t 2>/dev/null | head -1 | grep -q . && return 0 || return 1
}

# === 主检查 ===

# 1. Release worker (3 expected)
#    v2.2.10: 优先 inline 启 (uvicorn :8000 在跑), 否则调 start-release.sh
release_pids=$(list_workers_by_queue "processing")
release_count=0
if [ -n "$release_pids" ]; then
    release_count=$(echo "$release_pids" | wc -l | tr -d ' ')
fi
if [ "$release_count" -lt 3 ]; then
    if _should_inline_workers 8000; then
        log "WARN: release workers=$release_count < 3, uvicorn :8000 在跑, inline 启 3 worker"
        notify "Worker Watchdog" "release worker 不足 ($release_count/3), inline 启 (uvicorn 在跑)"
        start_release_workers
    else
        restart_group "release" "processing" 3 "$START_SCRIPT_RELEASE"
    fi
else
    # v2.2.23: count 够, 验 broker 一致性 (跟 mix worker 同款)
    if worker_broker_mismatch "$(echo "$release_pids" | head -1)" "redis://localhost:6379/0" "processing"; then
        for pid in $release_pids; do
            if worker_broker_mismatch "$pid" "redis://localhost:6379/0" "processing"; then
                actual_broker=$(worker_actual_broker "$pid")
                log "WARN: release worker PID=$pid broker 不一致 (actual: $actual_broker, expected: redis://localhost:6379/0) → 杀"
                notify "Worker Watchdog" "release worker broker 不一致, 自动 restart (v2.2.23 防护)"
                kill -9 "$pid" 2>/dev/null || true
            fi
        done
        sleep 2
        if [ -z "$(list_workers_by_queue "processing")" ] && _should_inline_workers 8000; then
            start_release_workers
        fi
    else
        # count 够 + broker 一致, 7d uptime 检查走 restart_group
        restart_group "release" "processing" 3 "$START_SCRIPT_RELEASE" > /dev/null 2>&1 || true
    fi
fi

# 2. Beta worker (3 expected)
#    v2.2.10: 同样优先 inline 启
beta_pids=$(list_workers_by_queue "processing_beta")
beta_count=0
if [ -n "$beta_pids" ]; then
    beta_count=$(echo "$beta_pids" | wc -l | tr -d ' ')
fi

# v2.2.23: beta worker broker 一致性 check
if [ "$beta_count" -ge 1 ]; then
    beta_broker_mismatch_pids=""
    for pid in $beta_pids; do
        if worker_broker_mismatch "$pid" "redis://localhost:6379/1" "processing_beta"; then
            actual_broker=$(worker_actual_broker "$pid")
            log "WARN: beta worker PID=$pid broker 不一致 (actual: $actual_broker, expected: redis://localhost:6379/1) → 杀"
            beta_broker_mismatch_pids="$beta_broker_mismatch_pids $pid"
        fi
    done
    if [ -n "$beta_broker_mismatch_pids" ]; then
        notify "Worker Watchdog" "beta worker broker 不一致, 自动 restart (v2.2.23 防护)"
        for pid in $beta_broker_mismatch_pids; do
            kill -9 "$pid" 2>/dev/null || true
        done
        sleep 2
        if [ -z "$(list_workers_by_queue "processing_beta")" ] && _should_inline_workers 8030; then
            start_beta_workers
        fi
    fi
fi
if [ "$beta_count" -lt 3 ]; then
    if _should_inline_workers 8030; then
        log "WARN: beta workers=$beta_count < 3, uvicorn :8030 在跑, inline 启 3 worker"
        notify "Worker Watchdog" "beta worker 不足 ($beta_count/3), inline 启 (uvicorn 在跑)"
        start_beta_workers
    else
        restart_group "beta" "processing_beta" 3 "$START_SCRIPT_BETA"
    fi
else
    restart_group "beta" "processing_beta" 3 "$START_SCRIPT_BETA" > /dev/null 2>&1 || true
fi

# 3. Mix worker (1 expected) — 没有 start 脚本, inline 启
mix_pids=$(list_workers_by_queue "processing_mix")
mix_count=0
if [ -n "$mix_pids" ]; then
    mix_count=$(echo "$mix_pids" | wc -l | tr -d ' ')
fi

# v2.2.23: broker 一致性 check (实际 broker 跟期望 db=0 / queue=processing_mix 对比)
# 不一致 → 杀 + restart (16h 前实际踩过: 7-10 beta mode 启的 worker 跟 release env 冲突,
# task 派发到 db=0/processing_mix 但 worker 监听 db=1, 任务堆积 redis 24h TTL 清掉)
MIX_EXPECTED_BROKER="redis://localhost:6379/0"
MIX_EXPECTED_QUEUE="processing_mix"
if [ "$mix_count" -ge 1 ]; then
    for pid in $mix_pids; do
        if worker_broker_mismatch "$pid" "$MIX_EXPECTED_BROKER" "$MIX_EXPECTED_QUEUE"; then
            actual_broker=$(worker_actual_broker "$pid")
            actual_queue=$(worker_actual_queue "$pid")
            log "WARN: mix worker PID=$pid broker 不一致 (actual: $actual_broker queue=$actual_queue, expected: $MIX_EXPECTED_BROKER queue=$MIX_EXPECTED_QUEUE) → 杀 + restart"
            notify "Worker Watchdog" "mix worker broker 不一致 (db 错), 自动 restart (v2.2.23 防护)"
            kill -9 "$pid" 2>/dev/null || true
            sleep 2
            # 杀完再启 (replace in-place)
            if [ -z "$(list_workers_by_queue "processing_mix")" ]; then
                start_mix_worker
            fi
            # 重设 mix_pids (老 worker 死了, 新的可能还没 ready)
            mix_pids=$(list_workers_by_queue "processing_mix")
            mix_count=0
            if [ -n "$mix_pids" ]; then
                mix_count=$(echo "$mix_pids" | wc -l | tr -d ' ')
            fi
            break
        fi
    done
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