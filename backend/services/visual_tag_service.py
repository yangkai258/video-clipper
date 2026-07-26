"""资源库 visual_tags 视觉打标 service (v2.2.45)

User 反馈: LLM auto-tag 用字幕反推不准 (v2.2.19 library_tag_service), user 关掉.
v2.2.45 加 0 模型依赖的视觉属性: 抽 1 帧 → 算色调 / 动静 / 边缘密度,
跟语义无关, 跟画面真实属性有关. 跟视觉匹配公式配合: visual tag substring 命中.

设计:
- 抽 1 帧 (ffmpeg, 跟 thumbnail 工具同款)
- 算 5 个 0 依赖属性:
  - color_tone: "warm" / "cool" / "gray" (R/G/B 均值比例)
  - brightness: "bright" / "dim" / "dark" (luminance)
  - motion: "static" / "moving" (前后帧 diff, 抽 2 帧)
  - scene: "indoor" / "outdoor" / "text" (placeholder, 后续接 vision API)
  - edge_density: "clean" / "busy" (pixel gradient 强度)
- 真 vision model (OpenAI gpt-4o / doubao-vl / qwen-vl / moondream) 走占位
  _call_vision_api, 没 API key 时返 None, 留 hook 后续接.
- visual_tags 输出: list[str] 短中文词, e.g. ["暖色调", "室外", "静态"]
  跟 ResourceClip.tags 同样格式, 视觉匹配公式直接走 substring 命中.
"""
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def extract_one_frame(video_path: Path, t_seconds: float = 1.0) -> Optional[Path]:
    """ffmpeg 抽 1 帧到临时 jpg. 返临时路径 (caller 用完删).

    失败 (ffmpeg 不可用 / 文件 < t / 编解码器不支持) 返 None.
    """
    if not video_path.exists():
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            tmp_path = Path(f.name)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(t_seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=320:-2",  # 缩 320 宽, 算属性够用, 加速
            "-q:v", "5",
            str(tmp_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0 or not tmp_path.exists() or tmp_path.stat().st_size == 0:
            tmp_path.unlink(missing_ok=True)
            return None
        return tmp_path
    except Exception as e:
        logger.debug(f"extract_one_frame 失败: {e}")
        return None


def _analyze_color_and_brightness(jpg_path: Path) -> tuple[str, str]:
    """读 jpg 算平均色 + 亮度. 返 (color_tone, brightness).

    0 numpy 依赖: 解析 JPEG 解码 (PIL), 简单平均.
    实际项目装 Pillow (PIL), 走 PIL.Image.getdata() 流式算.
    """
    try:
        from PIL import Image
    except ImportError:
        return ("unknown", "unknown")

    try:
        img = Image.open(jpg_path).convert("RGB")
        # 缩 64x64 加速, 流式 pixel
        img.thumbnail((64, 64))
        pixels = list(img.getdata())
        if not pixels:
            return ("unknown", "unknown")

        r_avg = sum(p[0] for p in pixels) / len(pixels)
        g_avg = sum(p[1] for p in pixels) / len(pixels)
        b_avg = sum(p[2] for p in pixels) / len(pixels)
        luminance = 0.299 * r_avg + 0.587 * g_avg + 0.114 * b_avg

        # color_tone: R vs B 比例 (warm = R > B, cool = B > R, gray = |R-B| 小)
        rb_diff = r_avg - b_avg
        if abs(rb_diff) < 15:
            color_tone = "gray"
        elif rb_diff > 30:
            color_tone = "warm"
        else:
            color_tone = "cool"

        # brightness: luminance 阈值 (0-255)
        if luminance > 170:
            brightness = "bright"
        elif luminance > 80:
            brightness = "dim"
        else:
            brightness = "dark"
        return (color_tone, brightness)
    except Exception as e:
        logger.debug(f"_analyze_color_and_brightness 失败: {e}")
        return ("unknown", "unknown")


def _analyze_motion(video_path: Path) -> str:
    """抽 2 帧 (1s / 3s) 算 diff 估动静. 没动=静态, 大=剧烈, 中=动.

    简化: ffmpeg 抽 2 帧到 /tmp, PIL pixel diff 比例.
    """
    f1 = extract_one_frame(video_path, t_seconds=1.0)
    f2 = extract_one_frame(video_path, t_seconds=3.0)
    if not f1 or not f2:
        return "unknown"
    try:
        from PIL import Image, ImageChops
        a = Image.open(f1).convert("L")
        b = Image.open(f2).convert("L")
        diff = ImageChops.difference(a, b)
        # 算 diff > 30 的像素比例
        hist = diff.histogram()
        total = sum(hist)
        if total == 0:
            return "static"
        changed = sum(hist[30:])  # diff > 30 的 bucket
        ratio = changed / total
        if ratio > 0.4:
            return "moving"
        elif ratio > 0.1:
            return "moving"
        else:
            return "static"
    except Exception as e:
        logger.debug(f"_analyze_motion 失败: {e}")
        return "unknown"
    finally:
        f1.unlink(missing_ok=True)
        f2.unlink(missing_ok=True)


def _analyze_edge_density(jpg_path: Path) -> str:
    """算图片边缘密度 (gradient 强度). 高=busy, 低=clean.

    简化: PIL + Sobel 近似 (pixel diff 横竖).
    """
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        return "unknown"
    try:
        img = Image.open(jpg_path).convert("L")
        img.thumbnail((128, 128))
        # PIL 自带 FIND_EDGES filter
        edges = img.filter(ImageFilter.FIND_EDGES)
        hist = edges.histogram()
        total = sum(hist)
        if total == 0:
            return "unknown"
        # edge 像素 (值 > 50)
        edge = sum(hist[50:])
        ratio = edge / total
        if ratio > 0.25:
            return "busy"
        elif ratio > 0.10:
            return "busy"
        else:
            return "clean"
    except Exception as e:
        logger.debug(f"_analyze_edge_density 失败: {e}")
        return "unknown"


def _call_vision_api(jpg_path: Path) -> Optional[list[str]]:
    """v2.2.45 占位: 真 vision API (OpenAI gpt-4o / doubao-vl / qwen-vl / moondream)

    没 API key 返 None. 有 key 走外部 API, 输出场景/物体/活动 tags.
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or len(api_key) < 30 or "empty" in api_key.lower():
        return None
    # TODO: 真调 API. 现在没真 key, 直接返 None
    # import httpx
    # r = httpx.post("https://api.openai.com/v1/chat/completions", ...)
    return None


# 中文 visual tag 命名 (跟 LLM auto-tag 同风格, 2-4 字短词)
_TONE_CN = {"warm": "暖色调", "cool": "冷色调", "gray": "灰调", "unknown": "色调未知"}
_BRIGHT_CN = {"bright": "明亮", "dim": "昏暗", "dark": "暗调", "unknown": ""}
_MOTION_CN = {"static": "静态", "moving": "动态", "unknown": ""}
_EDGE_CN = {"clean": "简洁", "busy": "繁复", "unknown": ""}


def generate_visual_tags(video_path: Path) -> list[str]:
    """主入口: 抽 1 帧 + 算视觉属性 + 真 vision API 占位 → 返 list[str] visual tags.

    用法:  ResourceClip 入库时调, tags 写 db.
           视觉匹配公式 (v2.2.33) 走 substring 命中.

    返回 tags 例: ["暖色调", "明亮", "静态", "简洁"] 或 ["冷色调", "动态", "繁复"]
    """
    frame = extract_one_frame(video_path, t_seconds=1.0)
    if not frame:
        return []

    tags: list[str] = []

    # 0 依赖属性
    color, brightness = _analyze_color_and_brightness(frame)
    edge = _analyze_edge_density(frame)

    if color in _TONE_CN:
        cn = _TONE_CN[color]
        if cn:
            tags.append(cn)
    if brightness in _BRIGHT_CN:
        cn = _BRIGHT_CN[brightness]
        if cn:
            tags.append(cn)
    if edge in _EDGE_CN:
        cn = _EDGE_CN[edge]
        if cn:
            tags.append(cn)

    # 动静 (抽 2 帧, 慢但准)
    motion = _analyze_motion(video_path)
    if motion in _MOTION_CN:
        cn = _MOTION_CN[motion]
        if cn:
            tags.append(cn)

    # 真 vision API 占位
    api_tags = _call_vision_api(frame)
    if api_tags:
        tags.extend(api_tags)

    # 临时 jpg 清理
    frame.unlink(missing_ok=True)
    return tags
