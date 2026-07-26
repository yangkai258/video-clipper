"""用户偏好设置 API"""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.database import UserPreference

router = APIRouter()


class SubtitleStyle(BaseModel):
    font_size: int = 28
    txt_color: str = "white"
    stroke_color: str = "black"
    stroke_width: float = 2
    font: str = "/System/Library/Fonts/STHeiti Medium.ttc"
    position: float = 0.78


class SubtitleStylePatch(BaseModel):
    """PATCH 部分更新：所有字段可选"""

    font_size: int | None = None
    txt_color: str | None = None
    stroke_color: str | None = None
    stroke_width: float | None = None
    font: str | None = None
    position: float | None = None


class UserPreferencesResponse(BaseModel):
    last_used_subtitle_style: dict | None = None


DEFAULT_SUBTITLE_STYLE = SubtitleStyle().model_dump()


def _merge_patch(current: dict, patch: dict) -> dict:
    """合并 patch 到 current（只覆盖 patch 中非 None 的字段）"""
    result = dict(current)
    for k, v in patch.items():
        if v is not None:
            result[k] = v
    return result


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences(db: AsyncSession = Depends(get_db)):
    """获取用户偏好设置（ORM）"""
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == "default")
    )
    pref = result.scalar_one_or_none()
    if pref and pref.last_used_subtitle_style:
        return {"last_used_subtitle_style": pref.last_used_subtitle_style}
    return {"last_used_subtitle_style": None}


@router.put("/preferences/subtitle-style")
async def update_subtitle_style(
    style: SubtitleStyle, db: AsyncSession = Depends(get_db)
):
    """全量替换字幕样式偏好"""
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == "default")
    )
    pref = result.scalar_one_or_none()
    if pref:
        pref.last_used_subtitle_style = style.model_dump()
        pref.updated_at = datetime.utcnow()
    else:
        pref = UserPreference(
            user_id="default",
            last_used_subtitle_style=style.model_dump(),
            updated_at=datetime.utcnow(),
        )
        db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return {"message": "字幕样式偏好已更新", "last_used_subtitle_style": style}


@router.patch("/preferences/subtitle-style")
async def patch_subtitle_style(
    patch: SubtitleStylePatch, db: AsyncSession = Depends(get_db)
):
    """部分更新字幕样式（只覆盖 patch 中非 None 的字段）

    修复：之前 PUT 是全量替换，传一个字段其他都被 Pydantic default 覆盖。
    现在 PATCH 支持只更新指定字段。
    """
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == "default")
    )
    pref = result.scalar_one_or_none()
    current = (
        pref.last_used_subtitle_style if pref else None
    ) or DEFAULT_SUBTITLE_STYLE
    merged = _merge_patch(current, patch.model_dump(exclude_unset=True))

    if pref:
        pref.last_used_subtitle_style = merged
        pref.updated_at = datetime.utcnow()
    else:
        pref = UserPreference(
            user_id="default",
            last_used_subtitle_style=merged,
            updated_at=datetime.utcnow(),
        )
        db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return {"message": "字幕样式偏好已部分更新", "last_used_subtitle_style": merged}
