"""v2.1.26+: 给 clips 表加 width / height 列 (idempotent)

v2.1.26 (model 改动) 给 Clip model 加了 width/height 列 (让前端区分横/竖屏, 避免竖屏裁切),
但当时没写 migration. 8 天没启动 dev mode 后, db schema 跟 model 不同步:
- model: width + height 在
- db: 没这 2 列
- from-project / from-clip API 查 clips.width → 500 Internal Server Error

修法: 给 2 个 db 都补上 columns (IF NOT EXISTS 兼容 sqlite < 3.35).

target DB:
  data/video_clipper.db             release
  data/video_clipper_beta.db        beta
"""
import sqlite3
from pathlib import Path

DB_PATHS = [
    Path("data/video_clipper.db"),       # release
    Path("data/video_clipper_beta.db"),  # beta
]

COLUMNS = [
    ("width", "INTEGER"),
    ("height", "INTEGER"),
]


def _migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # 查 clips 表所有列
        cur.execute("PRAGMA table_info(clips)")
        existing = {row[1] for row in cur.fetchall()}

        for col_name, col_type in COLUMNS:
            if col_name in existing:
                print(f"  [skip] {db_path.name} clips.{col_name} 已存在")
                continue
            # sqlite 3.35+ 支持 ALTER TABLE ... ADD COLUMN IF NOT EXISTS
            # macOS 12+ / 系统 sqlite 3.39 都支持, 安全用
            try:
                cur.execute(f"ALTER TABLE clips ADD COLUMN {col_name} {col_type}")
                print(f"  [ok]   {db_path.name} clips.{col_name} {col_type} 加好")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    print(f"  [skip] {db_path.name} clips.{col_name} 重复列 (race)")
                else:
                    raise
        conn.commit()
    finally:
        conn.close()


def main():
    for db_path in DB_PATHS:
        print(f"[migrate] {db_path}")
        _migrate_one(db_path)


if __name__ == "__main__":
    main()
