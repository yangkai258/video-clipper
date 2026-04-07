"""视频处理 Celery 任务"""
import gc
import logging
import uuid
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
    from ..models.database import Clip, Collection
    
    logger.info(f"开始处理项目：{project_id}")
    
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
            shutil.copy(input_srt_path, srt_path)
        else:
            logger.info("自动生成字幕")
            srt_path = generate_subtitle(input_video_path, srt_path)
        
        if not srt_path or not srt_path.exists():
            raise Exception("字幕生成失败")
        
        # 清理内存
        gc.collect()
        
        # Step 2: 大纲提取（可选，失败时使用本地备用方案）
        logger.info("Step 2: 提取大纲")
        outlines = extract_outline(srt_path, metadata_dir)
        
        if not outlines:
            logger.warning("AI 大纲提取失败，使用本地备用方案（基于字幕段落自动切片）")
            # 使用本地方案：直接从字幕生成时间线
            from ..services.local_processor import generate_clips_from_subtitle
            clips_data = generate_clips_from_subtitle(srt_path, metadata_dir)
            outlines = clips_data.get("outlines", [])
            titled_clips = clips_data.get("clips", [])
            collections = clips_data.get("collections", [])
        else:
            # Step 3: 时间线创建
            logger.info("Step 3: 创建时间线")
            timeline = create_timeline(outlines, srt_path, metadata_dir)
            
            # Step 4: 切片评分
            logger.info("Step 4: 切片评分")
            scored_clips = score_clips(timeline, metadata_dir)
            
            # Step 5: 生成标题
            logger.info("Step 5: 生成标题")
            titled_clips = generate_titles(scored_clips, metadata_dir)
            
            # Step 6: 主题聚类
            logger.info("Step 6: 主题聚类")
            collections = cluster_collections(titled_clips, metadata_dir)
        
        # Step 7: 切割视频
        logger.info("Step 7: 切割视频")
        cut_clips(titled_clips, input_video_path, clips_dir)
        
        # Step 8: 合并合集
        logger.info("Step 8: 合并合集")
        merge_collections(collections, clips_dir, collections_dir)
        
        # Step 9: 写入数据库
        logger.info("Step 9: 写入数据库")
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
                    video_path=f"output/clips/{clip_data.get('index', 1)}_片段.mp4",
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
