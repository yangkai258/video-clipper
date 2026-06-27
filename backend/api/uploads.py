"""分片上传 API（断点续传 + 进度显示）

流程：
1. POST /uploads/init        → 返回 upload_id（保留到本地 storage）
2. PUT  /uploads/{uid}/chunk?offset=N&total=ALL → 上传 1 片
3. GET  /uploads/{uid}/status → 查已传 offset（断点续传时调用）
4. POST /uploads/{uid}/complete → 合并 + 创建 project
"""
import json
import logging
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import Depends

from ..core.config import settings
from ..core.database import get_db
from ..models.database import Project
from .projects import _get_last_subtitle_style  # 复用：从用户偏好读字幕配置

logger = logging.getLogger(__name__)

router = APIRouter()

# 临时上传根目录：data/.uploads/{upload_id}/
UPLOADS_DIR = settings.PROJECTS_DIR.parent / ".uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 元数据文件
META_SUFFIX = ".meta.json"
# 分片文件命名：{offset:012d}.part
PART_SUFFIX = ".part"
# chunk 大小（前端默认 5MB；cloudflared 30s timeout 下建议 1MB）
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024
# 上传大小上限：fallback 默认 5GB（如果 settings.MAX_UPLOAD_SIZE 未配）
DEFAULT_MAX_UPLOAD_SIZE = 5 * 1024 * 1024 * 1024


def _upload_dir(upload_id: str) -> Path:
    return UPLOADS_DIR / upload_id


def _meta_path(upload_id: str) -> Path:
    return _upload_dir(upload_id) / f"upload{META_SUFFIX}"


def _part_path(upload_id: str, offset: int) -> Path:
    return _upload_dir(upload_id) / f"{offset:012d}{PART_SUFFIX}"


@router.post("/uploads/init")
async def init_upload(
    name: str = Form(...),
    description: str = Form(default=""),
    filename: str = Form(...),
    total_size: int = Form(...),
):
    """初始化上传会话

    Returns:
        upload_id: 用于后续分片上传
        chunk_size: 推荐分片大小（前端可自定义）
        existing_offset: 已上传偏移（0 表示新会话）
    """
    # 验证文件类型
    ext = filename.split(".")[-1].lower()
    if not settings.is_allowed_video_ext(ext):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的视频格式：{ext}。支持的格式：{[e.lstrip('.') for e in settings.ALLOWED_VIDEO_EXTENSIONS]}"
        )

    # 验证 total_size（用 settings.MAX_UPLOAD_SIZE，未配则 fallback 到 5GB）
    max_size = getattr(settings, "MAX_UPLOAD_SIZE", DEFAULT_MAX_UPLOAD_SIZE) or DEFAULT_MAX_UPLOAD_SIZE
    if total_size <= 0 or total_size > max_size:
        raise HTTPException(status_code=400, detail=f"无效的文件大小：{total_size}（上限 {max_size // 1024 // 1024} MB）")

    upload_id = f"up_{uuid.uuid4().hex[:16]}"
    udir = _upload_dir(upload_id)
    udir.mkdir(parents=True, exist_ok=True)

    # 写元数据
    meta = {
        "upload_id": upload_id,
        "name": name,
        "description": description,
        "filename": filename,
        "total_size": total_size,
        "created_at": time.time(),
        "completed": False,
    }
    _meta_path(upload_id).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    logger.info(f"init_upload: {upload_id} name={name} filename={filename} total={total_size}")
    return {
        "upload_id": upload_id,
        "chunk_size": DEFAULT_CHUNK_SIZE,
        "existing_offset": 0,
    }


@router.get("/uploads/{upload_id}/status")
async def upload_status(upload_id: str):
    """查询已上传偏移（断点续传用）"""
    mpath = _meta_path(upload_id)
    if not mpath.exists():
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    meta = json.loads(mpath.read_text(encoding="utf-8"))
    # 计算实际已上传字节数（扫描所有 part 文件）
    received = _count_received_bytes(upload_id)
    return {
        "upload_id": upload_id,
        "total_size": meta["total_size"],
        "received_bytes": received,
        "completed": meta.get("completed", False),
    }


def _count_received_bytes(upload_id: str) -> int:
    """扫描 part 文件，累加到第一个 gap 处（断点续传用）

    算法：
    - 所有 part 文件按 offset 排序
    - 第一片必须 offset=0，否则视为 0
    - 从 offset=0 开始累加，遇到 offset 不连续的 part 停止
    """
    udir = _upload_dir(upload_id)
    if not udir.exists():
        return 0

    # 文件名格式：{offset:012d}.part → split(".")[0] 拿 offset
    parts = sorted(udir.glob(f"*{PART_SUFFIX}"), key=lambda p: int(p.name.split(".")[0]))
    if not parts:
        return 0

    received = 0
    expected_next = 0
    for p in parts:
        offset = int(p.name.split(".")[0])
        if offset != expected_next:
            break  # gap：连续中断
        received += p.stat().st_size
        expected_next = offset + p.stat().st_size
    return received


