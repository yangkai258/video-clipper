"""应用配置"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置

    自动从 BASE_DIR/.env 读取环境变量 (v2.1.24 fix: 之前没指定 _env_file,
    手动启动 uvicorn 时 MINIMAX_API_KEY 等 key 读不到, LLM 调用全失败)
    """
    
    # 基础配置
    APP_NAME: str = "Video Clipper"
    # v2.2.12: bump APP_VERSION 跟 git tag 同步 (之前 v1.0.0 卡 1 年)
    # admin/system endpoint 用这个返给前端 (/admin/system → version 字段)
    APP_VERSION: str = "v2.2.36"
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
    
    # Celery Worker 队列配置
    CELERY_QUEUE_NAME: str = os.getenv("CELERY_QUEUE_NAME", "processing")
    
    # AI 配置 - MiniMax（主）
    MINIMAX_API_KEY: str = os.getenv("MINIMAX_API_KEY", "")
    MINIMAX_BASE_URL: str = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    MINIMAX_MODEL: str = os.getenv("MINIMAX_MODEL", "MiniMax-Text-01")

    # AI 配置 - DashScope（保留兼容，备用）
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    MODEL_NAME: str = os.getenv("LEGACY_MODEL_NAME", "qwen3.5-plus")  # 旧字段，保留兼容
    
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
    
    # 上传配置（extensions 标准化为小写不带点）
    MAX_UPLOAD_SIZE: int = 5 * 1024 * 1024 * 1024  # 5GB
    ALLOWED_VIDEO_EXTENSIONS: tuple = (".mp4", ".mov", ".avi", ".mkv", ".flv", ".webm", ".m4v")

    def is_allowed_video_ext(self, ext: str) -> bool:
        """判断扩展名是否允许（大小写不敏感，自动补点）"""
        ext = ext.lower().lstrip(".")
        return f".{ext}" in self.ALLOWED_VIDEO_EXTENSIONS
    
    class Config:
        env_file = str(Path(__file__).parent.parent.parent / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
settings.PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)


# v2.2.22: encrypted secrets 启动集成
# 流程: data/.env.encrypted 存在 + ENV_MASTER_KEY 在 env → decrypt 写 .env
# 然后 pydantic_settings 读 .env (跟之前一致)
# 没 master key → 警告走明文 .env (本地 dev 模式, 不阻塞)
def _load_encrypted_secrets() -> None:
    """启动时从 data/.env.encrypted 解密 secrets 写到 .env (如果 .env 还不存在).

    触发条件: data/.env.encrypted 存在 + ENV_MASTER_KEY env 有 + .env 不存在
    否则跳过 (明文 .env 优先, 走 pydantic_settings 原生读).
    """
    import logging as _logging
    import os as _os
    from pathlib import Path

    _logger = _logging.getLogger(__name__)

    encrypted_path = settings.DATA_DIR / ".env.encrypted"
    env_path = Path(__file__).parent.parent.parent / ".env"

    if not encrypted_path.exists():
        return  # 没 encrypted, 走明文

    if env_path.exists() and env_path.stat().st_size > 0:
        # 明文 .env 已存在 (本地 dev), 跳过
        return

    master_key = _os.environ.get("ENV_MASTER_KEY")
    if not master_key:
        _logger.warning(
            "data/.env.encrypted 存在但 ENV_MASTER_KEY 未设, "
            "跳过解密 — 当前用 .env 或 system env (本地 dev 模式)",
        )
        return

    try:
        from cryptography.fernet import Fernet, InvalidToken
        content = encrypted_path.read_text(encoding="utf-8")
        token = "\n".join(l for l in content.splitlines() if not l.startswith("#")).strip()
        plaintext = Fernet(master_key.encode()).decrypt(token.encode()).decode()
        env_path.write_text(plaintext, encoding="utf-8")
        _logger.info(f"已从 {encrypted_path.relative_to(settings.DATA_DIR.parent.parent)} 解密 secrets → {env_path.name}")
    except InvalidToken:
        _logger.error("ENV_MASTER_KEY 错, 无法解密 .env.encrypted — 检查 1Password / Keychain")
    except Exception as e:  # noqa: BLE001 — decrypt 可能 IO/permission 错, 静默警告不阻塞启动
        _logger.error(f"解密 .env.encrypted 失败: {e}")


_load_encrypted_secrets()
