"""
v2.2.45 visual_tag_service 测试

User 反馈: LLM auto-tag 抽过来的规则不准 (v2.2.19).
v2.2.45 加 0 依赖视觉打标: 抽 1 帧 + 算色调/亮度/动静/边缘密度.

测试:
- extract_one_frame: 抽 1 帧返 Path, 不存在/损坏返 None
- _analyze_color_and_brightness: 算色调 (warm/cool/gray) + 亮度 (bright/dim/dark)
- _analyze_motion: 抽 2 帧算动静 (static/moving)
- _analyze_edge_density: 算边缘密度 (clean/busy)
- generate_visual_tags 主入口: 返 list[str] 短中文
- _call_vision_api: 占位, 无 API key 返 None
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def test_extract_one_frame_不存在_返_None():
    from backend.services.visual_tag_service import extract_one_frame
    result = extract_one_frame(Path("/nonexistent/fake.mp4"))
    assert result is None


def test_generate_visual_tags_返_list_str():
    """主入口返 list[str] 短中文."""
    from backend.services.visual_tag_service import generate_visual_tags
    # 用 fake path (不实际 ffmpeg), 测 API 形状
    result = generate_visual_tags(Path("/nonexistent/fake.mp4"))
    assert isinstance(result, list)
    # 任何 string 元素 (如果有) 都是 2-4 字
    for t in result:
        assert isinstance(t, str)
        assert 2 <= len(t) <= 6


def test_analyze_color_known_colors():
    """测 color_tone 判别逻辑: 暖色 vs 冷色 vs 灰."""
    from backend.services.visual_tag_service import _analyze_color_and_brightness
    from PIL import Image
    import tempfile

    # 暖色 (R > B 30+)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        warm_path = Path(f.name)
    Image.new("RGB", (64, 64), (200, 100, 50)).save(warm_path)
    color, _ = _analyze_color_and_brightness(warm_path)
    assert color == "warm", f"warm image 应识 warm, 实 {color}"
    warm_path.unlink()

    # 冷色 (B > R 30+)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        cool_path = Path(f.name)
    Image.new("RGB", (64, 64), (50, 100, 200)).save(cool_path)
    color, _ = _analyze_color_and_brightness(cool_path)
    assert color == "cool", f"cool image 应识 cool, 实 {color}"
    cool_path.unlink()

    # 灰色 (R ≈ B)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        gray_path = Path(f.name)
    Image.new("RGB", (64, 64), (128, 128, 128)).save(gray_path)
    color, _ = _analyze_color_and_brightness(gray_path)
    assert color == "gray", f"gray image 应识 gray, 实 {color}"
    gray_path.unlink()


def test_analyze_brightness_known_levels():
    """测 brightness 判别: bright / dim / dark."""
    from backend.services.visual_tag_service import _analyze_color_and_brightness
    from PIL import Image
    import tempfile

    # bright (>170 luminance)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        bright_path = Path(f.name)
    Image.new("RGB", (64, 64), (240, 240, 240)).save(bright_path)
    _, brightness = _analyze_color_and_brightness(bright_path)
    assert brightness == "bright", f"bright image 应识 bright, 实 {brightness}"
    bright_path.unlink()

    # dark (<80 luminance)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        dark_path = Path(f.name)
    Image.new("RGB", (64, 64), (20, 20, 20)).save(dark_path)
    _, brightness = _analyze_color_and_brightness(dark_path)
    assert brightness == "dark", f"dark image 应识 dark, 实 {brightness}"
    dark_path.unlink()


def test_call_vision_api_无_key_返_None():
    """占位: 没 API key 返 None (跟 v2.2.39 placeholder skip 一致)."""
    from backend.services.visual_tag_service import _call_vision_api
    import os
    os.environ.pop("OPENAI_API_KEY", None)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        from pathlib import Path
        Path(f.name).touch()
    from pathlib import Path as _P
    result = _call_vision_api(_P(f.name))
    assert result is None
    _P(f.name).unlink(missing_ok=True)


def test_call_vision_api_placeholder_key_返_None():
    """占位: placeholder key 返 None (跟 v2.2.39 一致)."""
    from backend.services.visual_tag_service import _call_vision_api
    import os
    os.environ["OPENAI_API_KEY"] = "sk-empty-placeholder"
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        from pathlib import Path
        result = _call_vision_api(Path(f.name))
    assert result is None
    Path(f.name).unlink(missing_ok=True)


def test_chinese_tag_mapping_complete():
    """_TONE_CN / _BRIGHT_CN / _MOTION_CN / _EDGE_CN 覆盖所有 enum 值."""
    from backend.services.visual_tag_service import (
        _TONE_CN, _BRIGHT_CN, _MOTION_CN, _EDGE_CN,
    )
    for color in ("warm", "cool", "gray", "unknown"):
        assert color in _TONE_CN
        assert _TONE_CN[color]  # 非空 (除 unknown)
    for b in ("bright", "dim", "dark", "unknown"):
        assert b in _BRIGHT_CN
    for m in ("static", "moving", "unknown"):
        assert m in _MOTION_CN
    for e in ("clean", "busy", "unknown"):
        assert e in _EDGE_CN


def test_generate_visual_tags_真_mp4_e2e():
    """e2e: 真 mp4 (data/resources/) 跑通, 返非空 tags (基础视觉属性)."""
    from backend.services.visual_tag_service import generate_visual_tags
    # 找 size 1-50MB 的真 mp4
    for f in sorted(Path("data/resources").glob("*.mp4")):
        if 1_000_000 < f.stat().st_size < 50_000_000:
            tags = generate_visual_tags(f)
            # 真素材至少 1 个 visual tag
            assert len(tags) >= 1, f"{f.name} 应至少 1 个 tag, 实 {tags}"
            # tag 是 2-6 字短词
            for t in tags:
                assert 2 <= len(t) <= 6, f"tag '{t}' 应 2-6 字"
            break
    else:
        pytest.skip("data/resources/ 没 1-50MB 真 mp4, 跳过 e2e")
