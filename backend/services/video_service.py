"""视频处理服务"""
import logging
import subprocess
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def burn_subtitles_with_moviepy(input_video: Path, output_path: Path, srt_path: Path, start: float, duration: float, subtitle_config: dict = None):
    """使用 moviepy 烧录字幕（不依赖 FFmpeg libass）
    
    Args:
        input_video: 输入视频路径
        output_path: 输出视频路径
        srt_path: SRT 字幕路径
        start: 起始时间（秒）
        duration: 时长（秒）
        subtitle_config: 字幕配置 {font_size, txt_color, stroke_color, stroke_width, font, position}
    """
    from moviepy import VideoFileClip, TextClip, CompositeVideoClip
    from moviepy.video.tools.subtitles import SubtitlesClip
    import re
    
    # 默认字幕配置
    default_config = {
        "font_size": 22,
        "txt_color": "white",
        "stroke_color": "white",
        "stroke_width": 1,
        "font": "/System/Library/Fonts/STHeiti Medium.ttc",
        "position": 0.33  # 视频高度的 1/3 处
    }
    config = {**default_config, **(subtitle_config or {})}
    
    logger.info(f"使用 moviepy 烧录字幕：{start}s - {start+duration}s, 配置：{config}")
    
    # 加载视频片段
    video = VideoFileClip(str(input_video)).subclipped(start, start + duration)
    
    # 解析 SRT 字幕
    def parse_srt(srt_path: Path, start_offset: float):
        """解析 SRT 文件，返回 (start, end, text) 列表"""
        subtitles = []
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # SRT 格式：序号 \n 时间 --> 时间 \n 字幕文本
        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n*$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        def time_to_seconds(time_str: str) -> float:
            h, m, s = time_str.replace(',', '.').split(':')
            return float(h) * 3600 + float(m) * 60 + float(s)
        
        for _, start_time, end_time, text in matches:
            start_sec = time_to_seconds(start_time) - start_offset
            end_sec = time_to_seconds(end_time) - start_offset
            # 清理字幕文本（移除 HTML 标签等）
            text = re.sub(r'<[^>]+>', '', text).strip()
            if start_sec < duration and end_sec > 0:
                subtitles.append((max(0, start_sec), min(duration, end_sec), text))
        
        return subtitles
    
    # 解析字幕
    subtitles = parse_srt(srt_path, start)
    
    if not subtitles:
        logger.warning("未找到有效字幕，跳过烧录")
        video.write_videofile(str(output_path), codec='libx264', audio_codec='aac', preset='medium')
        return
    
    # 创建字幕片段
    def make_textclip(text):
        return TextClip(
            text=text,
            font_size=config["font_size"],
            color=config["txt_color"],
            stroke_color=config["stroke_color"],
            stroke_width=config["stroke_width"],
            font=config["font"]
        )
    
    subclips = []
    for start_sec, end_sec, text in subtitles:
        if text.strip():
            # position: ('center', y) y=0.33 表示视频高度的 33% 处
            sub = make_textclip(text).with_start(start_sec).with_end(end_sec).with_position(('center', config["position"]), relative=True)
            subclips.append(sub)
    
    # 合成视频 + 字幕
    final = CompositeVideoClip([video] + subclips)
    final.write_videofile(str(output_path), codec='libx264', audio_codec='aac', preset='medium')
    
    logger.info(f"字幕烧录完成：{output_path}")


