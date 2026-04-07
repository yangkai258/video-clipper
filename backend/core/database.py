"""数据库初始化"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, Session

from .config import settings
from ..models.database import Base


# 创建数据库引擎
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True
)

# 同步引擎（用于 Celery 等同步场景）
sync_engine = create_engine(
    settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite"),
    echo=settings.DEBUG,
    future=True
)

# 创建会话工厂
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 同步会话工厂（用于 Celery）
SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


def init_db():
    """初始化数据库（创建表）"""
    import asyncio
    from sqlalchemy import text
    
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


def sync_get_db():
    """获取数据库会话（同步，用于 Celery）"""
    session = SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