@router.put("/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    offset: int = Query(..., ge=0),
    chunk: UploadFile = File(...),
):
    """接收 1 个分片

    Args:
        upload_id: 初始化时返回的 ID
        offset: 本片在文件中的起始字节位置（0-based）
        chunk: 分片内容（HTTP body）
    """
    mpath = _meta_path(upload_id)
    if not mpath.exists():
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    meta = json.loads(mpath.read_text(encoding="utf-8"))
    if meta.get("completed"):
        raise HTTPException(status_code=400, detail="上传已完成，不能再传分片")

    # offset 校验：offset 必须在 [0, total_size) 范围内
    # 防止恶意客户端声明 offset=total_size 然后写 0 字节造成混乱
    if offset < 0 or offset >= meta["total_size"]:
        raise HTTPException(status_code=400, detail=f"offset 超出文件大小：{offset} >= {meta['total_size']}")

    # 写 part 文件（直接读完，避免 while 循环的隐藏 bug）
    part_file = _part_path(upload_id, offset)
    try:
        data = await chunk.read()  # 一次读完整个 body
        if not data:
            raise HTTPException(status_code=400, detail="空的分片")
        with open(part_file, "wb") as f:
            f.write(data)
        bytes_written = len(data)
    finally:
        await chunk.close()

    received = _count_received_bytes(upload_id)
    logger.info(f"chunk {upload_id}: offset={offset} size={bytes_written} received={received}/{meta['total_size']}")
    return {
        "upload_id": upload_id,
        "chunk_offset": offset,
        "chunk_size": bytes_written,
        "received_bytes": received,
        "total_size": meta["total_size"],
    }


@router.post("/uploads/{upload_id}/complete")
async def complete_upload(upload_id: str, db: AsyncSession = Depends(get_db)):
    """合并分片 + 创建项目"""
    mpath = _meta_path(upload_id)
    if not mpath.exists():
        raise HTTPException(status_code=404, detail="上传会话不存在或已过期")

    meta = json.loads(mpath.read_text(encoding="utf-8"))
    if meta.get("completed"):
        raise HTTPException(status_code=400, detail="上传已完成")

    # 验证完整性
    received = _count_received_bytes(upload_id)
    if received != meta["total_size"]:
        raise HTTPException(
            status_code=400,
            detail=f"分片不完整：已传 {received}/{meta['total_size']} 字节",
        )

    # 合并：按 offset 顺序拼接
    project_id = str(uuid.uuid4())
    project_dir = settings.PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    video_path = project_dir / "raw" / "input.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)

    udir = _upload_dir(upload_id)
    parts = sorted(udir.glob(f"*{PART_SUFFIX}"), key=lambda p: int(p.name.split(".")[0]))
    written = 0
    with open(video_path, "wb") as out:
        for p in parts:
            with open(p, "rb") as inp:
                shutil.copyfileobj(inp, out, length=1024 * 1024)
            written += p.stat().st_size
    if written != meta["total_size"]:
        # 异常：清理
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=500,
            detail=f"合并后大小异常：{written}/{meta['total_size']}",
        )

    # 标记完成
    meta["completed"] = True
    meta["completed_at"] = time.time()
    meta["project_id"] = project_id
    _meta_path(upload_id).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # 清理 part 文件（保留 meta 以备查询）
    for p in parts:
        try:
            p.unlink()
        except OSError:
            pass

    # 校验文件有效性（防止截断的假文件进入处理流程）
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(video_path)],
            capture_output=True, text=True, timeout=30
        )
        duration_str = probe.stdout.strip()
        if not duration_str or float(duration_str) <= 0:
            # 文件不可读 / 无 moov atom / 截断
            shutil.rmtree(project_dir, ignore_errors=True)
            raise HTTPException(
                status_code=400,
                detail=f"文件无效：ffprobe 读不到时长（可能上传被截断、moov atom 缺失）",
            )
        video_duration = float(duration_str)
    except HTTPException:
        raise
    except Exception as e:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise HTTPException(
            status_code=400,
            detail=f"文件校验失败：{e}",
        )

    # 创建项目记录
    subtitle_style = await _get_last_subtitle_style(db)
    project = Project(
        id=project_id,
        name=meta["name"],
        description=meta.get("description", ""),
        status="pending",
        video_path=str(video_path.relative_to(settings.PROJECTS_DIR)),
        video_size=meta["total_size"],
        video_duration=video_duration,
        processing_config={"subtitle_style": subtitle_style} if subtitle_style else {},
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    logger.info(f"complete_upload: {upload_id} → project={project_id} size={meta['total_size']}")
    return {
        "message": "项目创建成功",
        "project_id": project_id,
        "name": project.name,
        "video_size": meta["total_size"],
    }


@router.delete("/uploads/{upload_id}")
async def cancel_upload(upload_id: str):
    """取消上传 + 清理临时文件"""
    udir = _upload_dir(upload_id)
    if udir.exists():
        shutil.rmtree(udir, ignore_errors=True)
    return {"message": "已取消", "upload_id": upload_id}
