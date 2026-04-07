"""Celery 配置"""
from celery import Celery
from .config import settings


# 创建 Celery 应用
celery_app = Celery(
    "video_clipper",
    broker="redis://127.0.0.1:6379/0",
    backend="redis://127.0.0.1:6379/0",
    include=["backend.tasks.processing"]
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 小时超时（适应长视频处理）
    worker_prefetch_multiplier=1,
    task_routes={
        "backend.tasks.processing.*": {"queue": "processing"},
    },
)
