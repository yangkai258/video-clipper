"""混剪项目独立 API (v2.2.5 完全跟切片 API 分开)

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
  POST   /api/v1/mix/ai-help-write  AI 帮写带货脚本 (v2.2.5)
"""

import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..core.database_mix import get_mix_db
from ..models.mix import MixBatch, MixProject, MixTask
from ..services.risk_detector import check_script_risk

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
        raise HTTPException(
            status_code=400, detail="target_duration_seconds 必须是 30/60/180/300"
        )

    # 1) 创建 MixProject (v2.2.6 batch_id 透传)
    project_id = str(_uuid.uuid4())
    project = MixProject(
        id=project_id,
        name=name,
        description=payload.get("description", ""),
        status="pending",
        script_text=script_text,
        target_duration_seconds=target_duration,
        subtitle_style=subtitle_style,
        batch_id=payload.get("batch_id"),  # v2.2.6: 批量批次关联
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
        # v2.2.24: 显式走 db=0 broker (跟 mix worker 一致, 跨 release/beta 模式)
        from ..services.mix_dispatch import dispatch_mix_task

        celery_id = dispatch_mix_task(
            mix_project_id=project_id,
            script_text=script_text,
            target_duration_seconds=target_duration,
            candidate_clip_ids=candidate_clip_ids,
            task_id=task_id,
        )
        # v2.2.25: 写 celery_task_id 到 db (worker 收到时验证 + 卡死 stuck 排查)
        task.celery_task_id = celery_id
        await db.commit()
        logger.info(
            f"混剪项目已派发: {project_id}, task_id={task_id}, celery_id={celery_id}"
        )
    except Exception as e:
        logger.exception(f"派发混剪任务失败: {e}")
        project.status = "failed"
        task.status = "failed"
        task.error_message = f"派发失败: {str(e)[:300]}"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"派发失败: {e!s}")

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
    query = select(MixProject).options(
        selectinload(MixProject.tasks), selectinload(MixProject.source_clips)
    )
    if not include_deleted:
        query = query.where(MixProject.deleted_at.is_(None))
    query = query.order_by(MixProject.created_at.desc())

    result = await db.execute(query)
    projects = result.scalars().all()

    items = []
    for p in projects:
        latest = (
            max(p.tasks, key=lambda t: t.created_at, default=None) if p.tasks else None
        )
        items.append(
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                "target_duration_seconds": p.target_duration_seconds,
                "output_video_path": p.output_video_path,
                "video_size": p.video_size,
                "video_duration": p.video_duration,
                "thumbnail_path": p.thumbnail_path,  # v2.2.4: 缩略图 (list card 用)
                "source_clip_count": len(p.source_clips),
                "task": {
                    "progress": latest.progress if latest else 0,
                    "current_step": latest.current_step if latest else "",
                    "status": latest.status if latest else "pending",
                    "error_message": latest.error_message if latest else "",
                }
                if latest
                else None,
            }
        )
    return {"projects": items}


