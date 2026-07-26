"""Match fallback test (v2.2.26)

测 0 match 时用第一个 candidate clip 兜底 (避免 progress=30% fail).
"""
import pytest
from unittest.mock import patch, MagicMock

from backend.services.mix_service import match_clips_for_segments


def _seg(position, text, keywords):
    return {"position": position, "text": text, "keywords": keywords}


def _clip(clip_id, title, duration=10, source_type="library", project_name=""):
    return {
        "clip_id": clip_id,
        "title": title,
        "duration": duration,
        "source_project_id": "proj-1",
        "source_project_name": project_name,
        "source_type": source_type,
        "video_path": f"/data/{clip_id}.mp4",
    }


def test_0_match_uses_first_clip_fallback():
    """0 match → 用第一个 candidate clip 兜底 (而不是 fail)"""
    segments = [_seg(0, "屋面防水工程施工", ["屋面", "防水", "施工"])]
    # 5 个 resource clip 都没相关 keyword (test_speed_xxx)
    clip_library = [
        _clip("clip-1", "test_speed_1784268413", duration=10),
        _clip("clip-2", "test_speed_2", duration=10),
        _clip("clip-3", "test_speed_3", duration=10),
    ]

    with patch("backend.services.embedding_service.get_embedding") as mock_emb:
        mock_emb.return_value = None  # 模拟 embedding API 失败
        results = match_clips_for_segments(segments, clip_library, target_duration=30)

    # 0 match → fallback 兜底, 仍返 1 个 result (不 fail)
    assert len(results) == 1
    r = results[0]
    assert r["matched_clip_id"] == "clip-1"  # 用第一个
    assert r["match_score"] == 0.0  # 标 0 分
    assert r.get("fallback") is True  # 标 fallback


def test_real_match_takes_precedence():
    """有真 match 时, 不 fallback"""
    segments = [_seg(0, "屋面防水工程施工", ["屋面", "防水", "施工"])]
    clip_library = [
        _clip("clip-1", "test_speed_1", duration=10),  # 不匹配
        _clip("clip-2", "屋面防水工程", duration=10),  # 完美匹配
        _clip("clip-3", "test_speed_3", duration=10),
    ]

    with patch("backend.services.embedding_service.get_embedding") as mock_emb:
        mock_emb.return_value = None
        results = match_clips_for_segments(segments, clip_library, target_duration=30)

    assert len(results) == 1
    r = results[0]
    # 真匹配, 选 clip-2
    assert r["matched_clip_id"] == "clip-2"
    assert r.get("fallback") is not True
    assert r["match_score"] > 0.0  # 关键词命中, 应该有分


def test_no_candidate_clips_at_all_skips():
    """0 candidate clip (没素材) → 跳过这一段 (不返回 result)"""
    segments = [_seg(0, "屋面防水", ["屋面"])]
    clip_library = []  # 完全没素材

    with patch("backend.services.embedding_service.get_embedding") as mock_emb:
        mock_emb.return_value = None
        results = match_clips_for_segments(segments, clip_library, target_duration=30)

    # 0 candidate → 0 result (跳过)
    assert len(results) == 0


def test_mixed_segments_some_match_some_fallback():
    """多段: 有的真匹配, 有的 fallback"""
    segments = [
        _seg(0, "屋面防水", ["屋面", "防水"]),
        _seg(1, "完全不相关的话题", ["玻璃", "幕墙"]),
    ]
    clip_library = [
        _clip("clip-1", "test_speed_1", duration=10),
        _clip("clip-2", "屋面防水", duration=10),  # 匹配 seg 0
    ]

    with patch("backend.services.embedding_service.get_embedding") as mock_emb:
        mock_emb.return_value = None
        results = match_clips_for_segments(segments, clip_library, target_duration=30)

    # 2 段都有 result (seg 0 真匹配 clip-2, seg 1 fallback clip-1)
    assert len(results) == 2
    # 验证每个 result 都有 matched_clip_id
    for r in results:
        assert r.get("matched_clip_id")
        assert "source_start" in r
        assert "source_end" in r
