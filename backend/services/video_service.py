# -*- coding: utf-8 -*-
"""视频处理服务（协调层）

本模块对外提供三个公开函数：
- _build_video_encoder_args: 生成 ffmpeg 编码参数（硬件加速）
- cut_clips: 切割视频片段（高层协调）
- merge_collections: 合并合集（高层协调）

字幕烧录的具体逻辑已拆分到 subtitle_burner.py，缩略图抽帧封装在 _extract_*
辅助函数里。本文件只做"协调"，每个函数都短而清晰。
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Dict

from .ffprobe_helper import get_video_dimensions

logger = logging.getLogger(__name__)

# === 切割时的 ffmpeg 超时（秒）===
CUT_TIMEOUT_SECONDS = 300
# === 合集合并时的 ffmpeg 超时（秒）===
MERGE_TIMEOUT_SECONDS = 600
# === 缩略图抽帧参数 ===
CLIP_THUMB_SCALE = 480        # 每片缩略图宽度
CLIP_THUMB_QUALITY = 3        # q:v 值（1=最好，31=最差）
COVER_THUMB_SCALE = 600       # 项目封面缩略图宽度
COVER_THUMB_QUALITY = 2       # q:v 值（封面比每片质量高）


# ───────────────────────── 公开 API ─────────────────────────


def _build_video_encoder_args(output_format: str, output_path: Path = None, use_libx264: bool = False) -> list:
    """根据 output_format 生成 ffmpeg 编码参数。

    Args:
        output_format: "original" | "9:16-letterbox" | "9:16-smart-crop"
        output_path: v2.1.44 fix: 不传 ffmpeg 会报 "At least one output file must be specified"
        use_libx264: True 强制 libx264 软件编码 (防 4K + h264_videotoolbox 合并 bug, v2.2.1+)

    Returns:
        list of ffmpeg args (不含 -i input)
    """
    # 基础编码参数 (硬件加速 + 抖音兼容)
    # ⚠️ bug fix (v2.2.1+): h264_videotoolbox 合并 4K + concat demuxer 时炸
    # (Could not open encoder before EOF, exit 187). 切单文件 step 7 OK,
    # 合并多文件 step 8 触发. 简单修法: 合并时 use_libx264=True 走软件编码.
    if use_libx264:
        base = [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",  # 4K 兼容 (videotoolbox 自动选, libx264 必须显式)
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
        ]
    else:
        base = [
            "-c:v", "h264_videotoolbox",
            "-keyint_min", "60",
            "-g", "60",
        "-profile:v", "high",
        "-level", "4.0",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
    ]

    vf = _video_filter_for_format(output_format)
    args = ["-vf", vf] if vf else []
    args.extend(base)
    if output_path is not None:
        args.append(str(output_path))
    return args


# v2.2.1+: 4K + h264_videotoolbox 合并 bug, 强制 merge 走 libx264
_MERGE_USE_LIBX264 = True


def cut_clips(
    clips: List[Dict],
    input_video: Path,
    output_dir: Path,
    input_srt: Path = None,
    task_id: str = None,
    subtitle_config: dict = None,
    with_subtitle: bool = True,
    project_id: str = None,
    output_format: str = "original",
) -> None:
    """切割视频切片（高层协调）。

    对每条 clip:
    1) 解析字段名（兼容 start/start_time, end/end_time）
    2) 构建输出路径（清理非法字符）
    3) 调 _cut_single_clip 执行 ffmpeg / moviepy
    4) 抽 clip 缩略图
    5) 每 5 条更新一次进度（65% → 90%）

    切完所有 clip 后，若有 project_id 且至少 1 个成功，生成项目封面缩略图。
    """
    output_format = _normalize_output_format(output_format)
    srt_path = _resolve_srt_path(input_srt, with_subtitle)

    logger.info(f"切割 {len(clips)} 个切片, output_format={output_format}")

    for i, clip in enumerate(clips):
        try:
            _cut_single_clip(
                clip=clip,
                index=i,
                total=len(clips),
                input_video=input_video,
                output_dir=output_dir,
                srt_path=srt_path,
                output_format=output_format,
                subtitle_config=subtitle_config,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"切割切片 {i+1} 超时（{CUT_TIMEOUT_SECONDS} 秒），跳过")
        except Exception as e:
            logger.error(f"切割切片 {i+1} 失败：{e}")

        if task_id and ((i + 1) % 5 == 0 or i == len(clips) - 1):
            _update_task_progress_safely(
                task_id,
                65 + int(((i + 1) / len(clips)) * 25),
                f"切割中... ({i+1}/{len(clips)})",
            )

    if project_id and clips:
        _generate_project_thumbnail(project_id, clips, output_dir)


def merge_collections(
    collections: List[Dict],
    clips_dir: Path,
    output_dir: Path,
    task_id: str = None,
) -> None:
    """合并合集（高层协调）。

    对每个合集:
    1) 构建 ffmpeg concat 列表（绝对路径）
    2) 调 ffmpeg 硬件加速合并
    3) 写回相对路径 + 更新进度（93% → 99%）
    """
    logger.info(f"开始合并 {len(collections)} 个合集")

    for i, collection in enumerate(collections):
        try:
            _merge_single_collection(collection, i, clips_dir, output_dir)
        except Exception as e:
            logger.error(f"合并合集 {i+1} 失败：{e}")

        if task_id:
            _update_task_progress_safely(
                task_id,
                min(93 + int(((i + 1) / len(collections)) * 6), 99),
                f"合并合集中... ({i+1}/{len(collections)})",
            )


# ───────────────────────── 内部协调 ─────────────────────────


def _cut_single_clip(
    clip: Dict,
    index: int,
    total: int,
    input_video: Path,
    output_dir: Path,
    srt_path: Path,
    output_format: str,
    subtitle_config: dict,
) -> None:
    """切割单条 clip，含烧字幕或回退、抽缩略图、获取 ffprobe 尺寸。"""
    start = clip.get("start_time") or clip.get("start", 0)
    end = clip.get("end_time") or clip.get("end", start + 300)
    duration = end - start
    title = clip.get("title", f"clip_{index+1}")
    safe_title = _sanitize_filename(title)
    output_path = output_dir / f"{index+1}_{safe_title[:50]}.mp4"

    logger.info(f"切割切片 {index+1}: {start}s - {start+duration}s")

    # 字幕烧录 vs 硬件加速
    if srt_path:
        logger.info(f"烧录字幕：{srt_path}（moviepy 软件编码）")
        try:
            from .subtitle_burner import burn_subtitles_with_moviepy
            burn_subtitles_with_moviepy(input_video, output_path, srt_path, start, duration, subtitle_config)
        except Exception as e:
            logger.error(f"moviepy 烧录失败：{e}，回退到 FFmpeg 无字幕模式")
            _run_ffmpeg_cut(input_video, start, duration, output_format, output_path)
    else:
        logger.info("无字幕，使用 h264_videotoolbox 硬件加速")
        _run_ffmpeg_cut(input_video, start, duration, output_format, output_path)

    # 回写 clip 字段（processing.py 写库用）
    clip["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
    clip["start"] = start
    clip["end"] = end
    clip["duration"] = duration
    clip["title"] = safe_title

    _populate_clip_dimensions(output_path, clip)
    _extract_clip_thumbnail(output_path, output_dir, clip)


def _merge_single_collection(collection: Dict, index: int, clips_dir: Path, output_dir: Path) -> None:
    """合并单条合集。"""
    title = collection.get("title", f"collection_{index+1}")
    clips = collection.get("clips", [])
    if not clips:
        return

    list_path = output_dir / f"concat_list_{index}.txt"
    _write_concat_list(list_path, clips, clips_dir)
    try:
        output_path = output_dir / f"{title}.mp4"
        # ⚠️ v2.2.1+: merge 用 libx264, 防 4K + h264_videotoolbox 合并 bug
        # (Could not open encoder before EOF, exit 187). step 7 cut 单文件 OK,
        # step 8 merge 多文件触发 macOS VideoToolbox 偶发 bug. software 编码
        # 慢但稳, merge 是 I/O bound 不是 CPU bound, 实际差几秒.
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(list_path),
            *_build_video_encoder_args("original", output_path, use_libx264=_MERGE_USE_LIBX264),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=MERGE_TIMEOUT_SECONDS)
        collection["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
        logger.info(f"合集 {index+1} 合并完成：{output_path}")
    finally:
        if list_path.exists():
            list_path.unlink()


# ───────────────────────── 内部工具 ─────────────────────────


def _normalize_output_format(output_format: str) -> str:
    """归一化 output_format，未知值回退到 "original"，smart-crop 暂用 letterbox 替代。"""
    if output_format not in ("original", "9:16-letterbox", "9:16-smart-crop"):
        logger.warning(f"未知 output_format '{output_format}', 回退到 original")
        return "original"
    if output_format == "9:16-smart-crop":
        logger.warning("9:16-smart-crop 暂未实现, 用 9:16-letterbox 替代")
        return "9:16-letterbox"
    return output_format


def _video_filter_for_format(output_format: str) -> str:
    """返回 ffmpeg -vf 滤镜字符串；original 返回空串。"""
    if output_format == "9:16-letterbox":
        # 横屏电影适配抖音: 上下加黑边变 9:16
        # scale=1080:-2 按宽缩放, pad 居中; 输出 1080x1920
        return "scale=1080:-2:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
    return ""


def _resolve_srt_path(input_srt: Path, with_subtitle: bool) -> Path:
    """决定是否烧录字幕。返回 srt 路径或 None。"""
    if with_subtitle and input_srt and Path(input_srt).exists():
        logger.info(f"将烧录字幕：{input_srt}")
        return input_srt
    if not with_subtitle:
        logger.info("用户选择纯剪片子（不烧字幕）")
    else:
        logger.info("未提供字幕文件，跳过字幕烧录")
    return None


def _sanitize_filename(title: str) -> str:
    """清理标题中的非法字符。"""
    return "".join(c for c in title if c not in '<>:"/\\|？*')


def _run_ffmpeg_cut(input_video: Path, start: float, duration: float, output_format: str, output_path: Path) -> None:
    """硬件加速切割（无字幕模式）。"""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_video),
        "-ss", str(start),
        "-t", str(duration),
        *_build_video_encoder_args(output_format, output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=CUT_TIMEOUT_SECONDS)


def _populate_clip_dimensions(output_path: Path, clip: Dict) -> None:
    """ffprobe 抽 clip 宽高，让前端区分横/竖屏。"""
    try:
        dims = get_video_dimensions(output_path)
        if dims:
            clip["width"] = dims[0]
            clip["height"] = dims[1]
    except Exception as e:
        logger.warning(f"clip 宽高 ffprobe 失败 ({output_path.name}): {e}")


def _extract_clip_thumbnail(output_path: Path, output_dir: Path, clip: Dict) -> None:
    """给该片抽一张中段帧作缩略图（clip 是独立小视频，用 duration/2）。"""
    try:
        clip_thumb_dir = output_dir.parent / "thumbnails" / "clips"
        clip_thumb_dir.mkdir(parents=True, exist_ok=True)
        clip_thumb = clip_thumb_dir / (output_path.stem + ".jpg")
        # clip 是独立视频文件 (0..duration), 不能用原视频 start_time
        mid_t = max(0.5, (clip.get("duration", 0) or 1) / 2)
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(mid_t),
                "-i", str(output_path),
                "-vframes", "1", "-q:v", str(CLIP_THUMB_QUALITY),
                "-vf", f"scale={CLIP_THUMB_SCALE}:-1",
                str(clip_thumb),
            ],
            check=True, capture_output=True, timeout=15,
        )
    except Exception as e:
        logger.warning(f"clip 缩略图抽帧失败 ({output_path.name}): {e}")


def _generate_project_thumbnail(project_id: str, clips: List[Dict], output_dir: Path) -> None:
    """切完第一个成功后生成项目封面缩略图（非阻塞，失败仅 warn）。"""
    try:
        thumb_dir = output_dir.parent / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{project_id}.jpg"
        # 用第一片抽 1 秒处一帧
        first_clip = next((c for c in clips if c.get("video_path")), None)
        if not first_clip:
            return
        clip_path = output_dir.parent.parent / first_clip["video_path"]
        if not clip_path.exists():
            return
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "1", "-i", str(clip_path),
                "-vframes", "1", "-q:v", str(COVER_THUMB_QUALITY),
                "-vf", f"scale={COVER_THUMB_SCALE}:-1", str(thumb_path),
            ],
            check=True, capture_output=True, timeout=30,
        )
        logger.info(f"项目封面已生成：{thumb_path}")
    except Exception as e:
        logger.warning(f"项目封面生成失败（非阻塞）：{e}")


def _write_concat_list(list_path: Path, clips: List[Dict], clips_dir: Path) -> None:
    """把合集里的所有 clip 路径写成 ffmpeg concat 列表（绝对路径）。"""
    with open(list_path, "w") as f:
        for clip in clips:
            clip_path = clip.get("video_path")
            if not clip_path:
                continue
            clip_path_obj = Path(clip_path)
            if not clip_path_obj.is_absolute():
                clip_path_obj = clips_dir / clip_path_obj.name
            if clip_path_obj.exists():
                f.write(f"file '{clip_path_obj.absolute()}'\n")


def _update_task_progress_safely(task_id: str, progress: int, message: str) -> None:
    """更新任务进度，失败仅 warn（不冒泡到 cut_clips 主循环）。"""
    try:
        from ..tasks.processing import _update_task_progress
        _update_task_progress(task_id, progress, message)
    except Exception as e:
        logger.warning(f"进度更新失败：{e}")