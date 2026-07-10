"""混剪项目独立 API (v2.2.3 完全跟切片 API 分开)

跟 backend/api/projects.py 完全分离:
- 独立 db (mix db) — 通过 backend.core.database_mix.sync_get_mix_db
- 独立 router — prefix=/api/v1/mix (跟切片 /api/v1/projects 并列)
- 不读不写切片 db Project/Clip 表 (只读 Clip 表当素材库)

端点:
  POST   /api/v1/mix              创建混剪项目 (派发到 processing_mix queue)
  GET    /api/v1/mix              列表 (project_type='mix')
  GET    /api/v1/mix/{id}         详情 (MixProject + MixSourceClips + 最新 task)
  DELETE /api/v1/mix/{id}         软删除
  GET    /api/v1/mix/clips/library  候选素材库 (从切片 db 读 clips)
  GET    /api/v1/mix/videos/{id}  输出视频流 (前端 player 用)
"""
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database_mix import get_mix_db, sync_get_mix_db
from ..models.mix import MixProject, MixSourceClip, MixTask, MixBase

router = APIRouter(prefix="/mix", tags=["mix"])
logger = logging.getLogger(__name__)


@router.post("")
async def create_mix_project(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_mix_db),
):
    """创建混剪项目, 派发到 processing_mix queue

    payload:
        name: str                  项目名
        script_text: str           直播脚本原文
        target_duration_seconds: int  目标时长 (30/60/180/300)
        candidate_clip_ids: list[str]  候选 source clip id 列表
        subtitle_style: dict (可选)  字幕样式
    """
    import uuid as _uuid

    name = payload.get("name") or "混剪项目"
    script_text = (payload.get("script_text") or "").strip()
    target_duration = int(payload.get("target_duration_seconds") or 60)
    candidate_clip_ids = payload.get("candidate_clip_ids") or []
    subtitle_style = payload.get("subtitle_style") or {}

    if not script_text:
        raise HTTPException(status_code=400, detail="script_text 不能为空")
    if not candidate_clip_ids:
        raise HTTPException(status_code=400, detail="candidate_clip_ids 不能为空")
    if target_duration not in (30, 60, 180, 300):
        raise HTTPException(status_code=400, detail="target_duration_seconds 必须是 30/60/180/300")

    # 1) 创建 MixProject
    project_id = str(_uuid.uuid4())
    project = MixProject(
        id=project_id,
        name=name,
        description=payload.get("description", ""),
        status="pending",
        script_text=script_text,
        target_duration_seconds=target_duration,
        subtitle_style=subtitle_style,
    )
    db.add(project)

    # 2) 创建 MixTask
    task_id = str(_uuid.uuid4())
    task = MixTask(
        id=task_id,
        mix_project_id=project_id,
        task_type="mix_processing",
        name="混剪处理",
        description=f"AI 混剪 {len(candidate_clip_ids)} 素材, 目标 {target_duration}s",
        status="pending",
        progress=0,
        current_step="等待 worker 启动",
    )
    db.add(task)
    await db.commit()

    # 3) 派发到 processing_mix queue (跟切片 processing 独立)
    try:
        from ..tasks.processing_mix import process_mix_pipeline
        process_mix_pipeline.apply_async(
            kwargs={
                "mix_project_id": project_id,
                "script_text": script_text,
                "target_duration_seconds": target_duration,
                "candidate_clip_ids": candidate_clip_ids,
                "task_id": task_id,
            },
            queue="processing_mix",
        )
        logger.info(f"混剪项目已派发: {project_id}, task_id={task_id}")
    except Exception as e:
        logger.exception(f"派发混剪任务失败: {e}")
        project.status = "failed"
        task.status = "failed"
        task.error_message = f"派发失败: {str(e)[:300]}"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"派发失败: {str(e)}")

    return {
        "project_id": project_id,
        "task_id": task_id,
        "status": "pending",
        "name": name,
        "target_duration_seconds": target_duration,
        "candidate_clip_count": len(candidate_clip_ids),
    }


@router.get("")
async def list_mix_projects(
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_mix_db),
):
    """列出混剪项目 (从 mix db)"""
    query = (
        select(MixProject)
        .options(selectinload(MixProject.tasks), selectinload(MixProject.source_clips))
    )
    if not include_deleted:
        query = query.where(MixProject.deleted_at.is_(None))
    query = query.order_by(MixProject.created_at.desc())

    result = await db.execute(query)
    projects = result.scalars().all()

    items = []
    for p in projects:
        latest = max(p.tasks, key=lambda t: t.created_at, default=None) if p.tasks else None
        items.append({
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "target_duration_seconds": p.target_duration_seconds,
            "output_video_path": p.output_video_path,
            "video_size": p.video_size,
            "video_duration": p.video_duration,
            "source_clip_count": len(p.source_clips),
            "task": {
                "progress": latest.progress if latest else 0,
                "current_step": latest.current_step if latest else "",
                "status": latest.status if latest else "pending",
                "error_message": latest.error_message if latest else "",
            } if latest else None,
        })
    return {"projects": items}


