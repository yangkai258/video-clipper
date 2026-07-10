"""混剪项目独立 ORM 模型 (v2.2.3 完全跟切片项目分开)

跟切片项目 db 完全分离, Base 用 MixBase (跟 database.py 的 Base 区分),
不要在同一个 session 混用两个 Base 的表.

表:
  - mix_projects: 混剪项目主表 (跟切片 Project 字段不同, 不复用)
  - mix_source_clips: 混剪引用了哪些 source clips + 拼接顺序 + 脚本文本 + 匹配分
  - mix_tasks: 混剪任务进度 (跟切片 Task 类似, 但 task_type='mix_processing')

db 文件:
  - data/video_clipper_mix.db (release) / video_clipper_mix_beta.db (beta)
"""
import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Text, Integer, Float, ForeignKey, DateTime, JSON,
)
from sqlalchemy.orm import declarative_base, relationship

# 独立 Base, 跟切片项目 database.Base 区分
MixBase = declarative_base()


def _uuid_str() -> str:
    return str(_uuid.uuid4())


class MixProject(MixBase):
    """混剪项目"""
    __tablename__ = "mix_projects"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")

    # 状态: pending / processing / completed / failed
    status = Column(String(50), default="pending")
    # 软删除
    deleted_at = Column(DateTime, nullable=True)

    # 用户输入
    script_text = Column(Text, default="")  # 直播脚本原文
    target_duration_seconds = Column(Integer, default=60)  # 30/60/180/300

    # LLM 处理结果 (中间产物, 调试用)
    script_segments = Column(JSON, default=list)  # [{position, text, keywords}]

    # 输出
    output_video_path = Column(String(512))
    video_size = Column(Integer, default=0)
    video_duration = Column(Float, default=0.0)
    video_width = Column(Integer, nullable=True)
    video_height = Column(Integer, nullable=True)
    # v2.2.4: 缩略图路径 (output/thumbnail.jpg, 列表 card 用)
    thumbnail_path = Column(String(512), nullable=True)

    # 字幕样式 (跟切片项目一致, 用户偏好同步)
    subtitle_style = Column(JSON, default=dict)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # 关系
    source_clips = relationship(
        "MixSourceClip", back_populates="mix_project",
        cascade="all, delete-orphan",
        order_by="MixSourceClip.position",
    )
    tasks = relationship(
        "MixTask", back_populates="mix_project",
        cascade="all, delete-orphan",
    )


class MixSourceClip(MixBase):
    """混剪引用的 source clip

    - mix_project_id: 哪个混剪项目
    - source_clip_id: 源 clip id (从切片 db 查, 不在 mix db 存 detail)
    - source_project_id: 源项目 id (冗余便于查询)
    - source_project_name: 源项目名 (冗余, mix 项目展示用, 不用 join 切片 db)
    - position: 拼接顺序 0/1/2/...
    - script_segment_text: 对应的脚本片段文本 (烧字幕用)
    - keywords: 脚本片段的关键词
    - match_score: LLM/关键词 匹配分 0-1
    - source_start/source_end/duration: 从 source clip 上截取的起止 + 时长
    """
    __tablename__ = "mix_source_clips"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    mix_project_id = Column(String(36), ForeignKey("mix_projects.id"), nullable=False)

    # 来源 clip 信息 (冗余存, 不 join 切片 db)
    source_clip_id = Column(String(36), nullable=False)
    source_project_id = Column(String(36), nullable=False)
    source_project_name = Column(String(255), default="")
    source_clip_title = Column(String(512), default="")
    # v2.2.5: 来源类型 — 'project' (切片项目 clip) / 'library' (资源库 clip)
    source_type = Column(String(20), default="project")

    # 拼接顺序 + 脚本匹配
    position = Column(Integer, default=0)
    script_segment_text = Column(Text, default="")
    keywords = Column(JSON, default=list)
    match_score = Column(Float, default=0.0)

    # 时间范围 (从 source clip 上截取的)
    source_start = Column(Float, default=0.0)
    source_end = Column(Float, default=0.0)
    duration = Column(Float, default=0.0)

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    mix_project = relationship("MixProject", back_populates="source_clips")


class MixTask(MixBase):
    """混剪任务进度 (跟切片 Task 类似)

    task_type='mix_processing'
    progress 0-100
    current_step 显示给用户的中文标签
    """
    __tablename__ = "mix_tasks"

    id = Column(String(36), primary_key=True, default=_uuid_str)
    mix_project_id = Column(String(36), ForeignKey("mix_projects.id"), nullable=False)

    # 任务元数据
    task_type = Column(String(50), default="mix_processing")
    name = Column(String(255), default="混剪处理")
    description = Column(Text, default="")

    # 状态 + 进度
    status = Column(String(50), default="pending")  # pending / running / completed / failed
    progress = Column(Integer, default=0)
    current_step = Column(String(255), default="")

    # Celery task id
    celery_task_id = Column(String(36))

    # 错误信息
    error_message = Column(Text, default="")

    # 字幕状态 (跟切片 Task 一致)
    subtitle_status = Column(String(50), default="")
    subtitle_error = Column(Text, default="")

    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress_changed_at = Column(DateTime, nullable=True)

    # 耗时归集 (跟切片 Task 一致)
    estimated_total_at_start_seconds = Column(Float, nullable=True)
    actual_total_seconds = Column(Float, nullable=True)

    # 关系
    mix_project = relationship("MixProject", back_populates="tasks")