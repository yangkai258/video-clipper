#!/usr/bin/env bash
# check_release_health.sh — release 端健康巡检 (worker + uvicorn + disk + orphan raw)
#
# 跟 check_workers.sh 互补:
#   check_workers.sh          → beta worker + 8030 uvicorn (老的)
#   check_release_health.sh   → release worker + 8000 uvicorn + disk + orphan raw (新的)
#   check_task_health.sh      → task 心跳 (同事 v2.2.1)
#
# 触发: 每 5 分钟 (由 launchd 调度)
# 行为:
#   1. release worker 进程数 >= 3 (1 main + 2 forkpool) 否则 ALERT
#   2. 8000 uvicorn listening 否则 ALERT
#   3. /System/Volumes/Data 磁盘使用率:
#        < 85%  : OK (静默)
#        85-95% : WARN (通知, 不处理)
#        >= 95% : CRITICAL (通知 + 自动清孤儿 raw)
#   4. 孤儿 raw 自动清理 (db 查不到 + raw mtime > 1h):
#        - 双 db 联合查 (release `data/video_clipper.db` + beta `data/video_clipper_beta.db`)
#        - 释放空间后写 log (供用户审计)
#
# 不自动重启 worker (代码 bug 自动重启没用, 留给人判断)

set -euo pipefail

# === Paths ===
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi
RELEASE_DB="$PROJECT_ROOT/data/video_clipper.db"
BETA_DB="$PROJECT_ROOT/data/video_clipper_beta.db"
PROJECTS_DIR="$PROJECT_ROOT/data/projects"

LOG_FILE="/tmp/video-clipper-release-health.log"
WARN_PCT=85
CRIT_PCT=95
ORPHAN_MIN_AGE_SEC=3600  # 1h

log() {
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$ts] $*" >> "$LOG_FILE"
}

notify() {
    local title="$1" subtitle="$2" msg="$3"
    log "ALERT [$title / $subtitle] $msg"
    osascript -e "display notification \"$msg\" with title \"$title\" subtitle \"$subtitle\"" 2>/dev/null || true
    logger -t video-clipper-release-health "[$title] $msg" 2>/dev/null || true
}

# === 1. Release worker process check ===
worker_count=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | grep -E " -Q processing( |$)" | wc -l | tr -d ' ')
if [ "$worker_count" -lt 3 ]; then
    notify "video-clipper Release" "worker 异常" "release worker 进程数=$worker_count (期望>=3), 跑 processing 队列"
fi

# === 2. Release uvicorn 8000 listening check ===
if ! lsof -i :8000 > /dev/null 2>&1; then
    notify "video-clipper Release" "uvicorn 8000" "8000 端口无人监听, 跑 bash start-release.sh 重启"
fi

# === 3. Disk usage check (APFS data volume) ===
disk_info=$(df -P /System/Volumes/Data | tail -1)
use_pct=$(echo "$disk_info" | awk '{print $5}' | tr -d '%')
avail=$(echo "$disk_info" | awk '{print $4}')

if [ "$use_pct" -ge "$CRIT_PCT" ]; then
    notify "video-clipper Release" "磁盘 CRITICAL" "Data 盘 ${use_pct}% 已用 (剩 $avail), 启动孤儿清理"
    CRIT_MODE=1
elif [ "$use_pct" -ge "$WARN_PCT" ]; then
    notify "video-clipper Release" "磁盘 WARN" "Data 盘 ${use_pct}% 已用 (剩 $avail), 关注"
    CRIT_MODE=0
else
    log "tick: disk=${use_pct}% avail=$avail OK"
    CRIT_MODE=0
fi

# === 4. Orphan raw cleanup (双 db 联合查) ===
# 仅在 CRIT (>=95%) 时自动清, 否则只 log 不清 (避免误伤)
if [ "${CRIT_MODE:-0}" = "1" ] || [ "${1:-}" = "--force-cleanup" ]; then
    log "orphan cleanup: starting (CRIT_MODE=$CRIT_MODE)"
    "$PYTHON_BIN" <<PY
import os, time, sqlite3, shutil

ROOT = "$PROJECT_ROOT"
PROJECTS_DIR = "$PROJECTS_DIR"
ORPHAN_MIN_AGE_SEC = $ORPHAN_MIN_AGE_SEC

# 双 db 联合查
# ⚠️ sqlite3.connect() 返 Connection, execute() 返 Cursor
#    必须用 cursor.fetchall(), 不能 Connection.fetchall() (会报 'Connection' object has no attribute 'fetchall')
db_ids = set()
for db_path in ["$RELEASE_DB", "$BETA_DB"]:
    if not os.path.exists(db_path):
        continue
    try:
        c = sqlite3.connect(db_path)
        cur = c.execute("SELECT id FROM projects")
        db_ids.update(r[0] for r in cur.fetchall())
        c.close()
    except Exception as e:
        print(f"  warn: {db_path} read fail: {e}")

disk_ids = set(os.listdir(PROJECTS_DIR)) if os.path.isdir(PROJECTS_DIR) else set()
orphans = disk_ids - db_ids

if not orphans:
    print("  无孤儿目录")
else:
    now = time.time()
    cleaned = 0
    freed = 0
    skipped_young = 0
    for oid in orphans:
        pdir = os.path.join(PROJECTS_DIR, oid)
        raw_dir = os.path.join(pdir, "raw")
        # 只清 raw/ (output 是产物, 可能用户在前端展示, 不动)
        if not os.path.isdir(raw_dir):
            continue
        # mtime 取 raw/input.mp4 (或 raw 目录最新文件)
        mtime = os.path.getmtime(raw_dir)
        age = now - mtime
        if age < ORPHAN_MIN_AGE_SEC:
            skipped_young += 1
            print(f"  skip young: {oid[:8]}... ({age/60:.0f}m < 1h)")
            continue
        # 算 size
        size = 0
        for root, _, files in os.walk(raw_dir):
            for f in files:
                try: size += os.path.getsize(os.path.join(root, f))
                except: pass
        # 真删
        try:
            shutil.rmtree(raw_dir, ignore_errors=True)
            cleaned += 1
            freed += size
            print(f"  cleaned raw/: {oid[:8]}... (age={age/3600:.1f}h, freed={size/1024/1024/1024:.2f}GB)")
        except Exception as e:
            print(f"  fail: {oid[:8]}...: {e}")
    print(f"  total: cleaned={cleaned} freed={freed/1024/1024/1024:.2f}GB skipped_young={skipped_young}")
PY
    log "orphan cleanup: done"
fi
