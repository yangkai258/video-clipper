"""添加 subtitle_config 字段到 styles 表"""
import sqlite3
import os

# 动态获取数据库路径
# v2.2.13 fix: 4 层 dirname 算到 workspace 父目录 (错的), 改 3 层
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")

def migrate():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    # v2.2.13: idempotent — 列已存在跳过 (老 migration 第二次跑会 "duplicate column")
    cursor.execute("PRAGMA table_info(styles)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    if "subtitle_config" not in existing_cols:
        cursor.execute("ALTER TABLE styles ADD COLUMN subtitle_config JSON")
        conn.commit()
        print("Migration completed: added subtitle_config column to styles table")
    else:
        print("Migration skipped: subtitle_config column already exists")
    conn.close()

if __name__ == "__main__":
    migrate()
