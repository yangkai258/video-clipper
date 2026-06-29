# -*- coding: utf-8 -*-
"""视频处理 Celery 任务

流水线分 10 个 step，每个 step 一个独立函数：
- _load_project_config: 读 project.processing_config
- _run_step1_subtitle: 字幕生成（带心跳）
- _run_step2_to_6_outline: 大纲 + 时间线 + 评分 + 标题 + 聚类
- _run_step7_cut_clips: 切视频
- _run_step8_merge_collections: 合并合集
- _verify_files: 文件完整性验证
- _persist_results: 写库 + 标 completed
- _cleanup_temp_files: 删 raw + 临时文件
- _mark_failed: 失败时标 failed

process_video_pipeline 只做协调 + 异常处理 + 进度推进。
"""

import gc
import logging
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

from celery import shared_task
from sqlalchemy import select

from ..core.config import settings

logger = logging.getLogger(__name__)


# 进度常量（统一维护，避免魔数散落）
PROGRESS_DICT = {
    "task_start": 0,
    "subtitle_prepare": 2,
    "subtitle_done": 30,
    "outline_start": 32,
    "outline_done": 40,
    "timeline_done": 45,
    "score_done": 50,
    "title_done": 55,
    "cluster_done": 60,
    "fallback_done": 55,
    "cut_start": 65,
    "cut_done": 92,
    "merge_start": 93,
    "verify_done": 96,
    "complete": 100,
}

# 临时文件名
TEMP_SRT_PREFIX = "video_clipper_"
TEMP_SRT_SUFFIX = ".srt"
TEMP_SRT_DIR = "/tmp"

# 临时音频/中间文件
TEMP_AUDIO_FILES = ("temp_audio.wav", "temp_audio.m4a", "extracted_audio.wav")
INTERMEDIATE_JSON_FILES = (
    "step1_outline.json", "step2_clips.json",
    "step3_scored.json", "step4_titled.json", "step5_collections.json",
)

# 0-clip guard 错误信息
ZERO_CLIP_REASON = "未能识别到任何切片片段 (视频过短 或 无有效切点)"


# ───────────────────────── 公开 task ─────────────────────────


@shared_task(bind=True)
def process_video_pipeline(
    self,
    project_id: str,
    input_video_path: str,
    input_srt_path: str = None,
    task_id: str = None,
) -> dict:
    """视频处理流水线（celery task）。"""
    logger.info(f"开始处理项目：{project_id}")

    _mark_task_running(task_id)
    project_config, subtitle_config, project_dir, metadata_dir, output_dir, clips_dir, collections_dir = _prepare_directories(project_id, input_video_path)

    try:
        input_path = _validate_input(input_video_path)

        # Step 1: 字幕生成
        srt_path = _run_step1_subtitle(input_video_path, input_srt_path, metadata_dir, project_id, task_id, project_config)
        if not srt_path or not srt_path.exists():
            raise Exception("字幕生成失败")
        gc.collect()

        # Step 2-6: 大纲/时间线/评分/标题/聚类
        titled_clips, collections, outlines = _run_step2_to_6(srt_path, metadata_dir, project_config, task_id)

        # v2.2.1: 前/后置 padding — 给每个 clip 边界外扩几秒, 避免 LLM 判定 topic
        # 边界时切得太突兀。读 project_config.pre_padding_seconds /
        # post_padding_seconds (默认 0)。clamp 到 [0, video_duration], 防止越界。
        pre_pad = float(project_config.get("pre_padding_seconds", 0) or 0)
        post_pad = float(project_config.get("post_padding_seconds", 0) or 0)
        if pre_pad > 0 or post_pad > 0:
            video_duration = project_config.get("video_duration") or 0
            _apply_clip_padding(titled_clips, pre_pad, post_pad, video_duration)
            # collections 也得跟着外扩 (合集复用 clip 的 start/end)
            _apply_clip_padding(collections, pre_pad, post_pad, video_duration)
            logger.info(f"clip padding: pre={pre_pad}s, post={post_pad}s, video_duration={video_duration}s")

        # Step 7: 切割视频（cut_clips 内部维护 70%-90% 进度）
        with_subtitle = project_config.get("with_subtitle", True) if project_config else True
        output_format = project_config.get("output_format", "original") if project_config else "original"
        _run_step7_cut_clips(
            titled_clips, input_video_path, clips_dir, srt_path, subtitle_config,
            with_subtitle, project_id, output_format, task_id,
        )

        # Step 8: 合并合集（merge_collections 内部维护 90%-99% 进度）
        _run_step8_merge_collections(collections, clips_dir, collections_dir, task_id)

        # Step 9: 文件完整性验证
        _verify_files(titled_clips, collections, project_dir, clips_dir, collections_dir)

        # 清理临时 SRT（Y 方案：with_subtitle=False 时使用 /tmp）
        _cleanup_temp_srt(with_subtitle, srt_path)

        # Step 10: 写库 + 标 completed
        _persist_results(project_id, titled_clips, collections, task_id)

        # 0-clip guard：跑完 10 步但 0 产物
        if len(titled_clips) == 0 and len(collections) == 0:
            _mark_zero_output_failed(project_id, task_id, ZERO_CLIP_REASON)
            return {
                "success": False,
                "project_id": project_id,
                "reason": "no_clips_generated",
                "message": ZERO_CLIP_REASON,
            }

        # 清理 raw 视频 + 临时文件
        _cleanup_temp_files(project_dir)

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
        _mark_failed(project_id, task_id, e)
        raise


