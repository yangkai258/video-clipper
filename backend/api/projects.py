"""项目 API 路由"""
import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from ..core.database import get_db, to_iso_utc
from ..core.config import settings
from ..models.database import Project, Task, Clip, Collection, UserPreference, Style
from sqlalchemy.orm import selectinload


router = APIRouter()
logger = logging.getLogger(__name__)


# 进度估算的典型切片数（用于"切割中"进度的近似计算）
TYPICAL_CLIP_COUNT = 162
TYPICAL_COLLECTION_COUNT = 21


def _build_timing_info(task: Task, video_duration_seconds: float = None) -> dict:
    """从 task 状态推算 elapsed / total / eta 秒数

    返回给前端直接渲染的 dict:
    - elapsed_seconds: 已用秒数 (None 如果还没 start)
    - total_estimated_seconds: 预计总秒数 (None 如果算不出)
    - eta_seconds: 剩余秒数 (None 如果算不出)
    """
    # 已用
    if task.started_at and task.status == "running":
        elapsed = int((datetime.utcnow() - task.started_at).total_seconds())
    elif task.started_at and task.completed_at:
        elapsed = int((task.completed_at - task.started_at).total_seconds())
    else:
        elapsed = 0

    # 剩余 (核心)
    progress = task.progress or 0
    eta = _estimate_eta_seconds(progress, elapsed, video_duration_seconds)

    # 总预计 (用于显示 "预计 X 分钟")
    if eta is not None:
        total_estimated = elapsed + eta
    elif progress >= 5 and elapsed > 0:
        total_estimated = int(elapsed / (progress / 100.0))
    else:
        total_estimated = None

    return {
        "elapsed_seconds": elapsed if elapsed > 0 else None,
        "total_estimated_seconds": total_estimated,
        "eta_seconds": eta,
    }


def _estimate_eta_seconds(
    progress_pct: int,
    elapsed_seconds: int,
    video_duration_seconds: float = None,
) -> int | None:
    """估算剩余时间 (秒)

    两阶段策略:
    1. progress < 5% → 启发式: video_duration × 0.25 + 120s (whisper + LLM + 切割 + 合并)
    2. progress >= 5% → 线性外推: 总时间 = elapsed / (progress/100)

    返回 None 表示太早无法估算 (没视频时长 + progress = 0)
    """
    if elapsed_seconds <= 0:
        return None

    if progress_pct >= 5:
        # 线性外推
        total_estimated = elapsed_seconds / (progress_pct / 100.0)
        return max(0, int(total_estimated - elapsed_seconds))

    # 启发式 (progress < 5% 时不准, 用历史均值)
    if video_duration_seconds and video_duration_seconds > 0:
        # whisper base ≈ 0.25x 视频时长
        # + LLM 4 步 ≈ 60s
        # + 切割 (30 段 × 3s) ≈ 90s
        # + 合并 ≈ 30s
        # 合计 ≈ video_duration × 0.25 + 180s
        estimated_total = video_duration_seconds * 0.25 + 180
        return max(0, int(estimated_total - elapsed_seconds))

    return None


# 项目显示用的默认风格标识（DB 里没选过 style_id 时的占位）
DEFAULT_STYLE_ID = "_default"
DEFAULT_STYLE_NAME = "默认"


async def _resolve_style(project: Project, db: AsyncSession) -> dict:
    """解析项目用的风格 → {style_id, style_name, target_duration, max_clips, has_subtitle}

    优先级：
    1. processing_config.style_id 存在 → 查 Style 表
    2. 不存在或查不到 → 默认 (灰色)
    3. target_duration / max_clips：项目级 processing_config 覆盖 Style 表
    4. has_subtitle：直接读 cfg.with_subtitle（None=未设置 = 视作 False）
    """
    cfg = project.processing_config or {}
    style_id_raw = cfg.get("style_id")
    has_subtitle = bool(cfg.get("with_subtitle", False))

    if not style_id_raw:
        return {
            "style_id": DEFAULT_STYLE_ID,
            "style_name": DEFAULT_STYLE_NAME,
            "target_duration": cfg.get("target_duration"),
            "max_clips": cfg.get("max_clips"),
            "has_subtitle": has_subtitle,
        }

    result = await db.execute(select(Style).where(Style.id == style_id_raw))
    s = result.scalar_one_or_none()
    if s:
        return {
            "style_id": s.id,
            "style_name": s.name,
            "target_duration": cfg.get("target_duration", s.target_duration),
            "max_clips": cfg.get("max_clips", s.max_clips),
            "has_subtitle": has_subtitle,
        }
    # style_id 写了但 Style 已被删
    return {
        "style_id": style_id_raw,
        "style_name": "已删除",
        "target_duration": cfg.get("target_duration"),
        "max_clips": cfg.get("max_clips"),
        "has_subtitle": has_subtitle,
    }


