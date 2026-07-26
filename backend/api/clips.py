"""切片 API 路由"""

import logging
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import get_db, to_iso_utc
from ..models.database import Clip

logger = logging.getLogger(__name__)
router = APIRouter()


class ClipUpdate(BaseModel):
    """切片更新请求体"""

    title: str | None = None
    description: str | None = None
    score: float | None = None


def _serialize_clip(clip: Clip) -> dict:
    """把 Clip 模型序列化为 API 响应"""
    return {
        "id": clip.id,
        "project_id": clip.project_id,
        "title": clip.title,
        "description": clip.description or "",
        "start_time": clip.start_time,
        "end_time": clip.end_time,
        "duration": clip.duration,
        "score": clip.score,
        "score_reason": clip.score_reason or "",
        "video_path": clip.video_path,
        "thumbnail_path": clip.thumbnail_path,
        "metadata": clip.clip_metadata or {},
        "created_at": to_iso_utc(clip.created_at),
    }


def _resolve_clip_video_path(clip: Clip) -> Path | None:
    """解析切片的视频文件绝对路径"""
    if not clip.video_path:
        return None

    # video_path 可能是相对路径（相对于 PROJECTS_DIR）或绝对路径
    p = Path(clip.video_path)
    if p.is_absolute():
        return p if p.exists() else None

    # 相对路径：在 PROJECTS_DIR 下找
    project_dir = settings.PROJECTS_DIR / clip.project_id
    candidates = [
        project_dir / clip.video_path,
        project_dir / "output" / "clips" / Path(clip.video_path).name,
        settings.PROJECTS_DIR / clip.video_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


@router.get("/")
async def list_clips(
    project_id: str | None = Query(None, description="按项目 ID 过滤"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取切片列表（可按项目过滤，支持分页）"""
    stmt = select(Clip).order_by(Clip.created_at.desc()).limit(limit).offset(offset)
    if project_id:
        stmt = stmt.where(Clip.project_id == project_id)

    result = await db.execute(stmt)
    clips = result.scalars().all()

    return {
        "clips": [_serialize_clip(c) for c in clips],
        "count": len(clips),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{clip_id}")
async def get_clip(clip_id: str, db: AsyncSession = Depends(get_db)):
    """获取切片详情"""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()

    if not clip:
        raise HTTPException(status_code=404, detail="切片不存在")

    return {"clip": _serialize_clip(clip)}


@router.put("/{clip_id}", response_model=dict)
async def update_clip(
    clip_id: str,
    payload: ClipUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新切片元数据（title / description / score）"""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()

    if not clip:
        raise HTTPException(status_code=404, detail="切片不存在")

    if payload.title is not None:
        clip.title = payload.title
    if payload.description is not None:
        clip.description = payload.description
    if payload.score is not None:
        clip.score = payload.score

    await db.commit()
    await db.refresh(clip)

    return {"message": "切片已更新", "clip": _serialize_clip(clip)}


@router.delete("/{clip_id}")
async def delete_clip(clip_id: str, db: AsyncSession = Depends(get_db)):
    """删除切片（仅删数据库记录，文件可选删除）"""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()

    if not clip:
        raise HTTPException(status_code=404, detail="切片不存在")

    await db.delete(clip)
    await db.commit()

    return {"message": "切片已删除", "clip_id": clip_id}


@router.get("/{clip_id}/video")
async def get_clip_video(clip_id: str, db: AsyncSession = Depends(get_db)):
    """获取切片视频文件流"""
    result = await db.execute(select(Clip).where(Clip.id == clip_id))
    clip = result.scalar_one_or_none()

    if not clip:
        raise HTTPException(status_code=404, detail="切片不存在")

    video_path = _resolve_clip_video_path(clip)
    if not video_path:
        raise HTTPException(status_code=404, detail="切片视频文件不存在")

    encoded_filename = quote(video_path.name)
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"},
    )