@shared_task
def scan_watch_folders() -> dict:
    """扫描 watch folder（v2.1.x 后期加的占位，避免打破路由）。"""
    return {"scanned": 0}


# ───────────────────────── Step 0: 任务启动 ─────────────────────────


def _mark_task_running(task_id: str) -> None:
    """标记 celery task 为 running + 写 started_at（ETA 估算需要）。"""
    if not task_id:
        return
    try:
        from ..core.database import sync_get_db
        from ..models.database import Task

        with sync_get_db() as db:
            task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
            if task:
                task.status = "running"
                if not task.started_at:
                    task.started_at = datetime.utcnow()
                # ponytail: 心跳字段, task_health watchdog 用来判断真"卡死"
                task.progress_changed_at = datetime.utcnow()
                db.commit()
    except Exception as e:
        logger.warning(f"task 启动标记失败: {e}")


def _prepare_directories(
    project_id: str, input_video_path: str
) -> Tuple[dict, dict, Path, Path, Path, Path, Path]:
    """读项目配置 + 准备输出目录。"""
    from ..core.database import sync_get_db
    from ..models.database import Project

    strategy_config, subtitle_config = _load_project_config(project_id)

    project_dir = Path(input_video_path).parent.parent
    metadata_dir = project_dir / "metadata"
    output_dir = project_dir / "output"
    clips_dir = output_dir / "clips"
    collections_dir = output_dir / "collections"
    for d in (metadata_dir, clips_dir, collections_dir):
        d.mkdir(parents=True, exist_ok=True)

    return strategy_config, subtitle_config, project_dir, metadata_dir, output_dir, clips_dir, collections_dir


def _apply_clip_padding(items: list, pre_pad: float, post_pad: float, video_duration: float) -> None:
    """给 clip / collection 列表应用前后置 padding, 在原地修改 dict。

    字段名兼容 start/start_time, end/end_time。clamp 到 [0, video_duration],
    防止 start < 0 或 end > video_duration 越界。

    为啥改 in-place: cut_clips / merge_collections / _persist_results 都
    读同一份 titled_clips / collections list, 改了它们都受益。
    """
    for item in items:
        start = item.get("start_time") or item.get("start", 0) or 0
        end = item.get("end_time") or item.get("end", start + 1) or (start + 1)
        new_start = max(0, float(start) - pre_pad)
        new_end = (float(end) + post_pad) if video_duration <= 0 else min(float(video_duration), float(end) + post_pad)
        # 也保证 new_end > new_start (clamp 后不能反转)
        if new_end <= new_start:
            new_end = min(float(video_duration) if video_duration > 0 else new_start + 1, new_start + 1)
        item["start_time"] = new_start
        item["end_time"] = new_end
        # 兼容 start/end 别名
        item["start"] = new_start
        item["end"] = new_end


