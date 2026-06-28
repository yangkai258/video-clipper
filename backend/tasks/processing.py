"""视频处理 Celery 任务"""
import gc
import logging
import uuid
from datetime import datetime
from pathlib import Path
from celery import shared_task

from ..core.config import settings

logger = logging.getLogger(__name__)


def _update_task_progress(task_id: str, progress: int, current_step: str) -> None:
    """更新 Task 表的 progress + current_step（短事务，写完即关）

    约定：
    - progress: 0-100
    - current_step: 显示给用户的中文标签
    - 失败仅 warning，不影响主流程
    """
    if not task_id:
        return
    try:
        from ..core.database import sync_get_db
        from ..models.database import Task
        from sqlalchemy import select

        with sync_get_db() as db:
            task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
            if task:
                task.progress = max(0, min(100, progress))
                task.current_step = current_step[:255]  # 列宽保护
                db.commit()
    except Exception as e:
        logger.warning(f"进度更新失败 (progress={progress}, step={current_step}): {e}")


def _mark_zero_output_failed(project_id: str, task_id: str, reason: str) -> None:
    """0-clip guard (v2.1.23): 把 pipeline 跑完但 0 产物的项目改标 failed

    设计：
    - 检查项目状态必须是 completed 且未删除 (避免覆盖用户主动删除的项目)
    - 检查 task 状态必须是 completed (避免覆盖正在运行的 task)
    - 失败仅 warning，不抛异常 (主流程已经完成, 这里只是修正状态)
    """
    try:
        from ..core.database import sync_get_db
        from ..models.database import Project, Task

        with sync_get_db() as db:
            proj = db.query(Project).filter(Project.id == project_id).first()
            # 加 deleted_at 检查 (v2.1.23 review fix): 用户中途删了的项目, 不应被 guard 覆盖
            if proj and proj.status == "completed" and proj.deleted_at is None:
                proj.status = "failed"
                proj.completed_at = None  # 清掉误写的完成时间
            if task_id:
                task_row = db.query(Task).filter(Task.id == task_id).first()
                if task_row and task_row.status == "completed":
                    task_row.status = "failed"
                    task_row.error_message = reason
            db.commit()
            logger.warning(f"0-clip guard: project {project_id} 跑完 6 步但 0 产物, 改标 failed")
    except Exception as guard_err:
        logger.warning(f"0-clip guard 写库失败: {guard_err}")


