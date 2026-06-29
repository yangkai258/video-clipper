"""Add progress_changed_at to tasks table (P0#2 watchdog fix).

v2.1.18 (a146818) introduced _cleanup_stuck_tasks that used a hard 30min
cutoff from created_at, which falsely killed 1GB / 3.6h videos that were
still cutting clips (real time: 50-60min).

This migration adds progress_changed_at so task_health.py can do real
heartbeat-based detection: only mark tasks failed when their progress
has been stale for >30min, not just because they are old.

Backfill: existing running tasks get progress_changed_at = started_at
(if set) or created_at - gives the watchdog a sensible fallback for
tasks that were already running when this migration ran.

Idempotent: safe to run multiple times.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")
# ponytail: beta env runs same migration against a different db filename
BETA_DB = os.path.join(BASE_DIR, "data", "video_clipper_beta.db")


def _migrate_one(path):
    if not os.path.exists(path):
        print(f"  skip (not found): {path}")
        return
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tasks)")
    cols = {row[1] for row in cur.fetchall()}
    if "progress_changed_at" in cols:
        print(f"  already has column: {path}")
        conn.close()
        return
    cur.execute("ALTER TABLE tasks ADD COLUMN progress_changed_at TIMESTAMP")
    cur.execute("""
        UPDATE tasks
        SET progress_changed_at = COALESCE(started_at, created_at)
        WHERE status = "running"
    """)
    conn.commit()
    print(f"  + progress_changed_at added, backfilled: {path}")
    conn.close()


def migrate():
    for db in (DATABASE_PATH, BETA_DB):
        _migrate_one(db)


if __name__ == "__main__":
    migrate()
