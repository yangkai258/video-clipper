"""
v2.2.37 mix_dispatch 跨 release/beta 模式测试

之前 v2.2.24 hardcode db=0/processing_mix, beta 模式混剪 0 match
(worker 在 release 切片 db 查不到 beta 资源库 ID, 详情页"来源片段"空).

v2.2.37 修: dispatch 跟 uvicorn env 走 (CELERY_BROKER_URL + CELERY_QUEUE_NAME).
"""


def test_resolve_dispatch_helpers_default_release():
    """不 export env 时, _resolve_* default 是 release (db=0/processing_mix), 跟老行为兼容."""
    import os
    os.environ.pop("CELERY_BROKER_URL", None)
    os.environ.pop("CELERY_QUEUE_NAME", None)
    from backend.services.mix_dispatch import _resolve_mix_dispatch_broker, _resolve_mix_dispatch_queue

    assert _resolve_mix_dispatch_broker() == "redis://localhost:6379/0"
    assert _resolve_mix_dispatch_queue() == "processing_mix"


def test_resolve_dispatch_helpers_beta_env():
    """export CELERY_BROKER_URL=db=1 + CELERY_QUEUE_NAME=processing_mix_beta → dispatch 跟 env 走."""
    import os
    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/1"
    os.environ["CELERY_QUEUE_NAME"] = "processing_mix_beta"
    try:
        # 重新 import 拿新值 (函数体内 os.environ 读, 不依赖 reload)
        from backend.services.mix_dispatch import _resolve_mix_dispatch_broker, _resolve_mix_dispatch_queue
        assert _resolve_mix_dispatch_broker() == "redis://localhost:6379/1"
        assert _resolve_mix_dispatch_queue() == "processing_mix_beta"
    finally:
        os.environ.pop("CELERY_BROKER_URL", None)
        os.environ.pop("CELERY_QUEUE_NAME", None)


def test_resolve_dispatch_helpers_dynamic():
    """_resolve_mix_dispatch_broker/queue 每次调用都读 env, 不依赖模块级常量."""
    import os
    from backend.services.mix_dispatch import _resolve_mix_dispatch_broker, _resolve_mix_dispatch_queue

    os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/1"
    os.environ["CELERY_QUEUE_NAME"] = "processing_mix_beta"
    try:
        assert _resolve_mix_dispatch_broker() == "redis://localhost:6379/1"
        assert _resolve_mix_dispatch_queue() == "processing_mix_beta"
    finally:
        os.environ.pop("CELERY_BROKER_URL", None)
        os.environ.pop("CELERY_QUEUE_NAME", None)
    # 不 export env → default release
    assert _resolve_mix_dispatch_broker() == "redis://localhost:6379/0"
    assert _resolve_mix_dispatch_queue() == "processing_mix"
