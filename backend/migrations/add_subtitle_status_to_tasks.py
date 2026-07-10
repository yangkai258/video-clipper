"""Add subtitle_status / subtitle_error to tasks table (v2.2.2 fail-tolerant subtitle).

P0 follow-up: user 报告 "切片失败" 实际是字幕识别失败 (Whisper hallucination)
导致 pipeline 终止, 但用户希望继续切视频 (不烧字幕) + task 标 completed,
字幕后续人工配. 字段:
  subtitle_status — '' | 'success' | 'failed' (字幕是否成功生成)
  subtitle_error — 失败具体原因 (RuntimeError message, 给 UI 提示 user)

Idempotent: 安全重复跑.
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
    if "subtitle_status" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN subtitle_status VARCHAR(50) DEFAULT ''")
        added.append("subtitle_status")
    if "subtitle_error" not in cols:
        cur.execute("ALTER TABLE tasks ADD COLUMN subtitle_error TEXT DEFAULT ''")
        added.append("subtitle_error")
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