@router.get("/clips/library")
async def list_candidate_clips(
    limit: int = 500,
    source: str = "all",  # "all" | "project" | "library"  v2.2.5 wizard 接资源库
):
    """候选素材库: 从切片 db 读 clips + 资源库 (只读)

    用于 /mix/new wizard 步骤 2 (选素材).
    v2.2.5: source query 区分来源 — project (切片项目 clip) / library (资源库) / all (默认)
    """
    from ..core.database import sync_get_db
    from ..models.database import Clip, Project, ResourceClip

    items = []

    if source in ("all", "project"):
        # 切片项目的 clips
        with sync_get_db() as db:
            rows = (
                db.query(Clip, Project.name.label("project_name"))
                .join(Project, Clip.project_id == Project.id)
                .filter(
                    Project.deleted_at.is_(None),
                )
                .order_by(Clip.created_at.desc())
                .limit(limit)
                .all()
            )

            for clip, pname in rows:
                subtitle_preview = ""
                if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
                    subtitle_preview = (clip.clip_metadata.get("subtitle_text") or "")[
                        :200
                    ]
                items.append(
                    {
                        "id": clip.id,  # v2.2.5: 统一用 id 字段 (前端一致处理)
                        "clip_id": clip.id,  # 兼容旧字段
                        "title": clip.title,
                        "source_project_id": clip.project_id,
                        "source_project_name": pname or "",
                        "source_type": "project",
                        "video_path": clip.video_path,
                        "duration": clip.duration,
                        "width": clip.width,
                        "height": clip.height,
                        "subtitle_text_preview": subtitle_preview,
                        "created_at": clip.created_at.isoformat()
                        if clip.created_at
                        else None,
                    }
                )

    if source in ("all", "library"):
        # 资源库 clips (ResourceClip 跟切片 Project 在同一个 db, 用同一个 session)
        with sync_get_db() as db:
            rows = (
                db.query(ResourceClip)
                .filter(
                    ResourceClip.deleted_at.is_(None),
                )
                .order_by(ResourceClip.created_at.desc())
                .limit(limit)
                .all()
            )
            for rc in rows:
                items.append(
                    {
                        "id": rc.id,
                        "clip_id": rc.id,  # wizard Step 3 POST /mix 用 candidate_clip_ids, 都按 id 处理
                        "title": rc.name,
                        "source_project_id": rc.source_project_id,
                        "source_project_name": rc.source_project_name or "资源库",
                        "source_type": "library",
                        "video_path": rc.file_path,
                        "duration": rc.duration,
                        "width": rc.width,
                        "height": rc.height,
                        "subtitle_text_preview": "",  # 资源库没存字幕
                        "created_at": rc.created_at.isoformat()
                        if rc.created_at
                        else None,
                    }
                )

    return {"clips": items, "count": len(items)}


# ──────────────────────────── v2.2.6: 批量混剪 ────────────────────────────


