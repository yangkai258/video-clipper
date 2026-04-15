"""项目 API 路由"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..core.config import settings
from ..models.database import Project, Task, Clip, Collection
from sqlalchemy.orm import selectinload


router = APIRouter()


def calculate_progress(project: Project) -> dict:
    """计算项目处理进度"""
    if project.status == "completed":
        return {"progress": 100, "current_step": "已完成", "estimated_remaining": "0 分钟"}
    
    if project.status == "pending":
        return {"progress": 0, "current_step": "等待开始", "estimated_remaining": "未知"}
    
    if project.status == "failed":
        return {"progress": 0, "current_step": "处理失败", "estimated_remaining": "-"}
    
    # processing 状态：根据已有数据估算进度
    clip_count = len(project.clips)
    collection_count = len(project.collections)
    
    # 完整流程：字幕生成 (20%) → 大纲/时间线 (20%) → 评分 (10%) → 切割 (30%) → 合集 (15%) → 写入数据库 (5%)
    if clip_count == 0 and collection_count == 0:
        return {"progress": 15, "current_step": "生成字幕中...", "estimated_remaining": "约 8-12 分钟"}
    
    if clip_count > 0 and collection_count == 0:
        # 已有切片记录，正在切割或刚完成切割
        progress = 50 + min(clip_count / 162 * 30, 30)  # 假设 162 是典型切片数
        return {"progress": int(progress), "current_step": f"切割视频中... ({clip_count} 切片)", "estimated_remaining": "约 1-3 分钟"}
    
    if collection_count > 0:
        progress = 80 + min(collection_count / 21 * 15, 15)
        return {"progress": int(progress), "current_step": f"合并合集中... ({collection_count} 合集)", "estimated_remaining": "约 30 秒"}
    
    return {"progress": 50, "current_step": "处理中...", "estimated_remaining": "未知"}


@router.get("/")
async def list_projects(db: AsyncSession = Depends(get_db)):
    """获取项目列表"""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.clips), selectinload(Project.collections))
        .order_by(Project.created_at.desc())
    )
    projects = result.scalars().all()
    
    return {
        "projects": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "status": p.status,
                "video_duration": p.video_duration,
                "clip_count": len(p.clips),
                "collection_count": len(p.collections),
                "created_at": p.created_at.isoformat(),
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                **calculate_progress(p)
            }
            for p in projects
        ]
    }


@router.get("/{project_id}/files/{file_path:path}")
async def get_project_file(project_id: str, file_path: str):
    """获取项目文件（视频流）"""
    from fastapi.responses import FileResponse
    from urllib.parse import quote
    
    full_path = settings.PROJECTS_DIR / project_id / file_path
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    # URL 编码文件名以支持中文
    encoded_filename = quote(full_path.name)
    
    return FileResponse(
        str(full_path),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
        }
    )


@router.get("/{project_id}")
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目详情"""
    result = await db.execute(
        select(Project)
        .options(selectinload(Project.clips), selectinload(Project.collections))
        .where(Project.id == project_id)
    )
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
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
            "created_at": project.created_at.isoformat(),
            "completed_at": project.completed_at.isoformat() if project.completed_at else None,
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
    
    await db.commit()
    await db.refresh(project)
    
    return {
        "message": "配置已更新",
        "processing_config": project.processing_config
    }


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
    if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式：{ext}。支持的格式：{settings.ALLOWED_VIDEO_EXTENSIONS}"
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
    
    # 创建项目记录
    project = Project(
        id=project_id,
        name=name,
        description=description,
        status="pending",
        video_path=str(video_path.relative_to(settings.PROJECTS_DIR)),
        video_size=video_size,
        processing_config={},
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
    
    # 直接配置 Celery broker（从环境变量读取，支持版本隔离）
    import os
    from celery import Celery
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
    result_backend = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
    queue_name = os.getenv("CELERY_QUEUE_NAME", "processing")
    
    temp_app = Celery("temp", broker=broker_url, backend=result_backend)
    temp_app.config_from_object({
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "Asia/Shanghai",
    })
    
    celery_task = temp_app.send_task(
        "backend.tasks.processing.process_video_pipeline",
        args=[project_id, str(video_path), srt_path, task.id],
        queue=queue_name,
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
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """删除项目"""
    import shutil
    
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # 删除项目目录
    project_dir = settings.PROJECTS_DIR / project_id
    if project_dir.exists():
        shutil.rmtree(project_dir)
    
    # 删除数据库记录
    await db.delete(project)
    await db.commit()
    
    return {"message": "项目已删除"}
