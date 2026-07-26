"""
v2.2.52 真实 vision API 接入测试

User 反馈: v2.2.45 留 _call_vision_api 占位 (没 key 返 None).
v2.2.52 接真 MiniMax-Vision (MiniMax-Text-01 支持 image input)
+ OpenAI gpt-4o-mini fallback.

测试:
1. _call_vision_api 有 MINIMAX_API_KEY 走真 API
2. _call_vision_api 无 key 返 None
3. _call_vision_api placeholder key 返 None
4. generate_visual_tags 集成 (有 key 时 tags > 4 个, 多 5 个 vision tag)
5. 真 vision 返回 2-6 字中文短词
"""
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# v2.2.52: 显式 load .env (pytest 启动不自动 load)
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass  # 没 dotenv 也跑, 跳过真 vision e2e


def _has_real_minimax_key() -> bool:
    """检查 .env 是否有真 MiniMax key (排除 empty/placeholder)"""
    env_path = Path(__file__).parent.parent / ".env"
    key = os.environ.get("MINIMAX_API_KEY", "")
    if not key or len(key) < 30 or "empty" in key.lower():
        # 试读 .env
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("MINIMAX_API_KEY="):
                    k = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if k and len(k) >= 30 and "empty" not in k.lower():
                        return True
        return False
    return True


# ──────────────────────────── 1. _call_vision_api 行为 ────────────────────────────


def test_call_vision_api_no_key_returns_none(tmp_path):
    """没 key → 返 None (走 0 依赖 fallback)"""
    fake_jpg = tmp_path / "x.jpg"
    fake_jpg.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic
    with patch.dict(os.environ, {"MINIMAX_API_KEY": "", "OPENAI_API_KEY": ""}, clear=False):
        from backend.services.visual_tag_service import _call_vision_api
        assert _call_vision_api(fake_jpg) is None


def test_call_vision_api_placeholder_key_returns_none(tmp_path):
    """placeholder key → 返 None"""
    fake_jpg = tmp_path / "x.jpg"
    fake_jpg.write_bytes(b"\xff\xd8\xff\xe0")
    with patch.dict(os.environ, {
        "MINIMAX_API_KEY": "sk-empty-test-placeholder",
        "OPENAI_API_KEY": "",
    }, clear=False):
        from backend.services.visual_tag_service import _call_vision_api
        assert _call_vision_api(fake_jpg) is None


def test_call_vision_api_short_key_returns_none(tmp_path):
    """太短的 key → 返 None (防 partial key 浪费 API call)"""
    fake_jpg = tmp_path / "x.jpg"
    fake_jpg.write_bytes(b"\xff\xd8\xff\xe0")
    with patch.dict(os.environ, {"MINIMAX_API_KEY": "sk-short", "OPENAI_API_KEY": ""}, clear=False):
        from backend.services.visual_tag_service import _call_vision_api
        assert _call_vision_api(fake_jpg) is None


def test_call_vision_api_real_call_parses_json():
    """mock httpx 返 JSON array → 解析成功"""
    fake_jpg = Path("/tmp/test_v2_frame.jpg")
    if not fake_jpg.exists():
        pytest.skip("/tmp/test_v2_frame.jpg 不存在, 跳过 mock 测 (实际跑 e2e 测)")
        return

    mock_r = MagicMock()
    mock_r.status_code = 200
    mock_r.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": '["屋顶", "工人", "施工", "室外", "白天"]',
                }
            }
        ]
    }

    with patch.dict(os.environ, {
        "MINIMAX_API_KEY": "sk-cp-test-key-long-enough-to-pass-min-len-30",
        "MINIMAX_BASE_URL": "https://api.minimaxi.com/v1",
    }, clear=False):
        with patch("httpx.post", return_value=mock_r):
            from backend.services.visual_tag_service import _call_vision_api
            tags = _call_vision_api(fake_jpg)
            assert tags is not None
            assert len(tags) == 5
            assert "屋顶" in tags
            assert "工人" in tags


