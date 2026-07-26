"""v2.2.6: 批量混剪 — mix_projects 加 batch_id 列 + mix_batches 表 (idempotent)

复用 add_mix_thumbnail_path.py 风格: 已有列/表 skip, 没有则加.
"""

import sqlite3
from pathlib import Path


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    try:
        # 1) mix_projects 加 batch_id 列
        cur.execute("PRAGMA table_info(mix_projects)")
        cols = [row[1] for row in cur.fetchall()]
        if "batch_id" in cols:
            print(f"[skip] {db_path.name}.mix_projects 已含 batch_id 列")
        else:
            cur.execute("ALTER TABLE mix_projects ADD COLUMN batch_id VARCHAR(36)")
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_mix_projects_batch_id ON mix_projects(batch_id)"
            )
            conn.commit()
            print(f"[ok] {db_path.name}.mix_projects 加 batch_id 列 + idx")

        # 2) mix_batches 表 (新表, 用 inspector 风格查)
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mix_batches'"
        )
        if cur.fetchone():
            print(f"[skip] {db_path.name} 已含 mix_batches 表")
        else:
            cur.execute("""
                CREATE TABLE mix_batches (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    description TEXT DEFAULT '',
                    common_script_text TEXT DEFAULT '',
                    common_target_duration INTEGER DEFAULT 60,
                    variations JSON DEFAULT '[]',
                    max_concurrent INTEGER DEFAULT 1,
                    status VARCHAR(50) DEFAULT 'pending',
                    total_count INTEGER DEFAULT 0,
                    completed_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    created_at DATETIME,
                    updated_at DATETIME,
                    completed_at DATETIME
                )
            """)
            conn.commit()
            print(f"[ok] {db_path.name} 建 mix_batches 表")
    finally:
        conn.close()


def main():
    base = Path("data")
    targets = [
        base / "video_clipper_mix.db",
        base / "video_clipper_mix_beta.db",
    ]
    for db_path in targets:
        migrate_one(db_path)


if __name__ == "__main__":
    main()
