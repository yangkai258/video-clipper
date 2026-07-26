"""混剪 task 派发 (v2.2.24)

fix: 之前 mix router 调 `process_mix_pipeline.apply_async(queue="processing_mix")`
用默认 broker = 当前 uvicorn 进程 CELERY_BROKER_URL.
- release uvicorn (8000): CELERY_BROKER_URL=db=0 → 派 db=0/processing_mix ✅
- beta uvicorn (8030):    CELERY_BROKER_URL=db=1 → 派 db=1/processing_mix ❌

但 mix worker 永远 db=0 (跟 release 共享, v2.2.10 设计).
结果: beta 模式派混剪 task 永远堆积, 24h 后 redis TTL 清掉, project 卡 pending.

修: 派发时显式用 db=0 broker connection, 跟 mix worker 一致.
实现: celery_app.send_task + 显式 create connection to redis db=0 (Kombu).

用法:
    from backend.services.mix_dispatch import dispatch_mix_task
    dispatch_mix_task(
        project_id=...,
        script_text=...,
        target_duration_seconds=...,
        candidate_clip_ids=...,
        task_id=...,
    )
"""
import logging
import uuid
from typing import List

from kombu import Connection

from ..core.celery_app import celery_app

logger = logging.getLogger(__name__)


# v2.2.24: 固定的 mix dispatch broker (跟 mix worker 一致, db=0)
# 不读 settings.CELERY_BROKER_URL (那个跟 uvicorn 模式走 db=0 / db=1)
# 不读 os.environ (同上, 取决于当前进程是 release 还是 beta)
MIX_DISPATCH_BROKER_URL = "redis://localhost:6379/0"
MIX_DISPATCH_QUEUE = "processing_mix"


def dispatch_mix_task(
    mix_project_id: str,
    script_text: str,
    target_duration_seconds: int,
    candidate_clip_ids: List[str],
    task_id: str,
) -> str:
    """派发混剪 task, 显式走 db=0 broker (跟 mix worker 一致).

    跨 release/beta 模式都能跑: 不管 uvicorn CELERY_BROKER_URL 是什么,
    混剪 task 永远走 db=0, 跟 mix worker 监听一致.

    Returns: celery task id.
    Raises: Exception 派发失败 (caller 应该 catch 设 project.status=failed)
    """
    # 1. 显式 create connection to db=0 (跟 mix worker 监听一致)
    with Connection(MIX_DISPATCH_BROKER_URL) as conn:
        # 2. send_task 走 connection, 强制 db=0 broker
        async_result = celery_app.send_task(
            "backend.tasks.processing_mix.process_mix_pipeline",
            kwargs={
                "mix_project_id": mix_project_id,
                "script_text": script_text,
                "target_duration_seconds": target_duration_seconds,
                "candidate_clip_ids": candidate_clip_ids,
                "task_id": task_id,
            },
            queue=MIX_DISPATCH_QUEUE,
            task_id=task_id,
            connection=conn,  # v2.2.24: 显式传 connection, 强制 db=0
            reply_to=str(uuid.uuid4()),
        )
    logger.info(
        f"混剪 task 派发: project={mix_project_id} task_id={task_id} "
        f"→ redis db=0/{MIX_DISPATCH_QUEUE} (v2.2.24 fix: 跨 release/beta 模式)"
    )
    return task_id