async def _get_last_subtitle_style(db: AsyncSession) -> Optional[dict]:
    """读取用户最后使用的字幕样式偏好（异步，ORM）

    修复：原来 hardcoded `data/video_clipper.db` (release)，beta 部署时会读错库。
    现在走 ORM + 当前 db session，跨进程一致。
    """
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == "default")
    )
    pref = result.scalar_one_or_none()
    if pref and pref.last_used_subtitle_style:
        return pref.last_used_subtitle_style
    return None


def calculate_progress(project: Project) -> dict:
    """计算项目处理进度

    优先用 task 表的实时 progress + current_step (worker 每 5s 心跳写一次)
    fallback 到 clip/collection 数量估算 (老逻辑, 兼容)
    """
    if project.status == "completed":
        return {"progress": 100, "current_step": "已完成", "estimated_remaining": "0 分钟"}

    if project.status == "pending":
        return {"progress": 0, "current_step": "等待开始", "estimated_remaining": "未知"}

    if project.status == "failed":
        return {"progress": 0, "current_step": "处理失败", "estimated_remaining": "-"}

    # 优先: 用 task 表的实时进度 (v2.1.4 心跳写入)
    if project.tasks:
        latest = max(project.tasks, key=lambda t: t.created_at, default=None)
        if latest and latest.progress is not None and latest.progress > 0:
            return {
                "progress": latest.progress,
                "current_step": latest.current_step or "处理中...",
                "estimated_remaining": "见 timing.eta_seconds",
            }
        # task 存在但 progress=0, 还在排队 / 准备中
        if latest and latest.status == "running":
            return {
                "progress": 0,
                "current_step": "排队中, 等待 worker..." if not latest.started_at else "准备中...",
                "estimated_remaining": "见 timing.eta_seconds",
            }

    # Fallback: 根据已有数据估算 (老逻辑, 没 task 进度时用)
    clip_count = len(project.clips)
    collection_count = len(project.collections)

    if clip_count == 0 and collection_count == 0:
        return {"progress": 15, "current_step": "生成字幕中...", "estimated_remaining": "约 8-12 分钟"}

    if clip_count > 0 and collection_count == 0:
        progress = 50 + min(clip_count / TYPICAL_CLIP_COUNT * 30, 30)
        return {"progress": int(progress), "current_step": f"切割视频中... ({clip_count} 切片)", "estimated_remaining": "约 1-3 分钟"}

    if collection_count > 0:
        progress = 80 + min(collection_count / TYPICAL_COLLECTION_COUNT * 15, 15)
        return {"progress": int(progress), "current_step": f"合并合集中... ({collection_count} 合集)", "estimated_remaining": "约 30 秒"}

    return {"progress": 50, "current_step": "处理中...", "estimated_remaining": "未知"}


@router.get("/")
async def list_projects(
    include_deleted: bool = Query(default=False, description="是否包含已软删除的（回收站）"),
    search: Optional[str] = Query(default=None, description="按名称模糊搜索"),
    db: AsyncSession = Depends(get_db)
):
    """获取项目列表（默认不显示已删除）"""
    # 先清理卡死的 task (worker 被强杀后 task 永远卡 running, 影响 UI 体验)
    await _cleanup_stuck_tasks(db)

    query = select(Project).options(
        selectinload(Project.clips),
        selectinload(Project.collections),
        selectinload(Project.tasks),  # 进度估算需要 task.started_at/progress
    )
    if not include_deleted:
        query = query.where(Project.deleted_at.is_(None))
    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))
    query = query.order_by(Project.created_at.desc())
    result = await db.execute(query)
    projects = result.scalars().all()

    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "video_duration": p.video_duration,
                "video_size": p.video_size,  # v2.1.22 修: list 漏返 video_size 导致 UI 显示 None
                "clip_count": len(p.clips),
                "collection_count": len(p.collections),
                "created_at": to_iso_utc(p.created_at),
                "completed_at": to_iso_utc(p.completed_at),
                "deleted_at": to_iso_utc(p.deleted_at),
                **(await _resolve_style(p, db)),
                **calculate_progress(p),
                "timing": _build_timing_info(
                    max(p.tasks, key=lambda t: t.created_at, default=None) if p.tasks else None,
                    p.video_duration,
                ) if p.tasks else None,
            }
            for p in projects
        ]
    }


