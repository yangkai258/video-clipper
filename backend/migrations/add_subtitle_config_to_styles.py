"""添加 subtitle_config 字段到 styles 表"""
import sqlite3
import os

# 动态获取数据库路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")

def migrate():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # 添加 subtitle_config 字段
    cursor.execute("ALTER TABLE styles ADD COLUMN subtitle_config JSON")
    
    conn.commit()
    conn.close()
    print("Migration completed: added subtitle_config column to styles table")

if __name__ == "__main__":
    migrate()
