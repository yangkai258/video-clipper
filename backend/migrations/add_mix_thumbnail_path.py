"""v2.2.4: mix_projects 加 thumbnail_path 列 (idempotent)

MixBase.metadata.create_all 不会 ALTER 已有表, 必须手动 ALTER.
跟之前 add_subtitle_status_to_tasks.py 一样的 idempotent 模式.
"""

import sqlite3
from pathlib import Path


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(mix_projects)")
    cols = [row[1] for row in cur.fetchall()]
    if "thumbnail_path" in cols:
        print(f"[skip] {db_path.name} 已含 thumbnail_path 列")
    else:
        cur.execute("ALTER TABLE mix_projects ADD COLUMN thumbnail_path VARCHAR(512)")
        conn.commit()
        print(f"[ok] {db_path.name} 加 thumbnail_path 列")
    conn.close()


def main():
    base = Path("data")
    targets = [
        base / "video_clipper_mix.db",  # release
        base / "video_clipper_mix_beta.db",  # beta
    ]
    for db_path in targets:
        migrate_one(db_path)


if __name__ == "__main__":
    main()