async def _cleanup_stuck_tasks(db: AsyncSession) -> int:
    """检测并清理卡死的 task (running 状态超过 30 分钟无进度更新)
    防止 worker 被强杀后 task 永远卡在 running
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    # 找所有 running 状态 task, 且 created_at 超过 30 分钟
    result = await db.execute(
        select(Task).where(
            Task.status == "running",
            Task.created_at < cutoff,
        )
    )
    stuck_tasks = result.scalars().all()
    cleaned = 0
    for task in stuck_tasks:
        task.status = "failed"
        task.error_message = f"任务卡死超过 30 分钟, 疑似 worker 被强杀, 自动标记为失败 (请重新提交处理)"
        task.completed_at = datetime.utcnow()
        # 关联 project 也标 failed
        result = await db.execute(select(Project).where(Project.id == task.project_id))
        project = result.scalar_one_or_none()
        if project and project.status == "processing":
            project.status = "failed"
        cleaned += 1
    if cleaned > 0:
        await db.commit()
        logger.warning(f"清理 {cleaned} 个卡死 task (running 超过 30 分钟)")
    return cleaned


@router.get("/{project_id}/files/{file_path:path}")
async def get_project_file(project_id: str, file_path: str, db: AsyncSession = Depends(get_db)):
    """获取项目文件（视频流）

    安全修复：
    - 校验 project 存在 + 未软删（404 而不是 200）
    - 防止 path traversal（file_path 必须在 project_dir 内）
    """
    from urllib.parse import quote

    # 1) project 必须存在且未被软删
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2) 解析路径 + 防止 path traversal
    project_dir = (settings.PROJECTS_DIR / project_id).resolve()
    full_path = (project_dir / file_path).resolve()

    # 确保解析后的路径仍在 project_dir 下（防 ../ 逃逸）
    try:
        full_path.relative_to(project_dir)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden: path outside project directory")

    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    encoded_filename = quote(full_path.name)
    return FileResponse(
        str(full_path),
        media_type="video/mp4",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"}
    )


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目详情"""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.clips), selectinload(Project.collections), selectinload(Project.tasks))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 取最近一个 task（最相关）—— tasks 已通过 selectinload eager load
    latest_task = max(project.tasks, key=lambda t: t.created_at, default=None)

    return {
        "project": {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "video_path": project.video_path,
            "video_duration": project.video_duration,
            "video_size": project.video_size,
            "subtitle_path": project.subtitle_path,
            "processing_config": project.processing_config,
            **(await _resolve_style(project, db)),
            "created_at": to_iso_utc(project.created_at),
            "completed_at": to_iso_utc(project.completed_at),
            "deleted_at": to_iso_utc(project.deleted_at),
            "task": {
                "status": latest_task.status,
                "progress": latest_task.progress,
                "current_step": latest_task.current_step,
                "error_message": latest_task.error_message,
                "started_at": to_iso_utc(latest_task.started_at),
                "completed_at": to_iso_utc(latest_task.completed_at),
                **_build_timing_info(latest_task, project.video_duration),
            } if latest_task else None,
            "clips": [
                {
                    "id": c.id,
                    "title": c.title,
                    "start_time": c.start_time,
                    "end_time": c.end_time,
                    "duration": c.duration,
                    "score": c.score,
                    "video_path": c.video_path,
                }
                for c in project.clips
            ],
            "collections": [
                {
                    "id": col.id,
                    "title": col.title,
                    "clip_count": len(col.clip_ids),
                    "video_path": col.video_path,
                }
                for col in project.collections
            ],
        }
    }


