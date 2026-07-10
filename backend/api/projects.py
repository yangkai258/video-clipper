# -*- coding: utf-8 -*-
"""项目 API 路由"""

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, select as sa_select
from sqlalchemy.orm import selectinload

from ..core.database import get_db, to_iso_utc
from ..core.config import settings
from ..models.database import Project, Task, Clip, Collection, UserPreference, Style
from ..services.subtitle_preferences import (
    DEFAULT_SUBTITLE_STYLE,
    get_last_subtitle_style,
    sync_subtitle_style_to_preferences,
)


router = APIRouter()
logger = logging.getLogger(__name__)


# 进度估算的典型切片数（用于"切割中"进度的近似计算）
TYPICAL_CLIP_COUNT = 162
TYPICAL_COLLECTION_COUNT = 21

# 项目允许触发的状态集合（pending 新建 / failed 失败重试 / processing 主动重置）
RESTARTABLE_STATUSES = {"pending", "failed", "processing"}
# 视频文件最小大小（< 1MB 视作上传未完成）
MIN_VIDEO_SIZE_BYTES = 1024 * 1024


# ───────────────────────── 公开 API ─────────────────────────


# v2.2.1 fix: /trash 和 /trash/all 必须注册在 /{project_id} 之前, 否则
# FastAPI/Starlette 路由按注册顺序匹配, DELETE /trash 会被 DELETE /{project_id}
# (project_id="trash") 截胡 → 404 "Project not found"
# 同理 DELETE /trash/all 会被 DELETE /{project_id}/restore 等截胡 (但目前还没踩到,
# 因为 Starlette 会先精确匹配 "/trash/all" 字面量再 fallback 到 path param)
@router.delete("/trash")
async def cleanup_trash(days: int = Query(default=30), db: AsyncSession = Depends(get_db)):
    """清理 N 天前的已删除项目（软删 → 硬删）"""
    threshold = datetime.utcnow() - timedelta(days=days)
    result = await db.execute(
        select(Project).where(
            Project.deleted_at.is_not(None),
            Project.deleted_at < threshold,
        )
    )
    stale = result.scalars().all()
    for p in stale:
        await db.delete(p)
    await db.commit()
    return {"message": f"已清理 {len(stale)} 个项目", "count": len(stale)}


@router.delete("/trash/all")
async def purge_all_trash(db: AsyncSession = Depends(get_db)):
    """清空整个回收站（不可恢复）"""
    result = await db.execute(select(Project).where(Project.deleted_at.is_not(None)))
    stale = result.scalars().all()
    for p in stale:
        await db.delete(p)
    await db.commit()
    return {"message": f"已清空 {len(stale)} 个项目", "count": len(stale)}


