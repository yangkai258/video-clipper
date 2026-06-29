"""Add estimated/actual total seconds to tasks table (v2.2.1 数据归集).

P0#1 ask: 用户希望归集 预估总时长 vs 实际总耗时, 后续运营层用这俩
字段 + 视频时长 + 输出 clip 数 等做模型, 得更准的预估。

字段:
  estimated_total_at_start_seconds — task 启动时 (progress=0), 用
    _estimate_eta_seconds(video_duration) 算一次, 存起来
    (避免 progress 涨时 total_estimated_seconds 跟着涨, 无法做"启动
    时以为多久 / 实际多久"对比)

  actual_total_seconds — task 跑完时 (step 10), completed_at -
    started_at 的真实秒数

P0#2 follow-up: 完成时, ProjectCard / ProjectDetail 显示
"预估 X / 实际 Y", 用户能直观看出预估准不准。

Idempotent: 安全重复跑。
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")
BETA_DB = os.path.join(BASE_DIR, "data", "video_clipper_beta.db")


def _migrate_one(path):
    if not os.path.exists(path):
        print(f"  skip (not found): {path}")
        return
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(tasks)")
    cols = {row[1] for row in cur.fetchall()}

    added = []
    if "estimated_total_at_start_seconds" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN estimated_total_at_start_seconds FLOAT")
        added.append("estimated_total_at_start_seconds")
    if "actual_total_seconds" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN actual_total_seconds FLOAT")
        added.append("actual_total_seconds")
    conn.commit()
    if added:
        print(f"  + added: {', '.join(added)}  ({path})")
    else:
        print(f"  already has both columns: {path}")
    conn.close()


def migrate():
    for db in (DATABASE_PATH, BETA_DB):
        _migrate_one(db)


if __name__ == "__main__":
    migrate()