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
        "font_size": 28,
        "txt_color": "white",
        "stroke_color": "black",
        "stroke_width": 2,
        "font": "/System/Library/Fonts/STHeiti Medium.ttc",
        "position": 0.78  # 视频高度的 78% 处（避开人脸）
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
            # 留 0.05s buffer 防止浮点精度导致 moviepy 报
            # "end_time (X) should be smaller or equal to the clip's duration (Y)"
            if start_sec < duration and end_sec > 0:
                s = max(0, min(start_sec, duration - 0.05))
                e = max(0.05, min(end_sec, duration - 0.05))
                # 断句 + 换行：长字幕拆成多条短字幕，时间均分
                for piece_s, piece_e, piece_text in _split_subtitle(s, e, text):
                    subtitles.append((piece_s, piece_e, piece_text))

        return subtitles

    def _split_subtitle(s: float, e: float, text: str):
        """把长字幕按标点拆短句，单句过长自动换行。

        短视频字幕最佳实践：
        - 每条 7-12 汉字
        - 最多 2 行
        - 显示 1-3 秒

        例：「直播间右下方的小黄车,1号链接,可以报名,然后留下您的姓名跟联系方式」
          → ['直播间右下方的小黄车', '1号链接 可以报名', '然后留下您的姓名跟联系方式']
          → 3 段短字幕，时间窗口均分
        """
        import re
        # 1) 去掉尾部标点（保留中间）
        text = text.strip().rstrip('。！？!?,，;；.!?')
        if not text:
            return [(s, e, text)]
        # 2) 按中文/英文标点切分
        #    用零宽位置切，保留分隔符以便后续断句参考
        parts = re.split(r'([。！？!?\.？!]+|[，,；;]+)', text)
        sentences = []
        buf = ''
        for p in parts:
            if not p:
                continue
            if re.match(r'^[。！？!?\.？!,，;；]+$', p):
                buf += p  # 标点合并到前一句
                if buf.strip():
                    sentences.append(buf.strip())
                    buf = ''
            else:
                buf += p
        if buf.strip():
            sentences.append(buf.strip())
        # 3) 单句过长强制按字数切 + 换行
        MAX_LINE = 10       # 每行最多 10 汉字
        MAX_LINES = 2       # 最多 2 行
        MAX_CHARS = MAX_LINE * MAX_LINES
        pieces = []
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            if len(sent) <= MAX_CHARS:
                pieces.append(sent)
                continue
            # 强制切：每 MAX_LINE 字一段，最后一段在剩余字数
            for i in range(0, len(sent), MAX_LINE):
                chunk = sent[i:i + MAX_LINE]
                pieces.append(chunk)
        if not pieces:  # 兜底：原文
            pieces = [text]
        # 4) 短句均分时间窗口
        n = len(pieces)
        step = (e - s) / n
        out = []
        for i, p in enumerate(pieces):
            ps = s + i * step
            pe = s + (i + 1) * step
            # 短句如果还长，单句内换行（用 \n）
            wrapped = _wrap_line(p, MAX_LINE, MAX_LINES)
            out.append((ps, pe, wrapped))
        return out

    def _wrap_line(text: str, max_line: int, max_lines: int) -> str:
        """单句超长按 max_line 字一行，最多 max_lines 行（用 \\n 换行）"""
        if len(text) <= max_line * max_lines:
            # 看是否需要换行
            if len(text) > max_line:
                mid = len(text) // 2
                # 找最近的标点切
                best = mid
                for off in range(0, mid):
                    if mid - off >= 0 and text[mid - off] in '，,。. ':
                        best = mid - off
                        break
                    if mid + off < len(text) and text[mid + off] in '，,。. ':
                        best = mid + off + 1
                        break
                return text[:best] + '\n' + text[best:].lstrip()
            return text
        # 太长：硬切
        lines = []
        for i in range(0, len(text), max_line):
            lines.append(text[i:i + max_line])
            if len(lines) >= max_lines:
                break
        return '\n'.join(lines)

    # 解析字幕
    subtitles = parse_srt(srt_path, start)

    if not subtitles:
        logger.warning("未找到有效字幕，跳过烧录")
        video.write_videofile(
            str(output_path),
            codec='h264_videotoolbox', audio_codec='aac',
            ffmpeg_params=['-movflags', '+faststart', '-g', '60', '-keyint_min', '60', '-b:v', '8M'],
        )
        return
    
    # 创建字幕片段（带字体 fallback）
    import os
    _MAC_FALLBACK_FONTS = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/Library/Fonts/Songti.ttc",
    ]

    def _resolve_font(requested):
        """如果请求字体不存在，自动 fallback 到 macOS 中文字体"""
        if requested and os.path.exists(requested):
            return requested
        for fp in _MAC_FALLBACK_FONTS:
            if os.path.exists(fp):
                logger.warning(f"字体 {requested} 不可用，fallback 到 {fp}")
                return fp
        return requested  # 让 MoviePy 自己处理

    def make_textclip(text):
        return TextClip(
            text=text,
            font_size=config["font_size"],
            color=config["txt_color"],
            stroke_color=config["stroke_color"],
            stroke_width=config["stroke_width"],
            font=_resolve_font(config["font"])
        )
    
    subclips = []
    for start_sec, end_sec, text in subtitles:
        if text.strip():
            # position: ('center', y) y=0.33 表示视频高度的 33% 处
            sub = make_textclip(text).with_start(start_sec).with_end(end_sec).with_position(('center', config["position"]), relative=True)
            subclips.append(sub)
    
    # 合成视频 + 字幕
    final = CompositeVideoClip([video] + subclips)
    # +faststart：把 moov atom 写到文件头，浏览器秒开（前 3 秒不卡顿）
    # -g 30 -keyint_min 30：每 30 帧 1 个 I 帧（≈ 1 秒 1 个 30fps 视频），
    #                     保证首帧后能快速 seek / 接续解码
    final.write_videofile(
        str(output_path),
        codec='h264_videotoolbox', audio_codec='aac',
        ffmpeg_params=['-movflags', '+faststart', '-g', '60', '-keyint_min', '60', '-b:v', '8M'],
    )
    
    logger.info(f"字幕烧录完成：{output_path}")