def cut_clips(clips: List[Dict], input_video: Path, output_dir: Path, input_srt: Path = None, task_id: str = None, subtitle_config: dict = None):
    """切割视频切片
    
    Args:
        clips: 切片数据列表
        input_video: 输入视频路径
        output_dir: 输出目录
        input_srt: 字幕文件路径（可选，有则烧录字幕）
        task_id: 可选的任务 ID，用于更新进度
        subtitle_config: 字幕配置 {font_size, txt_color, stroke_color, stroke_width, font, position}
    """
    logger.info(f"开始切割 {len(clips)} 个切片")
    
    # 检查字幕文件是否存在
    srt_path = None
    if input_srt and input_srt.exists():
        srt_path = input_srt
        logger.info(f"将烧录字幕：{srt_path}")
    else:
        logger.info("未提供字幕文件，跳过字幕烧录")
    
    for i, clip in enumerate(clips):
        try:
            # 兼容两种字段名（start/start_time, end/end_time）
            start = clip.get("start_time") or clip.get("start", 0)
            end = clip.get("end_time") or clip.get("end", start + 300)
            duration = end - start
            title = clip.get("title", f"clip_{i+1}")
            
            # 清理标题中的非法字符
            safe_title = "".join(c for c in title if c not in '<>:"/\\|？*')
            output_path = output_dir / f"{i+1}_{safe_title[:50]}.mp4"
            
            logger.info(f"切割切片 {i+1}: {start}s - {start+duration}s")
            
            # 构建 FFmpeg 命令
            cmd = [
                "ffmpeg", "-y",
                "-i", str(input_video),
                "-ss", str(start),
                "-t", str(duration),
            ]
            
            # 字幕烧录：使用 moviepy（不依赖 FFmpeg libass）
            if srt_path:
                logger.info(f"烧录字幕：{srt_path}（moviepy 软件编码）")
                try:
                    burn_subtitles_with_moviepy(input_video, output_path, srt_path, start, duration, subtitle_config)
                except Exception as e:
                    logger.error(f"moviepy 烧录失败：{e}，回退到 FFmpeg 无字幕模式")
                    # 回退到 FFmpeg 硬件加速
                    cmd.extend([
                        "-c:v", "h264_videotoolbox",
                        "-keyint_min", "30",
                        "-g", "30",
                        "-profile:v", "high",
                        "-level", "4.0",
                        "-c:a", "aac",
                        "-b:a", "128k",
                        "-movflags", "+faststart",
                        str(output_path)
                    ])
                    subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            else:
                # 无字幕：使用硬件加速
                logger.info("无字幕，使用 h264_videotoolbox 硬件加速")
                cmd.extend([
                    "-c:v", "h264_videotoolbox",
                    "-keyint_min", "30",
                    "-g", "30",
                    "-profile:v", "high",
                    "-level", "4.0",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(output_path)
                ])
                subprocess.run(cmd, check=True, capture_output=True, timeout=300)
            
            # 保存相对路径
            clip["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
            
            # ✅ 修复：每 5 个切片或最后一个切片时更新进度（70% → 90%）
            if task_id and ((i + 1) % 5 == 0 or i == len(clips) - 1):
                try:
                    from ..core.database import sync_get_db
                    from ..models.database import Task
                    from sqlalchemy import select
                    
                    progress = 70 + int(((i + 1) / len(clips)) * 20)  # 70% → 90%
                    db_gen = sync_get_db()
                    db = next(db_gen)
                    try:
                        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
                        if task:
                            task.progress = progress
                            task.current_step = f"切割中... ({i+1}/{len(clips)})"
                            db.commit()
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"进度更新失败：{e}")
            
        except subprocess.TimeoutExpired:
            logger.error(f"切割切片 {i+1} 超时（300 秒），跳过")
        except Exception as e:
            logger.error(f"切割切片 {i+1} 失败：{e}")


def merge_collections(collections: List[Dict], clips_dir: Path, output_dir: Path, task_id: str = None):
    """合并合集
    
    Args:
        collections: 合集数据列表
        clips_dir: 切片目录
        output_dir: 输出目录
        task_id: 可选的任务 ID，用于更新进度
    """
    logger.info(f"开始合并 {len(collections)} 个合集")
    
    for i, collection in enumerate(collections):
        try:
            title = collection.get("title", f"collection_{i+1}")
            clips = collection.get("clips", [])
            
            if not clips:
                continue
            
            # 创建合并列表 - 使用绝对路径
            list_path = output_dir / f"concat_list_{i}.txt"
            with open(list_path, "w") as f:
                for clip in clips:
                    # 如果是相对路径，转换为绝对路径
                    clip_path = clip.get("video_path")
                    if clip_path:
                        clip_path_obj = Path(clip_path)
                        if not clip_path_obj.is_absolute():
                            clip_path_obj = clips_dir / clip_path_obj.name
                        if clip_path_obj.exists():
                            f.write(f"file '{clip_path_obj.absolute()}'\n")
            
            # 合并视频
            output_path = output_dir / f"{title}.mp4"
            
            # VideoToolbox 硬件加速重新编码
            # 关键帧间隔 30 帧（1 秒），保证流畅播放
            # ✅ 修复：添加 600 秒超时（合集合并更耗时）
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c:v", "h264_videotoolbox",
                "-keyint_min", "30",
                "-g", "30",
                "-profile:v", "high",
                "-level", "4.0",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path)
            ], check=True, capture_output=True, timeout=600)
            
            # 保存相对路径
            collection["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
            logger.info(f"合集 {i+1} 合并完成：{output_path}")
            
            # ✅ 修复：每个合集完成后更新进度（90% → 100%）
            if task_id:
                try:
                    from ..core.database import sync_get_db
                    from ..models.database import Task
                    from sqlalchemy import select
                    
                    progress = 90 + int(((i + 1) / len(collections)) * 10)  # 90% → 100%
                    db_gen = sync_get_db()
                    db = next(db_gen)
                    try:
                        task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
                        if task:
                            task.progress = min(progress, 99)  # 保留 100% 给最终状态更新
                            task.current_step = f"合并合集中... ({i+1}/{len(collections)})"
                            db.commit()
                    finally:
                        db.close()
                except Exception as e:
                    logger.warning(f"进度更新失败：{e}")
            
            # 清理临时文件
            list_path.unlink()
            
        except Exception as e:
            logger.error(f"合并合集 {i+1} 失败：{e}")