@router.get("/")
async def list_projects(
    include_deleted: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """列出项目（默认不含已删除）"""
    query = (
        select(Project)
        .options(selectinload(Project.tasks))
    )
    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))
    query = query.order_by(Project.created_at.desc())

    result = await db.execute(query)
    projects = result.scalars().all()

    project_list = []
    # v2.2.1: 一次性批量查 Style 表, 给所有有 style_id 的 project 填 style_name
    # 老项目可能 processing_config 里存了 style_id 但没存 strategy_name (老 config 模板),
    # 查 Style 表补上
    from ..models.database import Style
    style_ids = {cfg.get("style_id") for cfg in (p.processing_config or {} for p in projects) if cfg.get("style_id")}
    style_map = {}
    if style_ids:
        result = await db.execute(select(Style).where(Style.id.in_(style_ids)))
        for s in result.scalars().all():
            style_map[s.id] = s.name

    # v2.2.2: 批量查 clip_count (group by project_id), 避免 N+1
    # ProjectCard 显示 "切片 N" 用这个字段 (之前 list_projects 没返, UI 永远 0)
    from ..models.database import Clip
    from sqlalchemy import func
    project_ids = [p.id for p in projects]
    clip_counts: dict = {}
    if project_ids:
        result = await db.execute(
            select(Clip.project_id, func.count(Clip.id))
            .where(Clip.project_id.in_(project_ids))
            .group_by(Clip.project_id)
        )
        clip_counts = dict(result.all())

    for p in projects:
        latest = _latest_task(p.tasks)
        # 只暴露 ProjectCard 用的 task 字段 (progress / current_step / timing)
        # status / started_at 仍来自 project,避免重名覆盖
        task_fields = {}
        if latest:
            td = _task_to_dict(latest, p.video_duration)
            task_fields = {
                "progress": td.get("progress", 0),
                "current_step": td.get("current_step"),
                # v2.2.1: 预估/实际归集字段透出, 后续做更好预估模型
                "estimated_total_at_start_seconds": td.get("estimated_total_at_start_seconds"),
                "actual_total_seconds": td.get("actual_total_seconds"),
                "timing": {
                    "elapsed_seconds": td.get("elapsed_seconds", 0),
                    "eta_seconds": td.get("eta_seconds"),
                    "total_estimated_seconds": td.get("total_estimated_seconds"),
                },
            }
        # v2.2.1: 从 processing_config 提 style_id / style_name / target_duration /
        # max_clips / with_subtitle / output_format。ProjectCard 用 style_name 显示
        # 风格 (用户选了"电影切片"而不是默认), 字幕用 with_subtitle 文字显示。
        cfg = p.processing_config or {}
        style_id = cfg.get("style_id")
        # 老 config 可能只存 style_id 没存 strategy_name, 用 style_map 补
        style_name = cfg.get("strategy_name") or style_map.get(style_id)
        project_list.append({
            "id": p.id,
            "name": p.name,
            "status": p.status,
            "video_size": p.video_size,
            "video_duration": p.video_duration,
            "created_at": to_iso_utc(p.created_at),
            "deleted_at": to_iso_utc(p.deleted_at),
            # v2.2.2: clip_count (clips 表 group by count) — ProjectCard 显示用
            "clip_count": clip_counts.get(p.id, 0),
            # 风格信息 (ProjectCard 显示用)
            "style_id": style_id,
            "style_name": style_name,
            "target_duration": cfg.get("target_duration"),
            "max_clips": cfg.get("max_clips"),
            # 字幕 + 输出格式
            "has_subtitle": cfg.get("with_subtitle", False),
            "output_format": cfg.get("output_format"),
            # v2.2.1: 前/后置 padding (cut_clips 时给每个 clip 边界外扩几秒)
            "pre_padding_seconds": cfg.get("pre_padding_seconds", 0),
            "post_padding_seconds": cfg.get("post_padding_seconds", 0),
            **task_fields,
        })
    return {"projects": project_list}


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目详情（包含 clips/collections/tasks 的完整快照）"""
    project = await _load_project_full(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    style_overrides = await _resolve_style(project, db)
    latest_task = _latest_task(project.tasks)

    return {
        "project": {
            **_project_summary(project),
            **style_overrides,
            "task": _task_to_dict(latest_task, project.video_duration) if latest_task else None,
            "clips": [_clip_to_dict(c) for c in project.clips],
            "collections": [_collection_to_dict(col) for col in project.collections],
        }
    }


@router.post("/")
async def create_project(
    name: str = Form(...),
    description: str = Form(default=""),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """创建新项目并上传视频"""
    _validate_video_extension(video.filename)
    project_id = str(uuid.uuid4())
    video_size = await _save_uploaded_video(project_id, video)
    subtitle_style = await get_last_subtitle_style(db)
    project = await _create_project_record(db, project_id, name, description, video_size, subtitle_style)
    return {
        "message": "项目创建成功",
        "project_id": project.id,
        "name": project.name,
        "video_size": video_size,
    }


@router.post("/{project_id}/process")
async def start_processing(project_id: str, db: AsyncSession = Depends(get_db)):
    """开始处理项目

    流程：
    1. 校验项目状态（必须是 pending/failed/processing）
    2. 如果是 processing，先取消旧 task + 标 cancelled
    3. 校验视频文件存在 + 大小
    4. 写 project.status = processing + 创建 Task 记录
    5. 提交 celery 任务
    """
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _ensure_status_restartable(project)

    if project.status == "processing":
        await _revoke_existing_tasks(db, project_id)

    video_path = settings.PROJECTS_DIR / project.video_path
    _ensure_video_file_exists(video_path)

    project.status = "processing"
    await db.commit()

    task = await _create_processing_task(db, project_id)
    celery_task_id = _dispatch_celery_task(project_id, video_path, project.subtitle_path, task.id)
    task.celery_task_id = celery_task_id
    task.status = "running"
    await db.commit()

    return {
        "message": "处理已开始",
        "project_id": project_id,
        "task_id": task.id,
        "celery_task_id": celery_task_id,
    }


@router.post("/{project_id}/rerun")
async def rerun_project(
    project_id: str,
    config: dict = None,
    db: AsyncSession = Depends(get_db),
):
    """v2.2.1: 重新处理项目 (复用 raw, 改 with_subtitle/output_format/style/padding)

    流程：
    1. 校验项目存在 + raw 视频在 (raw 没保留就 422, 提示重传)
    2. 应用 config overrides (with_subtitle / output_format / style_id / padding)
    3. 清 output/clips + output/collections + output/thumbnails + metadata/step*.json
       (input.srt 留, 但 rerun_all 也会重新生成 step 1; 留了不影响)
    4. 重置 project.status = pending
    5. 复用 start_processing 流程: 标 processing + dispatch celery
    """
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    video_path = settings.PROJECTS_DIR / project.video_path
    if not video_path.exists():
        # v2.2.1: 友好提示 — raw 没保留就要重传
        raise HTTPException(
            status_code=422,
            detail=f"原视频已清理（未启用「保留 raw」），无法重新处理。请重新上传视频。",
        )

    # 应用 config overrides (跟 update_project_config 一样, 但不强制 style_id 触发 padding snapshot)
    overrides = config or {}
    current_cfg = dict(project.processing_config or {})
    current_cfg.update(overrides)
    # style_id override 时, 从 Style 表 snapshot 当前 padding (跟 update_project_config 一致)
    if overrides.get("style_id"):
        style_result = await db.execute(select(Style).where(Style.id == overrides["style_id"]))
        s = style_result.scalar_one_or_none()
        if s:
            if "pre_padding_seconds" not in overrides:
                current_cfg["pre_padding_seconds"] = s.pre_padding_seconds
            if "post_padding_seconds" not in overrides:
                current_cfg["post_padding_seconds"] = s.post_padding_seconds
    project.processing_config = current_cfg
    project.updated_at = datetime.utcnow()
    await db.commit()

    # 清 output + metadata/step*.json (重跑会重新生成)
    project_dir = settings.PROJECTS_DIR / project_id
    for sub in ("output/clips", "output/collections", "output/thumbnails", "metadata"):
        target = project_dir / sub
        if target.exists():
            import shutil
            if target.is_dir():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)
    # 重建目录 (后续 step 7/8/10 要写)
    (project_dir / "output" / "clips").mkdir(parents=True, exist_ok=True)
    (project_dir / "output" / "collections").mkdir(parents=True, exist_ok=True)
    (project_dir / "output" / "thumbnails").mkdir(parents=True, exist_ok=True)
    (project_dir / "metadata").mkdir(parents=True, exist_ok=True)

    # 重置 status -> pending, 复用 start_processing 流程
    project.status = "pending"
    await db.commit()

    # 走 start_processing 主流程
    return await start_processing(project_id, db)
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    _ensure_status_restartable(project)

    if project.status == "processing":
        await _revoke_existing_tasks(db, project_id)

    video_path = settings.PROJECTS_DIR / project.video_path
    _ensure_video_file_exists(video_path)

    project.status = "processing"
    await db.commit()

    task = await _create_processing_task(db, project_id)
    celery_task_id = _dispatch_celery_task(project_id, video_path, project.subtitle_path, task.id)
    task.celery_task_id = celery_task_id
    task.status = "running"
    await db.commit()

    return {
        "message": "处理已开始",
        "project_id": project_id,
        "task_id": task.id,
        "celery_task_id": celery_task_id,
    }


@router.put("/{project_id}/config")
async def update_project_config(
    project_id: str,
    config: dict,
    db: AsyncSession = Depends(get_db),
):
    """更新项目处理配置（如切片策略）"""
    from ..models.database import Style
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # v2.2.1: 如果传了 style_id, 自动从 Style 表复制 pre/post_padding snapshot
    # 到 processing_config。这样切的时候读 snapshot, 跟当前 style 表解耦
    # (用户改 style padding 不会影响已经在跑的 task)
    merged_config = {**project.processing_config, **config}
    if config.get("style_id"):
        style_result = await db.execute(select(Style).where(Style.id == config["style_id"]))
        s = style_result.scalar_one_or_none()
        if s:
            # 只在 client 没显式传 padding 时才覆盖 (避免 client 显式 override 时被吞)
            if "pre_padding_seconds" not in config:
                merged_config["pre_padding_seconds"] = s.pre_padding_seconds
            if "post_padding_seconds" not in config:
                merged_config["post_padding_seconds"] = s.post_padding_seconds

    project.processing_config = merged_config
    project.updated_at = datetime.utcnow()

    if config.get("subtitle_style"):
        await sync_subtitle_style_to_preferences(db, config["subtitle_style"])

    await db.commit()
    await db.refresh(project)
    return {
        "message": "配置已更新",
        "processing_config": project.processing_config,
    }


@router.get("/{project_id}/file")
async def get_project_file(project_id: str, db: AsyncSession = Depends(get_db)):
    """下载项目原始视频"""
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    file_path = settings.PROJECTS_DIR / project.video_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path=str(file_path), filename=file_path.name)


@router.get("/{project_id}/files/{file_path:path}")
async def get_project_file_path(project_id: str, file_path: str, db: AsyncSession = Depends(get_db)):
    """获取项目内任意文件 (clips, subtitles, thumbnails)。

    v2.1.53: 4afb777 refactor 漏掉了这个 endpoint, 导致前端
    `ClipCard.jsx` 加载 clip 视频 src 404。
    修法: 解析 file_path 在 project_dir 内, 防 path traversal,
    返 FileResponse + Accept-Ranges bytes 让浏览器可 seek。
    """
    from urllib.parse import quote

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")

    project_dir = (settings.PROJECTS_DIR / project_id).resolve()
    full_path = (project_dir / file_path).resolve()
    try:
        full_path.relative_to(project_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden: path outside project directory")

    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # 根据扩展名给 media_type
    suffix = full_path.suffix.lower()
    media_type = {
        ".mp4": "video/mp4",
        ".srt": "application/x-subrip",
        ".vtt": "text/vtt",
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")

    encoded_filename = quote(full_path.name)
    return FileResponse(
        str(full_path),
        media_type=media_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
            "Accept-Ranges": "bytes",
        },
    )


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """软删除（标 deleted_at）"""
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    project.deleted_at = datetime.utcnow()
    await db.commit()
    return {"message": "项目已移入回收站", "project_id": project_id}


@router.post("/{project_id}/restore")
async def restore_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """从回收站恢复"""
    project = await _load_project_basic(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.deleted_at is None:
        raise HTTPException(status_code=400, detail="项目未被删除")

    project.deleted_at = None
    await db.commit()
    return {"message": "项目已恢复", "project_id": project_id}


# ───────────────────────── 进度/时间辅助 ─────────────────────────


def _build_timing_info(task: Task, video_duration_seconds: float = None) -> dict:
    """从 task 状态推算 elapsed / total / eta 秒数。"""
    if not task.started_at:
        return {"elapsed_seconds": 0, "eta_seconds": None, "total_estimated_seconds": None}

    now = datetime.utcnow()
    elapsed = (now - task.started_at).total_seconds()

    if task.status == "completed":
        total = (task.completed_at - task.started_at).total_seconds() if task.completed_at else elapsed
        return {"elapsed_seconds": int(elapsed), "eta_seconds": 0, "total_estimated_seconds": int(total)}

    if task.status == "running" and task.progress and task.progress > 0:
        total_estimated = elapsed / (task.progress / 100)
        eta = max(0, total_estimated - elapsed)
        return {
            "elapsed_seconds": int(elapsed),
            "eta_seconds": int(eta),
            "total_estimated_seconds": int(total_estimated),
        }

    # pending / failed / 进度为 0 → 用典型切片数估算
    estimated = _estimate_eta_seconds(video_duration_seconds)
    return {
        "elapsed_seconds": int(elapsed),
        "eta_seconds": int(estimated),
        "total_estimated_seconds": int(estimated + elapsed),
    }


def _estimate_eta_seconds(video_duration_seconds: float = None) -> int:
    """用典型切片数 + 时长估算总耗时（仅用于进度条 ETA 显示）。"""
    base = 60
    if video_duration_seconds and video_duration_seconds > 0:
        base += int(video_duration_seconds / 60) * 5
    return base


# ───────────────────────── 样式解析 ─────────────────────────


async def _resolve_style(project: Project, db: AsyncSession) -> dict:
    """解析项目当前样式：项目内 processing_config > 用户偏好 > 默认"""
    config_style = (project.processing_config or {}).get("subtitle_style")
    if config_style:
        return {"subtitle_style": config_style, "style_source": "project_config"}

    pref_style = await get_last_subtitle_style(db)
    if pref_style:
        return {"subtitle_style": pref_style, "style_source": "user_preference"}

    return {"subtitle_style": DEFAULT_SUBTITLE_STYLE, "style_source": "default"}


# ───────────────────────── 内部 DB 操作 ─────────────────────────


async def _load_project_basic(db: AsyncSession, project_id: str) -> Project | None:
    """加载项目基本字段（不含关联表）。"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    return result.scalar_one_or_none()


