"""混剪项目独立数据库 (v2.2.3 完全分开)

跟切片项目 db 完全分离:
- 切片: data/video_clipper.db (release) / video_clipper_beta.db (beta)
- 混剪: data/video_clipper_mix.db (release) / video_clipper_mix_beta.db (beta)

为什么分开:
1. 业务不同: 切片 vs 混剪, 字段/关系/索引全不同
2. 部署解耦: 混剪 worker / api 跟切片 worker / api 互不影响
3. 故障隔离: 混剪 schema 升级 / 数据清理不影响切片
"""

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ..models.mix import MixBase  # 独立 Base (跟切片 Base 区分)
from .config import settings


def _resolve_mix_db_path() -> str:
    """根据 DATABASE_URL 推算混剪独立 db path

    e.g. settings.DATABASE_URL = sqlite+aiosqlite:///./data/video_clipper.db
    -> data/video_clipper_mix.db

    v2.2.25: 永远用 release mix db (data/video_clipper_mix.db), 不分 release/beta.
    修 7-26 ramply beta 模式混剪 task 跑失败的根因: 之前按 DATABASE_URL 派生
    (release 派 video_clipper_mix.db, beta 派 video_clipper_mix_beta.db),
    但 mix worker 永远跑在 release env (DATABASE_URL=video_clipper.db),
    派生 release mix db, 查不到 beta mode uvicorn 写到 _beta mix db 的 project.

    解决: 混剪 db 跟 uvicorn 模式**解耦**, 永远用 release mix db.
    - release uvicorn 写 release mix db ✅ (worker 查得到)
    - beta uvicorn 写 release mix db ✅ (worker 查得到)
    - mix worker (release env) 查 release mix db ✅

    注: 切片 db 仍按 uvicorn 模式 (release 切片 db 跟 beta 切片 db 独立),
    只有混剪 db 统一.
    """
    # 不分 release/beta, 永远用 video_clipper_mix.db
    from ..core.config import settings as _settings

    base = Path(_settings.BASE_DIR) / "data"
    return f"sqlite+aiosqlite:///{base / 'video_clipper_mix.db'}"


MIX_DATABASE_URL = _resolve_mix_db_path()
MIX_SYNC_DATABASE_URL = MIX_DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")


# 异步引擎 (FastAPI)
mix_engine = create_async_engine(
    MIX_DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

# 同步引擎 (Celery)
mix_sync_engine = create_engine(
    MIX_SYNC_DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args={"check_same_thread": False, "timeout": 30},
)


@event.listens_for(mix_sync_engine, "connect")
def _set_mix_sqlite_pragma(dbapi_connection, connection_record):
    """WAL + busy_timeout"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA cache_size=-20000")
    cursor.close()


# 会话工厂
MixAsyncSessionLocal = sessionmaker(
    bind=mix_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

MixSyncSessionLocal = sessionmaker(
    bind=mix_sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_mix_db():
    """FastAPI 异步依赖"""
    async with MixAsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@contextmanager
def sync_get_mix_db():
    """Celery 同步依赖

    用法: `with sync_get_mix_db() as db:`
    """
    session = MixSyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_mix_db():
    """初始化混剪 db (启动时调)

    - 创建 db 文件 (如果不存在)
    - 创建所有 MixBase 表 (MixProject, MixSourceClip, MixTask)
    """
    # 触发 db 文件创建 (用 sync engine 跑 CREATE TABLE)
    MixBase.metadata.create_all(bind=mix_sync_engine)
    print(f"[mix_db] 初始化完成: {MIX_SYNC_DATABASE_URL}")


# 自动初始化 (import 时)
try:
    init_mix_db()
except Exception as e:
    print(f"[mix_db] 初始化失败: {e}")