@shared_task(bind=True)
def process_video_pipeline(
    self,
    project_id: str,
    input_video_path: str,
    input_srt_path: str = None,
    task_id: str = None
):
    """视频处理流水线"""
    from ..services.subtitle_service import generate_subtitle
    from ..services.llm_service import extract_outline, create_timeline, score_clips, generate_titles, cluster_collections
    from ..services.video_service import cut_clips, merge_collections
    from ..core.database import sync_get_db
    from ..models.database import Clip, Collection, Project
    from sqlalchemy import select
    
    logger.info(f"开始处理项目：{project_id}")

    # 标记 task 为 running + 写 started_at (v2.1.5 ETA 估算需要)
    if task_id:
        try:
            with sync_get_db() as db:
                from ..models.database import Task
                task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
                if task:
                    task.status = "running"
                    if not task.started_at:
                        task.started_at = datetime.utcnow()
                    db.commit()
        except Exception as e:
            logger.warning(f"task 启动标记失败: {e}")

    # 读取项目配置（包含切片策略 + 字幕配置）
    with sync_get_db() as db:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if project:
            strategy_config = project.processing_config or {}
            # 字段名兼容：DB 存的是 subtitle_style，老字段叫 subtitle_config
            subtitle_config = strategy_config.get("subtitle_style") or strategy_config.get("subtitle_config") or {}
            logger.info(f"使用切片策略：{strategy_config.get('strategy_name', '默认')}")
            logger.info(f"策略参数：target_duration={strategy_config.get('target_duration', 60)}s, max_clips={strategy_config.get('max_clips', 20)}")
            logger.info(f"字幕配置：{subtitle_config}")
        else:
            strategy_config = {}
            subtitle_config = {}
            logger.warning("项目配置不存在，使用默认策略")
    
    try:
        # === 前置检查: 视频文件必须存在 + 大小 > 0 (v2.1.20 修 0 byte 视频卡完成假成功) ===
        input_path = Path(input_video_path)
        if not input_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {input_video_path}")
        input_size = input_path.stat().st_size
        if input_size < 1024:  # 小于 1KB 视作无效 (正常视频至少几 MB)
            raise ValueError(f"视频文件过小 ({input_size} bytes), 上传可能未完成. 请重新上传.")

        project_dir = input_path.parent.parent
        metadata_dir = project_dir / "metadata"
        output_dir = project_dir / "output"
        clips_dir = output_dir / "clips"
        collections_dir = output_dir / "collections"
        
        metadata_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        collections_dir.mkdir(parents=True, exist_ok=True)
        
        # === Step 1: 字幕生成 (进度 2% → 30%) ===
        logger.info("Step 1: 生成字幕")
        _update_task_progress(task_id, 2, "准备生成字幕")
        # 从 strategy_config 提取 with_subtitle 标志（默认 True 保持向后兼容）
        with_subtitle = strategy_config.get("with_subtitle", True) if strategy_config else True
        logger.info(f"字幕模式：{'落盘到项目目录' if with_subtitle else 'in_memory 模式（不写项目目录，用完即删）'}")

        # === Step 1 心跳: whisper 跑得慢（30s-3min），每 5s 推一次进度 ===
        import threading
        _heartbeat_stop = threading.Event()
        def _heartbeat():
            import time as _time
            _t0 = _time.time()
            while not _heartbeat_stop.is_set():
                _elapsed = int(_time.time() - _t0)
                # 0s→2%, 60s→16%, 120s→25%, 180s+→30%
                _pct = 2 + min(28, int(_elapsed / 120 * 28))
                _update_task_progress(task_id, _pct, f"生成字幕中... ({_elapsed}s)")
                _heartbeat_stop.wait(5)  # 5s 一次，可被 stop 提前唤醒
        _hb_thread = threading.Thread(target=_heartbeat, daemon=True)
        _hb_thread.start()
        with_subtitle = strategy_config.get("with_subtitle", True) if strategy_config else True
        logger.info(f"字幕模式：{'落盘到项目目录' if with_subtitle else 'in_memory 模式（不写项目目录，用完即删）'}")

        if with_subtitle:
            # 旧行为：写盘到 metadata/input.srt
            srt_path = metadata_dir / "input.srt"
            if input_srt_path and Path(input_srt_path).exists():
                logger.info(f"使用现有字幕文件：{input_srt_path}")
                import shutil
                if Path(input_srt_path).resolve() != srt_path.resolve():
                    shutil.copy(input_srt_path, srt_path)
                else:
                    logger.info("字幕文件已在正确位置，跳过复制")
            else:
                logger.info("自动生成字幕（落盘模式）")
                srt_path = generate_subtitle(input_video_path, srt_path)
        else:
            # Y 方案：写到 /tmp 临时文件，不污染项目目录
            import tempfile
            tmp = tempfile.NamedTemporaryFile(
                suffix=".srt",
                prefix=f"video_clipper_{project_id}_",
                delete=False,
                mode="w",
                encoding="utf-8",
                dir="/tmp",
            )
            tmp.close()
            srt_path = Path(tmp.name)
            logger.info(f"自动生成字幕（临时文件模式）：{srt_path}")
            if input_srt_path and Path(input_srt_path).exists():
                # 用户传入了字幕，直接复制到临时文件
                import shutil
                shutil.copy(input_srt_path, srt_path)
                logger.info(f"使用现有字幕文件（复制到临时）：{input_srt_path}")
            else:
                # generate_subtitle 写入临时文件（落盘但项目目录干净）
                result = generate_subtitle(input_video_path, srt_path)
                # 确保 srt_path 指向生成的文件
                if result != srt_path and Path(result).exists():
                    srt_path = Path(result)

        if not srt_path or not Path(srt_path).exists():
            raise Exception("字幕生成失败")

        # 停心跳 + 推到 30%
        _heartbeat_stop.set()
        _update_task_progress(task_id, 30, "字幕生成完成")

        # 清理内存
        gc.collect()

        # === Step 2: 大纲提取 (进度 30% → 45%) ===
        _update_task_progress(task_id, 32, "提取内容大纲")
        # Step 2: 大纲提取（可选，失败时使用本地备用方案）
        logger.info("Step 2: 提取大纲")
        outlines = extract_outline(srt_path, metadata_dir, strategy_config)
        _update_task_progress(task_id, 40, "提取内容大纲")

        if not outlines:
            logger.warning("AI 大纲提取失败，使用本地备用方案（基于字幕段落自动切片）")
            # 使用本地方案：直接从字幕生成时间线
            from ..services.local_processor import generate_clips_from_subtitle
            clips_data = generate_clips_from_subtitle(srt_path, metadata_dir, strategy_config)
            outlines = clips_data.get("outlines", [])
            titled_clips = clips_data.get("clips", [])
            collections = clips_data.get("collections", [])
            _update_task_progress(task_id, 55, "本地方案生成完成")
        else:
            # Step 3: 时间线创建
            logger.info("Step 3: 创建时间线")
            _update_task_progress(task_id, 45, "构建时间线")
            timeline = create_timeline(outlines, srt_path, metadata_dir, strategy_config)

            # Step 4: 切片评分（使用策略参数）
            logger.info("Step 4: 切片评分")
            _update_task_progress(task_id, 50, "评分候选片段")
            scored_clips = score_clips(timeline, metadata_dir, strategy_config)

            # Step 5: 生成标题（传入 srt 让 LLM 看内容生成吸引人标题）
            logger.info("Step 5: 生成标题")
            _update_task_progress(task_id, 55, "生成片段标题")
            titled_clips = generate_titles(scored_clips, metadata_dir, srt_path=srt_path, strategy_config=strategy_config)

            # Step 6: 主题聚类（使用策略参数）
            logger.info("Step 6: 主题聚类")
            _update_task_progress(task_id, 60, "主题聚类")
            collections = cluster_collections(titled_clips, metadata_dir, strategy_config)

        # Step 7: 切割视频（传入字幕配置 + with_subtitle 标志）
        # 切割 step 内部自己维护 70% → 90% 的逐片进度 (见 video_service.cut_clips)
        logger.info("Step 7: 切割视频")
        _update_task_progress(task_id, 65, "开始切割视频")
        # 从 strategy_config 提取 with_subtitle 标志（默认 True 保持向后兼容）
        with_subtitle = strategy_config.get("with_subtitle", True) if strategy_config else True
        logger.info(f"字幕烧录：{'开启' if with_subtitle else '关闭（纯剪片子）'}")
        # v2.1.26: output_format 控制编码方式 (横屏电影→9:16 letterbox 等)
        output_format = strategy_config.get("output_format", "original") if strategy_config else "original"
        logger.info(f"输出格式：{output_format}")
        cut_clips(
            titled_clips,
            input_video_path,
            clips_dir,
            input_srt=srt_path if with_subtitle else None,  # 不烧字幕就不传 SRT
            task_id=task_id,
            subtitle_config=subtitle_config,
            with_subtitle=with_subtitle,
            project_id=project_id,  # 切完第一片后抽帧做封面
            output_format=output_format,
        )
        _update_task_progress(task_id, 92, "切割完成")

        # Step 8: 合并合集
        # 合并内部维护 90% → 99% 进度 (见 video_service.merge_collections)
        logger.info("Step 8: 合并合集")
        _update_task_progress(task_id, 93, "合并合集")
        merge_collections(collections, clips_dir, collections_dir, task_id=task_id)
        
        # Step 9: 验证文件完整性
        logger.info("Step 9: 验证文件完整性")
        missing_files = []
        for clip in titled_clips:
            # 优先检查 video_path 字段 (v2.1.7 fix: 拼绝对路径, 之前相对路径用 cwd 找永远找不到)
            video_path = clip.get("video_path")
            if video_path:
                abs_path = project_dir / video_path
                if abs_path.exists():
                    continue
            # fallback: 用 index 构造预期路径 (如果 index 是 i+1 才对得上, 否则会假阳性)
            safe_title = "".join(c for c in clip.get("title", f"clip_{clip.get('index', 1)}") if c not in '<>:"/\\|？*')
            expected_path = clips_dir / f"{clip.get('index', 1)}_{safe_title[:50]}.mp4"
            if not expected_path.exists():
                missing_files.append(str(expected_path))
        
        # 合集为可选，只记录警告不阻止完成
        missing_collections = []
        for coll in collections:
            video_path = coll.get("video_path")
            if video_path and Path(video_path).exists():
                continue
            expected_path = collections_dir / f"{coll.get('title', '合集')}.mp4"
            if not expected_path.exists():
                missing_collections.append(str(expected_path))
        
        if missing_collections:
            logger.warning(f"合集生成失败 {len(missing_collections)} 个，但切片正常，继续完成：{missing_collections[:3]}")
        
        if missing_files:
            logger.error(f"文件生成不完整，缺失 {len(missing_files)} 个文件：{missing_files[:5]}...")
            raise Exception(f"文件生成失败，缺失：{missing_files[:3]}")
        
        logger.info(f"文件完整性验证通过：{len(titled_clips)} clips + {len(collections) - len(missing_collections)} collections")

        # 清理临时 SRT 文件（Y 方案：with_subtitle=false 时使用 /tmp 临时文件）
        if not with_subtitle and srt_path and Path(srt_path).exists():
            try:
                Path(srt_path).unlink()
                logger.info(f"已清理临时 SRT 文件：{srt_path}")
            except Exception as e:
                logger.warning(f"清理临时 SRT 失败：{e}")

        # Step 10: 写入数据库 + 清理 raw 视频
        logger.info("Step 10: 写入数据库")
        from ..core.database import sync_get_db
        from ..models.database import Project

        cleanup_errors = []
        with sync_get_db() as db:
            try:
                # 清除旧记录
                db.query(Clip).filter(Clip.project_id == project_id).delete()
                db.query(Collection).filter(Collection.project_id == project_id).delete()

                # 插入 clips
                for clip_data in titled_clips:
                    clip = Clip(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        title=clip_data.get("title", f"片段 {clip_data.get('index', 1)}"),
                        start_time=clip_data.get("start", 0),
                        end_time=clip_data.get("end", 0),
                        duration=clip_data.get("duration", 0),
                        score=clip_data.get("score", 50),
                        video_path=clip_data.get("video_path", f"output/clips/{clip_data.get('index', 1)}_片段.mp4"),
                        # v2.1.26: 存 clip 宽高, 让前端区分横/竖屏
                        width=clip_data.get("width"),
                        height=clip_data.get("height"),
                    )
                    db.add(clip)
            
            # 插入 collections
                for coll_data in collections:
                    # v2.1.24 fix: 之前用 c["index"] 但 cluster_collections 输出的 clips 是完整 dict 没 index 字段
                    # 改用 cluster_collections 已经正确生成的 clip_ids 字段 (title 列表)
                    clip_ids = coll_data.get("clip_ids", [])
                    # title 兜底（cluster_collections 不写 index，用 len(collections)+1）
                    coll_title = coll_data.get("title") or f"合集 {len(collections)}"
                    # 移除 title 中可能的非法路径字符
                    safe_title = "".join(c for c in coll_title if c not in '<>:"/\\|？*')
                    coll = Collection(
                        id=str(uuid.uuid4()),
                        project_id=project_id,
                        title=coll_title,
                        clip_ids=clip_ids,
                        video_path=f"output/collections/{safe_title}.mp4",
                    )
                    db.add(coll)

            # 更新项目状态（在 cleanup 前更新，确保 raw 删除失败也不影响 status）
                project = db.query(Project).filter(Project.id == project_id).first()
                if project:
                    project.status = "completed"
                    project.completed_at = datetime.utcnow()

                # 同步 task.completed_at (v2.1.5 ETA 显示总耗时需要)
                if task_id:
                    task_row = db.query(Task).filter(Task.id == task_id).first()
                    if task_row:
                        task_row.status = "completed"
                        task_row.completed_at = datetime.utcnow()
                        task_row.progress = 100

                db.commit()  # 先提交 clips/collections/project 状态  # STEP10_DB_COMMIT_MARKER
            except Exception as db_error:
                logger.error(f"数据库写入失败：{db_error}")
                raise

        # 0-clip guard (v2.1.23): 视频太短/无切点时跑完 6 步但 0 产物, 不能标 completed  # ZERO_CLIP_GUARD_MARKER
        # 注意: 必须在 cleanup 之前! 否则 raw 视频被删, 用户改风格重切就没文件了 (v2.1.24 fix)
        if len(titled_clips) == 0 and len(collections) == 0:
            _mark_zero_output_failed(project_id, task_id, "未能识别到任何切片片段 (视频过短 或 无有效切点)")
            return {
                "success": False,
                "project_id": project_id,
                "reason": "no_clips_generated",
                "message": "未能识别到任何切片片段 (视频过短 或 无有效切点)",
            }

        # === 清理 raw 视频 + 临时文件（独立 try，不影响主流程已完成部分）===
        try:
            # 删 raw 视频（复用前面算的 project_dir 路径）
            raw_video = project_dir / "raw" / "input.mp4"
            if raw_video.exists():
                raw_size = raw_video.stat().st_size
                raw_video.unlink()
                logger.info(f"清理：删除 raw/input.mp4 ({raw_size/1024/1024:.1f} MB)")
                try:
                    (project_dir / "raw").rmdir()
                except OSError:
                    pass

            # 删临时音频
            for temp_name in ("temp_audio.wav", "temp_audio.m4a", "extracted_audio.wav"):
                temp_file = project_dir / "metadata" / temp_name
                if temp_file.exists():
                    temp_file.unlink()
                    logger.info(f"清理：删除 {temp_file.name}")

            # 删中间步骤 JSON（处理完已没用了）
            for step_file in ("step1_outline.json", "step2_clips.json",
                              "step3_scored.json", "step4_titled.json", "step5_collections.json"):
                f = project_dir / "metadata" / step_file
                if f.exists():
                    f.unlink()
        except Exception as cleanup_error:
            logger.warning(f"清理临时文件失败（不影响主流程）：{cleanup_error}")

        # 注: 不要把 video_size 清零! raw 删了, 但 video_size 仍记录原文件大小, UI 用来显示"1.2 GB"
        # 之前 v2.1.21 之前清零了, 导致用户看不到原视频多大, 误以为 0 byte

        logger.info(f"数据库写入完成：{len(titled_clips)} clips, {len(collections)} collections")

        # 清理内存
        gc.collect()

        logger.info(f"项目处理完成：{project_id}")

        return {
            "success": True,
            "project_id": project_id,
            "outlines": len(outlines),
            "clips": len(titled_clips),
            "collections": len(collections),
        }
        
    except Exception as e:
        logger.error(f"处理失败：{e}", exc_info=True)
        # 标记 task failed + project failed (修复: 之前只标 task, project 永远卡 processing)
        try:
            with sync_get_db() as db:
                from ..models.database import Project
                proj = db.query(Project).filter(Project.id == project_id).first()
                if proj and proj.status == "processing":
                    proj.status = "failed"
                if task_id:
                    from ..models.database import Task
                    task_row = db.query(Task).filter(Task.id == task_id).first()
                    if task_row:
                        task_row.status = "failed"
                        task_row.completed_at = datetime.utcnow()
                        task_row.error_message = str(e)[:1000]
                db.commit()
        except Exception as cleanup_err:
            logger.warning(f"标记失败状态失败: {cleanup_err}")
        raise


@shared_task(name="backend.tasks.processing.scan_watch_folders", bind=True)
def scan_watch_folders(self):
    """每 30s 跑一次（被 celery beat 调度）—— 扫所有 enabled watch folders"""
    from ..api.watch_folders import scan_all_due_folders
    logger.info("scan_watch_folders tick")
    try:
        scan_all_due_folders()
    except Exception as e:
        logger.error(f"scan_watch_folders 失败: {e}", exc_info=True)
    return {"ok": True}
