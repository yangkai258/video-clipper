"""v2.0+: 新增 watch_folders 表 (idempotent)

v2.0 (commit 0111136) 加 WatchFolder model (监控文件夹, 定期扫描发现新视频自动处理),
但 8 天没启动 dev mode 后, db 落后 model:
- 8 天前 db 创建时是 v2.0 之前, 没 watch_folders 表
- v2.0+ 之后 ramply 没重启过 + 没写 migration 触发 create
- 8 天后再启动 GET /watch-folders/ 500 (no such table: watch_folders)

修法: 跟 add_resource_clips 一样, 用 Base.metadata.create_all 补.
target DB:
  data/video_clipper.db             release
  data/video_clipper_beta.db        beta
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, inspect

from backend.models.database import Base, WatchFolder


def _engine_url_for_sqlite(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return

    engine = create_engine(
        _engine_url_for_sqlite(db_path), connect_args={"check_same_thread": False}
    )
    try:
        inspector = inspect(engine)
        if "watch_folders" in inspector.get_table_names():
            print(f"[skip] {db_path.name} 已含 watch_folders 表")
            return
    finally:
        engine.dispose()

    eng = create_engine(
        _engine_url_for_sqlite(db_path),
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    try:
        Base.metadata.create_all(eng, tables=[WatchFolder.__table__])
        print(f"[ok] {db_path.name} 创建 watch_folders 表")
    finally:
        eng.dispose()


def main():
    base = Path("data")
    targets = [
        base / "video_clipper.db",  # release
        base / "video_clipper_beta.db",  # beta
    ]
    for db_path in targets:
        migrate_one(db_path)


if __name__ == "__main__":
    main()
