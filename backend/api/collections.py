"""合集 API 路由"""
import logging
from pathlib import Path
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from ..core.database import get_db, to_iso_utc
from ..core.config import settings
from ..models.database import Collection, Clip

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_collection_video_path(collection: Collection) -> Optional[Path]:
    """解析合集的视频文件绝对路径"""
    if not collection.video_path:
        return None

    p = Path(collection.video_path)
    if p.is_absolute():
        return p if p.exists() else None

    project_dir = settings.PROJECTS_DIR / collection.project_id
    candidates = [
        project_dir / collection.video_path,
        project_dir / "output" / "collections" / Path(collection.video_path).name,
        settings.PROJECTS_DIR / collection.video_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _serialize_collection(collection: Collection, clips_map: dict = None) -> dict:
    """把 Collection 模型序列化为 API 响应

    Args:
        collection: Collection 模型实例
        clips_map: {clip_index: Clip} 用于展开每个 clip 的元信息（如果传了）
    """
    clip_ids = collection.clip_ids or []
    clips_detail = []
    clips_map = clips_map or {}

    for cid in clip_ids:
        # clip_ids 可能是索引（int）或字符串标题——根据实际数据兼容
        clip = clips_map.get(cid)
        if clip:
            clips_detail.append({
                "index": cid,
                "id": clip.id,
                "title": clip.title,
                "start_time": clip.start_time,
                "end_time": clip.end_time,
                "duration": clip.duration,
                "score": clip.score,
                "video_path": clip.video_path,
            })
        else:
            clips_detail.append({"index": cid})

    return {
        "id": collection.id,
        "project_id": collection.project_id,
        "title": collection.title,
        "description": collection.description or "",
        "clip_ids": clip_ids,
        "clip_count": len(clip_ids),
        "clips": clips_detail,
        "video_path": collection.video_path,
        "created_at": to_iso_utc(collection.created_at),
    }


async def _build_clips_map(project_id: str, clip_ids: list, db: AsyncSession) -> dict:
    """根据 collection 的 clip_ids 找到对应的 Clip 实例，按 index/title 索引

    实际数据中 clip_ids 通常存的是 clip 的"索引号"（int），匹配 Clip 表里某个字段。
    这里采取兼容策略：先按 video_path 文件名匹配，再按 title 模糊匹配。
    """
    if not clip_ids:
        return {}

    # 加载该项目所有 clips
    result = await db.execute(
        select(Clip).where(Clip.project_id == project_id)
    )
    all_clips = result.scalars().all()

    # 构建索引映射（多种方式）
    by_id = {c.id: c for c in all_clips}
    by_index = {}  # 假设 clip_ids 顺序对应 clip 创建顺序（index=i+1）

    clips_map = {}
    for cid in clip_ids:
        if isinstance(cid, str):
            # 尝试直接 id 匹配
            if cid in by_id:
                clips_map[cid] = by_id[cid]
                continue
            # 尝试 title 匹配
            for c in all_clips:
                if c.title == cid:
                    clips_map[cid] = c
                    break
        else:
            # int：作为 1-based 索引
            idx = int(cid)
            if 1 <= idx <= len(all_clips):
                # 注意：按 start_time 排序，因为切片通常按时间顺序
                sorted_clips = sorted(all_clips, key=lambda x: x.start_time or 0)
                clips_map[cid] = sorted_clips[idx - 1]

    return clips_map


@router.get("/")
async def list_collections(
    project_id: Optional[str] = Query(None, description="按项目 ID 过滤"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """获取合集列表（可按项目过滤，支持分页）"""
    stmt = select(Collection).order_by(Collection.created_at.desc()).limit(limit).offset(offset)
    if project_id:
        stmt = stmt.where(Collection.project_id == project_id)

    result = await db.execute(stmt)
    collections = result.scalars().all()

    return {
        "collections": [_serialize_collection(c) for c in collections],
        "count": len(collections),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{collection_id}")
async def get_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    """获取合集详情（含每个 clip 的元信息）"""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="合集不存在")

    clips_map = await _build_clips_map(
        collection.project_id,
        collection.clip_ids or [],
        db,
    )

    return {"collection": _serialize_collection(collection, clips_map)}


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    """删除合集（仅删数据库记录）"""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="合集不存在")

    await db.delete(collection)
    await db.commit()

    return {"message": "合集已删除", "collection_id": collection_id}


@router.get("/{collection_id}/video")
async def get_collection_video(collection_id: str, db: AsyncSession = Depends(get_db)):
    """获取合集视频文件流"""
    result = await db.execute(select(Collection).where(Collection.id == collection_id))
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="合集不存在")

    video_path = _resolve_collection_video_path(collection)
    if not video_path:
        raise HTTPException(status_code=404, detail="合集视频文件不存在")

    encoded_filename = quote(video_path.name)
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}"
        },
    )