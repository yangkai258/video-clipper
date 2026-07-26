"""数据库初始化 + 通用 helper"""

from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ..models.database import Base
from .config import settings

# 异步引擎（用于 FastAPI 等异步场景）
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# 同步引擎（用于 Celery 等同步场景）
# 多 worker 并发时必须用 WAL 模式 + busy_timeout 避免 "database is locked"
sync_engine = create_engine(
    settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite"),
    echo=settings.DEBUG,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """每个新连接启用 WAL 模式 + busy_timeout（解决多 worker 写锁）"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA cache_size=-20000")  # 20MB cache
    cursor.close()


# 创建会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 同步会话工厂（用于 Celery）
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def init_db():
    """初始化数据库（创建表）"""
    import asyncio

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    print("✅ 数据库初始化完成")


async def get_db():
    """获取数据库会话（异步）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def sync_get_db():
    """获取数据库会话（同步，用于 Celery）

    用法：`with sync_get_db() as db:`
    """
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def to_iso_utc(dt: datetime | None) -> str | None:
    """datetime → ISO 字符串（UTC，带 Z 后缀），供前端正确显示本地时间

    例：datetime(2026,6,27,14,0) → "2026-06-27T14:00:00Z"

    用法：
        return {"created_at": to_iso_utc(project.created_at)}
    """
    if dt is None:
        return None
    return dt.isoformat() + "Z"


def get_project_data_dir() -> str:
    """项目数据目录（绝对路径）—— 跨进程一致"""
    return str(settings.PROJECTS_DIR)