def _load_project_config(project_id: str) -> Tuple[dict, dict]:
    """从 DB 读项目处理配置。返回 (strategy_config, subtitle_config)。"""
    from ..core.database import sync_get_db
    from ..models.database import Project

    with sync_get_db() as db:
        project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
        if not project:
            logger.warning("项目配置不存在，使用默认策略")
            return {}, {}
        strategy_config = project.processing_config or {}
        # 字段名兼容：DB 存的是 subtitle_style，老字段叫 subtitle_config
        subtitle_config = (
            strategy_config.get("subtitle_style")
            or strategy_config.get("subtitle_config")
            or {}
        )
        logger.info(f"使用切片策略：{strategy_config.get('strategy_name', '默认')}")
        logger.info(f"策略参数：target_duration={strategy_config.get('target_duration', 60)}s, max_clips={strategy_config.get('max_clips', 20)}")
        logger.info(f"字幕配置：{subtitle_config}")
        return strategy_config, subtitle_config


def _validate_input(input_video_path: str) -> Path:
    """校验视频文件存在 + 大小足够。"""
    input_path = Path(input_video_path)
    if not input_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {input_video_path}")
    input_size = input_path.stat().st_size
    if input_size < 1024:  # 小于 1KB 视作无效
        raise ValueError(f"视频文件过小 ({input_size} bytes), 上传可能未完成. 请重新上传.")
    return input_path


# ───────────────────────── Step 1: 字幕生成 ─────────────────────────


def _run_step1_subtitle(
    input_video_path: str,
    input_srt_path: str,
    metadata_dir: Path,
    project_id: str,
    task_id: str,
    strategy_config: dict,
) -> Path:
    """Step 1: 字幕生成（含心跳线程）。"""
    from ..services.subtitle_service import generate_subtitle

    logger.info("Step 1: 生成字幕")
    _update_task_progress(task_id, PROGRESS_DICT["subtitle_prepare"], "准备生成字幕")

    with_subtitle = strategy_config.get("with_subtitle", True) if strategy_config else True
    logger.info(f"字幕模式：{'落盘到项目目录' if with_subtitle else 'in_memory 模式（不写项目目录，用完即删）'}")

    # 心跳：whisper 跑得慢（30s-3min），每 5s 推一次进度
    heartbeat_stop = _start_subtitle_heartbeat(task_id)

    try:
        if with_subtitle:
            srt_path = _generate_or_copy_srt_to_disk(input_video_path, input_srt_path, metadata_dir)
        else:
            srt_path = _generate_or_copy_srt_to_tmp(input_video_path, input_srt_path, project_id, generate_subtitle)
    finally:
        heartbeat_stop.set()

    _update_task_progress(task_id, PROGRESS_DICT["subtitle_done"], "字幕生成完成")
    return srt_path


def _start_subtitle_heartbeat(task_id: str) -> threading.Event:
    """启动字幕进度心跳线程，返回 stop event。"""
    import time as _time

    stop = threading.Event()

    def _heartbeat():
        t0 = _time.time()
        while not stop.is_set():
            elapsed = int(_time.time() - t0)
            # 0s→2%, 60s→16%, 120s→25%, 180s+→30%
            pct = PROGRESS_DICT["subtitle_prepare"] + min(28, int(elapsed / 120 * 28))
            _update_task_progress(task_id, pct, f"生成字幕中... ({elapsed}s)")
            stop.wait(5)

    t = threading.Thread(target=_heartbeat, daemon=True)
    t.start()
    return stop