async def _load_project_full(db: AsyncSession, project_id: str) -> Project | None:
    """加载项目完整快照（含 clips/collections/tasks）。"""
    result = await db.execute(
        select(Project)
        .options(
            selectinload(Project.clips),
            selectinload(Project.collections),
            selectinload(Project.tasks),
        )
        .where(Project.id == project_id)
    )
    return result.scalar_one_or_none()


async def _revoke_existing_tasks(db: AsyncSession, project_id: str) -> None:
    """取消项目中所有 running/pending 的 celery task。"""
    from ..core.celery_app import celery_app  # 局部导入：celery 启动慢

    old_tasks = (
        await db.execute(
            sa_select(Task).where(
                Task.project_id == project_id,
                Task.status.in_(["pending", "running"]),
            )
        )
    ).scalars().all()

    for old in old_tasks:
        if old.celery_task_id:
            try:
                celery_app.control.revoke(old.celery_task_id, terminate=False)
            except Exception as ex:
                logger.warning(f"revoke {old.celery_task_id} 失败: {ex}")
        old.status = "failed"
        old.error_message = "用户主动重新处理, 旧任务已取消"
        old.completed_at = datetime.utcnow()
    await db.commit()
    logger.info(f"项目 {project_id} 重置: 取消 {len(old_tasks)} 个旧 task")


