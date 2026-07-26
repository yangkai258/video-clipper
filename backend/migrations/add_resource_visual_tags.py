"""v2.2.47: 给 resource_clips 表加 visual_tags 列 (idempotent)

visual_tags = 视觉属性标签 (色调/亮度/动静/边缘密度),
0 依赖 visual_tag_service.generate_visual_tags 跑出, 跟 LLM auto-tag 独立.

老表 ALTER 加列 (SQLAlchemy inspector check).

target DB:
  data/video_clipper.db             release
  data/video_clipper_beta.db        beta
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, inspect, text

from backend.core.config import settings


def _engine_url_for_sqlite(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return

    engine = create_engine(
        _engine_url_for_sqlite(db_path),
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    try:
        inspector = inspect(engine)
        if "resource_clips" not in inspector.get_table_names():
            print(f"[skip] {db_path.name} 无 resource_clips 表 (无需 ALTER)")
            return

        cols = {c["name"] for c in inspector.get_columns("resource_clips")}
        if "visual_tags" in cols:
            print(f"[skip] {db_path.name} 已含 visual_tags 列")
            return

        # ALTER TABLE 加列 (default '[]' 兼容老 row)
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE resource_clips ADD COLUMN visual_tags JSON DEFAULT '[]'")
            )
        print(f"[ok] {db_path.name} 加 visual_tags 列")
    finally:
        engine.dispose()


def main():
    data_dir = Path(getattr(settings, "DATA_DIR", "data"))
    targets = [
        data_dir / "video_clipper.db",  # release
        data_dir / "video_clipper_beta.db",  # beta
    ]
    for db_path in targets:
        migrate_one(db_path)


if __name__ == "__main__":
    main()