@router.post("/batch")
async def create_mix_batch(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_mix_db),
):
    """批量创建混剪变体 (v2.2.6)

    payload:
        name: str                  批次名 (如 "防水 A/B 测试")
        common_script_text: str    公共脚本 (会被 variations[].script_text 覆盖)
        common_target_duration: int  公共目标时长 30/60/180/300
        max_concurrent: int        同一时刻最大并发数 (1-3, 默认 1)
        variations: list[dict]     N 个变体定义
            {
                "name": "变体 A",
                "script_text": "(可选, 覆盖 common)",
                "target_duration_seconds": 60,
                "candidate_clip_ids": ["id1", "id2", ...]
            }

    Returns: {batch_id, total_count, projects: [{project_id, name}]}

    性能约束:
      - 创建 batch + N 个 project + N 个 task, 一次性 commit (避免 N 次 round-trip)
      - 派 N 个 celery task 到 processing_mix queue
      - 实际并发由 worker side 控制 (task 启动时检查 batch.max_concurrent)
      - 默认 max_concurrent=1 (零额外负载, 跟现在一致)
    """
    import uuid as _uuid

    name = payload.get("name") or f"批量混剪 {datetime.utcnow().strftime('%H:%M')}"
    common_script = (payload.get("common_script_text") or "").strip()
    common_duration = int(payload.get("common_target_duration") or 60)
    max_concurrent = int(payload.get("max_concurrent") or 1)
    variations = payload.get("variations") or []

    if not variations:
        raise HTTPException(status_code=400, detail="variations 不能为空")
    if not common_script and not all(v.get("script_text") for v in variations):
        raise HTTPException(
            status_code=400,
            detail="common_script_text 或每个 variation.script_text 至少要有一个",
        )
    if common_duration not in (30, 60, 180, 300):
        raise HTTPException(
            status_code=400, detail="common_target_duration 必须是 30/60/180/300"
        )
    if max_concurrent < 1 or max_concurrent > 3:
        raise HTTPException(
            status_code=400, detail="max_concurrent 必须在 1-3 (考虑服务器性能)"
        )
    if len(variations) > 100:
        raise HTTPException(
            status_code=400, detail=f"variations 上限 100 (当前 {len(variations)})"
        )

    batch_id = str(_uuid.uuid4())

    # 一次性建 batch + N 个 project + N 个 task
    new_projects = []
    for i, var in enumerate(variations):
        if not var.get("candidate_clip_ids"):
            raise HTTPException(
                status_code=400, detail=f"variation {i} 缺 candidate_clip_ids"
            )

        var_script = (var.get("script_text") or common_script).strip()
        var_duration = int(var.get("target_duration_seconds") or common_duration)
        var_name = var.get("name") or f"{name} #{i + 1}"

        if var_duration not in (30, 60, 180, 300):
            raise HTTPException(
                status_code=400,
                detail=f"variation {i} target_duration_seconds 必须是 30/60/180/300",
            )
        if not var_script:
            raise HTTPException(status_code=400, detail=f"variation {i} 缺 script_text")

        pid = str(_uuid.uuid4())
        tid = str(_uuid.uuid4())
        new_projects.append(
            {
                "id": pid,
                "name": var_name,
                "script": var_script,
                "duration": var_duration,
                "clips": var["candidate_clip_ids"],
                "task_id": tid,
                "desc": f"批量 #{i + 1}/{len(variations)}: AI 混剪 {len(var['candidate_clip_ids'])} 素材, 目标 {var_duration}s",
            }
        )

    # 写 db (一次性 commit)
    batch = MixBatch(
        id=batch_id,
        name=name,
        description=payload.get("description", ""),
        common_script_text=common_script,
        common_target_duration=common_duration,
        variations=variations,
        max_concurrent=max_concurrent,
        status="pending",
        total_count=len(new_projects),
        completed_count=0,
        failed_count=0,
    )
    db.add(batch)

    for p in new_projects:
        db.add(
            MixProject(
                id=p["id"],
                name=p["name"],
                status="pending",
                script_text=p["script"],
                target_duration_seconds=p["duration"],
                batch_id=batch_id,
            )
        )
        db.add(
            MixTask(
                id=p["task_id"],
                mix_project_id=p["id"],
                task_type="mix_processing",
                name=p["name"],
                description=p["desc"],
                status="pending",
                progress=0,
                current_step="等待 worker 启动",
            )
        )

    await db.commit()

    # 派 celery tasks (依次派, 不并发派避免 Redis pipeline 压力)
    # v2.2.24: 用 dispatch_mix_task 走 db=0 broker (跟 mix worker 一致)
    from ..services.mix_dispatch import dispatch_mix_task

    dispatched = 0
    for p in new_projects:
        try:
            dispatch_mix_task(
                mix_project_id=p["id"],
                script_text=p["script"],
                target_duration_seconds=p["duration"],
                candidate_clip_ids=p["clips"],
                task_id=p["task_id"],
            )
            dispatched += 1
        except Exception as e:
            logger.exception(f"派发批量 task 失败: {e}")

    logger.info(
        f"批量混剪已派发: batch_id={batch_id}, total={len(new_projects)}, dispatched={dispatched}"
    )

    return {
        "batch_id": batch_id,
        "name": name,
        "total_count": len(new_projects),
        "max_concurrent": max_concurrent,
        "dispatched": dispatched,
        "projects": [
            {"project_id": p["id"], "task_id": p["task_id"], "name": p["name"]}
            for p in new_projects
        ],
    }


