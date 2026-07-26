"""
v2.2.38 embedding placeholder key skip 测试

User 报: 每次 e2e 跑 mix 报 100+ 条 "embedding API 调用失败: 'data'" warning.
Root cause: OPENAI_API_KEY 是 sk-empty-f...test placeholder (23 chars), 每次调都 401.
修: _call_embedding 检测 placeholder key 提前 skip, 不发请求, 不污染 log.
"""
import os
import logging


def test_placeholder_key_skipped_no_warning(caplog, monkeypatch):
    """placeholder key (sk-empty-fake-test) 提前 skip, 不发请求, 走 keyword fallback."""
    caplog.set_level(logging.DEBUG)
    # 清掉 settings 缓存的 MINIMAX_API_KEY (避免 pydantic 缓存优先级)
    monkeypatch.setattr("backend.services.embedding_service.settings.MINIMAX_API_KEY", "", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-empty-fake-test")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    from backend.services.embedding_service import _call_embedding
    result = _call_embedding(["test text"])

    assert result is None, "placeholder key 应返 None (走 fallback)"
    debug_msgs = [r for r in caplog.records if r.levelno <= logging.DEBUG]
    warning_msgs = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("placeholder" in r.getMessage() for r in debug_msgs), (
        f"应该 log placeholder skip 提示, got: {[(r.levelname, r.getMessage()) for r in caplog.records]}"
    )
    assert not warning_msgs, f"placeholder 跳过时不应有 warning, got: {[r.getMessage() for r in warning_msgs]}"


def test_real_key_attempts_request(monkeypatch):
    """真 key (>= 30 chars) 应该发请求 (这里 mock httpx.post 验证)"""
    from unittest.mock import patch, MagicMock

    real_key = "sk-" + "x" * 40  # 43 chars, 长度足够, 不含 placeholder markers
    monkeypatch.setattr("backend.services.embedding_service.settings.MINIMAX_API_KEY", "", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", real_key)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)

    # mock httpx.post 返正常响应
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "data": [{"embedding": [0.1, 0.2, 0.3]}]
    }
    fake_response.raise_for_status = MagicMock()

    with patch("backend.services.embedding_service.httpx.post", return_value=fake_response) as mock_post:
        from backend.services.embedding_service import _call_embedding
        result = _call_embedding(["test text"])

    assert result == [[0.1, 0.2, 0.3]], "真 key 应返 embedding 向量"
    mock_post.assert_called_once(), "真 key 应发 httpx.post 请求"


def test_short_key_skipped(monkeypatch):
    """key 长度 < 30 (e.g. 5 chars) 提前 skip"""
    monkeypatch.setattr("backend.services.embedding_service.settings.MINIMAX_API_KEY", "", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "abcde")
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    from backend.services.embedding_service import _call_embedding
    result = _call_embedding(["x"])
    assert result is None


def test_no_env_key_skipped(monkeypatch):
    """env 没 OPENAI_API_KEY → 返 None"""
    monkeypatch.setattr("backend.services.embedding_service.settings.MINIMAX_API_KEY", "", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    from backend.services.embedding_service import _call_embedding
    result = _call_embedding(["x"])
    assert result is None
