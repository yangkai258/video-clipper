"""Add pre/post padding seconds to styles table (v2.2.1).

User ask: 把 padding 放到 Style 表 (不是 Project), 这样切所有片选同一
风格都用同样的 padding。

字段:
  pre_padding_seconds  — 切片前 padding (默认 10.0s, 用户偏好)
  post_padding_seconds — 切片后 padding (默认 5.0s, 用户偏好)

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
    cur.execute("PRAGMA table_info(styles)")
    cols = {row[1] for row in cur.fetchall()}

    added = []
    if "pre_padding_seconds" not in cols:
        # 默认 10.0s (用户偏好)
        cur.execute("ALTER TABLE styles ADD COLUMN pre_padding_seconds FLOAT DEFAULT 10.0")
        cur.execute("UPDATE styles SET pre_padding_seconds = 10.0 WHERE pre_padding_seconds IS NULL")
        added.append("pre_padding_seconds")
    if "post_padding_seconds" not in cols:
        # 默认 5.0s (用户偏好)
        cur.execute("ALTER TABLE styles ADD COLUMN post_padding_seconds FLOAT DEFAULT 5.0")
        cur.execute("UPDATE styles SET post_padding_seconds = 5.0 WHERE post_padding_seconds IS NULL")
        added.append("post_padding_seconds")
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