def cut_clips(clips: List[Dict], input_video: Path, output_dir: Path, input_srt: Path = None, task_id: str = None, subtitle_config: dict = None, with_subtitle: bool = True, project_id: str = None):
    """切割视频切片

    Args:
        clips: 切片数据列表
        input_video: 输入视频路径
        output_dir: 输出目录
        input_srt: 字幕文件路径（可选，有则烧录字幕）
        task_id: 可选的任务 ID，用于更新进度
        subtitle_config: 字幕配置 {font_size, txt_color, stroke_color, stroke_width, font, position}
        with_subtitle: 是否烧录字幕（False = 纯剪片子，不烧字幕，省时省力）
    """
    logger.info(f"开始切割 {len(clips)} 个切片")

    # 决定是否烧录字幕
    srt_path = None
    if with_subtitle and input_srt and Path(input_srt).exists():
        srt_path = input_srt
        logger.info(f"将烧录字幕：{srt_path}")
    elif not with_subtitle:
        logger.info("用户选择纯剪片子（不烧字幕）")
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
                        "-keyint_min", "60",
                        "-g", "60",
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
                    "-keyint_min", "60",
                    "-g", "60",
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
            
            # ✅ 修复：每 5 个切片或最后一个切片时更新进度（65% → 90%）
            if task_id and ((i + 1) % 5 == 0 or i == len(clips) - 1):
                try:
                    from ..tasks.processing import _update_task_progress
                    progress = 65 + int(((i + 1) / len(clips)) * 25)  # 65% → 90%
                    _update_task_progress(task_id, progress, f"切割中... ({i+1}/{len(clips)})")
                except Exception as e:
                    logger.warning(f"进度更新失败：{e}")
            
        except subprocess.TimeoutExpired:
            logger.error(f"切割切片 {i+1} 超时（300 秒），跳过")
        except Exception as e:
            logger.error(f"切割切片 {i+1} 失败：{e}")

    # ✅ 切完第一个成功后生成项目封面缩略图
    if project_id and clips:
        try:
            thumb_dir = output_dir.parent / "thumbnails"
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / f"{project_id}.jpg"
            # 用第一片抽 1 秒处一帧
            first_clip = next((c for c in clips if c.get("video_path")), None)
            if first_clip:
                clip_path = output_dir.parent.parent / first_clip["video_path"]
                if clip_path.exists():
                    subprocess.run([
                        "ffmpeg", "-y", "-ss", "1", "-i", str(clip_path),
                        "-vframes", "1", "-q:v", "2",
                        "-vf", "scale=600:-1", str(thumb_path)
                    ], check=True, capture_output=True, timeout=30)
                    logger.info(f"项目封面已生成：{thumb_path}")
        except Exception as e:
            logger.warning(f"项目封面生成失败（非阻塞）：{e}")


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
                "-keyint_min", "60",
                "-g", "60",
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
            
            # ✅ 修复：每个合集完成后更新进度（93% → 99%）
            if task_id:
                try:
                    from ..tasks.processing import _update_task_progress
                    progress = 93 + int(((i + 1) / len(collections)) * 6)  # 93% → 99%
                    _update_task_progress(task_id, min(progress, 99), f"合并合集中... ({i+1}/{len(collections)})")
                except Exception as e:
                    logger.warning(f"进度更新失败：{e}")
            
            # 清理临时文件
            list_path.unlink()
            
        except Exception as e:
            logger.error(f"合并合集 {i+1} 失败：{e}")
