"""Watch Folder API + 扫描 daemon

- CRUD: /api/v1/watch-folders
- 扫描触发: /api/v1/watch-folders/{id}/scan (手动)
- 后台扫描: celery beat 任务，每 30s 触发一次，自动扫所有 enabled folders
"""

import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings  # 用于 BASE_DIR
from ..core.database import get_db
from ..models.database import Project, WatchFolder

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"}


def _to_iso_utc(dt: datetime | None) -> str | None:
    """datetime → ISO 字符串（UTC，带 Z 后缀）"""
    return dt.isoformat() + "Z" if dt else None


def _to_dict(wf: WatchFolder) -> dict:
    return {
        "id": wf.id,
        "name": wf.name,
        "path": wf.path,
        "style_id": wf.style_id,
        "style_config": wf.style_config,
        "with_subtitle": wf.with_subtitle,
        "scan_interval_seconds": wf.scan_interval_seconds,
        "source_action": wf.source_action,
        "enabled": wf.enabled,
        "last_scan_at": _to_iso_utc(wf.last_scan_at),
        "last_found_count": wf.last_found_count,
        "last_processed_at": _to_iso_utc(wf.last_processed_at),
        "created_at": _to_iso_utc(wf.created_at),
    }


# ============== Pydantic Models ==============
class WatchFolderCreate(BaseModel):
    name: str
    path: str
    style_id: str | None = None
    style_config: dict | None = None
    with_subtitle: bool = True
    scan_interval_seconds: int = 60
    source_action: str = "delete"  # delete / keep / move_done
    enabled: bool = True


class WatchFolderUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    style_id: str | None = None
    style_config: dict | None = None
    with_subtitle: bool | None = None
    scan_interval_seconds: int | None = None
    source_action: str | None = None
    enabled: bool | None = None


# ============== CRUD ==============
@router.get("/watch-folders")
async def list_watch_folders(
    include_disabled: bool = Query(
        default=False, description="是否包含已停用的 watch folder"
    ),
    db: AsyncSession = Depends(get_db),
):
    """列出所有 watch folder（默认只显示启用的）"""
    query = select(WatchFolder).order_by(WatchFolder.created_at.desc())
    if not include_disabled:
        query = query.where(WatchFolder.enabled)
    result = await db.execute(query)
    folders = result.scalars().all()
    return {"folders": [_to_dict(f) for f in folders]}


