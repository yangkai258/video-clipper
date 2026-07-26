"""数据库模型"""

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


def _uuid_str() -> str:
    """默认 id 生成器 (跟 mix.py 风格一致)"""
    return str(_uuid.uuid4())


class Project(Base):
    """项目模型"""

    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(
        String(50), default="pending"
    )  # pending, processing, completed, failed
    deleted_at = Column(
        DateTime, nullable=True
    )  # 软删除：NULL = 正常，时间戳 = 进入回收站

    # 视频文件
    video_path = Column(String(512))
    video_duration = Column(Float, default=0.0)
    video_size = Column(Integer, default=0)
    # 视频宽高 (v2.1.26: 让前端区分横/竖屏, 避免竖屏裁切)
    video_width = Column(Integer, nullable=True)
    video_height = Column(Integer, nullable=True)

    # 字幕文件
    subtitle_path = Column(String(512))
    subtitle_method = Column(String(50), default="auto")

    # 处理配置
    processing_config = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # 关系
    clips = relationship("Clip", back_populates="project", cascade="all, delete-orphan")
    collections = relationship(
        "Collection", back_populates="project", cascade="all, delete-orphan"
    )
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Clip(Base):
    """切片模型"""

    __tablename__ = "clips"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)

    # 切片信息
    title = Column(String(512))
    description = Column(Text, default="")

    # 时间范围
    start_time = Column(Float, default=0.0)
    end_time = Column(Float, default=0.0)
    duration = Column(Float, default=0.0)

    # 评分
    score = Column(Float, default=0.0)
    score_reason = Column(Text, default="")

    # 文件路径
    video_path = Column(String(512))
    thumbnail_path = Column(String(512))

    # 视频宽高 (v2.1.26: 让前端区分横/竖屏, 避免竖屏裁切)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    # 元数据
    clip_metadata = Column("metadata", JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    project = relationship("Project", back_populates="clips")


class Collection(Base):
    """合集模型"""

    __tablename__ = "collections"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)

    # 合集信息
    title = Column(String(512))
    description = Column(Text, default="")

    # 包含的切片
    clip_ids = Column(JSON, default=list)

    # 文件路径
    video_path = Column(String(512))

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    project = relationship("Project", back_populates="collections")


class WatchFolder(Base):
    """监控文件夹：定期扫描，发现新视频自动上传处理"""

    __tablename__ = "watch_folders"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)  # 显示名
    path = Column(String(1024), nullable=False)  # 监控的文件夹绝对路径
    style_id = Column(String(64), nullable=True)  # 关联的 style_id（自定义风格）
    style_config = Column(JSON, nullable=True)  # 完整 style 配置（presets 或自定义）
    with_subtitle = Column(Boolean, default=True)
    scan_interval_seconds = Column(Integer, default=60)  # 扫描间隔
    source_action = Column(String(20), default="delete")  # delete / keep / move_done
    enabled = Column(Boolean, default=True)
    last_scan_at = Column(DateTime, nullable=True)
    last_found_count = Column(Integer, default=0)  # 上次扫描发现的新文件数
    last_processed_at = Column(DateTime, nullable=True)
    processed_files = Column(JSON, default=dict)  # {"file.mp4": mtime, ...} 去重用
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    """任务模型"""

    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)

    # 任务信息
    task_type = Column(String(50))  # video_processing, subtitle_generation, etc.
    name = Column(String(255))
    description = Column(Text, default="")

    # 任务状态
    status = Column(
        String(50), default="pending"
    )  # pending, running, completed, failed
    progress = Column(Integer, default=0)
    current_step = Column(String(255), default="")

    # Celery 任务 ID
    celery_task_id = Column(String(36))

    # 错误信息
    error_message = Column(Text, default="")

    # 结果数据
    result_data = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    # 最近一次进度/心跳变化时间, task_health watchdog 用来判断真卡死
    progress_changed_at = Column(DateTime, nullable=True)
    # 预估 vs 实际耗时 (v2.2.1 数据归集, 8f1ec24 加; 4afb777 refactor 漏 model 字段 2 个月)
    estimated_total_at_start_seconds = Column(Float, nullable=True)
    actual_total_seconds = Column(Float, nullable=True)
    # 字幕子任务状态 (v2.2.2 fail-tolerant, 9c84a6f 加)
    subtitle_status = Column(String(50), default="", nullable=True)
    subtitle_error = Column(Text, default="", nullable=True)

    # 关系
    project = relationship("Project", back_populates="tasks")


class Style(Base):
    """切片风格（自定义策略）"""

    __tablename__ = "styles"

    id = Column(String(64), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    target_duration = Column(Integer, default=60)
    max_clips = Column(Integer, default=20)
    content_types = Column(JSON, default=list)
    rules = Column(JSON, default=dict)
    # 风格规则详情（用于 prompt 工程）
    content_guidelines = Column(Text, default="")
    keep_rules = Column(Text, default="")
    remove_rules = Column(Text, default="")
    style_positioning = Column(Text, default="")
    # 字幕配置
    subtitle_config = Column(JSON, nullable=True)
    # 选这个 Style 切新 project 时, snapshot 复制到 project.processing_config
    # 默认前 10s / 后 5s (用户偏好), 后续可改
    # v2.1.53 4afb777 refactor 漏了, db schema drift 2 个月, 2026-07-26 触发 AttributeError 修
    pre_padding_seconds = Column(Float, default=10.0)
    post_padding_seconds = Column(Float, default=5.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserPreference(Base):
    """用户偏好设置（key-value 风格）"""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), default="default", unique=True)
    last_used_subtitle_style = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceClip(Base):
    """资源库 (v2.2.5)

    跨项目长期保留的"金句片段" + 用户主动上传的素材.
    独立于切片项目 Project/Clip — 项目软删 30 天真删不影响这里.

    存储: data/resources/<id>.mp4 + <id>.jpg (跟项目 output 完全分离).
    """

    __tablename__ = "resource_clips"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)  # data/resources/<id>.mp4
    thumbnail_path = Column(String(512), nullable=True)  # data/resources/<id>.jpg
    duration = Column(Float, default=0.0)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    size = Column(Integer, default=0)
    source_type = Column(String(20), nullable=False)  # "upload" / "from_project"
    source_project_id = Column(String(36), nullable=True)
    source_clip_id = Column(String(36), nullable=True)
    source_project_name = Column(String(255), nullable=True)  # 冗余便于展示
    tags = Column(JSON, default=list)  # [{"category": "防水", "score": 0.85}, ...]
    description = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)  # 软删, NULL = 正常
