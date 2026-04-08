"""Celery 配置"""
import os
from celery import Celery
from .config import settings


# 从环境变量获取配置（支持版本隔离）
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/0")
CELERY_QUEUE_NAME = os.getenv("CELERY_QUEUE_NAME", "processing")

# 创建 Celery 应用
celery_app = Celery(
    "video_clipper",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
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
        "backend.tasks.processing.*": {"queue": CELERY_QUEUE_NAME},
    },
)