def _generate_or_copy_srt_to_disk(
    input_video_path: str, input_srt_path: str, metadata_dir: Path
) -> Path:
    """落盘模式：写到 metadata/input.srt。"""
    from ..services.subtitle_service import generate_subtitle

    srt_path = metadata_dir / "input.srt"
    if input_srt_path and Path(input_srt_path).exists():
        logger.info(f"使用现有字幕文件：{input_srt_path}")
        if Path(input_srt_path).resolve() != srt_path.resolve():
            shutil.copy(input_srt_path, srt_path)
        else:
            logger.info("字幕文件已在正确位置，跳过复制")
    else:
        logger.info("自动生成字幕（落盘模式）")
        srt_path = generate_subtitle(input_video_path, srt_path)
    return srt_path


def _generate_or_copy_srt_to_tmp(
    input_video_path: str, input_srt_path: str, project_id: str, generate_subtitle
) -> Path:
    """Y 方案：写到 /tmp 临时文件，不污染项目目录。"""
    tmp = tempfile.NamedTemporaryFile(
        suffix=TEMP_SRT_SUFFIX,
        prefix=f"{TEMP_SRT_PREFIX}{project_id}_",
        delete=False,
        mode="w",
        encoding="utf-8",
        dir=TEMP_SRT_DIR,
    )
    tmp.close()
    srt_path = Path(tmp.name)
    logger.info(f"自动生成字幕（临时文件模式）：{srt_path}")
    if input_srt_path and Path(input_srt_path).exists():
        shutil.copy(input_srt_path, srt_path)
        logger.info(f"使用现有字幕文件（复制到临时）：{input_srt_path}")
    else:
        result = generate_subtitle(input_video_path, srt_path)
        if result != srt_path and Path(result).exists():
            srt_path = Path(result)
    return srt_path


# ───────────────────────── Step 2-6: 大纲/时间线/评分/标题/聚类 ─────────────────────────


def _run_step2_to_6(
    srt_path: Path,
    metadata_dir: Path,
    strategy_config: dict,
    task_id: str,
) -> Tuple[list, list, list]:
    """Step 2-6: 大纲提取 → 时间线 → 评分 → 标题 → 聚类。"""
    from ..services.llm_service import (
        extract_outline, create_timeline, score_clips, generate_titles, cluster_collections
    )

    _update_task_progress(task_id, PROGRESS_DICT["outline_start"], "提取内容大纲")
    logger.info("Step 2: 提取大纲")
    outlines = extract_outline(srt_path, metadata_dir, strategy_config)
    _update_task_progress(task_id, PROGRESS_DICT["outline_done"], "提取内容大纲")

    if not outlines:
        # AI 失败 → local fallback
        return _run_local_fallback(srt_path, metadata_dir, strategy_config, task_id)

    # 正常 AI 路径
    return _run_ai_pipeline(outlines, srt_path, metadata_dir, strategy_config, task_id)


def _run_local_fallback(
    srt_path: Path, metadata_dir: Path, strategy_config: dict, task_id: str
) -> Tuple[list, list, list]:
    """AI 大纲失败 → 本地方案直接基于字幕段落切片。"""
    from ..services.local_processor import generate_clips_from_subtitle

    logger.warning("AI 大纲提取失败，使用本地备用方案（基于字幕段落自动切片）")
    clips_data = generate_clips_from_subtitle(srt_path, metadata_dir, strategy_config)
    titled_clips = clips_data.get("clips", [])
    collections = clips_data.get("collections", [])
    outlines = clips_data.get("outlines", [])
    _update_task_progress(task_id, PROGRESS_DICT["fallback_done"], "本地方案生成完成")
    return titled_clips, collections, outlines