def _ensure_status_restartable(project: Project) -> None:
    """校验项目状态可触发处理。"""
    if project.status not in RESTARTABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"项目状态不允许处理：{project.status}",
        )


def _ensure_video_file_exists(video_path: Path) -> None:
    """校验视频文件存在 + 大小足够。"""
    if not video_path.exists():
        logger.error(f"视频文件不存在：{video_path.absolute()}")
        raise HTTPException(status_code=404, detail="Video file not found")

    video_size = video_path.stat().st_size
    if video_size < MIN_VIDEO_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"视频文件过小 ({video_size} bytes / 0 MB), 上传可能未完成. 请重新上传完整视频.",
        )


async def _create_processing_task(db: AsyncSession, project_id: str) -> Task:
    """创建视频处理任务的 Task 记录。"""
    # v2.2.1: 启动时存 estimated_total, 后续数据归集得更好预估模型
    # progress=0 时一次性算, 不被 progress 涨影响 (避免归集时被
    # "中途被调过" 的 total_estimated_seconds 干扰)
    project = await _load_project_basic(db, project_id)
    estimated_total = _estimate_eta_seconds(project.video_duration if project else None)

    task = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        task_type="video_processing",
        name="视频处理流水线",
        status="pending",
        estimated_total_at_start_seconds=estimated_total,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


