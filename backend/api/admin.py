"""系统管理 API 路由"""

import logging
import platform
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.apache import HtpasswdFile
from sqlalchemy import func, select, text

from ..core.config import settings
from ..core.database import AsyncSessionLocal, to_iso_utc
from ..models.database import Clip, Collection, Project, Task

router = APIRouter()

logger = logging.getLogger(__name__)

# v2.2.11: 加 basic auth (P1-1 安全修)
# admin 端点能调 worker restart / database / system 信息, LAN 暴露风险
# 用 .htpasswd 现有文件 (passlib HtpasswdFile 校验 apr1 hash)
_HTPASSWD_PATH = Path(__file__).parent.parent.parent / ".htpasswd"
_security = HTTPBasic()


def get_admin_user(creds: HTTPBasicCredentials = Depends(_security)) -> str:
    """校验 basic auth, 返 username (后续 admin 操作可以 log 谁调的)

    失败: 401 + WWW-Authenticate: Basic 弹浏览器登录框
    """
    if not _HTPASSWD_PATH.exists():
        logger.error(f".htpasswd 不存在: {_HTPASSWD_PATH}")
        raise HTTPException(status_code=500, detail="admin auth not configured")
    try:
        ht = HtpasswdFile(str(_HTPASSWD_PATH))
        if not ht.check_password(creds.username, creds.password):
            raise HTTPException(
                status_code=401,
                detail="Invalid admin credentials",
                headers={"WWW-Authenticate": "Basic"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"admin auth 异常: {e}")
        raise HTTPException(status_code=500, detail=f"auth error: {e}")
    return creds.username


# 应用启动时间
START_TIME = datetime.now()


@router.get("/system", dependencies=[Depends(get_admin_user)])
async def get_system_info():
    """获取系统信息"""
    uptime = datetime.now() - START_TIME
    uptime_str = str(uptime).split(".")[0]  # 去掉微秒

    return {
        "version": settings.APP_VERSION,
        "status": "running",
        "uptime": uptime_str,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "start_time": to_iso_utc(START_TIME),
    }


@router.get("/worker", dependencies=[Depends(get_admin_user)])
async def get_worker_status():
    """获取 Celery Worker 状态"""
    try:
        # 检查 Redis 连接
        from ..core.celery_app import celery_app

        inspect = celery_app.control.inspect()

        # 获取活跃 worker
        active_workers = inspect.active()
        stats = inspect.stats()

        if not active_workers:
            return {
                "running": False,
                "workers": 0,
                "active_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
            }

        worker_count = len(active_workers)
        active_tasks = sum(len(tasks) for tasks in active_workers.values())

        # 获取任务统计（从数据库）
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(
                    func.count(Task.id).label("total"),
                    func.sum(func.case((Task.status == "completed", 1), else_=0)).label(
                        "completed"
                    ),
                    func.sum(func.case((Task.status == "failed", 1), else_=0)).label(
                        "failed"
                    ),
                )
            )
            row = result.first()

            return {
                "running": True,
                "workers": worker_count,
                "active_tasks": active_tasks,
                "completed_tasks": row.completed or 0,
                "failed_tasks": row.failed or 0,
            }

    except Exception as e:
        logger.error(f"获取 Worker 状态失败：{e}")
        return {
            "running": False,
            "workers": 0,
            "active_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "error": str(e),
        }


@router.get("/database", dependencies=[Depends(get_admin_user)])
async def get_database_stats():
    """获取数据库统计信息"""
    try:
        async with AsyncSessionLocal() as db:
            # 项目统计
            project_count = await db.execute(select(func.count(Project.id)))
            project_count = project_count.scalar()

            # 切片统计
            clip_count = await db.execute(select(func.count(Clip.id)))
            clip_count = clip_count.scalar()

            # 合集统计
            collection_count = await db.execute(select(func.count(Collection.id)))
            collection_count = collection_count.scalar()

            # 数据库文件大小
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")
            db_size = "未知"
            if Path(db_path).exists():
                size_bytes = Path(db_path).stat().st_size
                if size_bytes < 1024:
                    db_size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    db_size = f"{size_bytes / 1024:.1f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    db_size = f"{size_bytes / (1024 * 1024):.1f} MB"
                else:
                    db_size = f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

            # 最近任务
            result = await db.execute(
                select(Task).order_by(Task.created_at.desc()).limit(10)
            )
            recent_tasks = result.scalars().all()

            recent_tasks_data = []
            for task in recent_tasks:
                duration = "-"
                if task.started_at and task.completed_at:
                    delta = datetime.fromisoformat(
                        task.completed_at
                    ) - datetime.fromisoformat(task.started_at)
                    duration = str(delta).split(".")[0]
                elif task.started_at:
                    delta = datetime.now() - datetime.fromisoformat(task.started_at)
                    duration = str(delta).split(".")[0] + " (进行中)"

                recent_tasks_data.append(
                    {
                        "id": task.id,
                        "task_type": task.task_type,
                        "status": task.status,
                        "progress": task.progress,
                        "started_at": task.started_at,
                        "duration": duration,
                    }
                )

            # Redis 状态
            redis_connected = False
            queue_size = 0
            redis_memory = "-"

            try:
                from ..core.celery_app import celery_app

                conn = celery_app.connection()
                conn.ensure_connection()
                redis_connected = True

                # 获取队列大小
                with conn.channel() as channel:
                    queue_name = getattr(settings, "CELERY_QUEUE_NAME", "celery")
                    # 尝试获取队列长度（不同 broker 实现不同）
                    try:
                        queue_size = conn.default_channel.client.llen(queue_name)
                    except:
                        queue_size = 0

                # 获取 Redis 内存使用
                try:
                    client = conn.default_channel.client
                    info = client.info("memory")
                    used_memory = info.get("used_memory_human", "未知")
                    redis_memory = used_memory
                except:
                    pass

                conn.close()
            except Exception as e:
                logger.warning(f"Redis 连接检查失败：{e}")

            return {
                "projects": project_count,
                "clips": clip_count,
                "collections": collection_count,
                "db_size": db_size,
                "redis_connected": redis_connected,
                "queue_size": queue_size,
                "redis_memory": redis_memory,
                "recent_tasks": recent_tasks_data,
            }

    except Exception as e:
        logger.error(f"获取数据库统计失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks", dependencies=[Depends(get_admin_user)])
