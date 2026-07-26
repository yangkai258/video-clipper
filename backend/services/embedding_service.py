"""Embedding service (v2.2.21)

为混剪 match_clips_for_segments 提供 embedding 相似度评分, 跟 keyword substring
混合提升匹配质量. 设计:

- _call_embedding(texts) 调 OpenAI 兼容 /embeddings endpoint (MiniMax 也走同协议)
- 失败 / 无 key → 返 None (走 keyword fallback)
- 内存 LRU cache (max 1000 entries, 避免重复算)
- _cosine_similarity 纯 math 实现, 不依赖 numpy
- 开关: MIX_USE_EMBEDDING=0 env 强制 keyword-only

成本: OpenAI text-embedding-3-small $0.02/M tokens. 1 个 mix project
~10 segments × 50 candidate clips = 500 texts (~100KB) = $0.002. 1 美元
跑 500 个 project, 几乎免费.
"""

import logging
import os
from collections import OrderedDict
from math import sqrt

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────── 开关 ────────────────────────────

# v2.2.21: 开关, 默认开启 (有 API key 时)
# 设 MIX_USE_EMBEDDING=0 强制 keyword-only
_USE_EMBEDDING_ENV = os.getenv("MIX_USE_EMBEDDING", "1").lower() not in (
    "0",
    "false",
    "no",
)


def is_embedding_enabled() -> bool:
    """检查 embedding 评分是否启用.

    条件: env 开关开 + 有 LLM API key + 服务可用.
    """
    if not _USE_EMBEDDING_ENV:
        return False
    # 检查 API key (MINIMAX_API_KEY 是 MiniMax / OpenAI 兼容, 复用)
    api_key = getattr(settings, "MINIMAX_API_KEY", "") or os.getenv(
        "OPENAI_API_KEY", ""
    )
    return bool(api_key) and not api_key.startswith("sk-...")


# ──────────────────────────── Cache (LRU) ────────────────────────────

_CACHE_MAX = 1000
_embedding_cache: "OrderedDict[str, list[float]]" = OrderedDict()


def _cache_get(text: str) -> list[float] | None:
    """LRU 读 cache, 命中时刷新顺序 (最近使用排前)."""
    key = text.strip()
    if key in _embedding_cache:
        _embedding_cache.move_to_end(key)
        return _embedding_cache[key]
    return None


def _cache_put(text: str, vec: list[float]) -> None:
    """LRU 写 cache, 超限淘汰最久未用."""
    key = text.strip()
    if key in _embedding_cache:
        _embedding_cache.move_to_end(key)
    _embedding_cache[key] = vec
    if len(_embedding_cache) > _CACHE_MAX:
        _embedding_cache.popitem(last=False)  # 删最久


def cache_clear() -> None:
    """清空 cache (测试用)."""
    _embedding_cache.clear()


def cache_size() -> int:
    return len(_embedding_cache)


# ──────────────────────────── API call ────────────────────────────


def _call_embedding(
    texts: list[str], model: str = "embo-01"
) -> list[list[float]] | None:
    """调 OpenAI 兼容 /embeddings endpoint.

    Args:
        texts: 要 embed 的文本列表 (1-100, 跟 OpenAI 限速)
        model: embedding 模型名 (默认 embo-01, MiniMax 的; OpenAI 改 text-embedding-3-small)

    Returns:
        跟输入同长度的向量列表, 失败返 None.

    v2.2.38: 检测 placeholder key 提前 skip, 不发请求 (避免每次 e2e 跑 100+ 条 warning 噪音).
    判定: key 长度 < 30 OR key 包含 "empty"/"placeholder"/"test" 等占位符字符串.
    """
    # v2.2.21: MiniMax 走 OpenAI 兼容, base_url 从 settings 读
    api_key = getattr(settings, "MINIMAX_API_KEY", "") or os.getenv(
        "OPENAI_API_KEY", ""
    )
    if not api_key:
        logger.debug("embedding 跳过: 无 API key")
        return None

    # v2.2.38: placeholder key 检测 — 提前 skip, 不打 401 + 不污染 log
    placeholder_markers = ("empty", "placeholder", "your-key", "<", "test-key", "-test")
    if len(api_key) < 30 or any(m in api_key.lower() for m in placeholder_markers):
        logger.debug(
            "embedding 跳过: API key 是 placeholder (length=%d), 走 keyword fallback",
            len(api_key),
        )
        return None

    base_url = getattr(
        settings, "MINIMAX_BASE_URL", "https://api.minimaxi.com/v1"
    ).rstrip("/")
    if "minimaxi" in base_url and model == "embo-01":
        pass  # MiniMax 默认 embo-01
    elif "openai.com" in base_url and model == "embo-01":
        model = "text-embedding-3-small"  # OpenAI 换默认

    url = f"{base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "input": texts}

    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=30.0)
        if r.status_code != 200:
            logger.warning(
                f"embedding API 失败: status={r.status_code} body={r.text[:200]}"
            )
            return None
        data = r.json()
        return [item["embedding"] for item in data["data"]]
    except (httpx.HTTPError, KeyError, ValueError) as e:
        logger.warning(f"embedding API 调用失败: {e}")
        return None