def _dispatch_celery_task(
    project_id: str,
    video_path: Path,
    subtitle_path: Optional[str],
    task_id: str,
) -> str:
    """提交 celery 任务，返回 celery_task_id。"""
    from ..core.celery_app import celery_app  # 局部导入：celery 启动慢

    srt_path = None
    if subtitle_path:
        srt_path = str(settings.PROJECTS_DIR / subtitle_path)

    celery_task = celery_app.send_task(
        "backend.tasks.processing.process_video_pipeline",
        args=[project_id, str(video_path), srt_path, task_id],
    )
    return celery_task.id


# ───────────────────────── 视频上传 / 项目创建 ─────────────────────────


def _validate_video_extension(filename: str) -> None:
    """校验视频扩展名。"""
    ext = filename.split(".")[-1].lower()
    if not settings.is_allowed_video_ext(ext):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式：{ext}。支持的格式：{[e.lstrip('.') for e in settings.ALLOWED_VIDEO_EXTENSIONS]}",
        )


async def _save_uploaded_video(project_id: str, video: UploadFile) -> int:
    """流式保存上传视频到项目目录。返回字节数。"""
    project_dir = settings.PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    video_path = project_dir / "raw" / "input.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)

    video_size = 0
    with open(video_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):  # 1MB chunks
            f.write(chunk)
            video_size += len(chunk)
    return video_size