@router.get("/clips/library")
async def list_candidate_clips(
    limit: int = 500,
):
    """候选素材库: 从切片 db 读 clips (只读)

    用于 /mix/new wizard 步骤 2 (选素材).
    切片 db 完全只读, 不写.
    """
    from ..models.database import Clip, Project
    from ..core.database import sync_get_db

    with sync_get_db() as db:
        rows = db.query(Clip, Project.name.label("project_name")).join(
            Project, Clip.project_id == Project.id
        ).filter(
            Project.deleted_at.is_(None),
        ).order_by(Clip.created_at.desc()).limit(limit).all()

        items = []
        for clip, pname in rows:
            subtitle_preview = ""
            if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
                subtitle_preview = (clip.clip_metadata.get("subtitle_text") or "")[:200]
            items.append({
                "clip_id": clip.id,
                "title": clip.title,
                "source_project_id": clip.project_id,
                "source_project_name": pname or "",
                "video_path": clip.video_path,
                "duration": clip.duration,
                "width": clip.width,
                "height": clip.height,
                "subtitle_text_preview": subtitle_preview,
                "created_at": clip.created_at.isoformat() if clip.created_at else None,
            })
    return {"clips": items, "count": len(items)}


@router.get("/{project_id}")
async def get_mix_project(
    project_id: str,
    db: AsyncSession = Depends(get_mix_db),
):
    """混剪项目详情"""
    result = await db.execute(
        select(MixProject)
        .options(
            selectinload(MixProject.tasks),
            selectinload(MixProject.source_clips),
        )
        .where(MixProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Mix project not found")

    segments_info = []
    for ms in sorted(project.source_clips, key=lambda x: x.position):
        segments_info.append({
            "id": ms.id,
            "position": ms.position,
            "script_segment_text": ms.script_segment_text,
            "keywords": ms.keywords,
            "match_score": ms.match_score,
            "source_start": ms.source_start,
            "source_end": ms.source_end,
            "duration": ms.duration,
            "source_clip_id": ms.source_clip_id,
            "source_clip_title": ms.source_clip_title,
            "source_project_id": ms.source_project_id,
            "source_project_name": ms.source_project_name,
        })

    latest = max(project.tasks, key=lambda t: t.created_at, default=None) if project.tasks else None

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "script_text": project.script_text,
        "script_segments": project.script_segments,
        "target_duration_seconds": project.target_duration_seconds,
        "output_video_path": project.output_video_path,
        "video_size": project.video_size,
        "video_duration": project.video_duration,
        "video_width": project.video_width,
        "video_height": project.video_height,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "completed_at": project.completed_at.isoformat() if project.completed_at else None,
        "task": {
            "progress": latest.progress if latest else 0,
            "current_step": latest.current_step if latest else "",
            "status": latest.status if latest else "pending",
            "error_message": latest.error_message if latest else "",
            "created_at": latest.created_at.isoformat() if latest and latest.created_at else None,
            "started_at": latest.started_at.isoformat() if latest and latest.started_at else None,
            "completed_at": latest.completed_at.isoformat() if latest and latest.completed_at else None,
        } if latest else None,
        "source_clips": segments_info,
    }


@router.get("/videos/{project_id}")
async def stream_mix_video(project_id: str):
    """流式输出混剪视频 (前端 player 用)

    路径: data/projects/<mix_project_id>/output/mix_output.mp4
    """
    mix_projects_root = Path("data/projects").resolve()
    video_path = mix_projects_root / project_id / "output" / "mix_output.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="混剪视频不存在")
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        },
    )


@router.delete("/{project_id}")
async def delete_mix_project(
    project_id: str,
    db: AsyncSession = Depends(get_mix_db),
):
    """软删除"""
    result = await db.execute(
        select(MixProject).where(MixProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Mix project not found")
    if project.status == "processing":
        raise HTTPException(status_code=409, detail="处理中的混剪不能删除")

    project.deleted_at = datetime.utcnow()
    await db.commit()
    return {"id": project_id, "deleted": True}