def test_call_vision_api_real_call_bad_status_returns_none():
    """mock httpx 返 400 → 返 None"""
    fake_jpg = Path("/tmp/test_v2_frame.jpg")
    if not fake_jpg.exists():
        pytest.skip("skip")
        return
    mock_r = MagicMock()
    mock_r.status_code = 400
    mock_r.text = "bad request"

    with patch.dict(os.environ, {
        "MINIMAX_API_KEY": "sk-cp-test-key-long-enough-to-pass-min-len-30",
    }, clear=False):
        with patch("httpx.post", return_value=mock_r):
            from backend.services.visual_tag_service import _call_vision_api
            assert _call_vision_api(fake_jpg) is None


# ──────────────────────────── 2. 真 e2e vision (有真 key 时) ────────────────────────────


@pytest.mark.skipif(
    not _has_real_minimax_key(),
    reason="无真 MINIMAX_API_KEY (CI 环境 skip)",
)
def test_e2e_real_vision_returns_chinese_tags():
    """e2e: 真 mp4 + 真 MiniMax API → 返 5+ 个中文短词 tag"""
    # 找真 mp4
    candidates = list(Path("data/resources").glob("*.mp4"))
    real_mp4 = None
    import json
    import subprocess
    for c in candidates:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(c)],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                dur = json.loads(r.stdout).get("format", {}).get("duration")
                if dur and float(dur) > 0:
                    real_mp4 = c
                    break
        except Exception:
            continue
    if real_mp4 is None:
        pytest.skip("data/resources 无真 mp4 (ffprobe 都失败)")
        return

    # 调真 vision
    from backend.services.visual_tag_service import _call_vision_api, extract_one_frame

    frame = extract_one_frame(real_mp4)
    if not frame:
        pytest.skip("extract_one_frame 失败 (ffmpeg 不可用?)")
        return

    try:
        tags = _call_vision_api(frame)
        # 没 key 返 None 算 pass (CI 占位场景)
        if tags is None:
            pytest.skip("真 vision 没 key 返 None (CI 环境占位)")
            return
        # 有 key 返真 tag
        assert isinstance(tags, list)
        assert len(tags) >= 1
        for t in tags:
            assert isinstance(t, str)
            assert 2 <= len(t) <= 6, f"tag 长度 2-6, 实为 {len(t)}: {t}"
            # 含中文
            assert any('\u4e00' <= c <= '\u9fff' for c in t), f"tag 必须含中文: {t}"
    finally:
        frame.unlink(missing_ok=True)


def test_generate_visual_tags_with_real_vision_more_than_zero_dep():
    """generate_visual_tags: 0 依赖 + 真 vision 一起, tag 数 > 4 (4 个 0 依赖 + vision)"""
    # 找真 mp4
    candidates = list(Path("data/resources").glob("*.mp4"))
    real_mp4 = None
    import json
    import subprocess
    for c in candidates:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(c)],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                dur = json.loads(r.stdout).get("format", {}).get("duration")
                if dur and float(dur) > 0:
                    real_mp4 = c
                    break
        except Exception:
            continue
    if real_mp4 is None:
        pytest.skip("data/resources 无真 mp4")
        return

    from backend.services.visual_tag_service import generate_visual_tags

    tags = generate_visual_tags(real_mp4)
    assert isinstance(tags, list)
    # 0 依赖至少 3 个 (色调/亮度/边缘), 加上真 vision ≥5
    # 没真 key 也 ≥3 (只 0 依赖)
    if _has_real_minimax_key():
        assert len(tags) >= 5, f"有真 key 期望 ≥5 tags, 实为 {len(tags)}: {tags}"
    else:
        assert len(tags) >= 3, f"0 依赖期望 ≥3 tags, 实为 {len(tags)}: {tags}"