@router.post("/watch-folders")
async def create_watch_folder(
    folder: WatchFolderCreate, db: AsyncSession = Depends(get_db)
):
    """创建 watch folder"""
    p = Path(folder.path)
    if not p.is_absolute():
        raise HTTPException(status_code=400, detail="路径必须是绝对路径")
    if not p.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在：{folder.path}")
    if not p.is_dir():
        raise HTTPException(status_code=400, detail=f"不是文件夹：{folder.path}")
    if folder.source_action not in ("delete", "keep", "move_done"):
        raise HTTPException(
            status_code=400, detail="source_action 必须是 delete/keep/move_done"
        )

    fid = f"wf_{uuid.uuid4().hex[:8]}"
    wf = WatchFolder(
        id=fid,
        name=folder.name,
        path=folder.path,
        style_id=folder.style_id,
        style_config=folder.style_config,
        with_subtitle=folder.with_subtitle,
        scan_interval_seconds=max(10, folder.scan_interval_seconds),  # 最小 10s
        source_action=folder.source_action,
        enabled=folder.enabled,
        processed_files={},  # 显式初始化
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return {"id": fid, "message": "已创建", "folder": _to_dict(wf)}


@router.put("/watch-folders/{folder_id}")
async def update_watch_folder(
    folder_id: str, folder: WatchFolderUpdate, db: AsyncSession = Depends(get_db)
):
    """更新 watch folder"""
    result = await db.execute(select(WatchFolder).where(WatchFolder.id == folder_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="watch folder 不存在")

    update_data = folder.dict(exclude_unset=True)
    if "path" in update_data:
        np = Path(update_data["path"])
        if not np.is_absolute():
            raise HTTPException(status_code=400, detail="路径必须是绝对路径")
        if not np.exists() or not np.is_dir():
            raise HTTPException(
                status_code=400, detail=f"路径无效：{update_data['path']}"
            )
    if "source_action" in update_data and update_data["source_action"] not in (
        "delete",
        "keep",
        "move_done",
    ):
        raise HTTPException(
            status_code=400, detail="source_action 必须是 delete/keep/move_done"
        )
    if "scan_interval_seconds" in update_data:
        update_data["scan_interval_seconds"] = max(
            10, update_data["scan_interval_seconds"]
        )

    for k, v in update_data.items():
        setattr(wf, k, v)
    wf.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(wf)
    return {"message": "已更新", "folder": _to_dict(wf)}


@router.delete("/watch-folders/{folder_id}")
async def delete_watch_folder(folder_id: str, db: AsyncSession = Depends(get_db)):
    """删除 watch folder（不影响已处理的 projects）"""
    result = await db.execute(select(WatchFolder).where(WatchFolder.id == folder_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="watch folder 不存在")
    await db.delete(wf)
    await db.commit()
    return {"message": "已删除"}


# ============== 手动扫描 ==============
@router.post("/watch-folders/{folder_id}/scan")
async def trigger_scan(folder_id: str, db: AsyncSession = Depends(get_db)):
    """手动触发扫描（立即跑一次）"""
    result = await db.execute(select(WatchFolder).where(WatchFolder.id == folder_id))
    wf = result.scalar_one_or_none()
    if not wf:
        raise HTTPException(status_code=404, detail="watch folder 不存在")

    count = await _scan_folder(db, wf)
    return {"message": "扫描完成", "new_files": count}


# ============== 扫描（async 版，给手动 endpoint 用）==============
async def _scan_folder(db: AsyncSession, wf: WatchFolder) -> int:
    """扫描 watch folder，找新 mp4/mov 文件 → 创建 project + 触发 process

    Returns: 新处理的文件数

    ⚠️ 用 wf.processed_files 做去重（filename + mtime）
    """
    folder_path = Path(wf.path)
    if not folder_path.is_dir():
        logger.warning(f"watch folder {wf.name}: 路径不存在 {wf.path}")
        wf.last_scan_at = datetime.utcnow()
        wf.last_found_count = 0
        await db.commit()
        return 0

    # 已处理过的文件集合
    processed = dict(wf.processed_files or {})

    # 列出顶层视频文件（不递归，避免扫 done/ 子目录）
    files = [
        f
        for f in folder_path.iterdir()
        if f.is_file()
        and f.suffix.lower() in ALLOWED_VIDEO_EXT
        and not f.name.startswith("._")  # 排除 macOS 隐藏文件
    ]

    new_count = 0
    for f in files:
        try:
            mtime = str(int(f.stat().st_mtime))
            if processed.get(f.name) == mtime:
                continue  # 已处理过
            await _process_file(db, wf, f)
            processed[f.name] = mtime
            new_count += 1
        except Exception as e:
            logger.error(f"处理 {f} 失败: {e}")

    wf.last_scan_at = datetime.utcnow()
    wf.last_found_count = new_count
    wf.processed_files = processed
    if new_count > 0:
        wf.last_processed_at = datetime.utcnow()
    await db.commit()
    return new_count


async def _process_file(db: AsyncSession, wf: WatchFolder, file_path: Path):
    """处理一个文件：复制 → 建 project → 触发 celery → source_action"""
    base_dir = Path(settings.BASE_DIR) / "data" / "projects"
    project_id = str(uuid.uuid4())
    project_dir = base_dir / project_id
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / "input.mp4"

    logger.info(f"watch folder {wf.name}: 复制 {file_path} → {target}")
    shutil.copy2(file_path, target)
    file_size = target.stat().st_size

    # 组装 processing_config
    processing_config = {}
    if wf.style_config:
        processing_config.update(wf.style_config)
    if wf.style_id:
        processing_config["style_id"] = wf.style_id
    processing_config["with_subtitle"] = wf.with_subtitle

    project = Project(
        id=project_id,
        name=file_path.stem,
        status="pending",
        video_path=str(target.relative_to(base_dir)),
        video_size=file_size,
        processing_config=processing_config,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    # 触发 celery（异步）
    try:
        from ..core.celery_app import celery_app

        celery_app.send_task(
            "backend.tasks.processing.process_video_pipeline",
            args=[project_id, str(target), None, None],
            queue="processing_beta",
        )
        logger.info(f"watch folder {wf.name}: 已触发处理 project {project_id}")
    except Exception as e:
        logger.error(f"watch folder 触发 celery 失败: {e}")

    # 源文件处理
    _handle_source_action(file_path, wf.source_action, wf.name)


def _handle_source_action(file_path: Path, source_action: str, wf_name: str):
    """源文件处理：delete / keep / move_done"""
    if source_action == "delete":
        try:
            file_path.unlink()
            logger.info(f"watch folder {wf_name}: 已删除源文件 {file_path}")
        except Exception as e:
            logger.warning(f"删除源文件失败: {e}")
    elif source_action == "move_done":
        done_dir = file_path.parent / "done"
        done_dir.mkdir(exist_ok=True)
        try:
            shutil.move(str(file_path), str(done_dir / file_path.name))
            logger.info(f"watch folder {wf_name}: 已移到 {done_dir / file_path.name}")
        except Exception as e:
            logger.warning(f"移动到 done 失败: {e}")
    # "keep" 什么都不做


# ============== 定期扫描（被 celery beat 调用）==============
def scan_all_due_folders():
    """扫所有 enabled + 到期（last_scan_at + scan_interval < now）的 folders

    ⚠️ 必须 sync（celery worker 不是 async 环境）
    """
    from ..core.database import SyncSessionLocal

    db = SyncSessionLocal()
    try:
        result = db.query(WatchFolder).filter(WatchFolder.enabled).all()
        now = datetime.utcnow()
        for wf in result:
            if wf.last_scan_at is None:
                due = True
            else:
                elapsed = (now - wf.last_scan_at).total_seconds()
                due = elapsed >= wf.scan_interval_seconds
            if not due:
                continue
            try:
                _sync_scan_folder(db, wf)
                db.commit()  # sync_scan 自己 commit，但保险起见
            except Exception as e:
                logger.error(f"扫 {wf.name} 失败: {e}", exc_info=True)
                db.rollback()
    finally:
        db.close()


def _sync_scan_folder(db, wf: WatchFolder) -> int:
    """同步版本：用于 celery beat 调用"""
    folder_path = Path(wf.path)
    if not folder_path.is_dir():
        wf.last_scan_at = datetime.utcnow()
        wf.last_found_count = 0
        db.commit()
        return 0

    processed = dict(wf.processed_files or {})

    files = [
        f
        for f in folder_path.iterdir()
        if f.is_file()
        and f.suffix.lower() in ALLOWED_VIDEO_EXT
        and not f.name.startswith("._")
    ]

    new_count = 0
    for f in files:
        try:
            mtime = str(int(f.stat().st_mtime))
            if processed.get(f.name) == mtime:
                continue
            _sync_process_file(db, wf, f)
            processed[f.name] = mtime
            new_count += 1
        except Exception as e:
            logger.error(f"处理 {f} 失败: {e}", exc_info=True)

    wf.last_scan_at = datetime.utcnow()
    wf.last_found_count = new_count
    wf.processed_files = processed
    if new_count > 0:
        wf.last_processed_at = datetime.utcnow()
    db.commit()
    return new_count


def _sync_process_file(db, wf: WatchFolder, file_path: Path):
    """同步处理单文件（celery worker 环境）"""
    base_dir = Path(settings.BASE_DIR) / "data" / "projects"
    project_id = str(uuid.uuid4())
    project_dir = base_dir / project_id
    raw_dir = project_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / "input.mp4"

    shutil.copy2(file_path, target)
    file_size = target.stat().st_size

    processing_config = {}
    if wf.style_config:
        processing_config.update(wf.style_config)
    if wf.style_id:
        processing_config["style_id"] = wf.style_id
    processing_config["with_subtitle"] = wf.with_subtitle

    project = Project(
        id=project_id,
        name=file_path.stem,
        status="pending",
        video_path=str(target.relative_to(base_dir)),
        video_size=file_size,
        processing_config=processing_config,
    )
    db.add(project)
    db.commit()

    # 触发 celery
    try:
        from ..core.celery_app import celery_app

        celery_app.send_task(
            "backend.tasks.processing.process_video_pipeline",
            args=[project_id, str(target), None, None],
            queue="processing_beta",
        )
    except Exception as e:
        logger.error(f"celery send_task 失败: {e}", exc_info=True)

    # 源文件处理
    _handle_source_action(file_path, wf.source_action, wf.name)
