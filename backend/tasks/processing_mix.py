"""混剪项目独立 Celery task (v2.2.3 完全跟切片 task 分开)

跟 backend/tasks/processing.py 完全分离:
- 不依赖 Project / Clip / Task model (切片)
- 用 MixProject / MixSourceClip / MixTask (混剪独立 db)
- 读切片 db 只读 (build_clip_library_from_slice_db), 不写
- 写混剪 db 全部用 sync_get_mix_db

celery task: process_mix_pipeline
queue: processing_mix (跟切片 processing_beta 独立 worker / queue)
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from celery import shared_task
from sqlalchemy import select

from ..core.database_mix import sync_get_mix_db
from ..models.mix import MixProject, MixSourceClip, MixTask, MixBase
from ..services.mix_service import (
    parse_script,
    build_clip_library_from_slice_db,
    match_clips_for_segments,
    assemble_mix_video,
    build_script_srt,
    burn_mix_subtitle,
)

logger = logging.getLogger(__name__)


# 进度常量
MIX_PROGRESS = {
    "task_start": 0,
    "parse_start": 10,
    "parse_done": 25,
    "match_start": 30,
    "match_done": 55,
    "assemble_start": 60,
    "assemble_done": 90,
    "burn_done": 96,
    "complete": 100,
}


def _update_mix_task_progress(task_id: str, progress: int, current_step: str) -> None:
    """更新 MixTask 进度 + 心跳字段"""
    if not task_id:
        return
    try:
        with sync_get_mix_db() as db:
            task = db.execute(select(MixTask).where(MixTask.id == task_id)).scalar_one_or_none()
            if task:
                task.progress = max(0, min(100, progress))
                task.current_step = current_step[:255]
                task.progress_changed_at = datetime.utcnow()
                db.commit()
    except Exception as e:
        logger.warning(f"混剪 task 进度更新失败: {e}")


def _mark_mix_task_running(task_id: str) -> None:
    if not task_id:
        return
    try:
        with sync_get_mix_db() as db:
            task = db.execute(select(MixTask).where(MixTask.id == task_id)).scalar_one_or_none()
            if task:
                task.status = "running"
                if not task.started_at:
                    task.started_at = datetime.utcnow()
                task.progress_changed_at = datetime.utcnow()
                db.commit()
    except Exception as e:
        logger.warning(f"混剪 task 启动标记失败: {e}")


@shared_task(bind=True)
def process_mix_pipeline(
    self,
    mix_project_id: str,
    script_text: str,
    target_duration_seconds: int,
    candidate_clip_ids: List[str],
    task_id: str = None,
) -> dict:
    """混剪 pipeline (完全跟切片项目解耦)

    流程:
      Step 1 LLM 解析脚本 → segments
      Step 2 加载切片 db 的候选 clip (只读)
      Step 3 关键词匹配 + 时长分配
      Step 4 ffmpeg 拼接 (libx264)
      Step 5 烧脚本原字幕
      Step 6 写 mix db + 标 completed
    """
    logger.info(f"开始混剪项目: {mix_project_id}, target={target_duration_seconds}s, candidates={len(candidate_clip_ids)}")

    _mark_mix_task_running(task_id)

    # 加载 mix project
    with sync_get_mix_db() as db:
        project = db.execute(select(MixProject).where(MixProject.id == mix_project_id)).scalar_one_or_none()
        if not project:
            raise RuntimeError(f"混剪项目不存在: {mix_project_id}")

    # 混剪 output 路径: data/projects/<mix_project_id>/output/mix_output.mp4
    # 跟切片项目目录结构一致 (便于前端视频流通用)
    mix_projects_root = Path("data/projects").resolve()
    project_output_dir = mix_projects_root / mix_project_id / "output"
    project_output_dir.mkdir(parents=True, exist_ok=True)
    output_video = project_output_dir / "mix_output.mp4"

    subtitle_style = project.subtitle_style or {}

    try:
        # Step 1: LLM 解析脚本
        _update_mix_task_progress(task_id, MIX_PROGRESS["parse_start"], "解析脚本...")
        segments = parse_script(script_text, target_duration_seconds)
        if not segments:
            raise RuntimeError("LLM 解析脚本失败, 没得到有效分段")

        with sync_get_mix_db() as db:
            proj = db.execute(select(MixProject).where(MixProject.id == mix_project_id)).scalar_one()
            proj.script_segments = segments
            db.commit()

        # Step 2: 加载切片 db 的 clip 库 (只读)
        clip_library = build_clip_library_from_slice_db(candidate_clip_ids)

        # Step 3: 关键词匹配 + 时长分配
        _update_mix_task_progress(task_id, MIX_PROGRESS["match_start"], "匹配素材片段...")
        matched = match_clips_for_segments(segments, clip_library, target_duration_seconds)
        if not matched:
            raise RuntimeError("没匹配到任何 source clip, 检查素材库或脚本关键词")

        # Step 4: ffmpeg 拼接
        _update_mix_task_progress(task_id, MIX_PROGRESS["assemble_start"], f"拼接 {len(matched)} 段视频...")
        assemble_mix_video(matched, mix_projects_root, output_video)

        # Step 5: 烧脚本原字幕
        _update_mix_task_progress(task_id, MIX_PROGRESS["assemble_done"], "烧字幕...")
        total_dur = sum(s["clip_duration"] for s in matched)
        srt_text = build_script_srt(matched, total_duration=total_dur)
        burn_mix_subtitle(output_video, srt_text, subtitle_style, total_duration=total_dur)

        # Step 6: 写 mix db (MixProject.output_video_path + MixSourceClip rows + MixTask.completed)
        total_dur = sum(s["clip_duration"] for s in matched)
        with sync_get_mix_db() as db:
            proj = db.execute(select(MixProject).where(MixProject.id == mix_project_id)).scalar_one()
            proj.output_video_path = str(output_video.relative_to(mix_projects_root))
            proj.video_size = output_video.stat().st_size
            proj.video_duration = total_dur
            proj.status = "completed"
            proj.completed_at = datetime.utcnow()

            for seg in matched:
                ms = MixSourceClip(
                    id=str(uuid.uuid4()),
                    mix_project_id=mix_project_id,
                    source_clip_id=seg["matched_clip_id"],
                    source_project_id=seg["source_project_id"],
                    source_project_name=seg.get("source_project_name", ""),
                    source_clip_title=seg.get("source_clip_title", ""),
                    position=seg["position"],
                    script_segment_text=seg["text"],
                    keywords=seg.get("keywords", []),
                    match_score=seg["match_score"],
                    source_start=seg["source_start"],
                    source_end=seg["source_end"],
                    duration=seg["clip_duration"],
                )
                db.add(ms)

            task = db.execute(select(MixTask).where(MixTask.id == task_id)).scalar_one_or_none()
            if task:
                task.status = "completed"
                task.progress = 100
                task.completed_at = datetime.utcnow()
                if task.started_at:
                    task.actual_total_seconds = (datetime.utcnow() - task.started_at).total_seconds()

            db.commit()
            logger.info(f"混剪完成: {mix_project_id}, output={output_video}, segments={len(matched)}")

        _update_mix_task_progress(task_id, MIX_PROGRESS["complete"], "混剪完成")
        return {
            "status": "completed",
            "output_video": str(output_video),
            "segments_matched": len(matched),
            "total_duration": total_dur,
        }

    except Exception as e:
        logger.exception(f"混剪失败: {e}")
        with sync_get_mix_db() as db:
            proj = db.execute(select(MixProject).where(MixProject.id == mix_project_id)).scalar_one_or_none()
            if proj:
                proj.status = "failed"
            task = db.execute(select(MixTask).where(MixTask.id == task_id)).scalar_one_or_none()
            if task:
                task.status = "failed"
                task.error_message = str(e)[:500]
            db.commit()
        raise