@router.get("/batch")
async def list_mix_batches(
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_mix_db),
):
    """批量混剪批次列表"""
    query = select(MixBatch).order_by(MixBatch.created_at.desc()).limit(100)
    result = await db.execute(query)
    batches = result.scalars().all()
    items = []
    for b in batches:
        items.append(
            {
                "id": b.id,
                "name": b.name,
                "status": b.status,
                "total_count": b.total_count,
                "completed_count": b.completed_count,
                "failed_count": b.failed_count,
                "max_concurrent": b.max_concurrent,
                "created_at": b.created_at.isoformat() if b.created_at else None,
                "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            }
        )
    return {"batches": items}


@router.get("/batch/{batch_id}")
async def get_mix_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_mix_db),
):
    """批量混剪详情 + 所有子项目状态"""
    result = await db.execute(select(MixBatch).where(MixBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")

    # 查 N 个子项目 + 最新 task
    result = await db.execute(
        select(MixProject)
        .where(MixProject.batch_id == batch_id)
        .order_by(MixProject.created_at)
    )
    projects = result.scalars().all()

    items = []
    for p in projects:
        result = await db.execute(select(MixTask).where(MixTask.mix_project_id == p.id))
        task = result.scalar_one_or_none()
        items.append(
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "video_size": p.video_size,
                "video_duration": p.video_duration,
                "thumbnail_path": p.thumbnail_path,
                "output_video_path": p.output_video_path,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                "task": {
                    "progress": task.progress if task else 0,
                    "current_step": task.current_step if task else "",
                    "status": task.status if task else "pending",
                    "error_message": task.error_message if task else "",
                }
                if task
                else None,
            }
        )

    return {
        "id": batch.id,
        "name": batch.name,
        "description": batch.description,
        "status": batch.status,
        "total_count": batch.total_count,
        "completed_count": batch.completed_count,
        "failed_count": batch.failed_count,
        "max_concurrent": batch.max_concurrent,
        "common_script_text": batch.common_script_text,
        "common_target_duration": batch.common_target_duration,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "projects": items,
    }


@router.delete("/batch/{batch_id}")
async def cancel_mix_batch(
    batch_id: str,
    db: AsyncSession = Depends(get_mix_db),
):
    """取消批量混剪 — revoke 未跑的 task, 已跑的不停

    已跑的 task 占用 worker 资源, 强行 revoke 会失败 (worker 正在跑).
    pending 状态的 task 可以 revoke 让 worker 跳过.
    """
    result = await db.execute(select(MixBatch).where(MixBatch.id == batch_id))
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="批次不存在")
    if batch.status == "completed":
        raise HTTPException(status_code=409, detail="批次已完成, 无需取消")

    # revoke 所有 pending 状态的 MixTask (已 running 的不 revoke, 让它跑完自然失败)
    from ..core.celery_app import celery_app

    revoked = 0
    result = await db.execute(
        select(MixTask)
        .join(MixProject, MixTask.mix_project_id == MixProject.id)
        .where(MixProject.batch_id == batch_id)
    )
    tasks = result.scalars().all()
    for task in tasks:
        if task.status == "pending" and task.celery_task_id:
            try:
                celery_app.control.revoke(task.celery_task_id, terminate=False)
                revoked += 1
            except Exception:
                pass
        elif task.status == "pending":
            task.status = "failed"
            task.error_message = "batch 取消"
            revoked += 1

    # 把 batch 标 cancelled
    batch.status = "cancelled"
    batch.completed_at = datetime.utcnow()
    await db.commit()

    return {
        "batch_id": batch_id,
        "status": "cancelled",
        "revoked_tasks": revoked,
    }


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
        segments_info.append(
            {
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
            }
        )

    latest = (
        max(project.tasks, key=lambda t: t.created_at, default=None)
        if project.tasks
        else None
    )

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
        "completed_at": project.completed_at.isoformat()
        if project.completed_at
        else None,
        "task": {
            "progress": latest.progress if latest else 0,
            "current_step": latest.current_step if latest else "",
            "status": latest.status if latest else "pending",
            "error_message": latest.error_message if latest else "",
            "created_at": latest.created_at.isoformat()
            if latest and latest.created_at
            else None,
            "started_at": latest.started_at.isoformat()
            if latest and latest.started_at
            else None,
            "completed_at": latest.completed_at.isoformat()
            if latest and latest.completed_at
            else None,
        }
        if latest
        else None,
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