def _run_ai_pipeline(
    outlines: list, srt_path: Path, metadata_dir: Path, strategy_config: dict, task_id: str
) -> Tuple[list, list, list]:
    """正常 AI 流水线：timeline → score → titles → collections。"""
    from ..services.llm_service import (
        create_timeline, score_clips, generate_titles, cluster_collections
    )

    logger.info("Step 3: 创建时间线")
    _update_task_progress(task_id, PROGRESS_DICT["timeline_done"], "构建时间线")
    timeline = create_timeline(outlines, srt_path, metadata_dir, strategy_config)

    logger.info("Step 4: 切片评分")
    _update_task_progress(task_id, PROGRESS_DICT["score_done"], "评分候选片段")
    scored_clips = score_clips(timeline, metadata_dir, strategy_config)

    logger.info("Step 5: 生成标题")
    _update_task_progress(task_id, PROGRESS_DICT["title_done"], "生成片段标题")
    titled_clips = generate_titles(scored_clips, metadata_dir, srt_path=srt_path, strategy_config=strategy_config)

    logger.info("Step 6: 主题聚类")
    _update_task_progress(task_id, PROGRESS_DICT["cluster_done"], "主题聚类")
    collections = cluster_collections(titled_clips, metadata_dir, strategy_config)

    return titled_clips, collections, outlines


# ───────────────────────── Step 7: 切视频 ─────────────────────────


def _run_step7_cut_clips(
    titled_clips: list,
    input_video_path: str,
    clips_dir: Path,
    srt_path: Path,
    subtitle_config: dict,
    with_subtitle: bool,
    project_id: str,
    output_format: str,
    task_id: str,
) -> None:
    """Step 7: 切视频。cut_clips 内部维护 70%-90% 进度。"""
    from ..services.video_service import cut_clips

    logger.info("Step 7: 切割视频")
    _update_task_progress(task_id, PROGRESS_DICT["cut_start"], "开始切割视频")
    logger.info(f"字幕烧录：{'开启' if with_subtitle else '关闭（纯剪片子）'}")
    logger.info(f"输出格式：{output_format}")
    cut_clips(
        titled_clips,
        input_video_path,
        clips_dir,
        input_srt=srt_path if with_subtitle else None,
        task_id=task_id,
        subtitle_config=subtitle_config,
        with_subtitle=with_subtitle,
        project_id=project_id,  # 切完第一片后抽帧做封面
        output_format=output_format,
    )
    _update_task_progress(task_id, PROGRESS_DICT["cut_done"], "切割完成")


# ───────────────────────── Step 8: 合并合集 ─────────────────────────


def _run_step8_merge_collections(
    collections: list, clips_dir: Path, collections_dir: Path, task_id: str
) -> None:
    """Step 8: 合并合集。merge_collections 内部维护 90%-99% 进度。"""
    from ..services.video_service import merge_collections

    logger.info("Step 8: 合并合集")
    _update_task_progress(task_id, PROGRESS_DICT["merge_start"], "合并合集")
    merge_collections(collections, clips_dir, collections_dir, task_id=task_id)


# ───────────────────────── Step 9: 文件完整性 ─────────────────────────


def _verify_files(
    titled_clips: list,
    collections: list,
    project_dir: Path,
    clips_dir: Path,
    collections_dir: Path,
) -> None:
    """Step 9: 验证所有 clip + collection 视频文件都生成了。"""
    logger.info("Step 9: 验证文件完整性")

    missing_files = _find_missing_clips(titled_clips, project_dir, clips_dir)
    missing_collections = _find_missing_collections(collections, collections_dir)

    if missing_collections:
        logger.warning(f"合集生成失败 {len(missing_collections)} 个，但切片正常，继续完成：{missing_collections[:3]}")

    if missing_files:
        logger.error(f"文件生成不完整，缺失 {len(missing_files)} 个文件：{missing_files[:5]}...")
        raise Exception(f"文件生成失败，缺失：{missing_files[:3]}")

    logger.info(
        f"文件完整性验证通过：{len(titled_clips)} clips + "
        f"{len(collections) - len(missing_collections)} collections"
    )


