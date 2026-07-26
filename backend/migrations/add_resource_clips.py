"""v2.2.5: 新增 resource_clips 表 (idempotent)

复用切片 Base (跟 Project/Clip 用同一个 declarative_base),
新表直接 Base.metadata.create_all 即可 (SQLAlchemy 只创建不存在的表).

但 Base.metadata.create_all 不会 ALTER 已有表, 所以这里用 inspector 检查:
- 表不存在 → create_all 全套 (因为是新增表, 不需 ALTER, 跟切片项目初始一样)
- 表已存在 → skip (数据库已就绪)

target DB:
  data/video_clipper.db             release
  data/video_clipper_beta.db        beta
"""

import sys
from pathlib import Path

# 让脚本能从 repo root 直接跑 (跟其他 migrations 一样)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import create_engine, inspect

from backend.models.database import Base, ResourceClip


def _engine_url_for_sqlite(db_path: Path) -> str:
    return f"sqlite:///{db_path}"


def migrate_one(db_path: Path) -> None:
    if not db_path.exists():
        print(f"[skip] {db_path} 不存在")
        return

    # 1) 用 inspector 查表是否存在 (不依赖 ORM 自动建)
    engine = create_engine(
        _engine_url_for_sqlite(db_path), connect_args={"check_same_thread": False}
    )
    try:
        inspector = inspect(engine)
        if "resource_clips" in inspector.get_table_names():
            print(f"[skip] {db_path.name} 已含 resource_clips 表")
            return
    finally:
        engine.dispose()

    # 2) 用 Base.metadata.create_all 创建 (只建不存在的表 — SQLAlchemy 标准行为)
    #    用 sync engine 跑, 避开 aiosqlite 的 async loop 复杂性
    from sqlalchemy import create_engine as _ce

    sync_url = f"sqlite:///{db_path.resolve()}"
    eng = _ce(sync_url, connect_args={"check_same_thread": False, "timeout": 30})
    try:
        Base.metadata.create_all(eng, tables=[ResourceClip.__table__])
        print(f"[ok] {db_path.name} 创建 resource_clips 表")
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
