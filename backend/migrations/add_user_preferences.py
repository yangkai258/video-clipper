"""添加 user_preferences 表"""

import os
import sqlite3

# 动态获取数据库路径
# 项目根目录 (video-clipper/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")


def migrate():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # 创建 user_preferences 表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT DEFAULT 'default',
            last_used_subtitle_style TEXT DEFAULT '{}',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            UNIQUE(user_id)
        )
    """)

    # 插入默认用户记录（如果不存在）
    cursor.execute("""
        INSERT OR IGNORE INTO user_preferences (user_id, last_used_subtitle_style)
        VALUES ('default', '{}')
    """)

    conn.commit()
    conn.close()
    print("Migration completed: user_preferences table created")


if __name__ == "__main__":
    migrate()
