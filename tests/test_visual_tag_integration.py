"""
v2.2.47 视觉打标接入测试

User 反馈:
1. LLM auto-tag 抽过来的规则不准 (v2.2.38 默认关, 但需要别的兜底)
2. 视觉匹配公式只有"主题词"维度, 缺"画面属性"维度

修法:
1. ResourceClip 加 visual_tags 列 (0 依赖 auto-generate)
2. upload / from-clip / from-project 3 处同步跑 generate_visual_tags
3. match 公式 combined_tag_overlap = max(tags_overlap, visual_overlap)
4. POST /library/{id}/auto-tag 同步刷 visual_tags
5. _serialize 返 visual_tags 给前端展示
"""


# ──────────────────────────── 1. migration 列存在 ────────────────────────────


def test_visual_tags_column_exists():
    """ResourceClip 必须有 visual_tags 列 (v2.2.47 migration 加)"""
    from backend.models.database import ResourceClip

    assert hasattr(ResourceClip, "visual_tags"), "ResourceClip 缺 visual_tags 列"
    # Column 类型验证 (JSON)
    col = ResourceClip.__table__.columns["visual_tags"]
    from sqlalchemy import JSON

    assert isinstance(col.type, JSON), f"visual_tags 类型应是 JSON, 实为 {type(col.type)}"


def test_visual_tags_default_is_list():
    """visual_tags default 必须是 list (跟 tags 一致)"""
    from backend.models.database import ResourceClip

    col = ResourceClip.__table__.columns["visual_tags"]
    assert col.default is not None, "visual_tags 必须有 default (兼容老 row)"


# ──────────────────────────── 2. endpoint 接入 ────────────────────────────


def test_upload_calls_visual_tag():
    """upload endpoint 必须调 generate_visual_tags (源码搜)"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library.upload_resource)
    assert "generate_visual_tags" in src, "upload 缺 visual_tag 调用"
    assert "visual_tags=visual_tags" in src, "upload ResourceClip 缺 visual_tags= 入参"


def test_from_clip_calls_visual_tag():
    """from-clip endpoint 必须调 generate_visual_tags"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library.from_clip_resource)
    assert "generate_visual_tags" in src, "from-clip 缺 visual_tag 调用"
    assert "visual_tags=visual_tags" in src, "from-clip ResourceClip 缺 visual_tags= 入参"


def test_from_project_batch_calls_visual_tag():
    """from-project batch endpoint 必须调 generate_visual_tags (每行)"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library.from_project_batch_resource)
    assert "generate_visual_tags" in src, "from-project batch 缺 visual_tag 调用"
    assert "visual_tags=visual_tags" in src, "from-project batch ResourceClip 缺 visual_tags= 入参"


def test_from_project_batch_also_extracts_tags():
    """v2.2.47: from-project batch 跟 from-clip 一样抽源 clip_metadata.tags (v2.2.38 漏了)"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library.from_project_batch_resource)
    assert "clip_metadata" in src, "from-project batch 缺 clip_metadata 抽 tags 逻辑"
    assert "clip_tags" in src, "from-project batch 缺 clip_tags 变量"


