"""字幕样式偏好（user preferences）持久化服务。

负责将用户在某次项目中使用的字幕样式写入 UserPreference 表，
下次创建项目时自动复用。让"用户最近用的样式"自动同步到所有项目。
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.database import UserPreference

logger = logging.getLogger(__name__)

# 默认字幕样式（macOS 中文字体链；与 subtitle_burner 保持一致）
DEFAULT_SUBTITLE_STYLE = {
    "font_size": 28,
    "txt_color": "white",
    "stroke_color": "black",
    "stroke_width": 2,
    "font": "/System/Library/Fonts/STHeiti Medium.ttc",
    "position": 0.78,
}

# 单用户偏好标识（当前系统只服务一个用户）
DEFAULT_USER_ID = "default"


async def get_last_subtitle_style(db: AsyncSession) -> dict | None:
    """获取用户最近一次使用的字幕样式。返回 None 表示尚无偏好记录。"""
    result = await db.execute(
        select(UserPreference).where(UserPreference.user_id == DEFAULT_USER_ID)
    )
    pref = result.scalar_one_or_none()
    if not pref:
        return None
    return pref.last_used_subtitle_style


async def sync_subtitle_style_to_preferences(
    db: AsyncSession, subtitle_style: dict
) -> None:
    """把字幕样式同步到用户偏好（upsert）。

    失败仅 warn，不抛异常——偏好同步不应阻塞项目配置更新。
    """
    try:
        normalized = _normalize_subtitle_style(subtitle_style)
        result = await db.execute(
            select(UserPreference).where(UserPreference.user_id == DEFAULT_USER_ID)
        )
        pref = result.scalar_one_or_none()
        if pref:
            pref.last_used_subtitle_style = normalized
            pref.updated_at = datetime.utcnow()
        else:
            pref = UserPreference(
                user_id=DEFAULT_USER_ID,
                last_used_subtitle_style=normalized,
                updated_at=datetime.utcnow(),
            )
            db.add(pref)
        await db.commit()
    except Exception as e:
        logger.warning(f"同步字幕样式到 preferences 失败：{e}")


def _normalize_subtitle_style(subtitle_style: dict) -> dict:
    """归一化字幕样式 dict：缺失字段填默认值。"""
    return {
        "font_size": subtitle_style.get(
            "font_size", DEFAULT_SUBTITLE_STYLE["font_size"]
        ),
        "txt_color": subtitle_style.get(
            "txt_color", DEFAULT_SUBTITLE_STYLE["txt_color"]
        ),
        "stroke_color": subtitle_style.get(
            "stroke_color", DEFAULT_SUBTITLE_STYLE["stroke_color"]
        ),
        "stroke_width": subtitle_style.get(
            "stroke_width", DEFAULT_SUBTITLE_STYLE["stroke_width"]
        ),
        "font": subtitle_style.get("font", DEFAULT_SUBTITLE_STYLE["font"]),
        "position": subtitle_style.get("position", DEFAULT_SUBTITLE_STYLE["position"]),
    }
