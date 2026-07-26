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
import os
import uuid

from kombu import Connection

from ..core.celery_app import celery_app

logger = logging.getLogger(__name__)


def _resolve_mix_dispatch_broker() -> str:
    """v2.2.37: 派发 broker 跟 uvicorn 模式走 (release=db 0, beta=db 1)

    之前 v2.2.24 hardcode db=0/processing_mix, beta 模式混剪 0 match (worker 在 release db 查不到 beta 资源).
    修法: dispatch 读 uvicorn 启动时的 CELERY_BROKER_URL env (release=db 0, beta=db 1), 让 mix worker 端
    broker 跟 uvicorn 一致. worker 端同步改: release 启 processing_mix 队列, beta 启 processing_mix_beta.
    """
    return os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")


def _resolve_mix_dispatch_queue() -> str:
    """v2.2.37: 派发 queue 按 broker db 推 (release=processing_mix, beta=processing_mix_beta)

    不读 CELERY_QUEUE_NAME (那是 uvicorn 切片 worker queue, e.g. processing_beta, 跟 mix 无关).
    单独按 broker db 推算: db=0 → processing_mix (release), db=1 → processing_mix_beta (beta).
    """
    broker = _resolve_mix_dispatch_broker()
    if broker.endswith(("/1", "/2")):  # 0=release, 1/2=beta
        return "processing_mix_beta"
    return "processing_mix"


# v2.2.37: 动态读 env, 兼容 e2e / 单元测试 export 不同 env 走不同 broker
MIX_DISPATCH_BROKER_URL = _resolve_mix_dispatch_broker()
MIX_DISPATCH_QUEUE = _resolve_mix_dispatch_queue()


def dispatch_mix_task(
    mix_project_id: str,
    script_text: str,
    target_duration_seconds: int,
    candidate_clip_ids: list[str],
    task_id: str,
) -> str:
    """派发混剪 task, 走跟 uvicorn 模式一致的 broker (v2.2.37 跨 release/beta)

    之前 v2.2.24 hardcode db=0/processing_mix, beta 模式混剪 0 match (worker 在 release db 查不到 beta 资源).
    现在 broker 跟 queue 跟 uvicorn 模式走 (release=db 0/processing_mix, beta=db 1/processing_mix_beta).

    启动检查清单 (跟 check_workers.sh start_mix_worker 一致):
      release uvicorn :8000 → CELERY_BROKER_URL=redis://localhost:6379/0, mix worker Q=processing_mix
      beta    uvicorn :8030 → CELERY_BROKER_URL=redis://localhost:6379/1, mix worker Q=processing_mix_beta

    Returns: celery task id.
    Raises: Exception 派发失败 (caller 应该 catch 设 project.status=failed)
    """
    # v2.2.37: 每次派发都重新读 env (e2e / 单测 export 不同 env 走不同 broker)
    broker_url = _resolve_mix_dispatch_broker()
    queue = _resolve_mix_dispatch_queue()
    # 1. 显式 create connection (跟 mix worker 监听一致)
    with Connection(broker_url) as conn:
        # 2. send_task 走 connection, 强制指定 broker
        async_result = celery_app.send_task(
            "backend.tasks.processing_mix.process_mix_pipeline",
            kwargs={
                "mix_project_id": mix_project_id,
                "script_text": script_text,
                "target_duration_seconds": target_duration_seconds,
                "candidate_clip_ids": candidate_clip_ids,
                "task_id": task_id,
            },
            queue=queue,
            task_id=task_id,
            connection=conn,  # v2.2.24: 显式传 connection
            reply_to=str(uuid.uuid4()),
        )
    logger.info(
        f"混剪 task 派发: project={mix_project_id} task_id={task_id} "
        f"→ redis {broker_url}/{queue} (v2.2.37 跨 release/beta 模式)"
    )
    return task_id
