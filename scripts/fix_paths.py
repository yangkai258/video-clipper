#!/usr/bin/env python3
"""修复数据库视频路径 - 匹配实际文件名"""
import sqlite3
from pathlib import Path

PROJECT_ID = "37ae7c3a-63ee-4f01-aa05-9015409cc1ea"
PROJECT_DIR = Path(__file__).parent.parent / "data" / "projects" / PROJECT_ID
DB_PATH = Path(__file__).parent.parent / "data" / "video_clipper.db"
CLIPS_DIR = PROJECT_DIR / "output" / "clips"
COLLECTIONS_DIR = PROJECT_DIR / "output" / "collections"

def fix_paths():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 获取实际文件名
    actual_clip_files = list(CLIPS_DIR.glob("*.mp4"))
    actual_coll_files = list(COLLECTIONS_DIR.glob("*.mp4"))
    
    print(f"实际文件：{len(actual_clip_files)} clips, {len(actual_coll_files)} collections")
    
    # 修复 clips
    for file in actual_clip_files:
        # 从文件名提取索引：100_片段 100 晚宴.mp4 → 100
        filename = file.name
        index = filename.split("_")[0]
        
        # 新路径
        new_path = f"output/clips/{filename}"
        
        # 更新数据库（匹配索引）
        cursor.execute("""
            UPDATE clips 
            SET video_path = ?
            WHERE project_id = ? AND video_path LIKE ?
        """, (new_path, PROJECT_ID, f"output/clips/{index}_%"))
        
        if cursor.rowcount > 0:
            print(f"✓ Clip {index}: {new_path}")
    
    # 修复 collections
    for file in actual_coll_files:
        filename = file.name
        new_path = f"output/collections/{filename}"
        
        # 更新数据库（匹配标题）
        cursor.execute("""
            UPDATE collections 
            SET video_path = ?
            WHERE project_id = ? AND title = ?
        """, (new_path, PROJECT_ID, filename.replace(".mp4", "")))
        
        if cursor.rowcount > 0:
            print(f"✓ Collection: {new_path}")
    
    conn.commit()
    
    # 验证
    cursor.execute("SELECT COUNT(*) FROM clips WHERE project_id = ? AND video_path LIKE 'output/clips/%.mp4'", (PROJECT_ID,))
    clip_ok = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM collections WHERE project_id = ? AND video_path LIKE 'output/collections/%.mp4'", (PROJECT_ID,))
    coll_ok = cursor.fetchone()[0]
    
    print(f"\n✅ 验证：{clip_ok} clips, {coll_ok} collections 路径正确")
    conn.close()

if __name__ == "__main__":
    fix_paths()