async def get_tasks(limit: int = 50, status: str | None = None):
    """获取任务列表"""
    try:
        async with AsyncSessionLocal() as db:
            query = select(Task).order_by(Task.created_at.desc()).limit(limit)

            if status:
                query = query.where(Task.status == status)

            result = await db.execute(query)
            tasks = result.scalars().all()

            return {
                "tasks": [
                    {
                        "id": task.id,
                        "project_id": task.project_id,
                        "task_type": task.task_type,
                        "name": task.name,
                        "status": task.status,
                        "progress": task.progress,
                        "current_step": task.current_step,
                        "error_message": task.error_message,
                        "created_at": task.created_at,
                        "started_at": task.started_at,
                        "completed_at": task.completed_at,
                    }
                    for task in tasks
                ]
            }

    except Exception as e:
        logger.error(f"获取任务列表失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/worker/restart", dependencies=[Depends(get_admin_user)])
async def restart_worker():
    """重启 Worker（需要外部脚本配合）"""
    # 这个端点需要配合系统脚本使用
    # 实际重启由外部进程管理器完成
    return {"message": "Worker 重启请求已发送", "note": "实际重启由系统进程管理器执行"}


@router.get("/health")
async def detailed_health_check():
    """详细健康检查"""
    health_status = {"overall": "healthy", "checks": {}}

    # 数据库检查
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {"status": "healthy", "latency": "ok"}
    except Exception as e:
        health_status["checks"]["database"] = {"status": "unhealthy", "error": str(e)}
        health_status["overall"] = "unhealthy"

    # Redis 检查
    try:
        from ..core.celery_app import celery_app

        conn = celery_app.connection()
        conn.ensure_connection()
        conn.close()
        health_status["checks"]["redis"] = {"status": "healthy"}
    except Exception as e:
        health_status["checks"]["redis"] = {"status": "unhealthy", "error": str(e)}
        health_status["overall"] = "degraded"

    # 磁盘空间检查 (v2.2.12: 跨平台用 shutil.disk_usage, 之前 os.stat().f_bavail 在 macOS 不存在)
    try:
        import shutil

        projects_dir = settings.PROJECTS_DIR
        usage = shutil.disk_usage(projects_dir)
        free_gb = usage.free / (1024**3)
        if free_gb < 1:
            health_status["checks"]["disk"] = {
                "status": "warning",
                "free_gb": f"{free_gb:.2f}",
            }
            health_status["overall"] = "degraded"
        else:
            health_status["checks"]["disk"] = {
                "status": "healthy",
                "free_gb": f"{free_gb:.2f}",
            }
    except Exception as e:
        health_status["checks"]["disk"] = {"status": "unknown", "error": str(e)}

    return health_status


# v2.2.12: 加 /admin/users 端点 (P2-4 修)
# admin 想看当前有哪些 user 账号能登 (从 .htpasswd 拿)
# 不返 password hash, 只返 username + 来源文件
@router.get("/users", dependencies=[Depends(get_admin_user)])
async def list_admin_users():
    """列出 .htpasswd 里的所有 admin 账号 (P2-4)"""
    try:
        if not _HTPASSWD_PATH.exists():
            raise HTTPException(
                status_code=500, detail=f".htpasswd 不存在: {_HTPASSWD_PATH}"
            )
        ht = HtpasswdFile(str(_HTPASSWD_PATH))
        users = sorted(ht.users())
        return {
            "users": users,
            "count": len(users),
            "source_file": str(_HTPASSWD_PATH),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"list admin users 失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
