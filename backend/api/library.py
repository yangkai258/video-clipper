"""资源库 (Resource Library) API — v2.2.5

跨项目长期保留的"金句片段" + 用户主动上传的素材.
跟切片项目 Project/Clip 完全独立 — 项目软删 30 天真删不影响资源库.

存储: data/resources/<id>.mp4 + <id>.jpg
端点:
  GET    /api/v1/library                 列表 (默认不含 deleted, support ?search=&source_type=)
  POST   /api/v1/library/upload          主动上传 (multipart, field name=file, 接收 mp4)
  POST   /api/v1/library/from-clip       从切片项目抽 clip 进资源库
  GET    /api/v1/library/videos/{id}     视频流 (FileResponse)
  GET    /api/v1/library/thumbnails/{id} 缩略图 (有就返, 没有 404)
  DELETE /api/v1/library/{id}            软删 (删 mp4 + jpg + 设 deleted_at)
"""
import logging
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db, sync_get_db
from ..models.database import Clip, Project, ResourceClip
from ..services.library_tag_service import generate_tags_for_resource

router = APIRouter(tags=["library"])
logger = logging.getLogger(__name__)


# ──────────────────────────── v2.2.19: auto-tag background helper ────────────────────────────

def _auto_tag_in_thread(resource_id: str) -> None:
    """BackgroundTask 触发的 auto-tag (跑在 thread pool, 不阻塞 async endpoint).

    失败静默 — 主流程已完成, auto-tag 是 best-effort polish.
    user 可手动调 POST /library/{id}/auto-tag retry.
    """
    try:
        tags = generate_tags_for_resource(resource_id)
        logger.info(f"library auto-tag background: id={resource_id} tags={tags}")
    except Exception as e:
        logger.warning(f"library auto-tag background 失败 (非致命): id={resource_id} err={e}")


# ──────────────────────────── 路径 helper ────────────────────────────

def _resources_dir() -> Path:
    """资源库存储目录 (跟切片项目 output 完全分离)"""
    from ..core.config import settings
    base = Path(settings.DATA_DIR) if hasattr(settings, "DATA_DIR") else Path("data")
    d = base / "resources"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_id(resource_id: str) -> str:
    """防路径穿越: 只允许 uuid 字符串"""
    if "/" in resource_id or ".." in resource_id or "\\" in resource_id:
        raise HTTPException(status_code=400, detail="invalid resource id")
    # uuid4 hex 带 dash: 36 chars
    if not resource_id.replace("-", "").isalnum() or len(resource_id) > 64:
        raise HTTPException(status_code=400, detail="invalid resource id")
    return resource_id


# ──────────────────────────── ffprobe / ffmpeg ────────────────────────────

def _probe_video_metadata(video_path: Path) -> dict:
    """ffprobe 抽 duration + width/height

    Returns: {"duration": float, "width": int, "height": int}
    失败字段填空, 不抛异常 (容错 — 没 ffprobe 也不让上传挂掉).
    """
    result = {"duration": 0.0, "width": None, "height": None}
    try:
        # duration
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        if p.returncode == 0 and p.stdout.strip():
            try:
                d = float(p.stdout.strip())
                if d > 0:
                    result["duration"] = d
            except ValueError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"ffprobe duration 失败: {e}")

    try:
        # dimensions
        p = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-of", "csv=p=0", str(video_path)],
            capture_output=True, text=True, timeout=30,
        )
        if p.returncode == 0 and p.stdout.strip():
            parts = p.stdout.strip().split(",")
            if len(parts) == 2:
                try:
                    w, h = int(parts[0]), int(parts[1])
                    if w > 0 and h > 0:
                        result["width"] = w
                        result["height"] = h
                except ValueError:
                    pass
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"ffprobe dimensions 失败: {e}")

    return result