async def _create_project_record(
    db: AsyncSession,
    project_id: str,
    name: str,
    description: str,
    video_size: int,
    subtitle_style: dict | None,
) -> Project:
    """写入 Project ORM 记录。"""
    video_path = settings.PROJECTS_DIR / project_id / "raw" / "input.mp4"
    project = Project(
        id=project_id,
        name=name,
        description=description,
        status="pending",
        video_path=str(video_path.relative_to(settings.PROJECTS_DIR)),
        video_size=video_size,
        processing_config={"subtitle_style": subtitle_style} if subtitle_style else {},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


# ───────────────────────── 序列化辅助 ─────────────────────────


def _project_summary(project: Project) -> dict:
    """Project ORM → API 返回 dict（不含 clips/collections/task）。"""
    return {
        "id": project.id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "video_path": project.video_path,
        "video_duration": project.video_duration,
        "video_size": project.video_size,
        # v2.1.26: 让前端区分横/竖屏
        "video_width": project.video_width,
        "video_height": project.video_height,
        "subtitle_path": project.subtitle_path,
        "processing_config": project.processing_config,
        "created_at": to_iso_utc(project.created_at),
        "completed_at": to_iso_utc(project.completed_at),
        "deleted_at": to_iso_utc(project.deleted_at),
    }


def _task_to_dict(task: Task, video_duration_seconds: float = None) -> dict:
    """Task ORM → API 返回 dict（含 timing_info）。"""
    return {
        "status": task.status,
        "progress": task.progress,
        "current_step": task.current_step,
        "error_message": task.error_message,
        "started_at": to_iso_utc(task.started_at),
        "completed_at": to_iso_utc(task.completed_at),
        # v2.2.1: 预估 vs 实际归集 — estimated_total_at_start_seconds 是启动时
        # 一次性算的 (不被 progress 涨影响), actual_total_seconds 是完成后
        # (completed_at - started_at) 的真实秒数。后续做预估模型直接用这俩。
        "estimated_total_at_start_seconds": task.estimated_total_at_start_seconds,
        "actual_total_seconds": task.actual_total_seconds,
        **_build_timing_info(task, video_duration_seconds),
    }


def _clip_to_dict(clip: Clip) -> dict:
    """Clip ORM → API 返回 dict。"""
    return {
        "id": clip.id,
        "title": clip.title,
        "start_time": clip.start_time,
        "end_time": clip.end_time,
        "duration": clip.duration,
        "score": clip.score,
        "video_path": clip.video_path,
        # v2.1.26: 让前端区分横/竖屏
        "width": clip.width,
        "height": clip.height,
    }


def _collection_to_dict(col: Collection) -> dict:
    """Collection ORM → API 返回 dict。"""
    return {
        "id": col.id,
        "title": col.title,
        "clip_count": len(col.clip_ids),
        "video_path": col.video_path,
    }


def _latest_task(tasks: List[Task]) -> Task | None:
    """取最近的 task（按 created_at 最大的）。"""
    return max(tasks, key=lambda t: t.created_at, default=None) if tasks else None