"""
混剪 v2.2.33 视觉匹配回归测试

测试 match_clips_for_segments 改用 tag overlap (0.7) + embed (0.3) 后的行为:
- 资源库 ResourceClip 的 tags 主导匹配 (视觉关键词 vs 资源库 tag)
- embed 相似度降到 0.3 辅助
- 0 阈值放宽到 0.05 (tag=0 但 embed>0.1 也进)

加 build_clip_library_from_slice_db ResourceClip.tags 字段测试.
"""
import pytest


def _make_segment(position, text, keywords):
    return {"position": position, "text": text, "keywords": keywords}


def _make_clip(clip_id, source_type="library", tags=None, title="", subtitle_text=""):
    return {
        "clip_id": clip_id,
        "source_project_id": f"proj_{clip_id}",
        "source_project_name": f"测试项目 {clip_id}",
        "title": title,
        "subtitle_text": subtitle_text,
        "video_path": f"data/resources/{clip_id}.mp4",
        "duration": 30.0,
        "width": 1920,
        "height": 1080,
        "source_type": source_type,
        "tags": tags or [],
    }


# ────────────────────────── match_clips_for_segments 视觉匹配 ──────────────────────────


def test_tag_overlap_主导匹配():
    """视觉关键词 vs 资源库 tag 重叠多 = 高分."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "屋顶防水要做 3 件事", ["屋顶", "防水"])]
    clip_library = [
        _make_clip("a", tags=["屋顶", "防水", "瓦片"]),  # 100% overlap
        _make_clip("b", tags=["室内", "客厅"]),  # 0% overlap
        _make_clip("c", tags=["防水", "材料"]),  # 50% overlap
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=60)
    assert len(results) == 1
    # 排序按 score 降序, 第一个 best_clip 应该是 a (100% overlap)
    assert results[0]["matched_clip_id"] == "a"
    assert results[0]["match_score"] > 0.5


def test_纯_视觉_关键词_无_embed_也命中():
    """当 clip 标题/字幕为空, 但 tags 有视觉关键词 → 仍命中 (走 tag overlap 主导)."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "测试文本", ["瓦片", "雨"])]
    clip_library = [
        # title/subtitle 都空, 只能走 tag overlap
        _make_clip("a", title="", subtitle_text="", tags=["瓦片", "雨"]),
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    assert len(results) == 1
    assert results[0]["matched_clip_id"] == "a"
    # tag_overlap=1.0 * 0.7 + embed=0 * 0.3 = 0.7
    assert 0.6 < results[0]["match_score"] <= 0.7


def test_substring_命中_v2_2_36():
    """v2.2.36: 关键词 vs tag 严格相等 + substring 都算命中.
    例: kw='防水材料' 包含 '防水' (tag) → 命中 (LLM 抽长词, tag 是短词, 严格相等会 0)."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "x", ["防水材料"])]  # 长词
    clip_library = [
        _make_clip("a", tags=["防水"]),  # 短词, 是 "防水材料" 子串
        _make_clip("b", tags=["瓦片"]),  # 无关
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    # a 应得高分 (substring 命中)
    assert results[0]["matched_clip_id"] == "a"
    assert results[0]["match_score"] > 0.5


def test_substring_反向_v2_2_36():
    """v2.2.36: 反向 substring — kw='屋顶' (短), tag='屋顶防水' (长) → 命中."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "x", ["屋顶"])]
    clip_library = [
        _make_clip("a", tags=["屋顶防水"]),  # 长 tag, 包含 "屋顶"
        _make_clip("b", tags=["外墙"]),
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    assert results[0]["matched_clip_id"] == "a"
    assert results[0]["match_score"] > 0.5


def test_关键词_大小写_空格_容错():
    """关键词 vs tag 大小写/空格 normalize 后能命中."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "x", ["屋顶", "  防水  "])]
    clip_library = [
        _make_clip("a", tags=["ROOF", "防 水"]),  # 完全不同
        _make_clip("b", tags=["屋顶", "防水"]),  # 完全匹配
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    assert results[0]["matched_clip_id"] == "b"


def test_0_match_fallback_保留_v2_2_26():
    """没任何 tag 重叠 + embed=0 时, 走 fallback (0 分 + fallback=True)."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "x", ["未知关键词xyz"])]
    clip_library = [
        _make_clip("a", tags=["毫不相关", "tag"]),
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    assert len(results) == 1
    assert results[0]["fallback"] is True
    assert results[0]["match_score"] == 0.0


def test_多段_各自_匹配_top1():
    """3 段不同视觉关键词, 各自匹配最相关的 clip."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [
        _make_segment(0, "屋顶", ["屋顶"]),
        _make_segment(1, "外墙", ["外墙"]),
        _make_segment(2, "室内", ["室内"]),
    ]
    clip_library = [
        _make_clip("a", tags=["屋顶", "瓦片"]),
        _make_clip("b", tags=["外墙", "防水"]),
        _make_clip("c", tags=["室内", "客厅"]),
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=60)
    assert len(results) == 3
    assert results[0]["matched_clip_id"] == "a"  # 屋顶 → a
    assert results[1]["matched_clip_id"] == "b"  # 外墙 → b
    assert results[2]["matched_clip_id"] == "c"  # 室内 → c


def test_空_关键词_列表_用_embed_fallback():
    """seg.keywords 为空时, 走 embed + title 匹配 (0.05 阈值)."""
    from backend.services.mix_service import match_clips_for_segments

    segments = [_make_segment(0, "今天讲屋顶防水的重要", [])]  # keywords=[]
    clip_library = [
        _make_clip("a", title="屋顶防水施工", subtitle_text="屋顶防水", tags=[]),
        _make_clip("b", title="室内装修", subtitle_text="客厅", tags=[]),
    ]
    results = match_clips_for_segments(segments, clip_library, target_duration=30)
    # 至少有一个能命中 (a, 标题包含"屋顶防水", embed 能 match)
    assert len(results) >= 1
    assert results[0]["matched_clip_id"] == "a"


# ────────────────────────── build_clip_library_from_slice_db tags 字段 ──────────────────────────


def test_build_clip_library_resource_clip_tags():
    """ResourceClip 应把 tags 字段 (list[str]) 透传到 library dict."""
    from backend.services.mix_service import build_clip_library_from_slice_db
    from unittest.mock import MagicMock, patch
    from backend.models.database import ResourceClip

    # mock ResourceClip query 返 1 个有 tags 的
    fake_rc = MagicMock(spec=ResourceClip)
    fake_rc.id = "rc-123"
    fake_rc.name = "测试素材"
    fake_rc.file_path = "data/resources/rc-123.mp4"
    fake_rc.duration = 30.0
    fake_rc.width = 1920
    fake_rc.height = 1080
    fake_rc.source_type = "upload"
    fake_rc.source_project_id = None
    fake_rc.source_project_name = "资源库"
    fake_rc.tags = ["屋顶", "防水"]
    fake_rc.deleted_at = None

    fake_db = MagicMock()
    # 第一次 query (Clip) 返 None, 第二次 (ResourceClip) 返 fake_rc
    fake_db.query.return_value.filter.return_value.first.side_effect = [None, fake_rc]
    fake_db.query.return_value.filter.return_value.filter.return_value.first.return_value = fake_rc

    # patch 实际 import 路径: backend.core.database.sync_get_db
    with patch("backend.core.database.sync_get_db") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = fake_db
        mock_get_db.return_value.__exit__.return_value = False

        library = build_clip_library_from_slice_db(["rc-123"])

    assert len(library) == 1
    assert library[0]["tags"] == ["屋顶", "防水"]
    assert library[0]["source_type"] == "library"
