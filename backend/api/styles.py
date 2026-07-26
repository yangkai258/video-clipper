"""切片策略管理 API"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db, to_iso_utc
from ..models.database import Style

router = APIRouter()
logger = None  # 如需 logging.getLogger(__name__) 在下面加

# 预设切片策略（只读，写死在代码里）
PRESET_STRATEGIES = [
    {
        "id": "preset_golden_quotes",
        "name": "🎯 金句优先",
        "description": "优先提取观点鲜明、有传播力的金句片段，适合短视频分发",
        "target_duration": 45,
        "max_clips": 30,
        "content_types": ["金句", "观点", "高潮"],
        "rules": {
            "min_score": 0.8,
            "priority_keywords": ["我觉得", "我认为", "最重要的是", "记住", "关键"],
            "avoid_silence": True,
        },
    },
    {
        "id": "preset_complete_segments",
        "name": "📖 完整片段",
        "description": "保持内容完整性，每个切片讲述一个完整观点，适合中长视频",
        "target_duration": 600,
        "max_clips": 15,
        "content_types": ["完整观点", "案例分析", "讲解"],
        "rules": {
            "min_score": 0.6,
            "prefer_continuity": True,
            "min_segment_duration": 300,
        },
    },
    {
        "id": "preset_even_distribution",
        "name": "📏 均匀分布",
        "description": "按时间均匀切片，适合教程类、课程类内容",
        "target_duration": 60,
        "max_clips": 20,
        "content_types": ["讲解", "演示", "知识点"],
        "rules": {"even_split": True, "min_score": 0.5},
    },
    {
        "id": "preset_highlights",
        "name": "⚡ 高潮密集",
        "description": "只切出情绪高涨、节奏快的精彩片段，适合混剪",
        "target_duration": 30,
        "max_clips": 40,
        "content_types": ["高潮", "笑点", "冲突"],
        "rules": {"min_score": 0.85, "fast_pace": True, "quick_transitions": True},
    },
]


def _style_to_dict(s: Style) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description or "",
        "target_duration": s.target_duration,
        "max_clips": s.max_clips,
        "content_types": s.content_types or [],
        "rules": s.rules or {},
        "content_guidelines": s.content_guidelines or "",
        "keep_rules": s.keep_rules or "",
        "remove_rules": s.remove_rules or "",
        "style_positioning": s.style_positioning or "",
        "subtitle_config": s.subtitle_config,
        "created_at": to_iso_utc(s.created_at),
        "updated_at": to_iso_utc(s.updated_at),
    }


class StyleCreate(BaseModel):
    name: str
    description: str | None = ""
    target_duration: int = 60
    max_clips: int = 20
    content_types: list[str] = ["金句", "观点"]
    rules: dict = {}
    # 新增：风格规则详情（用于前端展示和编辑）
    content_guidelines: str | None = (
        ""  # 内容识别规则（如"经济时事/创业故事/连麦互动"）
    )
    keep_rules: str | None = ""  # 保留规则（如"保留金句、总结、方法论"）
    remove_rules: str | None = ""  # 删除规则（如"删除沉默、重复、跑题"）
    style_positioning: str | None = ""  # 风格定位（如"沉稳、务实、有阅历"）
    # 新增：字幕配置
    subtitle_config: dict | None = (
        None  # {font_size, txt_color, stroke_color, stroke_width, font, position}
    )


class StyleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    target_duration: int | None = None
    max_clips: int | None = None
    content_types: list[str] | None = None
    rules: dict | None = None
    # 新增：风格规则详情
    content_guidelines: str | None = None
    keep_rules: str | None = None
    remove_rules: str | None = None
    style_positioning: str | None = None
    # 新增：字幕配置
    subtitle_config: dict | None = None


class StyleResponse(BaseModel):
    id: str
    name: str
    description: str
    target_duration: int
    max_clips: int
    content_types: list[str]
    rules: dict
    created_at: str
    updated_at: str
    # 新增：风格规则详情
    content_guidelines: str | None = ""
    keep_rules: str | None = ""
    remove_rules: str | None = ""
    style_positioning: str | None = ""
    # 新增：字幕配置
    subtitle_config: dict | None = None


@router.get("/strategies/presets")
async def list_preset_strategies():
    """获取预设切片策略列表"""
    return {"strategies": PRESET_STRATEGIES}


@router.get("/styles", response_model=list[StyleResponse])
async def list_styles(db: AsyncSession = Depends(get_db)):
    """获取所有切片风格（ORM，走当前 db session）"""
    result = await db.execute(select(Style).order_by(Style.created_at.desc()))
    styles = result.scalars().all()
    return [_style_to_dict(s) for s in styles]


@router.get("/styles/{style_id}", response_model=StyleResponse)
async def get_style(style_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个风格详情"""
    result = await db.execute(select(Style).where(Style.id == style_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="风格不存在")
    return _style_to_dict(s)


@router.post("/styles", response_model=StyleResponse)
async def create_style(style: StyleCreate, db: AsyncSession = Depends(get_db)):
    """创建新风格"""
    style_id = f"style_{uuid.uuid4().hex[:8]}"

    s = Style(
        id=style_id,
        name=style.name,
        description=style.description or "",
        target_duration=style.target_duration,
        max_clips=style.max_clips,
        content_types=style.content_types or [],
        rules=style.rules or {},
        content_guidelines=style.content_guidelines or "",
        keep_rules=style.keep_rules or "",
        remove_rules=style.remove_rules or "",
        style_positioning=style.style_positioning or "",
        subtitle_config=style.subtitle_config,
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)

    # 同步字幕配置到用户偏好
    if style.subtitle_config:
        from .projects import _sync_subtitle_style_to_preferences

        await _sync_subtitle_style_to_preferences(db, style.subtitle_config)

    return _style_to_dict(s)


@router.put("/styles/{style_id}", response_model=StyleResponse)
async def update_style(
    style_id: str, style: StyleUpdate, db: AsyncSession = Depends(get_db)
):
    """更新风格（ORM）"""
    result = await db.execute(select(Style).where(Style.id == style_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="风格不存在")

    updates = style.dict(exclude_unset=True)
    for k, v in updates.items():
        setattr(s, k, v)
    s.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(s)

    # 同步字幕配置到用户偏好（自动复用）
    if style.subtitle_config is not None:
        from .projects import _sync_subtitle_style_to_preferences

        await _sync_subtitle_style_to_preferences(db, style.subtitle_config)

    return _style_to_dict(s)


@router.delete("/styles/{style_id}")
async def delete_style(style_id: str, db: AsyncSession = Depends(get_db)):
    """删除风格"""
    result = await db.execute(select(Style).where(Style.id == style_id))
    s = result.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="风格不存在")
    await db.delete(s)
    await db.commit()
    return {"message": "风格已删除"}
