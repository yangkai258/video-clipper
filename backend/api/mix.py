"""混剪项目 API v2.2.3"""
import logging
from datetime import datetime
from typing import Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Body
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database import get_db
from ..models.database import (
    Project, Clip, Task, Style, MixSegment,
)

router = APIRouter(prefix="/mix", tags=["mix"])
logger = logging.getLogger(__name__)


@router.post("")
async def create_mix_project(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """创建混剪项目, 派发到 worker

    payload:
        name: str              — 项目名
        script_text: str       — 直播脚本 (大段文字)
        target_duration_seconds: int  — 目标时长 (30/60/180/300)
        candidate_clip_ids: list[str]  — 候选 source clip id 列表
        processing_config: dict (可选)  — {subtitle_style, style_id, ...}
    """
    name = payload.get("name") or "混剪项目"
    script_text = payload.get("script_text", "").strip()
    target_duration = int(payload.get("target_duration_seconds") or 60)
    candidate_clip_ids = payload.get("candidate_clip_ids") or []
    processing_config = payload.get("processing_config") or {}

    if not script_text:
        raise HTTPException(status_code=400, detail="script_text 不能为空")
    if not candidate_clip_ids:
        raise HTTPException(status_code=400, detail="candidate_clip_ids 不能为空")
    if target_duration not in (30, 60, 180, 300):
        raise HTTPException(status_code=400, detail="target_duration_seconds 必须是 30/60/180/300")

    # 1) 创建 Project row (project_type='mix')
    project_id = str(uuid.uuid4())
    project = Project(
        id=project_id,
        name=name,
        description=payload.get("description", ""),
        project_type="mix",
        status="pending",
        script_text=script_text,
        target_duration_seconds=target_duration,
        processing_config=processing_config,
        # mix 项目没 video_path, output_video_path 后面写
    )
    db.add(project)

    # 2) 创建 Task row (跟现有 video_processing 同样的 task 模式, 让 progress / status / UI 都复用)
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        project_id=project_id,
        task_type="mix_processing",
        name="混剪处理",
        description=f"AI 混剪 {len(candidate_clip_ids)} 素材, 目标 {target_duration}s",
        status="pending",
        progress=0,
        current_step="等待 worker 启动",
    )
    db.add(task)
    await db.commit()

    # 3) 派发到 celery worker (用 processing.process_mix_pipeline 异步跑)
    try:
        from ..tasks.processing import process_mix_pipeline
        process_mix_pipeline.delay(
            mix_project_id=project_id,
            script_text=script_text,
            target_duration_seconds=target_duration,
            candidate_clip_ids=candidate_clip_ids,
            task_id=task_id,
        )
        logger.info(f"混剪项目已派发: {project_id}, task_id={task_id}")
    except Exception as e:
        logger.exception(f"派发混剪任务失败: {e}")
        # 回滚 project/task 状态
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
    db: AsyncSession = Depends(get_db),
):
    """列出混剪项目 (project_type='mix')

    复用 list_projects 类似的字段, 加 script_segments + target_duration + output_video_path
    """
    query = (
        select(Project)
        .options(selectinload(Project.tasks), selectinload(Project.mix_segments))
        .where(Project.project_type == "mix")
    )
    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))
    query = query.order_by(Project.created_at.desc())

    result = await db.execute(query)
    projects = result.scalars().all()

    # 批量查 mix_segments count
    project_ids = [p.id for p in projects]
    from sqlalchemy import func
    seg_counts = {}
    if project_ids:
        result = await db.execute(
            select(MixSegment.mix_project_id, func.count(MixSegment.id))
            .where(MixSegment.mix_project_id.in_(project_ids))
            .group_by(MixSegment.mix_project_id)
        )
        seg_counts = dict(result.all())

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
            "mix_segment_count": seg_counts.get(p.id, 0),
            "task": {
                "progress": latest.progress if latest else 0,
                "current_step": latest.current_step if latest else "",
                "status": latest.status if latest else "pending",
                "error_message": latest.error_message if latest else "",
            } if latest else None,
        })
    return {"projects": items}


@router.get("/{project_id}")
async def get_mix_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """混剪项目详情: 含 Project + Task + MixSegments + 来源 clips 信息"""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.tasks),
            selectinload(Project.mix_segments),
        )
        .where(Project.id == project_id)
        .where(Project.project_type == "mix")
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Mix project not found")

    # 关联加载每个 MixSegment 的 source_clip + source_project 信息
    segments_info = []
    for ms in sorted(project.mix_segments, key=lambda x: x.position):
        # 拿 source_clip
        clip_result = await db.execute(select(Clip).where(Clip.id == ms.source_clip_id))
        source_clip = clip_result.scalar_one_or_none()
        # 拿 source_project name
        proj_result = await db.execute(select(Project.name).where(Project.id == ms.source_project_id))
        source_project_name = proj_result.scalar_one_or_none()
        segments_info.append({
            "id": ms.id,
            "position": ms.position,
            "script_segment_text": ms.script_segment_text,
            "match_score": ms.match_score,
            "start_time": ms.start_time,
            "end_time": ms.end_time,
            "duration": ms.duration,
            "source_clip_id": ms.source_clip_id,
            "source_clip_title": source_clip.title if source_clip else "",
            "source_project_id": ms.source_project_id,
            "source_project_name": source_project_name or "",
        })

    latest = max(project.tasks, key=lambda t: t.created_at, default=None) if project.tasks else None

    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "project_type": "mix",
        "script_text": project.script_text,
        "script_segments": project.script_segments,
        "target_duration_seconds": project.target_duration_seconds,
        "output_video_path": project.output_video_path,
        "video_size": project.video_size,
        "video_duration": project.video_duration,
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
        "mix_segments": segments_info,
    }


@router.get("/clips/library")
async def list_candidate_clips(
    db: AsyncSession = Depends(get_db),
):
    """候选素材库: 列所有 project 的 clips (排除 mix 自己生成的)

    用于 /mix/new wizard 步骤 2 (选素材)
    返回 [{clip_id, title, source_project_id, source_project_name, video_path, duration, subtitle_text_preview}, ...]
    """
    result = await db.execute(
        select(Clip, Project.name.label("project_name"), Project.id.label("project_id_"))
        .join(Project, Clip.project_id == Project.id)
        .where(Project.project_type != "mix")  # 排除 mix 项目自己的 (虽然 mix 不生成 Clip)
        .where(Project.deleted_at.is_(None))
        .order_by(Clip.created_at.desc())
        .limit(500)
    )
    items = []
    for clip, pname, pid in result.all():
        # 优先用 metadata.subtitle_text, fallback title
        subtitle_preview = ""
        if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
            subtitle_preview = (clip.clip_metadata.get("subtitle_text") or "")[:200]
        items.append({
            "clip_id": clip.id,
            "title": clip.title,
            "source_project_id": pid,
            "source_project_name": pname,
            "video_path": clip.video_path,
            "duration": clip.duration,
            "subtitle_text_preview": subtitle_preview,
            "created_at": clip.created_at.isoformat() if clip.created_at else None,
        })
    return {"clips": items, "count": len(items)}


@router.delete("/{project_id}")
async def delete_mix_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """软删除混剪项目 (跟切片项目一致, 进回收站)"""
    result = await db.execute(
        select(Project).where(Project.id == project_id).where(Project.project_type == "mix")
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Mix project not found")
    if project.status == "processing":
        raise HTTPException(status_code=409, detail="处理中的混剪不能删除")

    project.deleted_at = datetime.utcnow()
    await db.commit()
    return {"id": project_id, "deleted": True}