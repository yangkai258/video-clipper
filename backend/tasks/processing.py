"""视频处理 Celery 任务"""
import gc
import logging
import uuid
from datetime import datetime
from pathlib import Path
from celery import shared_task

from ..core.config import settings

logger = logging.getLogger(__name__)


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
    
    # 读取项目配置（包含切片策略 + 字幕配置）
    db_gen = sync_get_db()
    db = next(db_gen)
    try:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if project:
            strategy_config = project.processing_config or {}
            subtitle_config = strategy_config.get("subtitle_config", {})
            logger.info(f"使用切片策略：{strategy_config.get('strategy_name', '默认')}")
            logger.info(f"策略参数：target_duration={strategy_config.get('target_duration', 60)}s, max_clips={strategy_config.get('max_clips', 20)}")
            logger.info(f"字幕配置：{subtitle_config}")
        else:
            strategy_config = {}
            subtitle_config = {}
            logger.warning("项目配置不存在，使用默认策略")
    finally:
        db.close()
    
    try:
        project_dir = Path(input_video_path).parent.parent
        metadata_dir = project_dir / "metadata"
        output_dir = project_dir / "output"
        clips_dir = output_dir / "clips"
        collections_dir = output_dir / "collections"
        
        metadata_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        collections_dir.mkdir(parents=True, exist_ok=True)
        
        # Step 1: 字幕生成
        logger.info("Step 1: 生成字幕")
        srt_path = metadata_dir / "input.srt"
        
        if input_srt_path and Path(input_srt_path).exists():
            logger.info(f"使用现有字幕文件：{input_srt_path}")
            import shutil
            # 检查是否是同一个文件
            if Path(input_srt_path).resolve() != srt_path.resolve():
                shutil.copy(input_srt_path, srt_path)
            else:
                logger.info("字幕文件已在正确位置，跳过复制")
        else:
            logger.info("自动生成字幕")
            srt_path = generate_subtitle(input_video_path, srt_path)
        
        if not srt_path or not srt_path.exists():
            raise Exception("字幕生成失败")
        
        # 清理内存
        gc.collect()
        
        # 更新进度到 50%
        from ..core.database import sync_get_db
        
        db_gen = sync_get_db()
        db = next(db_gen)  # 获取 session
        try:
            from ..models.database import Task
            from sqlalchemy import select
            task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
            if task:
                task.progress = 50
                task.current_step = "分析内容结构"
                db.commit()
        finally:
            db.close()  # ✅ 修复：确保连接释放
        
        # Step 2: 大纲提取（可选，失败时使用本地备用方案）
        logger.info("Step 2: 提取大纲")
        outlines = extract_outline(srt_path, metadata_dir)
        
        if not outlines:
            logger.warning("AI 大纲提取失败，使用本地备用方案（基于字幕段落自动切片）")
            # 使用本地方案：直接从字幕生成时间线
            from ..services.local_processor import generate_clips_from_subtitle
            clips_data = generate_clips_from_subtitle(srt_path, metadata_dir, strategy_config)
            outlines = clips_data.get("outlines", [])
            titled_clips = clips_data.get("clips", [])
            collections = clips_data.get("collections", [])
        else:
            # Step 3: 时间线创建
            logger.info("Step 3: 创建时间线")
            timeline = create_timeline(outlines, srt_path, metadata_dir)
            
            # Step 4: 切片评分（使用策略参数）
            logger.info("Step 4: 切片评分")
            scored_clips = score_clips(timeline, metadata_dir, strategy_config)
            
            # Step 5: 生成标题
            logger.info("Step 5: 生成标题")
            titled_clips = generate_titles(scored_clips, metadata_dir)
            
            # Step 6: 主题聚类（使用策略参数）
            logger.info("Step 6: 主题聚类")
            collections = cluster_collections(titled_clips, metadata_dir, strategy_config)
        
        # Step 7: 切割视频（传入字幕配置）
        logger.info("Step 7: 切割视频")
        cut_clips(titled_clips, input_video_path, clips_dir, input_srt=srt_path, task_id=task_id, subtitle_config=subtitle_config)
        
        # Step 8: 合并合集
        logger.info("Step 8: 合并合集")
        merge_collections(collections, clips_dir, collections_dir, task_id=task_id)
        
        # Step 9: 验证文件完整性
        logger.info("Step 9: 验证文件完整性")
        missing_files = []
        for clip in titled_clips:
            # 优先检查 video_path 字段，如果不存在则根据索引构建预期路径
            video_path = clip.get("video_path")
            if video_path and Path(video_path).exists():
                continue
            # 构建预期路径并检查
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
        
        # Step 10: 写入数据库
        logger.info("Step 10: 写入数据库")
        db = None
        try:
            db = next(sync_get_db())
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
                )
                db.add(clip)
            
            # 插入 collections
            for coll_data in collections:
                # 获取该合集的 clip IDs
                clip_ids = [c["index"] for c in coll_data.get("clips", [])]
                coll = Collection(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    title=coll_data.get("title", f"合集 {coll_data.get('index', 1)}"),
                    clip_ids=clip_ids,
                    video_path=f"output/collections/{coll_data.get('title', '合集')}.mp4",
                )
                db.add(coll)
            
            # 更新项目状态为 completed
            from ..models.database import Project
            project = db.query(Project).filter(Project.id == project_id).first()
            if project:
                project.status = "completed"
                project.completed_at = datetime.utcnow()
            
            db.commit()
            logger.info(f"数据库写入完成：{len(titled_clips)} clips, {len(collections)} collections")
        except Exception as db_error:
            if db:
                db.rollback()
            logger.error(f"数据库写入失败：{db_error}")
            raise
        finally:
            if db:
                db.close()
        
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
        raise
