"""FastAPI 应用"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pathlib import Path

from .core.config import settings
from .core.database import init_db
from .api import projects, clips, collections, styles, admin, user_preferences, uploads, watch_folders, mix


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    # 启动时初始化（数据库表已存在则跳过）
    yield
    # 关闭时清理


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
app.include_router(clips.router, prefix="/api/v1/clips", tags=["clips"])
app.include_router(collections.router, prefix="/api/v1/collections", tags=["collections"])
app.include_router(styles.router, prefix="/api/v1", tags=["styles"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])
app.include_router(user_preferences.router, prefix="/api/v1", tags=["preferences"])
app.include_router(uploads.router, prefix="/api/v1", tags=["uploads"])
app.include_router(watch_folders.router, prefix="/api/v1", tags=["watch-folders"])
app.include_router(mix.router, prefix="/api/v1", tags=["mix"])


@app.get("/api/v1/thumbnails/{project_id}.jpg")
async def get_project_thumbnail(project_id: str):
    """项目封面缩略图 (cut_clips 完成后抽帧生成)"""
    # 防路径穿越
    if "/" in project_id or ".." in project_id or not project_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(400, "invalid project_id")
    data_dir = Path(settings.DATA_DIR) if hasattr(settings, "DATA_DIR") else Path("data")
    thumb_path = data_dir / "projects" / project_id / "output" / "thumbnails" / f"{project_id}.jpg"
    if not thumb_path.exists():
        raise HTTPException(404, "thumbnail not generated")
    return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/v1/clip-thumbs/{project_id}/{clip_name}.jpg")
async def get_clip_thumbnail(project_id: str, clip_name: str):
    """单片缩略图 (cut_clips 完成后用中段帧生成)
    clip_name 不能含 / 或 ..
    """
    if "/" in project_id or ".." in project_id or "/" in clip_name or ".." in clip_name:
        raise HTTPException(400, "invalid path")
    data_dir = Path(settings.DATA_DIR) if hasattr(settings, "DATA_DIR") else Path("data")
    thumb_path = data_dir / "projects" / project_id / "output" / "thumbnails" / "clips" / f"{clip_name}.jpg"
    if not thumb_path.exists():
        raise HTTPException(404, "clip thumbnail not generated")
    return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy"}
