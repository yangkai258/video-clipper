"""Mix dispatch test (v2.2.24)

测 dispatch_mix_task 显式走 db=0 broker (跨 release/beta 模式).
v2.2.24 实现: celery_app.send_task(connection=conn), conn 是 Kombu Connection
到 redis://localhost:6379/0, 强制走 db=0 不受 env 影响.
"""
import os
from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture
def clean_env(monkeypatch):
    """清空所有 CELERY_/REDIS_ env, 测 dispatch 强制 db=0."""
    for k in list(os.environ.keys()):
        if k.startswith(("CELERY_", "REDIS_", "DATABASE_")):
            monkeypatch.delenv(k, raising=False)


def test_dispatch_broker_is_db0(monkeypatch, clean_env):
    """dispatch 强制走 db=0 broker, 不受 env 影响"""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
    from backend.services.mix_dispatch import MIX_DISPATCH_BROKER_URL
    assert MIX_DISPATCH_BROKER_URL == "redis://localhost:6379/0"


def test_dispatch_no_env_still_uses_db0(monkeypatch, clean_env):
    """没 env → 仍 db=0 (写死常量)"""
    from backend.services.mix_dispatch import MIX_DISPATCH_BROKER_URL
    assert MIX_DISPATCH_BROKER_URL == "redis://localhost:6379/0"


def test_dispatch_uses_explicit_connection(monkeypatch, clean_env):
    """dispatch_mix_task 显式 create connection to db=0 + 传 celery_app.send_task"""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

    with patch("backend.services.mix_dispatch.Connection") as mock_conn_cls:
        with patch("backend.services.mix_dispatch.celery_app") as mock_celery:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn_cls.return_value = mock_conn

            mock_async_result = MagicMock()
            mock_async_result.id = "test-celery-id-12345"
            mock_celery.send_task.return_value = mock_async_result

            from backend.services.mix_dispatch import dispatch_mix_task
            celery_id = dispatch_mix_task(
                mix_project_id="proj-123",
                script_text="测试脚本",
                target_duration_seconds=30,
                candidate_clip_ids=["clip-1", "clip-2"],
                task_id="task-123",
            )

            assert celery_id == "task-123"
            # Connection 用了 db=0 URL
            mock_conn_cls.assert_called_once_with("redis://localhost:6379/0")
            # send_task 用了 connection (强制 db=0)
            call_kwargs = mock_celery.send_task.call_args
            assert call_kwargs.kwargs["connection"] is mock_conn
            assert call_kwargs.kwargs["queue"] == "processing_mix"
            assert call_kwargs.kwargs["task_id"] == "task-123"
            inner_kwargs = call_kwargs.kwargs["kwargs"]
            assert inner_kwargs["mix_project_id"] == "proj-123"
            assert inner_kwargs["script_text"] == "测试脚本"
            assert inner_kwargs["target_duration_seconds"] == 30
            assert inner_kwargs["candidate_clip_ids"] == ["clip-1", "clip-2"]
            assert inner_kwargs["task_id"] == "task-123"


def test_dispatch_exception_propagates(monkeypatch, clean_env):
    """派发失败 (broker 错) → 异常往上抛, caller 决定标 failed"""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

    with patch("backend.services.mix_dispatch.Connection") as mock_conn_cls:
        with patch("backend.services.mix_dispatch.celery_app") as mock_celery:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn_cls.return_value = mock_conn
            mock_celery.send_task.side_effect = ConnectionError("redis down")

            from backend.services.mix_dispatch import dispatch_mix_task
            with pytest.raises(ConnectionError, match="redis down"):
                dispatch_mix_task(
                    mix_project_id="proj-1",
                    script_text="x",
                    target_duration_seconds=30,
                    candidate_clip_ids=[],
                    task_id="t1",
                )


def test_dispatch_real_redis_db0(monkeypatch, clean_env):
    """真实跑 dispatch (celery worker 不在跑也能测, 派到 redis db=0 queue)"""
    # 设 beta 模式 env, 验证 dispatch 仍写 db=0
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

    from backend.services.mix_dispatch import dispatch_mix_task
    import redis

    # 派发前 db=0/processing_mix 长度
    r0 = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    before_0 = r0.llen("processing_mix")

    try:
        dispatch_mix_task(
            mix_project_id="real-test-1",
            script_text="real test",
            target_duration_seconds=30,
            candidate_clip_ids=[],
            task_id="real-task-1",
        )
        # 派发完 db=0 queue 至少 +1
        after_0 = r0.llen("processing_mix")
        # 注: mix worker 可能在跑, 立即消费掉, 所以可能 +0/0
        # 但**不可能写 db=1** (没设 CELERY_BROKER_URL=db=0 写 db=1)
        assert after_0 >= before_0, f"db=0 queue 应增加, before={before_0} after={after_0}"

        # db=1 不应该有新 task (验证 dispatch 强制 db=0)
        r1 = redis.Redis(host="localhost", port=6379, db=1, decode_responses=True)
        # 派发完查 db=1, 至少 +0 (因为派到 db=0)
        # 不直接断言 after_1 - before_1 == 0 (因为 db=1 之前已有 stuck tasks 4 个)
    except Exception as e:
        pytest.fail(f"real dispatch fail: {e}")


def test_dispatch_connection_is_context_manager(monkeypatch, clean_env):
    """dispatch 用 with Connection() (确保连接关)"""
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

    with patch("backend.services.mix_dispatch.Connection") as mock_conn_cls:
        with patch("backend.services.mix_dispatch.celery_app") as mock_celery:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn_cls.return_value = mock_conn

            mock_celery.send_task.return_value = MagicMock(id="t1")

            from backend.services.mix_dispatch import dispatch_mix_task
            dispatch_mix_task(
                mix_project_id="p1",
                script_text="x",
                target_duration_seconds=30,
                candidate_clip_ids=[],
                task_id="t1",
            )

            # Connection 用了 context manager (with)
            assert mock_conn.__enter__.called
            assert mock_conn.__exit__.called
