"""
v2.2.41 /mix/preview-match 按段预选 endpoint 测试

修法: Step 2 加按段预选, 给每段 top-3 候选 clip + 自动勾选 top-1.
逻辑: 用 v2.2.36 substring tag overlap 公式 (0.7 tag + 0.3 embed, embed 失败 fallback keyword).
"""
import pytest


def test_preview_match_endpoint_400_empty_segments():
    """空 segments 返 400"""
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    r = client.post("/api/v1/mix/preview-match", json={"segments": [], "candidate_clip_ids": ["x"]})
    assert r.status_code == 400


def test_preview_match_endpoint_400_empty_candidates():
    """空 candidate_clip_ids 返 400"""
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app)
    r = client.post("/api/v1/mix/preview-match", json={"segments": [{"position": 0, "text": "x", "keywords": []}], "candidate_clip_ids": []})
    assert r.status_code == 400


def test_preview_match_substring_score_top1():
    """substring 公式正确: kw 包含 tag 子串也算命中, top-1 排第一"""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.main import app

    fake_library = [
        {"clip_id": "c1", "title": "屋顶施工", "source_project_name": "项目A",
         "duration": 30, "tags": ["屋顶", "防水"]},
        {"clip_id": "c2", "title": "室内装饰", "source_project_name": "项目B",
         "duration": 30, "tags": ["室内", "客厅"]},
    ]
    segments = [{"position": 0, "text": "屋顶", "keywords": ["屋顶", "瓦片"]}]

    with patch("backend.services.mix_service.build_clip_library_from_slice_db", return_value=fake_library):
        client = TestClient(app)
        r = client.post("/api/v1/mix/preview-match", json={
            "segments": segments,
            "candidate_clip_ids": ["c1", "c2"],
            "top_n": 3,
        })

    assert r.status_code == 200
    data = r.json()
    assert len(data["previews"]) == 1
    previews = data["previews"][0]
    assert previews["position"] == 0
    # c1 应排第一 (tag '屋顶' 命中 kw '屋顶')
    assert previews["top_clips"][0]["clip_id"] == "c1"
    assert previews["top_clips"][0]["match_score"] >= 0.4
    # matched_keywords 应包含 "屋顶"
    assert "屋顶" in previews["top_clips"][0]["matched_keywords"]


def test_preview_match_0_match_returns_empty_top_clips():
    """完全没匹配 → top_clips 空, frontend 显示 fallback 提示"""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.main import app

    fake_library = [
        {"clip_id": "c1", "title": "无关", "source_project_name": "X",
         "duration": 30, "tags": ["x", "y"]},
    ]
    segments = [{"position": 0, "text": "完全无关文本", "keywords": ["屋顶", "瓦片"]}]

    with patch("backend.services.mix_service.build_clip_library_from_slice_db", return_value=fake_library):
        client = TestClient(app)
        r = client.post("/api/v1/mix/preview-match", json={
            "segments": segments,
            "candidate_clip_ids": ["c1"],
        })

    assert r.status_code == 200
    data = r.json()
    assert data["previews"][0]["top_clips"] == []


def test_preview_match_top_n_limit():
    """top_n=2 → 最多返 2 个 top_clips"""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.main import app

    fake_library = [
        {"clip_id": f"c{i}", "title": f"屋顶 {i}", "source_project_name": "X",
         "duration": 30, "tags": ["屋顶"]}
        for i in range(5)
    ]
    segments = [{"position": 0, "text": "屋顶", "keywords": ["屋顶"]}]

    with patch("backend.services.mix_service.build_clip_library_from_slice_db", return_value=fake_library):
        client = TestClient(app)
        r = client.post("/api/v1/mix/preview-match", json={
            "segments": segments,
            "candidate_clip_ids": [f"c{i}" for i in range(5)],
            "top_n": 2,
        })

    assert r.status_code == 200
    assert len(r.json()["previews"][0]["top_clips"]) == 2


def test_preview_match_empty_library_warning():
    """素材库空 (没选素材) 返 previews=[] + warning 字段"""
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from backend.main import app

    with patch("backend.services.mix_service.build_clip_library_from_slice_db", return_value=[]):
        client = TestClient(app)
        r = client.post("/api/v1/mix/preview-match", json={
            "segments": [{"position": 0, "text": "x", "keywords": ["屋顶"]}],
            "candidate_clip_ids": ["non-existent-id"],
        })

    assert r.status_code == 200
    data = r.json()
    assert data["previews"] == []
    assert "warning" in data