@router.put("/{project_id}/config")
async def update_project_config(
    project_id: str,
    config: dict,
    db: AsyncSession = Depends(get_db)
):
    """更新项目处理配置（如切片策略）"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 更新 processing_config
    project.processing_config = {
        **project.processing_config,
        **config
    }
    project.updated_at = datetime.utcnow()
    
    # 如果传入了字幕配置，同步到用户偏好（自动复用）
    if config.get("subtitle_style"):
        await _sync_subtitle_style_to_preferences(db, config["subtitle_style"])
    
    await db.commit()
    await db.refresh(project)
    
    return {
        "message": "配置已更新",
        "processing_config": project.processing_config
    }


async def _sync_subtitle_style_to_preferences(db: AsyncSession, subtitle_style: dict):
    """将字幕配置同步到用户偏好（直接 ORM 写，不再跨进程 HTTP）

    修复：原来通过 HTTP 调用 release backend（localhost:8000），beta 部署时串库。
    现在走 ORM，同一 db session / 同一 DB 文件，跨进程一致。
    """
    try:
        # upsert
        result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == "default")
        )
        pref = result.scalar_one_or_none()
        if pref:
            pref.last_used_subtitle_style = {
                "font_size": subtitle_style.get("font_size", 28),
                "txt_color": subtitle_style.get("txt_color", "white"),
                "stroke_color": subtitle_style.get("stroke_color", "black"),
                "stroke_width": subtitle_style.get("stroke_width", 2),
                "font": subtitle_style.get("font", "/System/Library/Fonts/STHeiti Medium.ttc"),
                "position": subtitle_style.get("position", 0.78),
            }
            pref.updated_at = datetime.utcnow()
        else:
            pref = UserPreference(
                user_id="default",
                last_used_subtitle_style={
                    "font_size": subtitle_style.get("font_size", 28),
                    "txt_color": subtitle_style.get("txt_color", "white"),
                    "stroke_color": subtitle_style.get("stroke_color", "black"),
                    "stroke_width": subtitle_style.get("stroke_width", 2),
                    "font": subtitle_style.get("font", "/System/Library/Fonts/STHeiti Medium.ttc"),
                    "position": subtitle_style.get("position", 0.78),
                },
                updated_at=datetime.utcnow(),
            )
            db.add(pref)
        await db.commit()
    except Exception as e:
        logger.warning(f"同步字幕样式到 preferences 失败：{e}")


@router.post("/")
async def create_project(
    name: str = Form(...),
    description: str = Form(default=""),
    video: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """创建新项目并上传视频"""
    # 验证文件类型
    ext = video.filename.split(".")[-1].lower()
    if not settings.is_allowed_video_ext(ext):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式：{ext}。支持的格式：{[e.lstrip('.') for e in settings.ALLOWED_VIDEO_EXTENSIONS]}"
        )
    
    # 创建项目 ID 和目录
    project_id = str(uuid.uuid4())
    project_dir = settings.PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存视频文件
    video_path = project_dir / "raw" / "input.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    
    video_size = 0
    with open(video_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):  # 1MB chunks
            f.write(chunk)
            video_size += len(chunk)
    
    # 读取用户字幕偏好，自动注入到项目配置（ORM 走当前 db session）
    subtitle_style = await _get_last_subtitle_style(db)
    
    # 创建项目记录
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
    
    return {
        "message": "项目创建成功",
        "project_id": project_id,
        "name": project.name,
        "video_size": video_size,
    }


@router.post("/{project_id}/process")
async def start_processing(project_id: str, db: AsyncSession = Depends(get_db)):
    """开始处理项目"""
    from celery import chain
    from ..tasks.processing import process_video_pipeline
    
    # 获取项目
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project.status not in ["pending", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"项目状态不允许处理：{project.status}"
        )
    
    # 检查视频文件是否存在
    video_path = settings.PROJECTS_DIR / project.video_path
    logger = logging.getLogger(__name__)
    logger.info(f"项目 {project_id} 视频路径：{video_path.absolute()}")

    if not video_path.exists():
        logger.error(f"视频文件不存在：{video_path.absolute()}")
        raise HTTPException(status_code=404, detail="Video file not found")

    # 检查文件大小 (v2.1.20 修 0 byte 卡完成假成功)
    video_size = video_path.stat().st_size
    if video_size < 1024 * 1024:  # 小于 1MB 视作无效
        raise HTTPException(
            status_code=400,
            detail=f"视频文件过小 ({video_size} bytes / 0 MB), 上传可能未完成. 请重新上传完整视频."
        )
    
    # 更新项目状态
    project.status = "processing"
    await db.commit()
    
    # 创建任务记录
    task = Task(
        id=str(uuid.uuid4()),
        project_id=project_id,
        task_type="video_processing",
        name="视频处理流水线",
        status="pending",
    )
    db.add(task)
    await db.commit()
    
    # 提交 Celery 任务
    srt_path = None
    if project.subtitle_path:
        srt_path = str(settings.PROJECTS_DIR / project.subtitle_path)

    # 使用全局 celery_app（配置已就绪，含 task_routes 和 beat_schedule）
    # 修复：原来临时创建 Celery 实例 → 配置不一致 + 路由错乱
    from ..core.celery_app import celery_app
    celery_task = celery_app.send_task(
        "backend.tasks.processing.process_video_pipeline",
        args=[project_id, str(video_path), srt_path, task.id],
    )

    # 更新任务
    task.celery_task_id = celery_task.id
    task.status = "running"
    await db.commit()

    return {
        "message": "处理已开始",
        "project_id": project_id,
        "task_id": task.id,
        "celery_task_id": celery_task.id,
    }


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    permanent: bool = Query(default=False, description="是否真删除（默认软删除进回收站）"),
    db: AsyncSession = Depends(get_db)
):
    """删除项目（默认软删除到回收站，可恢复 30 天）"""
    import shutil

    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # processing 状态禁止删除（避免 worker 写文件时目录被删）
    if project.status == "processing" and not permanent:
        raise HTTPException(
            status_code=409,
            detail="项目正在处理中，无法删除。请等待处理完成，或用 ?permanent=true 强制真删（会撤销 celery task）"
        )

    # 撤销 celery task（如果还在跑）—— 直接查 tasks 表，不用 lazy load
    revoke_msg = None
    tasks_result = await db.execute(select(Task).where(Task.project_id == project_id, Task.status == "running"))
    running_tasks = [t for t in tasks_result.scalars().all() if t.celery_task_id]
    for t in running_tasks:
        try:
            from ..core.celery_app import celery_app
            celery_app.control.revoke(t.celery_task_id, terminate=True)
        except Exception as e:
            logger.warning(f"撤销 celery task 失败: {e}")
    if running_tasks:
        revoke_msg = f"已撤销 {len(running_tasks)} 个 celery task"

    if permanent:
        # 真删除：删目录 + 删 DB
        project_dir = settings.PROJECTS_DIR / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir)
        await db.delete(project)
        await db.commit()
        return {"message": "项目已永久删除", "permanent": True, "revoke": revoke_msg}
    else:
        # 软删除：标记 deleted_at，目录保留
        project.deleted_at = datetime.utcnow()
        project.status = "deleted"
        await db.commit()
        return {
            "message": "项目已移到回收站，30 天内可恢复",
            "permanent": False,
            "deleted_at": to_iso_utc(project.deleted_at),
            "restore_within_days": 30,
            "revoke": revoke_msg,
        }


@router.post("/{project_id}/restore")
async def restore_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """从回收站恢复项目"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.deleted_at is None:
        raise HTTPException(status_code=400, detail="项目未被删除，无需恢复")

    # 恢复：清掉 deleted_at，状态回 completed/pending
    project.deleted_at = None
    if project.status == "deleted":
        # 看 clips 数量决定回到 completed 还是 failed（直接查不用 lazy load）
        clip_count = await db.execute(select(func.count(Clip.id)).where(Clip.project_id == project_id))
        has_clips = (clip_count.scalar() or 0) > 0
        project.status = "completed" if has_clips else "pending"
    await db.commit()
    return {"message": "项目已恢复", "project_id": project_id, "status": project.status}


@router.post("/trash/cleanup")
async def cleanup_trash(older_than_days: int = Query(default=30, ge=1, le=365), db: AsyncSession = Depends(get_db)):
    """清理回收站：永久删除 N 天前的软删除项目"""
    import shutil

    cutoff = datetime.utcnow() - timedelta(days=older_than_days)
    result = await db.execute(
        select(Project).where(Project.deleted_at.isnot(None), Project.deleted_at < cutoff)
    )
    projects = result.scalars().all()

    cleaned = []
    for p in projects:
        project_dir = settings.PROJECTS_DIR / p.id
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)
        await db.delete(p)
        cleaned.append(p.id)
    await db.commit()

    return {"cleaned_count": len(cleaned), "project_ids": cleaned, "older_than_days": older_than_days}
