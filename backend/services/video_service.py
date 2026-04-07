"""视频处理服务"""
import logging
import subprocess
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def cut_clips(clips: List[Dict], input_video: Path, output_dir: Path):
    """切割视频切片"""
    logger.info(f"开始切割 {len(clips)} 个切片")
    
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
            
            # 方案一：流复制（最快，10-20 倍速，不重新编码）
            # 注意：FFmpeg 8.x 移除了 -avoid_negative_ts make_one，改用 -copyts
            subprocess.run([
                "ffmpeg", "-y",
                "-i", str(input_video),
                "-ss", str(start),
                "-t", str(duration),
                "-c", "copy",
                "-copyts",
                str(output_path)
            ], check=True, capture_output=True)
            
            # 保存相对路径
            clip["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
            
        except Exception as e:
            logger.error(f"切割切片 {i+1} 失败：{e}")


def merge_collections(collections: List[Dict], clips_dir: Path, output_dir: Path):
    """合并合集"""
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
            
            # 方案一：流复制（最快，不重新编码）
            subprocess.run([
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(output_path)
            ], check=True, capture_output=True)
            
            # 保存相对路径
            collection["video_path"] = str(output_path.relative_to(output_path.parent.parent.parent))
            logger.info(f"合集 {i+1} 合并完成：{output_path}")
            
            # 清理临时文件
            list_path.unlink()
            
        except Exception as e:
            logger.error(f"合并合集 {i+1} 失败：{e}")
