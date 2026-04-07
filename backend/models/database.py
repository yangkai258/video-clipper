"""数据库模型"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Project(Base):
    """项目模型"""
    __tablename__ = "projects"
    
    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    status = Column(String(50), default="pending")  # pending, processing, completed, failed
    
    # 视频文件
    video_path = Column(String(512))
    video_duration = Column(Float, default=0.0)
    video_size = Column(Integer, default=0)
    
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
    collections = relationship("Collection", back_populates="project", cascade="all, delete-orphan")
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
    status = Column(String(50), default="pending")  # pending, running, completed, failed
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
    
    # 关系
    project = relationship("Project", back_populates="tasks")
