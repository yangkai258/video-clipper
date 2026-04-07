"""项目 API 路由"""
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..core.database import get_db
from ..core.config import settings
from ..models.database import Project, Task, Clip, Collection
from sqlalchemy.orm import selectinload


router = APIRouter()


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
    if not video_path.exists():
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
    
    # 直接配置 Celery broker
    from celery import Celery
    temp_app = Celery("temp", broker="redis://127.0.0.1:6379/0", backend="redis://127.0.0.1:6379/0")
    temp_app.config_from_object({
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "Asia/Shanghai",
    })
    
    celery_task = temp_app.send_task(
        "backend.tasks.processing.process_video_pipeline",
        args=[project_id, str(video_path), srt_path, task.id],
        queue="processing",
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