@router.get("/thumbnails/{project_id}")
async def get_mix_thumbnail(project_id: str):
    """返回混剪项目缩略图 (v2.2.4 list card 用)

    路径: data/projects/<mix_project_id>/output/thumbnail.jpg
    生成于 processing_mix 烧字幕完的 ffmpeg -ss 1s -frames:v 1
    """
    mix_projects_root = Path("data/projects").resolve()
    thumb_path = mix_projects_root / project_id / "output" / "thumbnail.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="缩略图未生成")
    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete("/{project_id}")
async def delete_mix_project(
    project_id: str,
    db: AsyncSession = Depends(get_mix_db),
):
    """软删除"""
    result = await db.execute(select(MixProject).where(MixProject.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Mix project not found")
    if project.status == "processing":
        raise HTTPException(status_code=409, detail="处理中的混剪不能删除")

    project.deleted_at = datetime.utcnow()
    await db.commit()
    return {"id": project_id, "deleted": True}


# ──────────────────────────── v2.2.5: AI 帮写脚本 ────────────────────────────


@router.post("/ai-help-write")
async def ai_help_write_script_endpoint(payload: dict = Body(...)):
    """v2.2.5: AI 帮写带货脚本 (wizard Step 1 ✨ 按钮)

    输入:
        topic: str (可选) 用户输入的产品/主题方向, 留空时由 LLM 从素材库推断
        clips_context: [{title, source_project_name?, subtitle_text?}, ...] 候选素材标题片段
        target_duration_seconds: int (默认 60) 目标时长秒

    输出:
        {script_text: "...", model: "..."}

    失败 (LLM API key 缺失 / 网络异常 / 空响应) 返回 500 + 中文原因.
    """
    from ..services.mix_service import ai_help_write_script

    topic = payload.get("topic") or ""
    clips_context = payload.get("clips_context") or []
    target_duration = int(payload.get("target_duration_seconds") or 60)

    try:
        return ai_help_write_script(
            topic=topic,
            clips_context=clips_context,
            target_duration=target_duration,
        )
    except Exception as e:
        logger.exception(f"AI 帮写脚本失败: {e}")
        raise HTTPException(status_code=500, detail=f"AI 帮写失败: {str(e)[:300]}")


# ──────────────────────────── v2.2.35: 脚本分段预览 ────────────────────────────


@router.post("/parse-script")
async def parse_script_endpoint(payload: dict = Body(...)):
    """v2.2.35: LLM 解析脚本分段 (wizard Step 1 实时预览)

    输入:
        script_text: str 直播脚本
        target_duration_seconds: int (默认 60) 目标时长

    输出:
        {segments: [{position, text, keywords}, ...], model: "..."}

    失败返 500 + 中文原因. 跟 POST /mix 内部的 parse_script 一样, 但单独暴露让前端 preview 调.
    """
    from ..services.mix_service import parse_script

    script_text = payload.get("script_text", "")
    target_duration = int(payload.get("target_duration_seconds") or 60)

    if not script_text.strip():
        raise HTTPException(status_code=400, detail="script_text 不能为空")

    try:
        segments = parse_script(
            script_text=script_text, target_duration=target_duration
        )
        if not segments:
            raise HTTPException(status_code=500, detail="LLM 解析脚本失败, 返空")
        return {"segments": segments, "count": len(segments)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"parse-script 失败: {e}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)[:300]}")


# ──────────────────────────── v2.2.41: 按段预选预览 (Step 2) ────────────────────────────


@router.post("/preview-match")
async def preview_match_endpoint(payload: dict = Body(...)):
    """v2.2.41: Step 2 按段预选 — 每段给 top-N matched clips

    输入:
        segments: [{position, text, keywords}, ...]  来自 /parse-script
        candidate_clip_ids: list[str]  候选 source clip (从 /mix/clips/library 拿)
        top_n: int (默认 3) 每段返 top-N
        target_duration: int (默认 60)

    输出:
        {previews: [{position, top_clips: [{clip_id, title, project_name, duration,
                                            match_score, matched_keywords}, ...]}, ...]}

    不写 db, 不派 task, 纯计算. Step 2 用户界面: "段 0 屋顶/外墙/阳台" → 显示 top-3 缩略图,
    自动勾选 top-1, user 可改选.

    比 match_clips_for_segments 简化: 不算 embed (避免 100+ log 噪音), 纯 tag overlap substring
    (跟 v2.2.36 substring 公式一致, score 0.0-1.0). matched_keywords 列出该 clip 命中了哪些 kw,
    UI 标绿让 user 知道为什么这个 clip 排第一.
    """
    from ..services.mix_service import build_clip_library_from_slice_db

    segments = payload.get("segments") or []
    candidate_clip_ids = payload.get("candidate_clip_ids") or []
    top_n = int(payload.get("top_n") or 3)
    target_duration = int(payload.get("target_duration") or 60)

    if not segments:
        raise HTTPException(status_code=400, detail="segments 不能为空")
    if not candidate_clip_ids:
        raise HTTPException(status_code=400, detail="candidate_clip_ids 不能为空")

    # 加载候选库
    clip_library = build_clip_library_from_slice_db(candidate_clip_ids)
    if not clip_library:
        return {"previews": [], "warning": "素材库为空, 跑完批量入库后重试"}

    def _tag_overlap_substring(seg_keywords, clip_tags):
        """v2.2.36 substring 公式 (client-side 简化版, 跟 backend 一致)"""
        kw_norm = {k.strip().lower() for k in (seg_keywords or []) if k and k.strip()}
        ct_norm = {
            t.strip().lower()
            for t in (clip_tags or [])
            if isinstance(t, str) and t.strip()
        }
        if not kw_norm or not ct_norm:
            return 0.0, []
        hits = []
        for kw in kw_norm:
            for ct in ct_norm:
                if kw == ct or kw in ct or ct in kw:
                    hits.append(kw)
                    break
        return (len(hits) / len(kw_norm)) if kw_norm else 0.0, hits

    previews = []
    for seg in segments:
        seg_kw = seg.get("keywords", [])
        scored = []
        for clip in clip_library:
            score, hits = _tag_overlap_substring(seg_kw, clip.get("tags") or [])
            if score < 0.05:  # 0 阈值跟 v2.2.33 一致
                continue
            scored.append(
                {
                    "clip_id": clip["clip_id"],
                    "title": clip.get("title", ""),
                    "source_project_name": clip.get("source_project_name", ""),
                    "duration": clip.get("duration", 0),
                    "match_score": round(score, 3),
                    "matched_keywords": hits,
                }
            )
        scored.sort(key=lambda x: -x["match_score"])
        previews.append(
            {
                "position": seg.get("position"),
                "text": seg.get("text", ""),
                "keywords": seg_kw,
                "top_clips": scored[:top_n],
            }
        )

    return {"previews": previews}


# ──────────────────────────── v2.2.4: 风险词检测 ────────────────────────────


@router.post("/script-risk-check")
async def check_script_risk_endpoint(payload: dict = Body(...)):
    """扫描脚本中的抖音直播违规词 + 广告法敏感词

    输入: {"script_text": "..."} 或 {"segments": [{"text": "..."}, ...]}
    输出: {"total_risk_count", "has_risk", "level": "none/low/medium/high", "hits": [...], "version"}

    不阻止提交, 仅警告. user 可强制提交 (自己负责).
    """
    text = payload.get("script_text", "")
    segments = payload.get("segments") or []

    if not text and not segments:
        raise HTTPException(
            status_code=400, detail="script_text 或 segments 至少传一个"
        )

    # 多段合并: segment_text 用换行隔开
    if not text and segments:
        text = "\n".join(
            str(s.get("text", "") if isinstance(s, dict) else s) for s in segments
        )

    return check_script_risk(text)
