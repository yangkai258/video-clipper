"""Embedding service test (v2.2.21)

测 _cosine_similarity / cache / hybrid_match_score (mock API).
"""
from unittest.mock import MagicMock, patch

import pytest

from backend.services.embedding_service import (
    _call_embedding,
    _cosine_similarity,
    cache_clear,
    get_embedding,
    get_embeddings_batch,
    hybrid_match_score,
    is_embedding_enabled,
)

# === _cosine_similarity ===

def test_cosine_identical():
    """相同向量 = 1.0"""
    v = [1.0, 0.0, 0.0]
    assert _cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_orthogonal():
    """正交 = 0.0"""
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_opposite():
    """反向 = -1.0"""
    a = [1.0, 0.0]
    b = [-1.0, 0.0]
    assert _cosine_similarity(a, b) == pytest.approx(-1.0)


def test_cosine_dim_mismatch():
    """维度不一致返 0.0"""
    a = [1.0, 0.0]
    b = [1.0, 0.0, 0.0]
    assert _cosine_similarity(a, b) == 0.0


def test_cosine_zero_vector():
    """零向量返 0.0 (避免除 0)"""
    assert _cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0


def test_cosine_typical_high():
    """典型高相似度 (近 1)"""
    a = [0.6, 0.8]
    b = [0.5, 0.866]  # 跟 a 接近
    sim = _cosine_similarity(a, b)
    assert sim > 0.95


# === _call_embedding (mock httpx) ===

def test_call_embedding_success():
    """API 返 200 + data, 解析成 List[List[float]]"""
    with patch("backend.services.embedding_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"data": [
                {"embedding": [0.1, 0.2, 0.3]},
                {"embedding": [0.4, 0.5, 0.6]},
            ]},
        )
        result = _call_embedding(["text1", "text2"])
        assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]


def test_call_embedding_no_api_key():
    """无 API key 返 None"""
    with patch("backend.services.embedding_service.getattr") as mock_getattr:
        mock_getattr.return_value = ""  # MINIMAX_API_KEY 空
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            result = _call_embedding(["text"])
            assert result is None


def test_call_embedding_api_error():
    """API 返 500 → None"""
    with patch("backend.services.embedding_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=500, text="internal error")
        result = _call_embedding(["text"])
        assert result is None


def test_call_embedding_timeout():
    """timeout 异常 → None"""
    import httpx
    with patch("backend.services.embedding_service.httpx.post") as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timeout")
        result = _call_embedding(["text"])
        assert result is None


# === get_embedding (单条 + cache) ===

def test_get_embedding_cache_hit():
    """cache 命中 (不调 API)"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        mock_call.return_value = [[0.1, 0.2, 0.3]]
        v1 = get_embedding("hello")
        v2 = get_embedding("hello")  # cache 命中
        assert v1 == v2
        assert mock_call.call_count == 1
    cache_clear()


def test_get_embedding_empty_text():
    """空文本 → None (不调 API)"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        v = get_embedding("")
        assert v is None
        mock_call.assert_not_called()
    cache_clear()


def test_get_embedding_api_fail():
    """API 失败 → None"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        mock_call.return_value = None
        v = get_embedding("text")
        assert v is None
    cache_clear()


# === get_embeddings_batch (批量 + cache) ===

def test_batch_all_cache_hit():
    """部分 cache 命中 + 部分新: 只算 unique 新调一次"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        # 第 1 步: 填 foo cache
        mock_call.return_value = [[0.1]]
        get_embedding("foo")
        # 重置 count
        mock_call.reset_mock()
        # 第 2 步: batch ["foo", "bar"], foo 命中 cache, bar 新
        mock_call.return_value = [[0.2]]
        result = get_embeddings_batch(["foo", "bar"])
        assert result == [[0.1], [0.2]]
        # 1 次 (只 bar 调 _call_embedding)
        assert mock_call.call_count == 1
    cache_clear()


def test_batch_dedup_unique_texts():
    """重复文本去重, 只调 1 次"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        # 2 unique (foo, bar) → 2 输出
        mock_call.return_value = [[0.1], [0.2]]
        result = get_embeddings_batch(["foo", "foo", "bar", "foo"])
        # 4 输入, 2 unique, mock 1 次
        assert mock_call.call_count == 1
        assert len(result) == 4
        # 都填了
        assert all(r is not None for r in result)
    cache_clear()


def test_batch_api_fail_keeps_cached():
    """API 失败保留已 cache 的位置"""
    cache_clear()
    with patch("backend.services.embedding_service._call_embedding") as mock_call:
        # 第 1 次成功, 填 "foo" + "bar" cache
        mock_call.return_value = [[0.5], [0.6]]
        get_embeddings_batch(["foo", "bar"])
        # 第 2 次 "foo" 命中 cache, "baz" 失败
        mock_call.return_value = None
        result = get_embeddings_batch(["foo", "baz"])
        assert result[0] == [0.5]
        assert result[1] is None
    cache_clear()


def test_cache_lru_eviction():
    """超 1000 entry 淘汰最久 (走 cache_put 触发 LRU)"""
    from backend.services.embedding_service import (
        _CACHE_MAX,
        _cache_put,
        _embedding_cache,
        cache_clear,
    )

    cache_clear()
    for i in range(_CACHE_MAX + 100):
        _cache_put(f"text_{i}", [float(i)])
    # 超 1000 应该 popitem(last=False) 删最早的
    assert len(_embedding_cache) == _CACHE_MAX
    # text_0 已被淘汰
    assert "text_0" not in _embedding_cache
    # text_{1000} 还在
    assert f"text_{_CACHE_MAX}" in _embedding_cache
    cache_clear()


# helper for cache test
def _real_cache_get(text):
    from backend.services.embedding_service import _embedding_cache
    if text in _embedding_cache:
        _embedding_cache.move_to_end(text)
        return _embedding_cache[text]
    return None


# === is_embedding_enabled ===

def test_embedding_disabled_env_0(monkeypatch):
    """env MIX_USE_EMBEDDING=0 强制关"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    # 重置 module-level constant (因为之前 import 时 evaluate)
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)
    assert is_embedding_enabled() is False


