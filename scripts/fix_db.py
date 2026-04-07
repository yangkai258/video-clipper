#!/usr/bin/env python3
"""修复项目数据库记录 - SQLite 直接操作版"""
import json
import sqlite3
from pathlib import Path

PROJECT_ID = "37ae7c3a-63ee-4f01-aa05-9015409cc1ea"
PROJECT_DIR = Path(__file__).parent.parent / "data" / "projects" / PROJECT_ID
DB_PATH = Path(__file__).parent.parent / "data" / "video_clipper.db"

def fix_database():
    # 读取 clips 数据
    clips_path = PROJECT_DIR / "metadata" / "step2_clips.json"
    with open(clips_path, "r", encoding="utf-8") as f:
        clips_data = json.load(f)
    
    # 读取 collections 数据
    collections_path = PROJECT_DIR / "metadata" / "step3_collections.json"
    with open(collections_path, "r", encoding="utf-8") as f:
        collections_data = json.load(f)
    
    print(f"读取到 {len(clips_data)} 个 clips, {len(collections_data)} 个 collections")
    
    # 连接数据库
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 清除旧记录
        cursor.execute("DELETE FROM clips WHERE project_id = ?", (PROJECT_ID,))
        cursor.execute("DELETE FROM collections WHERE project_id = ?", (PROJECT_ID,))
        conn.commit()
        print("已清除旧记录")
        
        # 插入 clips
        for i, clip_data in enumerate(clips_data):
            clip_id = f"clip-{i+1:04d}"
            title = clip_data.get("title", f"片段 {clip_data.get('index', 1)}")
            video_path = f"output/clips/{clip_data['index']}_{title}.mp4"
            
            cursor.execute("""
                INSERT INTO clips (id, project_id, title, start_time, end_time, duration, score, video_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clip_id,
                PROJECT_ID,
                title,
                clip_data.get("start", 0),
                clip_data.get("end", 0),
                clip_data.get("duration", 0),
                clip_data.get("score", 50),
                video_path,
            ))
        
        conn.commit()
        print(f"已插入 {len(clips_data)} 个 clips")
        
        # 插入 collections
        for i, coll_data in enumerate(collections_data):
            coll_id = f"coll-{i+1:04d}"
            clip_ids = json.dumps([c["index"] for c in coll_data.get("clips", [])])
            title = coll_data.get("title", f"合集 {coll_data.get('index', 1)}")
            video_path = f"output/collections/{title}.mp4"
            
            cursor.execute("""
                INSERT INTO collections (id, project_id, title, clip_ids, video_path)
                VALUES (?, ?, ?, ?, ?)
            """, (
                coll_id,
                PROJECT_ID,
                title,
                clip_ids,
                video_path,
            ))
        
        conn.commit()
        print(f"已插入 {len(collections_data)} 个 collections")
        
        # 验证
        cursor.execute("SELECT COUNT(*) FROM clips WHERE project_id = ?", (PROJECT_ID,))
        clip_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM collections WHERE project_id = ?", (PROJECT_ID,))
        coll_count = cursor.fetchone()[0]
        
        print(f"\n✅ 验证：{clip_count} clips, {coll_count} collections")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ 错误：{e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()
