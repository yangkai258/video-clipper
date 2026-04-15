"""切片策略管理 API"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid
import json
import sqlite3
import os

router = APIRouter()

# 动态获取数据库路径（支持环境变量覆盖）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILENAME = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/video_clipper.db").split("/")[-1].replace(".db", ".db")
DATABASE_PATH = os.path.join(BASE_DIR, "data", DB_FILENAME)

# 预设切片策略
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
            "avoid_silence": True
        }
    },
    {
        "id": "preset_complete_segments",
        "name": "📖 完整片段",
        "description": "保持内容完整性，每个切片讲述一个完整观点，适合中长视频",
        "target_duration": 120,
        "max_clips": 15,
        "content_types": ["完整观点", "案例分析", "讲解"],
        "rules": {
            "min_score": 0.6,
            "prefer_continuity": True,
            "min_segment_duration": 60
        }
    },
    {
        "id": "preset_even_distribution",
        "name": "📏 均匀分布",
        "description": "按时间均匀切片，适合教程类、课程类内容",
        "target_duration": 60,
        "max_clips": 20,
        "content_types": ["讲解", "演示", "知识点"],
        "rules": {
            "even_split": True,
            "min_score": 0.5
        }
    },
    {
        "id": "preset_highlights",
        "name": "⚡ 高潮密集",
        "description": "只切出情绪高涨、节奏快的精彩片段，适合混剪",
        "target_duration": 30,
        "max_clips": 40,
        "content_types": ["高潮", "笑点", "冲突"],
        "rules": {
            "min_score": 0.85,
            "fast_pace": True,
            "quick_transitions": True
        }
    }
]


def get_db():
    """获取数据库连接"""
    return sqlite3.connect(DATABASE_PATH)


class StyleCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    target_duration: int = 60
    max_clips: int = 20
    content_types: List[str] = ["金句", "观点"]
    rules: dict = {}
    # 新增：风格规则详情（用于前端展示和编辑）
    content_guidelines: Optional[str] = ""  # 内容识别规则（如"经济时事/创业故事/连麦互动"）
    keep_rules: Optional[str] = ""  # 保留规则（如"保留金句、总结、方法论"）
    remove_rules: Optional[str] = ""  # 删除规则（如"删除沉默、重复、跑题"）
    style_positioning: Optional[str] = ""  # 风格定位（如"沉稳、务实、有阅历"）
    # 新增：字幕配置
    subtitle_config: Optional[dict] = None  # {font_size, txt_color, stroke_color, stroke_width, font, position}


class StyleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_duration: Optional[int] = None
    max_clips: Optional[int] = None
    content_types: Optional[List[str]] = None
    rules: Optional[dict] = None
    # 新增：风格规则详情
    content_guidelines: Optional[str] = None
    keep_rules: Optional[str] = None
    remove_rules: Optional[str] = None
    style_positioning: Optional[str] = None
    # 新增：字幕配置
    subtitle_config: Optional[dict] = None


class StyleResponse(BaseModel):
    id: str
    name: str
    description: str
    target_duration: int
    max_clips: int
    content_types: List[str]
    rules: dict
    created_at: str
    updated_at: str
    # 新增：风格规则详情
    content_guidelines: Optional[str] = ""
    keep_rules: Optional[str] = ""
    remove_rules: Optional[str] = ""
    style_positioning: Optional[str] = ""
    # 新增：字幕配置
    subtitle_config: Optional[dict] = None


@router.get("/strategies/presets")
async def list_preset_strategies():
    """获取预设切片策略列表"""
    return {"strategies": PRESET_STRATEGIES}


@router.get("/styles", response_model=List[StyleResponse])
async def list_styles():
    """获取所有切片风格"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM styles ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        styles = []
        for row in rows:
            styles.append({
                "id": row[0],
                "name": row[1],
                "description": row[2] or "",
                "target_duration": row[3],
                "max_clips": row[4],
                "content_types": json.loads(row[5] or '[]'),
                "rules": json.loads(row[6] or '{}'),
                "created_at": row[7],
                "updated_at": row[8],
                "content_guidelines": row[9] or "",
                "keep_rules": row[10] or "",
                "remove_rules": row[11] or "",
                "style_positioning": row[12] or "",
                "subtitle_config": json.loads(row[13]) if row[13] else None
            })
        
        return styles
    finally:
        db.close()


