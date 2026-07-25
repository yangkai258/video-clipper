"""Migration runner (v2.2.13)

背景:
  v2.1.18 起我们累积了 13 个 add_*.py migration scripts, 但跑法不规范:
  - 改了 model 但忘了写 migration (例: v2.1.26 加 clips.width/height 漏 migration)
  - 写了 migration 但忘了跑 (例: watch_folders v2.0 加 model, 7-17 才发现 db 缺表)
  - 跑过 migration 但 dev mode 8 天没重启, 别人 clone 拿到新代码 + 老 db

修法: 启动时自动跑所有未跑的 migration
  - 维护 schema_migrations 表 (name, applied_at), 记录每个 migration 跑了没
  - 启动 lifespan 调 run_pending_migrations(), 按文件名字母序跑
  - 每个 add_*.py 调 main() 必须 idempotent (我自己保证, 用 IF NOT EXISTS / inspector)
  - 跑失败的 migration 记录到 failed_migrations, 下次启动重试

用法:
  CLI:   python -m backend.migrations.runner
  启动:  main.py lifespan 自动调 run_pending_migrations()

跟 alembic 比:
  - 不用 alembic 版本号 (手工维护麻烦, 容易断链)
  - 用文件名字母序 + 跑过 mark applied (跟 rails/db 一样的简单模式)
  - 适合 dev 模式 / 单机部署 (没多台机器并发跑 migration)
"""
import importlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from sqlalchemy import Column, DateTime, String, Table, create_engine, inspect, text, MetaData
from sqlalchemy.exc import OperationalError

logger = logging.getLogger(__name__)

# migrations 目录: backend/migrations/
MIGRATIONS_DIR = Path(__file__).parent

# 跟踪表名
SCHEMA_HISTORY_TABLE = "schema_migrations"


def _ensure_history_table(sync_engine) -> None:
    """创建 schema_migrations 表 (记录跑过的 migration)

    Columns:
        name VARCHAR(255) PRIMARY KEY  (migration 文件名, e.g. "add_watch_folders.py")
        applied_at DATETIME
    """
    meta = MetaData()
    Table(
        SCHEMA_HISTORY_TABLE,
        meta,
        Column("name", String(255), primary_key=True),
        Column("applied_at", DateTime, default=datetime.utcnow),
    )
    meta.create_all(sync_engine, checkfirst=True)


def _get_applied_migrations(sync_engine) -> set:
    """查已经跑过的 migration 文件名集合"""
    try:
        with sync_engine.connect() as conn:
            rows = conn.execute(text(f"SELECT name FROM {SCHEMA_HISTORY_TABLE}")).fetchall()
            return {row[0] for row in rows}
    except OperationalError:
        # 表还没建, 返空集
        return set()


def _mark_applied(sync_engine, name: str) -> None:
    """mark migration 已跑过"""
    with sync_engine.connect() as conn:
        conn.execute(
            text(f"INSERT INTO {SCHEMA_HISTORY_TABLE} (name, applied_at) VALUES (:name, :ts)"),
            {"name": name, "ts": datetime.utcnow()},
        )
        conn.commit()


def _discover_migrations() -> List[Path]:
    """扫 migrations/ 目录, 找所有 add_*.py (按字母序)

    排除:
    - __init__.py
    - conftest.py (那是 pytest fixture)
    - runner.py 自己
    - 文件不在 MIGRATIONS_DIR
    """
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("add_*.py")):
        if path.name == "__init__.py":
            continue
        migrations.append(path)
    return migrations