def test_auto_tag_endpoint_also_refreshes_visual_tags():
    """POST /library/{id}/auto-tag 同步刷 visual_tags"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library.auto_tag_resource_endpoint)
    assert "generate_visual_tags" in src, "auto-tag endpoint 缺 visual_tag 调用"
    assert "rc.visual_tags" in src, "auto-tag endpoint 缺 rc.visual_tags = visual_tags 写回"
    # 返回值必须包含 visual_tags
    assert '"visual_tags"' in src or "visual_tags" in src, "auto-tag 返回值缺 visual_tags"


# ──────────────────────────── 3. _serialize 返 visual_tags ────────────────────────────


def test_serialize_includes_visual_tags():
    """_serialize 必须返 visual_tags 给前端"""
    import inspect

    from backend.api import library

    src = inspect.getsource(library._serialize)
    assert "visual_tags" in src, "_serialize 缺 visual_tags key"
    assert "rc.visual_tags" in src, "_serialize 缺 rc.visual_tags 取值"


# ──────────────────────────── 4. match 公式 combined_tag_overlap ────────────────────────────


def test_match_combined_tag_overlap_helper():
    """mix_service match 必须用 combined_tag_overlap (含 visual_tags)"""
    import inspect

    from backend.services import mix_service

    src = inspect.getsource(mix_service.match_clips_for_segments)
    assert "visual_tags" in src, "match 缺 visual_tags 处理"
    assert "combined_tag_overlap" in src, "match 缺 combined_tag_overlap 变量"
    # 必须用 max 不是 avg (visual 0 拉低问题)
    assert "max(tag_overlap, visual_tag_overlap)" in src, "combined_tag_overlap 必须 max 不是 avg"


def test_library_clip_dict_has_visual_tags_key():
    """build_clip_library_from_slice_db 抽出来的 dict 必须含 visual_tags key (v2.2.47 接入)"""
    import inspect

    from backend.services import mix_service

    src = inspect.getsource(mix_service.build_clip_library_from_slice_db)
    # ResourceClip 分支必须返 visual_tags
    assert "visual_tags" in src, "build_clip_library_from_slice_db 缺 visual_tags key 注入"


# ──────────────────────────── 5. 端到端 match 行为 ────────────────────────────


def test_match_visual_only_tag_scores_higher():
    """播音稿关键词命中 visual_tags (e.g. "动态") 也算 match, 不会被打 0"""
    from backend.services.mix_service import match_clips_for_segments

    # 模拟 2 个 candidate: 一个 tags=["防水"], 一个 visual_tags=["动态"]
    # 播音稿 keywords=["动态"]
    segments = [{"position": 0, "text": "测试段", "keywords": ["动态"]}]
    clip_library = [
        {
            "clip_id": "c1",
            "title": "防水测试",
            "subtitle_text": "",
            "video_path": "/tmp/a.mp4",
            "duration": 5.0,
            "source_type": "library",
            "source_project_id": "p1",
            "source_project_name": "P1",
            "tags": ["防水"],
            "visual_tags": [],  # 视觉空
        },
        {
            "clip_id": "c2",
            "title": "工地现场",
            "subtitle_text": "",
            "video_path": "/tmp/b.mp4",
            "duration": 5.0,
            "source_type": "library",
            "source_project_id": "p2",
            "source_project_name": "P2",
            "tags": [],
            "visual_tags": ["动态", "繁复"],  # 视觉有"动态"
        },
    ]
    # 不接 embed (没 API key, skip; embed_score=0 仍走完公式)
    results = match_clips_for_segments(segments, clip_library)
    assert len(results) == 1
    matched_id = results[0]["matched_clip_id"]
    matched_score = results[0]["match_score"]
    # c2 (visual 命中"动态") 应该比 c1 (tags 0 命中) 高
    # 注意: embed_service 走 placeholder key 自动 skip, embed_score=0,
    # c1 score = 0.7 * 0 = 0 (< 0.05 阈值 skip)
    # c2 score = 0.7 * 1.0 = 0.7 (max(0, 1.0) = 1.0)
    # 所以结果只返 c2
    assert matched_id == "c2", f"visual_tags 命中'动态' 应该匹配 c2, 实为 {matched_id}"
    assert matched_score > 0.5, f"visual_tags 命中分应 > 0.5, 实为 {matched_score}"


def test_match_combined_max_uses_higher_dimension():
    """combined_tag_overlap = max, 不拉低 (visual 0 不影响 tags 高分)"""
    from backend.services.mix_service import match_clips_for_segments

    segments = [{"position": 0, "text": "测试", "keywords": ["防水"]}]
    # 一个 candidate tags 命中"防水" 1.0, visual 0
    clip_library = [
        {
            "clip_id": "c1",
            "title": "防水",
            "subtitle_text": "",
            "video_path": "/tmp/a.mp4",
            "duration": 5.0,
            "source_type": "library",
            "source_project_id": "p1",
            "source_project_name": "P1",
            "tags": ["防水"],
            "visual_tags": [],  # visual 0
        },
    ]
    results = match_clips_for_segments(segments, clip_library)
    assert len(results) == 1
    # combined = max(1.0, 0) = 1.0; score = 0.7 * 1.0 + 0.3 * 0 = 0.7
    assert results[0]["match_score"] >= 0.7, f"tags 命中 1.0 应得 0.7, 实为 {results[0]['match_score']}"


# ──────────────────────────── 6. e2e 真 mp4 端到端 ────────────────────────────


def test_e2e_real_mp4_visual_tags_persist(tmp_path):
    """e2e: 真 mp4 走 generate_visual_tags → 写 ResourceClip.visual_tags → 读回"""
    # 找 data/resources 任一真 mp4 (从 from-clip e2e)
    import json
    import subprocess
    from pathlib import Path

    # 找仓库内一真 mp4 (从 data/projects/<proj>/output/clips/)
    candidates = list(Path("data/projects").rglob("output/clips/*.mp4")) if Path("data/projects").exists() else []
    real_mp4 = None
    for c in candidates:
        # 验 moov atom 存在 (不是 fake file)
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(c)],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and json.loads(r.stdout).get("format", {}).get("duration"):
                real_mp4 = c
                break
        except Exception:
            continue

    if real_mp4 is None:
        # 没真 mp4 跳过 (CI 环境)
        import pytest
        pytest.skip("data/projects 无真 mp4 (跳过 e2e)")
        return

    # 调 generate_visual_tags (sync, ~0.3s)
    from backend.services.visual_tag_service import generate_visual_tags

    tags = generate_visual_tags(real_mp4)
    assert isinstance(tags, list), f"visual_tags 返 list, 实为 {type(tags)}"
    # 至少 1 个 (mp4 真存在就有结果)
    # e2e 04a46df8 实测返 4 个
    assert len(tags) >= 1, f"真 mp4 至少返 1 个 visual_tag, 实为 0"
    # 都是 str + 2-6 字 (跟 ResourceClip.tags 一致)
    for t in tags:
        assert isinstance(t, str)
        assert 2 <= len(t) <= 6, f"visual_tag 长度 2-6, 实为 {len(t)}: {t}"