def _find_missing_clips(titled_clips: list, project_dir: Path, clips_dir: Path) -> list:
    """找出缺失的 clip 文件路径。"""
    missing = []
    for clip in titled_clips:
        # 优先检查 video_path 字段
        video_path = clip.get("video_path")
        if video_path and (project_dir / video_path).exists():
            continue
        # fallback: 用 index 构造预期路径
        safe_title = "".join(c for c in clip.get("title", f"clip_{clip.get('index', 1)}") if c not in '<>:"/\\|？*')
        expected_path = clips_dir / f"{clip.get('index', 1)}_{safe_title[:50]}.mp4"
        if not expected_path.exists():
            missing.append(str(expected_path))
    return missing


def _find_missing_collections(collections: list, collections_dir: Path) -> list:
    """找出缺失的 collection 文件路径。"""
    missing = []
    for coll in collections:
        video_path = coll.get("video_path")
        if video_path and Path(video_path).exists():
            continue
        expected_path = collections_dir / f"{coll.get('title', '合集')}.mp4"
        if not expected_path.exists():
            missing.append(str(expected_path))
    return missing


# ───────────────────────── Step 10: 写库 ─────────────────────────


def _persist_results(
    project_id: str,
    titled_clips: list,
    collections: list,
    task_id: str,
) -> None:
    """Step 10: 写库 + 标 project/task 为 completed。"""
    logger.info("Step 10: 写入数据库")
    _write_clips_collections(project_id, titled_clips, collections)
    _mark_project_completed(project_id, task_id)


def _write_clips_collections(
    project_id: str, titled_clips: list, collections: list
) -> None:
    """清旧记录 + 插入新 clip / collection。"""
    from ..core.database import sync_get_db
    from ..models.database import Clip, Collection

    with sync_get_db() as db:
        db.query(Clip).filter(Clip.project_id == project_id).delete()
        db.query(Collection).filter(Collection.project_id == project_id).delete()

        for clip_data in titled_clips:
            clip = Clip(
                id=str(uuid.uuid4()),
                project_id=project_id,
                title=clip_data.get("title", f"片段 {clip_data.get('index', 1)}"),
                start_time=clip_data.get("start", 0),
                end_time=clip_data.get("end", 0),
                duration=clip_data.get("duration", 0),
                score=clip_data.get("score", 50),
                video_path=clip_data.get(
                    "video_path",
                    f"output/clips/{clip_data.get('index', 1)}_片段.mp4",
                ),
                # v2.1.26: 存 clip 宽高, 让前端区分横/竖屏
                width=clip_data.get("width"),
                height=clip_data.get("height"),
            )
            db.add(clip)

        for coll_data in collections:
            coll_id = coll_data.get("id") or str(uuid.uuid4())
            coll = Collection(
                id=coll_id,
                project_id=project_id,
                title=coll_data.get("title", "合集"),
                description=coll_data.get("description", ""),
                clip_ids=coll_data.get("clip_ids", []),
                video_path=coll_data.get("video_path", ""),
            )
            db.add(coll)

        db.commit()  # 先提交 clips/collections, 下一步再 commit status


def _mark_project_completed(project_id: str, task_id: str) -> None:
    """标 project.status = completed + task.completed_at。"""
    from ..core.database import sync_get_db
    from ..models.database import Project, Task

    with sync_get_db() as db:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.status = "completed"
            project.completed_at = datetime.utcnow()

        if task_id:
            task_row = db.query(Task).filter(Task.id == task_id).first()
            if task_row:
                task_row.status = "completed"
                task_row.completed_at = datetime.utcnow()
                task_row.progress = PROGRESS_DICT["complete"]
                # v2.2.1: 实际总耗时归集 (completed_at - started_at)
                # 跟 estimated_total_at_start_seconds 一起, 后续做预估模型
                if task_row.started_at:
                    task_row.actual_total_seconds = (datetime.utcnow() - task_row.started_at).total_seconds()

        db.commit()


# ───────────────────────── Cleanup ─────────────────────────