def get_embedding(text: str) -> list[float] | None:
    """单条文本 embedding (走 cache)."""
    if not text or not text.strip():
        return None
    cached = _cache_get(text)
    if cached is not None:
        return cached
    result = _call_embedding([text])
    if not result:
        return None
    vec = result[0]
    _cache_put(text, vec)
    return vec


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None] | None:
    """批量 embedding (走 cache, 一次 API 调用).

    Returns:
        跟输入同长度, 每项要么是向量要么是 None (失败位置).
        整个 batch 失败返 None.
    """
    if not texts:
        return []
    # 先看 cache
    results: list[list[float] | None] = [None] * len(texts)
    need_call: list[int] = []
    need_texts: list[str] = []
    for i, t in enumerate(texts):
        if not t or not t.strip():
            continue
        cached = _cache_get(t)
        if cached is not None:
            results[i] = cached
        else:
            need_call.append(i)
            need_texts.append(t)
    if not need_texts:
        return results
    # 去重 (重复文本只算 1 次)
    unique_texts = list(dict.fromkeys(need_texts))  # 保序去重
    api_result = _call_embedding(unique_texts)
    if not api_result or len(api_result) != len(unique_texts):
        # API 失败, 没缓存的位置都 None
        return results
    # 建 unique_texts → vec 映射
    text_to_vec: dict[str, list[float]] = dict(zip(unique_texts, api_result, strict=False))
    # 回填 results + 写 cache
    for idx, t in zip(need_call, need_texts, strict=False):
        if t in text_to_vec:
            vec = text_to_vec[t]
            results[idx] = vec
            _cache_put(t, vec)
    return results


# ──────────────────────────── Cosine similarity ────────────────────────────


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """纯 math 实现 cosine 相似度, 返 [-1, 1].

    维度不一致返 0.0.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ──────────────────────────── Mix 集成 helper ────────────────────────────


def hybrid_match_score(
    seg_text: str,
    seg_keywords: list[str],
    clip_title: str,
    clip_subtitle: str = "",
) -> float:
    """混合 score (embedding + keyword), 返 [0, 1].

    用法: match_clips_for_segments 调这个替 keyword-only score.

    设计:
    - 0.6 * embedding_sim + 0.4 * keyword_score
    - 没 embedding 时 走 keyword 100%
    - 都失败 返 0.0
    """
    # 1. keyword 算分 (保留 v2.2.3 逻辑)
    search_text = (clip_title + " " + clip_subtitle).strip()
    if not search_text:
        return 0.0

    expanded: list[str] = []
    for kw in seg_keywords:
        if not kw:
            continue
        expanded.append(kw)
        if " " in kw or len(kw) > 4:
            expanded.extend(kw.replace(" ", ""))
    if not expanded:
        # 没 keyword 走 embedding only
        kw_score = 0.0
    else:
        hits = sum(1 for kw in expanded if kw in search_text)
        if hits == 0:
            kw_score = 0.0
        else:
            kw_score = hits / len(expanded)
            if any(kw and kw in clip_title for kw in expanded):
                kw_score = min(1.0, kw_score * 1.5)

    # 2. embedding 算分 (0.6 权重)
    if not is_embedding_enabled():
        return kw_score  # 没启用 → 100% keyword

    # 算 segment + clip embedding
    seg_vec = get_embedding(seg_text)
    clip_vec = get_embedding(search_text)
    if not seg_vec or not clip_vec:
        return kw_score  # 失败 → 100% keyword

    sim = _cosine_similarity(seg_vec, clip_vec)
    # 0.6 embedding + 0.4 keyword, embedding 主导
    final = 0.6 * sim + 0.4 * kw_score
    return max(0.0, min(1.0, final))  # clip [0, 1]
