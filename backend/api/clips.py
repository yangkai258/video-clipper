"""切片 API 路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

router = APIRouter()


@router.get("/")
async def list_clips(db: AsyncSession = Depends(get_db)):
    """获取所有切片"""
    # TODO: 实现
    return {"clips": []}


@router.get("/{clip_id}")
async def get_clip(clip_id: str, db: AsyncSession = Depends(get_db)):
    """获取切片详情"""
    # TODO: 实现
    return {"clip": {}}