@router.get("/styles/{style_id}", response_model=StyleResponse)
async def get_style(style_id: str):
    """获取单个风格详情"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM styles WHERE id = ?", (style_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="风格不存在")
        
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "target_duration": row[3],
            "max_clips": row[4],
            "content_types": json.loads(row[5] or '[]'),
            "rules": json.loads(row[6] or '{}'),
            "created_at": row[7],
            "updated_at": row[8],
            "content_guidelines": row[9] or "",
            "keep_rules": row[10] or "",
            "remove_rules": row[11] or "",
            "style_positioning": row[12] or "",
            "subtitle_config": json.loads(row[13]) if row[13] else None
        }
    finally:
        db.close()


@router.post("/styles", response_model=StyleResponse)
async def create_style(style: StyleCreate):
    """创建新风格"""
    db = get_db()
    try:
        style_id = f"style_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()
        
        cursor = db.cursor()
        cursor.execute("""
        INSERT INTO styles (id, name, description, target_duration, max_clips, content_types, rules, created_at, updated_at, content_guidelines, keep_rules, remove_rules, style_positioning, subtitle_config)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            style_id,
            style.name,
            style.description,
            style.target_duration,
            style.max_clips,
            json.dumps(style.content_types, ensure_ascii=False),
            json.dumps(style.rules, ensure_ascii=False),
            now,
            now,
            style.content_guidelines or "",
            style.keep_rules or "",
            style.remove_rules or "",
            style.style_positioning or "",
            json.dumps(style.subtitle_config, ensure_ascii=False) if style.subtitle_config else None
        ))
        db.commit()
        
        return {
            "id": style_id,
            "name": style.name,
            "description": style.description,
            "target_duration": style.target_duration,
            "max_clips": style.max_clips,
            "content_types": style.content_types,
            "rules": style.rules,
            "created_at": now,
            "updated_at": now,
            "content_guidelines": style.content_guidelines or "",
            "keep_rules": style.keep_rules or "",
            "remove_rules": style.remove_rules or "",
            "style_positioning": style.style_positioning or "",
            "subtitle_config": style.subtitle_config
        }
    finally:
        db.close()


@router.put("/styles/{style_id}", response_model=StyleResponse)
async def update_style(style_id: str, style: StyleUpdate):
    """更新风格"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM styles WHERE id = ?", (style_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="风格不存在")
        
        updates = []
        values = []
        
        if style.name is not None:
            updates.append("name = ?")
            values.append(style.name)
        if style.description is not None:
            updates.append("description = ?")
            values.append(style.description)
        if style.target_duration is not None:
            updates.append("target_duration = ?")
            values.append(style.target_duration)
        if style.max_clips is not None:
            updates.append("max_clips = ?")
            values.append(style.max_clips)
        if style.content_types is not None:
            updates.append("content_types = ?")
            values.append(json.dumps(style.content_types, ensure_ascii=False))
        if style.rules is not None:
            updates.append("rules = ?")
            values.append(json.dumps(style.rules, ensure_ascii=False))
        if style.content_guidelines is not None:
            updates.append("content_guidelines = ?")
            values.append(style.content_guidelines)
        if style.keep_rules is not None:
            updates.append("keep_rules = ?")
            values.append(style.keep_rules)
        if style.remove_rules is not None:
            updates.append("remove_rules = ?")
            values.append(style.remove_rules)
        if style.style_positioning is not None:
            updates.append("style_positioning = ?")
            values.append(style.style_positioning)
        if style.subtitle_config is not None:
            updates.append("subtitle_config = ?")
            values.append(json.dumps(style.subtitle_config, ensure_ascii=False) if style.subtitle_config else None)
        
        if updates:
            updates.append("updated_at = ?")
            values.append(datetime.now().isoformat())
            values.append(style_id)
            
            cursor.execute(f"UPDATE styles SET {', '.join(updates)} WHERE id = ?", values)
            db.commit()
        
        cursor.execute("SELECT * FROM styles WHERE id = ?", (style_id,))
        row = cursor.fetchone()
        
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2] or "",
            "target_duration": row[3],
            "max_clips": row[4],
            "content_types": json.loads(row[5] or '[]'),
            "rules": json.loads(row[6] or '{}'),
            "created_at": row[7],
            "updated_at": row[8],
            "content_guidelines": row[9] or "",
            "keep_rules": row[10] or "",
            "remove_rules": row[11] or "",
            "style_positioning": row[12] or "",
            "subtitle_config": json.loads(row[13]) if row[13] else None
        }
    finally:
        db.close()


@router.delete("/styles/{style_id}")
async def delete_style(style_id: str):
    """删除风格"""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("DELETE FROM styles WHERE id = ?", (style_id,))
        db.commit()
        
        return {"message": "风格已删除"}
    finally:
        db.close()
