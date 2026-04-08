"""应用配置"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    
    # 基础配置
    APP_NAME: str = "Video Clipper"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 路径配置
    BASE_DIR: Path = Path(__file__).parent.parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    PROJECTS_DIR: Path = DATA_DIR / "projects"
    CACHE_DIR: Path = DATA_DIR / "cache"
    
    # 数据库配置
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/video_clipper.db")
    
    # Celery 配置
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
    
    # AI 配置
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    MODEL_NAME: str = "qwen3.5-plus"
    
    # 语音识别配置
    SPEECH_RECOGNITION_METHOD: str = "auto"
    BCUT_SESSDATA: str = os.getenv("BCUT_SESSDATA", "")
    
    # 视频处理配置
    VIDEO_OUTPUT_FORMAT: str = "mp4"
    VIDEO_CODEC: str = "libx264"
    VIDEO_PRESET: str = "ultrafast"
    VIDEO_CRF: int = 28
    AUDIO_CODEC: str = "aac"
    AUDIO_BITRATE: str = "128k"
    
    # 切片配置
    MIN_CLIP_DURATION: int = 30
    MAX_CLIP_DURATION: int = 600
    MIN_SCORE_THRESHOLD: float = 0.7
    
    # 上传配置
    MAX_UPLOAD_SIZE: int = 2 * 1024 * 1024 * 1024
    ALLOWED_VIDEO_EXTENSIONS: list = ["mp4", "mov", "avi", "mkv", "flv", "webm"]
    
    class Config:
        extra = "ignore"


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