def _generate_thumbnail(video_path: Path, thumbnail_path: Path, t_seconds: float = 1.0) -> bool:
    """从视频抽 1s 帧生成 jpg 缩略图. 失败返回 False (不影响主流程)."""
    try:
        # 时长 < t 时 ffmpeg 会报错, fallback 到 0s
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(t_seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=720:-2",
            "-q:v", "3",
            str(thumbnail_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not thumbnail_path.exists():
            # fallback 到 0s
            cmd[2] = "0"
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if r.returncode != 0:
                logger.warning(f"thumbnail ffmpeg 失败: {r.stderr[:200]}")
                return False
        return thumbnail_path.exists()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.warning(f"thumbnail 生成失败: {e}")
        return False


# ──────────────────────────── 序列化 ────────────────────────────

def _serialize(rc: ResourceClip) -> dict:
    """跟 mix API 风格保持一致 — 列表轻量, 详情再扩展"""
    return {
        "id": rc.id,
        "name": rc.name,
        "duration": rc.duration or 0.0,
        "width": rc.width,
        "height": rc.height,
        "size": rc.size or 0,
        "source_type": rc.source_type,
        "source_project_id": rc.source_project_id,
        "source_clip_id": rc.source_clip_id,
        "source_project_name": rc.source_project_name,
        "tags": rc.tags or [],
        "description": rc.description or "",
        "thumbnail_path": rc.thumbnail_path,
        "has_video": bool(rc.file_path and Path(rc.file_path).exists()),
        "created_at": rc.created_at.isoformat() + "Z" if rc.created_at else None,
        "updated_at": rc.updated_at.isoformat() + "Z" if rc.updated_at else None,
    }


# ──────────────────────────── 端点 ────────────────────────────

@router.get("")
async def list_resources(
    search: str | None = None,
    source_type: str | None = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """资源库列表

    Query:
        search: 按 name / description / source_project_name 模糊匹配
        source_type: "upload" / "from_project"
        include_deleted: 是否含软删的 (默认 False)
    """
    query = select(ResourceClip)
    if not include_deleted:
        query = query.where(ResourceClip.deleted_at.is_(None))
    if source_type:
        query = query.where(ResourceClip.source_type == source_type)
    query = query.order_by(ResourceClip.created_at.desc())

    result = await db.execute(query)
    rows = result.scalars().all()

    items = [_serialize(r) for r in rows]

    if search:
        q = search.lower()
        items = [
            it for it in items
            if q in (it["name"] or "").lower()
            or q in (it["description"] or "").lower()
            or q in (it["source_project_name"] or "").lower()
        ]

    # metrics
    upload_count = sum(1 for it in items if it["source_type"] == "upload")
    from_project_count = sum(1 for it in items if it["source_type"] == "from_project")

    return {
        "resources": items,
        "count": len(items),
        "metrics": {
            "total": len(items),
            "upload": upload_count,
            "from_project": from_project_count,
        },
    }


@router.post("/upload")
async def upload_resource(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    description: str | None = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """主动上传 mp4 进资源库 (不走切片流程).

    Form:
        file: 视频文件 (multipart)
        name: 显示名 (默认 = 原 filename 不含扩展)
        description: 可选描述

    自动 ffprobe 拿 metadata + ffmpeg 抽 1s thumbnail.
    """
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="缺少 file")

    ext = (file.filename.split(".")[-1].lower() if "." in file.filename else "")
    if ext and ext not in ("mp4", "mov", "m4v", "webm", "mkv", "avi", "flv"):
        raise HTTPException(status_code=400, detail=f"不支持的格式: .{ext}")

    resource_id = str(uuid.uuid4())
    base_name = name or (file.filename.rsplit(".", 1)[0] if "." in file.filename else file.filename)
    save_name = f"{resource_id}.mp4"  # 统一存 mp4 容器, ffmpeg 友好
    save_path = _resources_dir() / save_name

    # v2.2.11: 上传 size 校验 (P1-2 安全修)
    # uploads.py 走 init endpoint + chunk 10MB, 5GB 上限在 init 时校验
    # library.py 走单次 multipart, 之前 0 校验, 用户能传 100GB 撑爆 disk
    MAX_LIBRARY_SIZE = 5 * 1024 * 1024 * 1024  # 5GB (跟 uploads 一致)

    # 流式写盘
    written = 0
    try:
        with open(save_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)  # 1MB
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_LIBRARY_SIZE:
                    # 提前 break, 避免 100GB 写完再报错
                    out.close()
                    save_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {MAX_LIBRARY_SIZE // 1024 // 1024 // 1024}GB 上限 (已写 {written // 1024 // 1024}MB)",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        # 清理半成品
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"写入失败: {e}")
    finally:
        await file.close()

    if written == 0:
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="空文件")

    # ffprobe metadata
    meta = _probe_video_metadata(save_path)

    # thumbnail (失败不影响主流程, 列表就显示无缩略图)
    thumb_path = _resources_dir() / f"{resource_id}.jpg"
    has_thumb = _generate_thumbnail(save_path, thumb_path, t_seconds=1.0)

    rc = ResourceClip(
        id=resource_id,
        name=base_name,
        file_path=str(save_path),
        thumbnail_path=str(thumb_path) if has_thumb else None,
        duration=meta["duration"],
        width=meta["width"],
        height=meta["height"],
        size=written,
        source_type="upload",
        tags=[],
        description=description or "",
    )
    db.add(rc)
    await db.commit()
    await db.refresh(rc)

    logger.info(f"library upload: id={resource_id} name={base_name} size={written} duration={meta['duration']:.1f}s")

    # v2.2.38: auto-tag 默认关闭 (user 反馈: 抽过来的规则不准, 暂时不用)
    # 留 _auto_tag_in_thread + POST /library/{id}/auto-tag manual endpoint, 想用时手跑
    # background_tasks.add_task(_auto_tag_in_thread, resource_id)
    return _serialize(rc)


@router.post("/from-clip")
async def from_clip_resource(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """从切片项目抽 clip 进资源库.

    Body: {"source_project_id": "...", "source_clip_id": "..."}

    复制 data/projects/<source_project_id>/output/clips/<clip_id>.mp4
    到 data/resources/<new_id>.mp4, 同步 metadata.
    """
    source_project_id = payload.get("source_project_id")
    source_clip_id = payload.get("source_clip_id")
    if not source_project_id or not source_clip_id:
        raise HTTPException(status_code=400, detail="source_project_id 和 source_clip_id 必填")

    # 同步查 source clip (clip 表用同步 session)
    with sync_get_db() as sdb:
        sc = sdb.query(Clip).filter(Clip.id == source_clip_id).first()
        if not sc:
            raise HTTPException(status_code=404, detail=f"source clip {source_clip_id} 不存在")
        sp = sdb.query(Project).filter(Project.id == source_project_id).first()
        if not sp:
            raise HTTPException(status_code=404, detail=f"source project {source_project_id} 不存在")

        # 防路径穿越 + 存在性
        source_video_path = Path(sc.video_path) if sc.video_path else None
        if not source_video_path:
            raise HTTPException(status_code=404, detail=f"source clip video_path 空: {source_clip_id}")
        if not source_video_path.is_absolute():
            # 跟 from-project 保持一致: 拼 data/projects/<project_id>/<video_path>
            source_video_path = (Path("data/projects") / source_project_id / sc.video_path).resolve()
        if not source_video_path.exists():
            raise HTTPException(status_code=404, detail=f"source clip 视频文件不存在: {source_video_path}")

        source_project_name = sp.name or ""
        clip_title = sc.title or f"clip-{source_clip_id[:8]}"

        # v2.2.38: 抽源 clip 的 tags (从 clip_metadata 提取, 跟 v2.2.21 visual match 配套)
        # 没 tags 就空 list (auto-tag 默认关闭, user 不想用)
        clip_tags = []
        if sc.clip_metadata and isinstance(sc.clip_metadata, dict):
            for t in (sc.clip_metadata.get("tags") or []):
                if isinstance(t, str):
                    clip_tags.append(t)
                elif isinstance(t, dict) and "category" in t:
                    clip_tags.append(t["category"])

        # 复制 mp4
        new_id = str(uuid.uuid4())
        new_video_path = _resources_dir() / f"{new_id}.mp4"
        shutil.copy2(source_video_path, new_video_path)

        # 复制 thumbnail (优先源 thumbnail, 兜底 ffmpeg 抽 1 帧)
        new_thumb_path = None
        if sc.thumbnail_path:
            src_thumb = Path(sc.thumbnail_path)
            if not src_thumb.is_absolute():
                # 跟 mp4 保持一致: 拼 data/projects/<project_id>/<thumbnail_path>
                src_thumb = (Path("data/projects") / source_project_id / sc.thumbnail_path).resolve()
            if src_thumb.exists():
                new_thumb_path = _resources_dir() / f"{new_id}.jpg"
                try:
                    shutil.copy2(src_thumb, new_thumb_path)
                except Exception as e:
                    logger.warning(f"thumbnail 复制失败 (非致命): {e}")
                    new_thumb_path = None
        # v2.2.38: 兜底 — 源 thumbnail 不存在/复制失败时, ffmpeg 抽 1 帧
        if new_thumb_path is None or not new_thumb_path.exists():
            fallback_thumb = _resources_dir() / f"{new_id}.jpg"
            if _generate_thumbnail(new_video_path, fallback_thumb, t_seconds=1.0):
                new_thumb_path = fallback_thumb
                logger.info(f"from-clip 兜底抽 thumbnail: {fallback_thumb}")
            else:
                new_thumb_path = None
                logger.warning(f"from-clip thumbnail 全失败: {new_id} (新资源将无封面)")

        size = new_video_path.stat().st_size if new_video_path.exists() else 0

        rc = ResourceClip(
            id=new_id,
            name=clip_title,
            file_path=str(new_video_path),
            thumbnail_path=str(new_thumb_path) if new_thumb_path else None,
            duration=sc.duration or 0.0,
            width=sc.width,
            height=sc.height,
            size=size,
            source_type="from_project",
            source_project_id=source_project_id,
            source_clip_id=source_clip_id,
            source_project_name=source_project_name,
            tags=clip_tags,  # v2.2.38: 从源 clip_metadata 抽 (visual match 用)
            description=f"从项目「{source_project_name}」提取",
        )
        db.add(rc)
        await db.commit()
        await db.refresh(rc)

        logger.info(f"library from-clip: new_id={new_id} src_clip={source_clip_id} src_proj={source_project_id}")

        # v2.2.38: auto-tag 默认关闭 (user 反馈: 规则不准, 暂时不用)
        # 想用时手跑 POST /library/{id}/auto-tag
        # background_tasks.add_task(_auto_tag_in_thread, new_id)
        return _serialize(rc)


@router.get("/videos/{resource_id}")
async def stream_resource_video(resource_id: str):
    """流式返回资源库视频 (前端 player 用)"""
    rid = _safe_id(resource_id)
    # 从路径直接构造 (不查 db, 减少 round trip)
    video_path = _resources_dir() / f"{rid}.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="视频不存在")
    return FileResponse(
        path=str(video_path),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "no-cache",
        },
    )


@router.get("/thumbnails/{resource_id}")
async def get_resource_thumbnail(resource_id: str):
    """返回资源库缩略图 (有就返, 没有 404)."""
    rid = _safe_id(resource_id)
    thumb_path = _resources_dir() / f"{rid}.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.delete("/{resource_id}")
async def delete_resource(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
):
    """软删除: 删 mp4 + jpg + 设 deleted_at"""
    rid = _safe_id(resource_id)
    result = await db.execute(select(ResourceClip).where(ResourceClip.id == rid))
    rc = result.scalar_one_or_none()
    if not rc:
        raise HTTPException(status_code=404, detail="资源不存在")

    # 真删文件
    if rc.file_path:
        try:
            Path(rc.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"删 mp4 失败 (非致命): {e}")
    if rc.thumbnail_path:
        try:
            Path(rc.thumbnail_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"删 jpg 失败 (非致命): {e}")

    rc.deleted_at = datetime.utcnow()
    await db.commit()

    logger.info(f"library delete: id={rid}")
    return {"id": rid, "deleted": True}


# ──────────────────────────── v2.2.19: auto-tag 手动 retry 端点 ────────────────────────────


@router.post("/{resource_id}/auto-tag")
async def auto_tag_resource_endpoint(
    resource_id: str,
    db: AsyncSession = Depends(get_db),
):
    """手动触发 auto-tag (retry / 强制刷新 tags).

    跟 upload/from-clip 异步 background task 一样逻辑, 同步等结果返.
    适合 user 在前端 ✨ 按钮 retry 场景.
    """
    rid = _safe_id(resource_id)
    result = await db.execute(select(ResourceClip).where(ResourceClip.id == rid))
    rc = result.scalar_one_or_none()
    if not rc:
        raise HTTPException(status_code=404, detail="资源不存在")
    if rc.deleted_at:
        raise HTTPException(status_code=410, detail="资源已删除")

    # 调 service (sync, 写 sync db)
    tags = generate_tags_for_resource(rid)
    return {"id": rid, "tags": tags, "count": len(tags)}


# ──────────────────────────── v2.2.5: 一键从项目批量导入 ────────────────────────────


@router.post("/from-project")
async def from_project_batch_resource(
    background_tasks: BackgroundTasks,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """一键从切片项目批量导入全部 clip 进资源库 (跨项目长期保留)

    Body: {"source_project_id": "..."}

    复制 data/projects/<id>/output/clips/*.mp4 到 data/resources/<new_id>.mp4,
    同步 metadata + thumbnail. 跳过缺失文件 + 已存在 (按 source_clip_id 查重).

    Returns: {"imported": N, "skipped": M, "errors": [...]}
    """
    source_project_id = payload.get("source_project_id")
    if not source_project_id:
        raise HTTPException(status_code=400, detail="source_project_id 必填")

    with sync_get_db() as sdb:
        sp = sdb.query(Project).filter(Project.id == source_project_id).first()
        if not sp:
            raise HTTPException(status_code=404, detail=f"source project {source_project_id} 不存在")
        source_project_name = sp.name or ""

        # 查这个项目的全部 clip
        clips = sdb.query(Clip).filter(
            Clip.project_id == source_project_id,
        ).order_by(Clip.created_at).all()

    if not clips:
        raise HTTPException(status_code=404, detail="该项目没有任何 clip")

    # 查重: 已经导入过这个 source_clip_id 的就跳过
    with sync_get_db() as sdb:
        existing = sdb.query(ResourceClip).filter(
            ResourceClip.source_project_id == source_project_id,
            ResourceClip.deleted_at.is_(None),
        ).all()
        existing_clip_ids = {rc.source_clip_id for rc in existing if rc.source_clip_id}

    imported = 0
    skipped = 0
    errors = []
    new_rows: List[ResourceClip] = []

    for sc in clips:
        if sc.id in existing_clip_ids:
            skipped += 1
            continue

        try:
            # 复制 mp4 — clip.video_path 是相对路径 (output/clips/xxx.mp4),
            # 必须拼上 data/projects/<source_project_id>/ 中间层
            if not sc.video_path:
                errors.append({"clip_id": sc.id, "title": sc.title, "error": "video_path 空"})
                continue
            src_p = Path(sc.video_path)
            if not src_p.is_absolute():
                src_p = (Path("data/projects") / source_project_id / sc.video_path).resolve()
            if not src_p.exists():
                errors.append({"clip_id": sc.id, "title": sc.title, "error": f"mp4 缺失: {src_p}"})
                continue

            new_id = str(uuid.uuid4())
            new_video = _resources_dir() / f"{new_id}.mp4"
            shutil.copy2(src_p, new_video)

            # 复制 thumbnail
            new_thumb = None
            if sc.thumbnail_path:
                src_thumb = Path(sc.thumbnail_path)
                if not src_thumb.is_absolute():
                    src_thumb = (Path("data/projects") / source_project_id / sc.thumbnail_path).resolve()
                if src_thumb.exists():
                    new_thumb = _resources_dir() / f"{new_id}.jpg"
                    try:
                        shutil.copy2(src_thumb, new_thumb)
                    except Exception:
                        new_thumb = None

            row = ResourceClip(
                id=new_id,
                name=sc.title or f"clip-{sc.id[:8]}",
                file_path=str(new_video),
                thumbnail_path=str(new_thumb) if new_thumb else None,
                duration=sc.duration or 0.0,
                width=sc.width,
                height=sc.height,
                size=new_video.stat().st_size,
                source_type="from_project",
                source_project_id=source_project_id,
                source_clip_id=sc.id,
                source_project_name=source_project_name,
                description=f"一键从项目「{source_project_name}」批量导入",
            )
            new_rows.append(row)
            imported += 1
        except Exception as e:
            errors.append({"clip_id": sc.id, "title": sc.title, "error": str(e)})

    if new_rows:
        with sync_get_db() as sdb:
            for row in new_rows:
                sdb.add(row)
            sdb.commit()
            logger.info(f"library from-project batch: imported={imported}, skipped={skipped}, errors={len(errors)}")

        # v2.2.38: auto-tag 默认关闭 (user 反馈: 规则不准, 暂时不用)
        # 想用时手跑 POST /library/{id}/auto-tag (循环每个)
        # for row in new_rows:
        #     background_tasks.add_task(_auto_tag_in_thread, row.id)

    return {
        "source_project_id": source_project_id,
        "source_project_name": source_project_name,
        "total_clips": len(clips),
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }
