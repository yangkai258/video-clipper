"""用户偏好设置 API"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
import json
from datetime import datetime

router = APIRouter()

# 动态获取数据库路径（与 styles.py 一致）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILENAME = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/video_clipper.db").split("/")[-1].replace(".db", ".db")
DATABASE_PATH = os.path.join(BASE_DIR, "data", DB_FILENAME)


def get_db():
    """获取数据库连接"""
    return sqlite3.connect(DATABASE_PATH)


class SubtitleStyle(BaseModel):
    font_size: int = 28
    txt_color: str = "white"
    stroke_color: str = "black"
    stroke_width: float = 2
    font: str = "/System/Library/Fonts/STHeiti Medium.ttc"
    position: float = 0.78


class UserPreferencesResponse(BaseModel):
    last_used_subtitle_style: Optional[SubtitleStyle] = None


@router.get("/preferences", response_model=UserPreferencesResponse)
async def get_user_preferences():
    """获取用户偏好设置"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            "SELECT last_used_subtitle_style FROM user_preferences WHERE user_id = 'default'"
        )
        row = cursor.fetchone()
        if row and row[0]:
            style = json.loads(row[0])
            return {"last_used_subtitle_style": style}
        return {"last_used_subtitle_style": None}
    finally:
        db.close()


@router.put("/preferences/subtitle-style")
async def update_subtitle_style(style: SubtitleStyle):
    """更新用户最后使用的字幕样式偏好"""
    db = get_db()
    try:
        style_json = json.dumps(style.model_dump(), ensure_ascii=False)
        now = datetime.now().isoformat()
        cursor = db.cursor()
        cursor.execute("""
            INSERT INTO user_preferences (user_id, last_used_subtitle_style, updated_at)
            VALUES ('default', ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_used_subtitle_style = excluded.last_used_subtitle_style,
                updated_at = excluded.updated_at
        """, (style_json, now))
        db.commit()
        return {"message": "字幕样式偏好已更新", "last_used_subtitle_style": style}
    finally:
        db.close()