def test_embedding_disabled_no_api_key(monkeypatch):
    """无 API key → 关"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "1")
    with patch("backend.services.embedding_service.settings") as mock_settings:
        mock_settings.MINIMAX_API_KEY = ""
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=False):
            import backend.services.embedding_service as em
            monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", True)
            assert is_embedding_enabled() is False


def test_embedding_enabled_with_key(monkeypatch):
    """有 API key + env 1 → 开"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "1")
    with patch("backend.services.embedding_service.settings") as mock_settings:
        mock_settings.MINIMAX_API_KEY = "test-key"
        with patch.dict("os.environ", {}, clear=False):
            # 清 OPENAI_API_KEY
            monkeypatch.delenv("OPENAI_API_KEY", raising=False)
            import backend.services.embedding_service as em
            monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", True)
            assert is_embedding_enabled() is True


# === hybrid_match_score (核心集成) ===

def test_hybrid_keyword_only_when_disabled(monkeypatch):
    """embedding 关闭 → 100% keyword 逻辑"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)

    # keyword "防水" 命中 title "防水工程"
    score = hybrid_match_score(
        seg_text="讲防水工程",
        seg_keywords=["防水"],
        clip_title="防水工程",
        clip_subtitle="",
    )
    # 1/1 = 1.0, title 命中 1.5 → clip 1.0
    assert score == pytest.approx(1.0, abs=0.01)


def test_hybrid_keyword_no_hit_returns_zero(monkeypatch):
    """keyword 没命中 → 0"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)

    score = hybrid_match_score(
        seg_text="讲玻璃幕墙",
        seg_keywords=["玻璃"],
        clip_title="防水工程",
    )
    assert score == 0.0


def test_hybrid_embedding_disabled_uses_keyword(monkeypatch):
    """embedding 关掉 + keyword 没命中 → 0 (不调 API)"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)
    with patch("backend.services.embedding_service.get_embedding") as mock_emb:
        score = hybrid_match_score("讲玻璃", ["玻璃"], "防水工程")
        # keyword 没命中 + embedding 关闭 → 0
        assert score == 0.0
        mock_emb.assert_not_called()


def test_hybrid_embedding_enabled_mix(monkeypatch):
    """embedding 开 + 模拟高相似度 → 混合 score"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "1")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", True)
    with patch("backend.services.embedding_service.settings") as mock_settings:
        mock_settings.MINIMAX_API_KEY = "test-key"
        with patch("backend.services.embedding_service.get_embedding") as mock_emb:
            # 模拟高相似度 (同方向)
            mock_emb.side_effect = lambda t: [1.0, 0.0, 0.0] if "防水" in t else [0.9, 0.1, 0.0]
            # keyword "防水" 命中
            score = hybrid_match_score(
                seg_text="讲防水施工",
                seg_keywords=["防水"],
                clip_title="防水工程",
            )
            # kw_score ~ 1.0 (title 命中), embedding ~ 1.0
            # final = 0.6 * 1.0 + 0.4 * 1.0 = 1.0
            assert score == pytest.approx(1.0, abs=0.05)


def test_hybrid_embedding_api_fail_falls_back(monkeypatch):
    """embedding API 失败 → 走 keyword 100%"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "1")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", True)
    with patch("backend.services.embedding_service.settings") as mock_settings:
        mock_settings.MINIMAX_API_KEY = "test-key"
        with patch("backend.services.embedding_service.get_embedding") as mock_emb:
            mock_emb.return_value = None  # API 失败
            score = hybrid_match_score(
                seg_text="讲玻璃幕墙",
                seg_keywords=["玻璃"],
                clip_title="玻璃幕墙",
            )
            # embedding 失败 → 100% keyword
            # "玻璃" 命中 "玻璃幕墙" → kw = 1/1 = 1.0, title 命中 1.5 → 1.0
            assert score == pytest.approx(1.0, abs=0.01)


def test_hybrid_empty_clip_returns_zero(monkeypatch):
    """clip title + subtitle 全空 → 0"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)
    score = hybrid_match_score("讲防水", ["防水"], "", "")
    assert score == 0.0


def test_hybrid_keyword_with_compound(monkeypatch):
    """复合词命中 (中文 title 直接含, 不需要 split)"""
    monkeypatch.setenv("MIX_USE_EMBEDDING", "0")
    import backend.services.embedding_service as em
    monkeypatch.setattr(em, "_USE_EMBEDDING_ENV", False)
    # keyword "防水套装" (复合) 命中 title "防水套装工程"
    score = hybrid_match_score(
        seg_text="讲防水",
        seg_keywords=["防水套装"],
        clip_title="防水套装工程",
    )
    # 命中 1/1 = 1.0, title 命中 1.5 → clip 1.0
    assert score == pytest.approx(1.0, abs=0.01)
