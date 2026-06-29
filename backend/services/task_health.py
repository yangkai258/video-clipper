"""Task health monitoring — real stuck-task detection, replaces v2.1.18 _cleanup_stuck_tasks.

Background (v2.1.41 incident):
  v2.1.18 (a146818) added _cleanup_stuck_tasks with WHERE task.status="running"
  AND task.created_at < utcnow()-30min.  1GB / 3.6h videos take 50-60min, so the
  30min hard cutoff falsely killed long-running jobs.  Real "stuck" means no
  progress heartbeat, not just "running a long time".

Two detection modes:
  1. no_worker_pickup: status=running, started_at IS NULL, created_at > 5min ago
     -> celery worker never picked it up (queue / env mismatch)
  2. no_progress_update: started_at + progress_changed_at both stale > 30min
     -> worker process dead (ForkPoolWorker crash / SIGKILL)

Worker side (backend/tasks/processing.py): writes progress_changed_at on every
_update_task_progress and on _mark_task_running.

Trigger: independent of list_projects.  Run from cron / launchd plist every
5min, e.g. via scripts/check_task_health.sh.
"""
import logging
from datetime import datetime, timedelta
from typing import List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import Project, Task

logger = logging.getLogger(__name__)

DEFAULT_STUCK_AFTER_MINUTES = 5   # created_at 超过这个时间但 started_at 仍空
DEFAULT_IDLE_AFTER_MINUTES = 30   # progress_changed_at 超过这个时间没动


async def find_stuck_tasks(
    db: AsyncSession,
    stuck_after_min: int = DEFAULT_STUCK_AFTER_MINUTES,
    idle_after_min: int = DEFAULT_IDLE_AFTER_MINUTES,
) -> List[dict]:
    """Return list of stuck-task dicts: {task_id, project_id, reason, stuck_for_min}."""
    now = datetime.utcnow()
    stuck_cutoff = now - timedelta(minutes=stuck_after_min)
    idle_cutoff = now - timedelta(minutes=idle_after_min)

    # Mode 1: status=running, no started_at, created_at too old
    no_pickup = (await db.execute(
        select(Task).where(
            Task.status == "running",
            Task.started_at.is_(None),
            Task.created_at < stuck_cutoff,
        )
    )).scalars().all()

    # Mode 2: started, but progress_changed_at (or started_at as fallback) is stale
    no_progress = (await db.execute(
        select(Task).where(
            Task.status == "running",
            Task.started_at.isnot(None),
            Task.started_at < idle_cutoff,
        )
    )).scalars().all()

    stuck: List[dict] = []
    for task in no_pickup:
        stuck.append({
            "task_id": task.id,
            "project_id": task.project_id,
            "reason": "no_worker_pickup",
            "stuck_for_min": int((now - task.created_at).total_seconds() / 60),
        })
    for task in no_progress:
        # ponytail: 老 task 没有 progress_changed_at, 用 started_at 当 fallback.
        # 升级路径: 历史 task 跑过一次 worker 就被写上 progress_changed_at 了.
        last_change = task.progress_changed_at or task.started_at
        stuck.append({
            "task_id": task.id,
            "project_id": task.project_id,
            "reason": "no_progress_update",
            "stuck_for_min": int((now - last_change).total_seconds() / 60),
        })
    return stuck


async def mark_stuck_tasks_as_failed(
    db: AsyncSession,
    stuck_tasks: List[dict],
) -> int:
    """Mark stuck tasks as failed; set their project back to pending so user can retry.

    Returns count of tasks handled.
    """
    if not stuck_tasks:
        return 0

    cleaned = 0
    for s in stuck_tasks:
        reason = s["reason"]
        minutes = s["stuck_for_min"]
        await db.execute(
            update(Task)
            .where(Task.id == s["task_id"])
            .values(
                status="failed",
                error_message=(
                    f"Task stuck ({reason}), idle {minutes} min, auto-failed. "
                    f"Retry from project page."
                ),
            )
        )
        await db.execute(
            update(Project)
            .where(Project.id == s["project_id"])
            .values(status="pending")
        )
        cleaned += 1
        logger.warning(
            "task_health: task %s (%s, %dmin) -> failed, project -> pending",
            s["task_id"], reason, minutes,
        )

    await db.commit()
    return cleaned


async def check_stuck_tasks(db: AsyncSession) -> int:
    """Entry point: find + mark.  Returns count handled (0 = none stuck)."""
    stuck = await find_stuck_tasks(db)
    if not stuck:
        return 0
    return await mark_stuck_tasks_as_failed(db, stuck)


if __name__ == "__main__":
    # ponytail: 让 cron 跟运维都能直接 python -m backend.services.task_health 跑.
    import asyncio
    from ..core.database import get_db

    async def _main():
        async for db in get_db():
            n = await check_stuck_tasks(db)
            print(f"task_health: handled {n} stuck task(s)")
            return

    asyncio.run(_main())
