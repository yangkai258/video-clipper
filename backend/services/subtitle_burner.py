"""字幕烧录服务 (moviepy 实现，不依赖 FFmpeg libass)

职责：把 SRT 字幕渲染到视频上。生成字幕见 subtitle_service.py。
"""

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# === 字幕布局常量（短视频字幕最佳实践：每条 7-12 汉字，最多 2 行） ===
MAX_CHARS_PER_LINE = 10
MAX_LINES = 2
MAX_CHARS = MAX_CHARS_PER_LINE * MAX_LINES  # = 20
EPSILON = 0.05  # moviepy 浮点 buffer，防止 end_time > duration 报错

# macOS 中文字体 fallback 链
_MAC_FALLBACK_FONTS = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Songti.ttc",
]

# 默认字幕样式
DEFAULT_SUBTITLE_CONFIG = {
    "font_size": 28,
    "txt_color": "white",
    "stroke_color": "black",
    "stroke_width": 2,
    "font": "/System/Library/Fonts/STHeiti Medium.ttc",
    "position": 0.78,  # 视频高度 78% 处（避开人脸）
}


# ───────────────────────── 公开 API ─────────────────────────


def burn_subtitles_with_moviepy(
    input_video: Path,
    output_path: Path,
    srt_path: Path,
    start: float,
    duration: float,
    subtitle_config: dict = None,
) -> None:
    """烧录字幕到视频片段。

    对外签名与重构前一致，调用方 (cut_clips) 不需要改动。
    """
    from moviepy import CompositeVideoClip, VideoFileClip

    config = {**DEFAULT_SUBTITLE_CONFIG, **(subtitle_config or {})}
    logger.info(
        f"使用 moviepy 烧录字幕：{start}s - {start + duration}s, 配置：{config}"
    )

    # 加载视频片段
    video = VideoFileClip(str(input_video)).subclipped(start, start + duration)

    # 解析字幕
    subtitles = parse_srt(srt_path, start, duration)
    if not subtitles:
        logger.warning("未找到有效字幕，跳过烧录")
        _write_video_no_subs(video, output_path)
        return

    # 创建字幕片段
    subclips = [
        make_textclip(text, config)
        .with_start(s)
        .with_end(e)
        .with_position(("center", config["position"]), relative=True)
        for s, e, text in subtitles
        if text.strip()
    ]

    # 合成
    final = CompositeVideoClip([video] + subclips)
    _write_video_no_subs(final, output_path, _codec="h264_videotoolbox")
    logger.info(f"字幕烧录完成：{output_path}")


# ───────────────────────── 内部辅助函数 ─────────────────────────


def parse_srt(
    srt_path: Path, start_offset: float, duration: float
) -> list[tuple[float, float, str]]:
    """解析 SRT 文件，返回 (start, end, text) 列表，时间已按 start_offset 偏移并 clip 到 duration。"""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # SRT 格式：序号 \n 时间 --> 时间 \n 字幕文本
    pattern = r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n*$)"
    matches = re.findall(pattern, content, re.DOTALL)

    subtitles: list[tuple[float, float, str]] = []
    for _, start_time, end_time, text in matches:
        start_sec = _time_to_seconds(start_time) - start_offset
        end_sec = _time_to_seconds(end_time) - start_offset
        # 清理 HTML 标签
        text = re.sub(r"<[^>]+>", "", text).strip()
        if not (start_sec < duration and end_sec > 0):
            continue
        # 浮点 buffer 防止 moviepy 报 "end_time should be <= duration"
        s = max(0, min(start_sec, duration - EPSILON))
        e = max(EPSILON, min(end_sec, duration - EPSILON))
        # 长字幕按标点切短
        subtitles.extend(_split_subtitle(s, e, text))

    return subtitles


def make_textclip(text: str, config: dict):
    """创建带字体 fallback 的 TextClip。"""
    from moviepy import TextClip  # 局部导入：moviepy 启动慢，不在模块级拉

    return TextClip(
        text=text,
        font_size=config["font_size"],
        color=config["txt_color"],
        stroke_color=config["stroke_color"],
        stroke_width=config["stroke_width"],
        font=_resolve_font(config["font"]),
    )


