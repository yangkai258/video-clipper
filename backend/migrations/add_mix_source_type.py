"""v2.2.5: mix_source_clips 加 source_type 列 (idempotent)

区分 project (切片项目 clip) / library (资源库 clip),
让 mix 详情页能显示 source 来源标签.
"""

import sqlite3
from pathlib import Path


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(mix_source_clips)")
    cols = [row[1] for row in cur.fetchall()]
    if "source_type" in cols:
        print(f"[skip] {db_path.name} 已含 source_type 列")
    else:
        cur.execute(
            "ALTER TABLE mix_source_clips ADD COLUMN source_type VARCHAR(20) DEFAULT 'project'"
        )
        conn.commit()
        print(f"[ok] {db_path.name} 加 source_type 列")
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