def _run_one(sync_engine, path: Path) -> Tuple[bool, str]:
    """跑一个 migration

    兼容老 migration 不同的入口名:
    - main()    (v2.2.5+ 推荐)
    - run()     (一些老 migration)
    - migrate() (v2.1.18~v2.2.4 老 migration)

    v2.2.13: 跑前 chdir 到项目根, 防老 migration 4 层 dirname 算错 BASE_DIR
    """
    import os
    module_name = f"backend.migrations.{path.stem}"
    try:
        logger.info(f"[migration] 跑 {path.name}...")
        project_root = Path(__file__).parent.parent.parent
        original_cwd = os.getcwd()
        os.chdir(project_root)
        try:
            module = importlib.import_module(module_name)
            # 找入口函数 (按优先级)
            for fn_name in ("main", "run", "migrate"):
                if hasattr(module, fn_name):
                    getattr(module, fn_name)()
                    _mark_applied(sync_engine, path.name)
                    return (True, f"✅ {path.name} ok ({fn_name}())")
            return (False, f"{path.name} 缺 main/run/migrate 函数")
        finally:
            os.chdir(original_cwd)
    except Exception as e:
        return (False, f"❌ {path.name} failed: {type(e).__name__}: {e}")


def run_pending_migrations(db_url: str = None) -> List[Tuple[str, bool, str]]:
    """跑所有未跑的 migration (启动时调)

    Args:
        db_url: SQLAlchemy URL. None 时用 settings 的 DATABASE_URL (但 settings
                可能是异步 aiosqlite URL, 跑 migration 用 sync sqlite URL)

    Returns:
        list of (filename, success, message)
    """
    if db_url is None:
        # 同步 sqlite URL (strip +async prefix)
        from ..core.config import settings
        db_url = settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")

    # v2.2.13: 直接用 db_url 里的 path, 别 fallback
    # 老逻辑: 关键字 "beta"/"mix" 决定走哪个 db, 但 db_url 才是真相
    if db_url.startswith("sqlite"):
        from urllib.parse import urlparse
        parsed = urlparse(db_url)
        raw_path = parsed.path
        # urlparse 把 "sqlite:///./data/foo.db" 解析成 "/./data/foo.db" (POSIX 误判为绝对)
        # 但实际是相对路径 (项目根 ./data/foo.db)
        # 启发: 开头 "/./" 视为相对, 用 project_root 拼
        db_path = Path(raw_path)
        if not db_path.is_absolute() or raw_path.startswith("/./"):
            project_root = Path(__file__).parent.parent.parent
            if raw_path.startswith("/./"):
                # "/./data/foo.db" -> "data/foo.db"
                rel = raw_path[3:]
                db_path = (project_root / rel).resolve()
            else:
                db_path = (project_root / db_path).resolve()
    else:
        # 混剪 db 自己的 URL (用 MIX_SYNC_DATABASE_URL)
        from ..core.database_mix import MIX_SYNC_DATABASE_URL
        db_path = Path(MIX_SYNC_DATABASE_URL.replace("sqlite:///", ""))
        if not db_path.is_absolute():
            project_root = Path(__file__).parent.parent.parent
            db_path = (project_root / db_path).resolve()

    # 没 db 文件 (新 init) — 让 Base.metadata.create_all 处理, 不跑 migration
    if not db_path.exists():
        logger.info(f"[migration] {db_path} 不存在, 跳过 (新 init 由 Base.metadata.create_all 处理)")
        return []

    sync_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )

    try:
        _ensure_history_table(sync_engine)
        applied = _get_applied_migrations(sync_engine)
        all_migrations = _discover_migrations()

        results = []
        for path in all_migrations:
            if path.name in applied:
                logger.debug(f"[migration] skip {path.name} (already applied)")
                continue
            ok, msg = _run_one(sync_engine, path)
            logger.info(f"[migration] {msg}")
            results.append((path.name, ok, msg))
        return results
    finally:
        sync_engine.dispose()


def main():
    """CLI: python -m backend.migrations.runner"""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = run_pending_migrations()
    if not results:
        print("✅ 没有 pending migration (db schema 跟代码同步)")
        return
    print(f"\n跑了 {len(results)} 个 pending migration:")
    for name, ok, msg in results:
        print(f"  {msg}")
    failed = [r for r in results if not r[1]]
    if failed:
        print(f"\n❌ {len(failed)} 个 migration 失败, 下次启动会重试")
        sys.exit(1)


if __name__ == "__main__":
    main()