# ───────────────────────── 私有工具 ─────────────────────────


def _time_to_seconds(time_str: str) -> float:
    """HH:MM:SS,ms → 秒。"""
    h, m, s = time_str.replace(",", ".").split(":")
    return float(h) * 3600 + float(m) * 60 + float(s)


def _split_subtitle(s: float, e: float, text: str) -> list[tuple[float, float, str]]:
    """把长字幕按标点拆短句，单句过长自动换行，时间窗口均分。"""
    # 1) 去尾部标点
    text = text.strip().rstrip("。！？!?,，;；.!?")
    if not text:
        return [(s, e, text)]

    # 2) 按中英文标点切分（保留分隔符以便断句）
    pieces = _split_by_punctuation(text)
    if not pieces:
        pieces = [text]

    # 3) 短句均分时间窗口
    n = len(pieces)
    step = (e - s) / n if n > 0 else 0
    return [
        (s + i * step, s + (i + 1) * step, _wrap_line(p, MAX_CHARS_PER_LINE, MAX_LINES))
        for i, p in enumerate(pieces)
    ]


def _split_by_punctuation(text: str) -> list[str]:
    """按中英文标点切分并保留标点到前一句。"""
    parts = re.split(r"([。！？!?\.？!]+|[，,；;]+)", text)
    sentences: list[str] = []
    buf = ""
    for p in parts:
        if not p:
            continue
        if re.match(r"^[。！？!?\.？!,，;；]+$", p):
            buf += p
            if buf.strip():
                sentences.append(buf.strip())
                buf = ""
        else:
            buf += p
    if buf.strip():
        sentences.append(buf.strip())
    return sentences


def _wrap_line(text: str, max_line: int, max_lines: int) -> str:
    """单句超长按 max_line 字一行，最多 max_lines 行（用 \\n 换行）。"""
    if len(text) <= max_line:
        return text
    if len(text) <= max_line * max_lines:
        # 在中点附近找最近的标点切；找不到标点就按 max_line 硬切
        mid = len(text) // 2
        best = _nearest_punctuation(text, mid)
        if best is not None and best != mid:
            return text[:best] + "\n" + text[best:].lstrip()
        # 找不到标点：在 max_line 处硬切
        return text[:max_line] + "\n" + text[max_line:].lstrip()
    # 太长：硬切到 max_lines 行
    chunks = [text[i : i + max_line] for i in range(0, len(text), max_line)]
    return "\n".join(chunks[:max_lines])


def _nearest_punctuation(text: str, mid: int) -> int | None:
    """从 mid 向两侧找最近的标点位置。返回 None 表示没找到。"""
    PUNCT = "，,。. "
    for off in range(mid + 1):
        if mid - off >= 0 and text[mid - off] in PUNCT:
            return mid - off
        if mid + off < len(text) and text[mid + off] in PUNCT:
            return mid + off + 1
    return None


def _resolve_font(requested: str) -> str:
    """如果请求字体不存在，自动 fallback 到 macOS 中文字体。"""
    if requested and os.path.exists(requested):
        return requested
    for fp in _MAC_FALLBACK_FONTS:
        if os.path.exists(fp):
            logger.warning(f"字体 {requested} 不可用，fallback 到 {fp}")
            return fp
    return requested  # 让 moviepy 自己处理（可能崩，但保留原行为）


def _write_video_no_subs(
    video, output_path: Path, _codec: str = "h264_videotoolbox"
) -> None:
    """写视频到文件，统一 +faststart 优化。"""
    video.write_videofile(
        str(output_path),
        codec=_codec,
        audio_codec="aac",
        ffmpeg_params=[
            "-movflags",
            "+faststart",
            "-g",
            "60",
            "-keyint_min",
            "60",
            "-b:v",
            "8M",
        ],
    )