def _cleanup_temp_srt(with_subtitle: bool, srt_path: Path) -> None:
    """清理临时 SRT 文件（Y 方案下 with_subtitle=False 才用临时文件）。"""
    if with_subtitle or not srt_path or not srt_path.exists():
        return
    try:
        srt_path.unlink()
        logger.info(f"已清理临时 SRT 文件：{srt_path}")
    except Exception as e:
        logger.warning(f"清理临时 SRT 失败：{e}")


def _cleanup_temp_files(project_dir: Path) -> None:
    """删 raw 视频 + 临时音频 + 中间 JSON（独立 try，不影响主流程）。"""
    try:
        raw_video = project_dir / "raw" / "input.mp4"
        if raw_video.exists():
            raw_size = raw_video.stat().st_size
            raw_video.unlink()
            logger.info(f"清理：删除 raw/input.mp4 ({raw_size/1024/1024:.1f} MB)")
            try:
                (project_dir / "raw").rmdir()
            except OSError:
                pass

        metadata_dir = project_dir / "metadata"
        for temp_name in TEMP_AUDIO_FILES:
            temp_file = metadata_dir / temp_name
            if temp_file.exists():
                temp_file.unlink()
                logger.info(f"清理：删除 {temp_file.name}")

        for step_file in INTERMEDIATE_JSON_FILES:
            f = metadata_dir / step_file
            if f.exists():
                f.unlink()
    except Exception as cleanup_error:
        logger.warning(f"清理临时文件失败（不影响主流程）：{cleanup_error}")


# ───────────────────────── 失败 / Guard ─────────────────────────


def _mark_failed(project_id: str, task_id, error: Exception) -> None:
    """失败时标 project.status = failed + task.error_message。"""
    try:
        from ..core.database import sync_get_db
        from ..models.database import Project, Task

        with sync_get_db() as db:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project and project.status == "processing":
                project.status = "failed"
            if task_id:
                task_row = db.query(Task).filter(Task.id == task_id).first()
                if task_row:
                    task_row.status = "failed"
                    task_row.completed_at = datetime.utcnow()
                    task_row.error_message = str(error)[:1000]
            db.commit()
    except Exception as cleanup_err:
        logger.warning(f"标记失败状态失败: {cleanup_err}")


def _mark_zero_output_failed(project_id: str, task_id: str, reason: str) -> None:
    """0-clip guard (v2.1.23): pipeline 跑完但 0 产物 → 改标 failed。

    设计：
    - 检查项目状态必须是 completed 且未删除 (避免覆盖用户主动删除的项目)
    - 检查 task 状态必须是 completed (避免覆盖正在运行的 task)
    - 失败仅 warning，不抛异常
    """
    try:
        from ..core.database import sync_get_db
        from ..models.database import Project, Task

        with sync_get_db() as db:
            project = db.query(Project).filter(Project.id == project_id).first()
            if project and project.status == "completed" and project.deleted_at is None:
                project.status = "failed"
                project.completed_at = None
            if task_id:
                task_row = db.query(Task).filter(Task.id == task_id).first()
                if task_row and task_row.status == "completed":
                    task_row.status = "failed"
                    task_row.error_message = reason
            db.commit()
            logger.warning(f"0-clip guard: project {project_id} 跑完 10 步但 0 产物, 改标 failed")
    except Exception as guard_err:
        logger.warning(f"0-clip guard 写库失败: {guard_err}")


# ───────────────────────── 进度更新辅助 ─────────────────────────


def _update_task_progress(task_id: str, progress: int, current_step: str) -> None:
    """更新 Task 表的 progress + current_step（短事务，写完即关）。

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

        with sync_get_db() as db:
            task = db.execute(select(Task).where(Task.id == task_id)).scalar_one_or_none()
            if task:
                task.progress = max(0, min(100, progress))
                task.current_step = current_step[:255]
                # 心跳字段, task_health watchdog 用来判断真"卡死"
                task.progress_changed_at = datetime.utcnow()
                db.commit()
    except Exception as e:
        logger.warning(f"进度更新失败 (progress={progress}, step={current_step}): {e}")