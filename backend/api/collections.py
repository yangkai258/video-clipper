"""合集 API 路由"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

router = APIRouter()


@router.get("/")
async def list_collections(db: AsyncSession = Depends(get_db)):
    """获取所有合集"""
    # TODO: 实现
    return {"collections": []}


@router.get("/{collection_id}")
async def get_collection(collection_id: str, db: AsyncSession = Depends(get_db)):
    """获取合集详情"""
    # TODO: 实现
    return {"collection": {}}
