"""混剪服务 v2.2.5 (跟切片项目解耦)

输入: 直播脚本 + 素材库 (从切片 db 读 clip 库, 不写切片 Project/Clip)
输出: 按脚本关键词匹配的 source clips 拼接 + 脚本原文本烧字幕

跟 v2.2.2 混剪 MVP 区别:
- 之前: 混剪数据写到切片 db Project (project_type='mix' + 字段) + MixSegment 共享 clip 库
- 现在: 混剪 db 完全独立 (mix_projects + mix_source_clips + mix_tasks),
        mix 启动时只读切片 db 的 Clip 表, 不写切片 db
"""
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


# ──────────────────────────── LLM 脚本分段 ────────────────────────────


def parse_script(script_text: str, target_duration: int = 60) -> list[dict]:
    """LLM 把脚本按主题/动作分段

    返回 [{position: int, text: str, keywords: [str]}, ...]
    """
    from ..services.llm_service import _call_llm

    prompt = f"""你是一个短视频脚本分析师。用户要做一个 {target_duration} 秒的混剪视频。

任务: 把下面的直播脚本按"主题/位置/动作"切成多个片段 (segment), 每个 segment 应该:
1. 描述一个独立的视觉场景 (例如"屋顶","外墙","阳台","材料展示","施工动作")
2. 包含原始脚本中的对应文字 (一字不漏, 保持原顺序)
3. 提供 2-4 个**视觉关键词** (用于从素材库找匹配的视频片段)

脚本:
\"\"\"
{script_text}
\"\"\"

输出 JSON 数组, 严格格式:
```json
[
  {{"position": 0, "text": "片段1的原文...", "keywords": ["屋顶", "施工"]}},
  {{"position": 1, "text": "片段2的原文...", "keywords": ["外墙", "防水"]}}
]
```

要求:
- 切片数 3-8 段
- 总时长约 {target_duration} 秒
- 每段 text 是脚本连续的一段 (按顺序不重叠)
- **keywords 必须是"画面/视觉"相关的名词 (如: 屋顶/瓦片/雨/工人/建筑/材料/防水卷材/吊车/室内/室外)**
  不要"主题/概念"词 (如: 防水/品质/保障/承诺/选择/正确/重要) — 视觉匹配系统靠这些关键词找对应画面
- 2-4 字中文优先, 逗号分隔

只输出 JSON 数组, 不要任何其他文字.
"""
    content = _call_llm(prompt)
    if not content:
        logger.error("LLM 解析脚本失败")
        return []

    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.removeprefix("json")
        text = text.strip()

    try:
        segments = json.loads(text)
        if not isinstance(segments, list):
            return []
        valid = []
        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            seg.setdefault("position", i)
            seg.setdefault("text", "")
            seg.setdefault("keywords", [])
            if seg["text"]:
                valid.append(seg)
        logger.info(f"脚本解析: {len(valid)} 段")
        return valid
    except json.JSONDecodeError as e:
        logger.error(f"脚本分段 JSON 解析失败: {e}")
        return []


# ──────────────────────────── v2.2.5: AI 帮写脚本 ────────────────────────────


def ai_help_write_script(
    topic: str | None,
    clips_context: list[dict],
    target_duration: int = 60,
) -> dict:
    """AI 根据用户主题 + 素材库标题, 生成一段带货口播脚本 (v2.2.5)

    Args:
        topic: 用户输入的产品/主题方向, 可空 (空时让 LLM 自己从素材库推断)
        clips_context: 前端传的候选素材 [{title, source_project_name?, subtitle_text?}, ...]
        target_duration: 目标时长秒, 默认 60

    Returns:
        {"script_text": "...", "model": "..."} 失败时 script_text 为空 + 抛异常
    """
    from ..core.config import settings
    from ..services.llm_service import _call_llm

    topic_str = (topic or "").strip() or "(自动)"
    titles = []
    for c in (clips_context or [])[:30]:
        title = (c.get("title") or "").strip()
        if title:
            titles.append(title)
    if not titles:
        titles_block = "(素材库为空, 请基于常见直播带货场景自由发挥)"
    else:
        titles_block = "\n".join(f"- {t}" for t in titles)

    prompt = f"""你是直播带货脚本撰写专家. 基于提供的素材库标题 + 用户主题, 生成一段 {target_duration} 秒左右的带货口播脚本.

要求:
- 中文, 适合口播
- 3-5 段自然语流, 每段包含产品卖点/痛点/解决方案
- 不要用极限词 (最佳/最好/100%/绝对/根治等)
- 长度 150-300 字 ({target_duration}s 大约这么多字)
- 不要用 "点击链接" "加微信" 等引流话术
- 风格口语化, 像在跟朋友推荐

用户主题: {topic_str}
素材库 (标题片段, 你只能引用这些):
{titles_block}

直接输出脚本正文, 不要 markdown 标题或注释.
"""

    content = _call_llm(prompt)
    if not content:
        raise RuntimeError("LLM 调用失败 (空响应), 请检查 API key / 网络")

    script_text = content.strip()
    # 去掉偶尔被加上的 markdown 代码块包裹
    if script_text.startswith("```"):
        parts = script_text.split("```")
        # parts: ['', 'language', 'content', '', ...]
        if len(parts) >= 3:
            script_text = parts[2].strip()
        else:
            script_text = script_text.strip("`").strip()

    logger.info(f"AI 帮写脚本完成: {len(script_text)} 字")
    return {
        "script_text": script_text,
        "model": settings.MINIMAX_MODEL,
    }


# ──────────────────────────── 素材库构建 ────────────────────────────


def build_clip_library_from_slice_db(
    candidate_clip_ids: list[str],
    slice_db_session_factory=None,
) -> list[dict]:
    """从切片 db 读 candidate_clip_ids 的 clip 详情 (不写切片 db)

    v2.2.5: candidate_clip_id 可能是 resource_clip (从 /library 来的) 或 clip (从 /clips/library 来的),
    先查切片 Clip 表, 找不到再查 ResourceClip 表. 两种 source 都加 source_type 字段区分.

    返回 [{clip_id, source_project_id, source_project_name, title,
           subtitle_text, video_path, duration, width, height, source_type, tags}, ...]

    v2.2.33: ResourceClip 加 tags 字段, 让 match_clips_for_segments 走视觉 tag overlap (主导 0.7)
    而不是纯 embed similarity (0.3). ResourceClip.tags 来自 v2.2.19 LLM auto-tag,
    中文 2-4 字关键词 (如 ["防水", "屋顶"]), 跟 seg.keywords 重叠度高 = 视觉匹配.
    """
    from ..core.database import sync_get_db
    from ..models.database import Clip, Project, ResourceClip

    library = []
    with sync_get_db() as db:
        for clip_id in candidate_clip_ids:
            # 先查切片 Clip 表
            clip = db.query(Clip).filter(Clip.id == clip_id).first()
            if clip:
                project = db.query(Project).filter(Project.id == clip.project_id).first()
                subtitle_text = (clip.description or clip.title or "").strip()
                if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
                    st = clip.clip_metadata.get("subtitle_text")
                    if st:
                        subtitle_text = st
                # 切片 Clip 也抽 tags (从 clip_metadata 提取 LLM 评分 tag, fallback to project.processing_config)
                clip_tags = []
                if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
                    for t in (clip.clip_metadata.get("tags") or []):
                        if isinstance(t, str):
                            clip_tags.append(t)
                        elif isinstance(t, dict) and "category" in t:
                            clip_tags.append(t["category"])
                library.append({
                    "clip_id": clip.id,
                    "source_project_id": clip.project_id,
                    "source_project_name": project.name if project else "",
                    "title": clip.title or "",
                    "subtitle_text": subtitle_text,
                    "video_path": clip.video_path or "",
                    "duration": clip.duration or 0,
                    "width": clip.width,
                    "height": clip.height,
                    "source_type": "project",
                    "tags": clip_tags,  # v2.2.33: tag overlap match
                })
                continue

            # 再查 ResourceClip (资源库)
            rc = db.query(ResourceClip).filter(ResourceClip.id == clip_id, ResourceClip.deleted_at.is_(None)).first()
            if rc:
                library.append({
                    "clip_id": rc.id,
                    "source_project_id": rc.source_project_id or rc.id,  # 资源库没源项目时用自身 id
                    "source_project_name": rc.source_project_name or "资源库",
                    "title": rc.name or "",
                    "subtitle_text": "",  # 资源库没存 subtitle_text
                    "video_path": rc.file_path or "",  # 资源库 file_path 是绝对路径 (data/resources/<id>.mp4)
                    "duration": rc.duration or 0,
                    "width": rc.width,
                    "height": rc.height,
                    "source_type": "library",
                    "tags": list(rc.tags or []) if isinstance(rc.tags, list) else [],  # v2.2.33: tag overlap match
                })
                continue

            logger.warning(f"candidate_clip_id 不存在 (Clip 或 ResourceClip 都查不到): {clip_id}")

    logger.info(f"从切片 db + 资源库加载 {len(library)} 个 clip (project: {sum(1 for x in library if x['source_type']=='project')}, library: {sum(1 for x in library if x['source_type']=='library')})")
    return library


# ──────────────────────────── 关键词匹配 ────────────────────────────


def match_clips_for_segments(
    segments: list[dict],
    clip_library: list[dict],
    target_duration: int = 60,
) -> list[dict]:
    """为每段 segment 匹配最合适的 clip + 时长分配

    返回 [{position, text, keywords, matched_clip_id, source_project_id,
            source_project_name, matched_video_path, source_start, source_end,
            clip_duration, match_score}, ...]
    """
    if not segments:
        return []

    # 时长分配 (按 text 长度比例)
    total_chars = sum(len(s["text"]) for s in segments) or len(segments)
    durations = []
    remaining = target_duration
    for i, seg in enumerate(segments):
        ratio = len(seg["text"]) / total_chars
        if i == len(segments) - 1:
            seg_duration = max(5, remaining)
        else:
            seg_duration = max(5, min(int(target_duration * ratio), remaining - 5 * (len(segments) - i - 1)))
            remaining -= seg_duration
        durations.append(seg_duration)

    results = []
    for seg, seg_dur in zip(segments, durations):
        keywords = seg.get("keywords", [])
        # 关键词归一化 (小写 + 去空格), 跟 clip_tags 对比
        keywords_norm = {k.strip().lower() for k in keywords if k and k.strip()}

        scored = []
        for clip in clip_library:
            clip_tags = clip.get("tags") or []
            # v2.2.33: tag overlap 主导 (0.7) — user 要"视觉匹配",
            # 播音稿关键词 vs 资源库 tag 重叠越多越匹配
            # 例: seg.keywords=["屋顶", "瓦片"] clip.tags=["屋顶", "防水"] → 1/2 = 0.5
            clip_tags_norm = {t.strip().lower() for t in clip_tags if isinstance(t, str) and t.strip()}
            tag_overlap = 0.0
            if keywords_norm and clip_tags_norm:
                hit = keywords_norm & clip_tags_norm
                tag_overlap = len(hit) / len(keywords_norm)  # 0.0 - 1.0

            # v2.2.33: embed 降到 0.3 (text-to-text 相似, 当作辅助)
            # tag 主导是因为: user 明确"画面匹配"而不是"语义匹配"
            embed_score = 0.0
            search_text = (clip.get("title", "") + " " + clip.get("subtitle_text", "")).strip()
            if search_text and keywords_norm:
                # 走老 hybrid_match_score 但只取 embed 部分 (0.0-1.0)
                from .embedding_service import hybrid_match_score
                embed_score = hybrid_match_score(
                    seg_text=seg["text"],
                    seg_keywords=keywords,
                    clip_title=clip.get("title", ""),
                    clip_subtitle=clip.get("subtitle_text", ""),
                )

            # 最终 score: tag 主导 (0.7) + embed 辅助 (0.3)
            score = 0.7 * tag_overlap + 0.3 * embed_score

            # v2.2.33: 0 阈值改成 0.05 (tag_overlap=0 但 embed>0.1 仍进)
            if score < 0.05:
                continue
            scored.append((score, clip))

        if not scored:
            logger.warning(f"segment {seg['position']} 没匹配到任何 clip (keywords={keywords})")
            # v2.2.26: 0 match fallback — 用第一个 candidate clip 兜底
            # 之前 v2.2.3 strict 0 match → fail, user 卡 progress=30%.
            # 现在: 0 match 时用第一个, score=0.0, warning log + project error_message 提示
            # 实际: resource_clips 没相关 keyword 的素材 (e.g. test_speed_xxx),
            #       fallback 让任务跑完, 给出可看的 video. user 后台上传真素材再重跑.
            if clip_library:
                fallback_clip = clip_library[0]
                fallback_dur = fallback_clip.get("duration", 0) or 10
                use_dur = min(seg_dur, fallback_dur)
                start = 0 if fallback_dur <= use_dur else (fallback_dur - use_dur) / 2
                end = start + use_dur
                results.append({
                    "position": seg["position"],
                    "text": seg["text"],
                    "keywords": keywords,
                    "matched_clip_id": fallback_clip["clip_id"],
                    "source_project_id": fallback_clip.get("source_project_id"),
                    "source_project_name": fallback_clip.get("source_project_name", ""),
                    "source_clip_title": fallback_clip.get("title", ""),
                    "matched_video_path": fallback_clip["video_path"],
                    "source_type": fallback_clip.get("source_type", "project"),
                    "source_start": float(start),
                    "source_end": float(end),
                    "clip_duration": use_dur,
                    "match_score": 0.0,  # 0 分, 标低质量 fallback
                    "fallback": True,  # 标 fallback 区分真匹配
                })
                logger.info(
                    f"segment {seg['position']} 用 fallback clip "
                    f"({fallback_clip.get('title', '?')!r}) 兜底, 实际匹配度低"
                )
                continue
            # 真的 0 candidate (没素材)
            continue

        scored.sort(key=lambda x: -x[0])
        best_score, best_clip = scored[0]
        clip_dur = best_clip.get("duration", 0) or 10

        use_dur = min(seg_dur, clip_dur)
        if clip_dur > use_dur:
            start = (clip_dur - use_dur) / 2
        else:
            start = 0
        end = start + use_dur

        results.append({
            "position": seg["position"],
            "text": seg["text"],
            "keywords": keywords,
            "matched_clip_id": best_clip["clip_id"],
            "source_project_id": best_clip["source_project_id"],
            "source_project_name": best_clip.get("source_project_name", ""),
            "source_clip_title": best_clip.get("title", ""),
            "matched_video_path": best_clip["video_path"],
            "source_type": best_clip.get("source_type", "project"),  # v2.2.5: project/library
            "source_start": float(start),
            "source_end": float(end),
            "clip_duration": use_dur,
            "match_score": float(best_score),
        })

    logger.info(f"匹配完成: {len(results)}/{len(segments)} 段")
    return results


# ──────────────────────────── ffmpeg 拼接 ────────────────────────────


def _is_valid_mp4(path: Path) -> bool:
    """v2.2.27: 检查文件是否真 mp4 (有 moov atom, ffmpeg 可读).

    dev mode 测时 resource clip 经常是 fake 文件 (size 大但内容 random, 没 moov atom).
    ffmpeg -c copy 会 "moov atom not found" 失败.

    Returns: True 真 mp4, False 无效.
    """
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if r.returncode != 0:
            return False
        # duration 应该是 "12.345678" 格式
        dur = r.stdout.strip()
        return bool(dur) and dur.replace(".", "").isdigit()
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:  # noqa: BLE001 — ffprobe 各种异常都当 invalid
        logger.debug(f"ffprobe 失败 ({path}): {e}")
        return False


def _make_placeholder_video(path: Path, duration: int = 5) -> bool:
    """v2.2.27: 生成 placeholder mp4 (color bars + tone, 通用 ffmpeg testsrc).

    兜底用 — 当 source clip 无效或 extract 失败时, 给这一段用 placeholder 补,
    整个 task 至少能产出可播的 video. user 看到 placeholder 段 + 警告 (source clip 失效).

    Args:
        path: 输出 mp4 路径
        duration: 秒数
    """
    try:
        # ffmpeg testsrc = color bars + 时间戳叠加, smptebars 也可
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=1280x720:rate=30",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "64k",
            "-shortest",
            str(path),
        ]
        subprocess.run(cmd, capture_output=True, text=True, timeout=60, check=False)
        return path.exists() and path.stat().st_size > 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:  # noqa: BLE001 — ffmpeg 各种异常都当失败
        logger.warning(f"生成 placeholder 失败: {e}")
        return False


def assemble_mix_video(
    segments: list[dict],
    slice_clips_root: Path,
    output_path: Path,
) -> Path:
    """按 segments 顺序拼接 (ffmpeg concat demuxer + libx264)

    segments: match_clips_for_segments 返回的列表
    slice_clips_root: data/projects/ (source clip 路径前缀)
    output_path: 输出 mp4 全路径
    """
    if not segments:
        raise ValueError("没有匹配的 segments, 无法拼接")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    concat_list = output_path.parent / "_concat_list.txt"
    extract_dir = output_path.parent / "_extract_parts"
    extract_dir.mkdir(parents=True, exist_ok=True)

    part_files = []
    try:
        for i, seg in enumerate(segments):
            # v2.2.5: source_type 分支 — library (资源库, 绝对路径) / project (切片项目, 相对路径要拼)
            source_type = seg.get("source_type", "project")
            src_rel = seg["matched_video_path"]

            if source_type == "library":
                # 资源库 file_path 已是绝对路径 (data/resources/<id>.mp4)
                src_video = Path(src_rel)
                if not src_video.is_absolute():
                    # 兼容万一存的是相对路径, fallback 到 data/resources/<basename>
                    src_video = (Path("data/resources") / src_rel).resolve()
            else:
                # v2.2.3 修: source clip 路径 = data/projects/<project_id>/<video_path>
                # 之前漏了 project_id 中间层, 现在用 seg["source_project_id"] 拼
                project_id = seg.get("source_project_id", "")
                if project_id and not src_rel.startswith(f"{project_id}/"):
                    # 相对路径 (output/clips/xxx.mp4) → 拼上 project_id 中间层
                    src_video = (slice_clips_root / project_id / src_rel).resolve()
                else:
                    # 已经是绝对或包含 project_id
                    src_video = Path(src_rel)
                    if not src_video.is_absolute():
                        src_video = (slice_clips_root / src_rel).resolve()

            if not src_video.exists():
                logger.warning(f"source clip 缺失: {src_video}")
                continue

            part_path = extract_dir / f"part_{i:03d}.mp4"
            # v2.2.27: 实际先用 ffprobe 验 mp4 有效 (moov atom), 无效 fallback 到 placeholder
            # 之前 dev mode 测上传 fake mp4 (100MB random data, 没 moov), ffmpeg -c copy fail
            # → "所有 part extract 都失败" 整个 task 挂. 现在用 placeholder 兜底
            is_valid = _is_valid_mp4(src_video)
            if not is_valid:
                logger.warning(
                    f"source clip 无效 (非真 mp4, e.g. dev test 文件): {src_video}, "
                    f"用 placeholder 兜底"
                )
                # 生成 placeholder (color bars + 时间戳)
                _make_placeholder_video(part_path, int(seg.get("source_end", 5) - seg.get("source_start", 0)))
                if part_path.exists() and part_path.stat().st_size > 0:
                    part_files.append(part_path)
                continue

            cmd_extract = [
                "ffmpeg", "-y",
                "-ss", str(seg["source_start"]),
                "-to", str(seg["source_end"]),
                "-i", str(src_video),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                str(part_path),
            ]
            try:
                subprocess.run(cmd_extract, check=True, capture_output=True, timeout=120)
                if part_path.exists() and part_path.stat().st_size > 0:
                    part_files.append(part_path)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
                logger.warning(f"extract part {i} 失败: {e}, 用 placeholder 兜底")
                # v2.2.27: extract 失败也走 placeholder, 不让整个 task 挂
                _make_placeholder_video(part_path, int(seg.get("source_end", 5) - seg.get("source_start", 0)))
                if part_path.exists() and part_path.stat().st_size > 0:
                    part_files.append(part_path)

        if not part_files:
            raise RuntimeError("所有 part extract 都失败")

        with open(concat_list, "w") as f:
            f.writelines(f"file '{pf.absolute()}'\n" for pf in part_files)

        # 用 libx264 (稳), 不用 h264_videotoolbox (v2.2.1 merge bug)
        cmd_concat = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            str(output_path),
        ]
        subprocess.run(cmd_concat, check=True, capture_output=True, timeout=600)
        logger.info(f"混剪拼接完成: {output_path}")

    finally:
        if concat_list.exists():
            concat_list.unlink()

    return output_path


# ──────────────────────────── SRT 生成 ────────────────────────────


def build_script_srt(segments: list[dict], total_duration: float = None) -> str:
    """用脚本分段生成 SRT 字幕 (烧字幕用)

    按 segments[].clip_duration 比例分配 SRT 时间戳.
    v2.2.3 修: 最后一个 segment end_time 必须 < total_duration (MoviePy 不允许 =),
    所以 total_duration 给定时, 留 0.1s buffer.
    """
    if not segments:
        return ""

    srt_lines = []
    cursor = 0.0
    for i, seg in enumerate(segments, 1):
        seg_dur = seg.get("clip_duration", 5.0)
        start = cursor
        end = cursor + seg_dur
        cursor = end

        # 最后一个 segment end_time 留 buffer (MoviePy 边界检查要求 <)
        if total_duration and i == len(segments):
            end = min(end, total_duration - 0.1)

        def fmt_time(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t - int(t)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        text = seg.get("text", "").strip().replace("\n", " ")
        srt_lines.append(f"{i}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n")

    return "\n".join(srt_lines)


# ──────────────────────────── 烧字幕 ────────────────────────────


def burn_mix_subtitle(
    video_path: Path,
    srt_text: str,
    subtitle_style: dict | None = None,
    total_duration: float = None,
) -> Path:
    """烧脚本原文本字幕到拼接视频

    输出替换原文件 (output_video_path 直接指向烧好的视频)

    v2.2.3: total_duration 透传给 build_script_srt 留 buffer (MoviePy 边界要求 end_time < duration)
    """
    from .subtitle_burner import burn_subtitles_with_moviepy

    if not srt_text.strip():
        logger.info("srt 为空, 跳过烧字幕")
        return video_path

    output_path = video_path.parent / f"{video_path.stem}.subtitled.mp4"

    tmp_srt = video_path.parent / "_burn.srt"
    tmp_srt.write_text(srt_text, encoding="utf-8")

    # 用 ffprobe 实时算 total_duration (如果 caller 没传)
    if total_duration is None or total_duration <= 0:
        import subprocess
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, timeout=30,
            )
            total_duration = float(result.stdout.strip() or 0)
        except Exception:
            total_duration = 0.0

    # 重写 srt 加 buffer
    if total_duration > 0:
        # 重新 parse srt 拿 segments, 加 buffer
        srt_text = build_script_srt_from_text(srt_text, total_duration)
        tmp_srt.write_text(srt_text, encoding="utf-8")

    try:
        burn_subtitles_with_moviepy(
            video_path,
            output_path,
            srt_path=tmp_srt,
            start=0.0,
            duration=total_duration or 60.0,
            subtitle_config=subtitle_style or {},
        )
        video_path.unlink()
        output_path.rename(video_path)
        logger.info(f"烧字幕完成: {video_path}")
        return video_path
    finally:
        if tmp_srt.exists():
            tmp_srt.unlink()


def build_script_srt_from_text(srt_text: str, total_duration: float) -> str:
    """给已有 srt 加 buffer (最后一 segment end_time < total_duration)"""
    import re
    # 简单实现: 解析最后一行 SRT, 限制 end_time
    lines = srt_text.strip().split("\n")
    if not lines:
        return srt_text

    # 找最后一个时间戳行
    last_ts_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if "-->" in lines[i]:
            last_ts_idx = i
            break

    if last_ts_idx < 0:
        return srt_text

    ts_line = lines[last_ts_idx]
    match = re.match(r"(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})", ts_line)
    if not match:
        return srt_text

    h, m, s, ms = int(match.group(5)), int(match.group(6)), int(match.group(7)), int(match.group(8))
    end_sec = h * 3600 + m * 60 + s + ms / 1000.0
    if end_sec >= total_duration:
        new_end = total_duration - 0.1
        new_h = int(new_end // 3600)
        new_m = int((new_end % 3600) // 60)
        new_s = int(new_end % 60)
        new_ms = int((new_end - int(new_end)) * 1000)
        new_ts = f"{new_h:02d}:{new_m:02d}:{new_s:02d},{new_ms:03d}"
        start_match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3}) -->", ts_line)
        if start_match:
            lines[last_ts_idx] = f"{start_match.group(1)} --> {new_ts}"

    return "\n".join(lines) + "\n"


def generate_thumbnail(video_path: Path, thumbnail_path: Path, ss_seconds: float = 1.0) -> bool:
    """抽视频某一秒作为缩略图 (mix project list card 用)

    v2.2.4: ffmpeg -ss 1s -frames:v 1 -vf scale=720:-2 (16:9 cover 等比)
    返回 True 成功, False 失败 (但不 raise — 缩略图不是关键路径)

    跟切片项目 thumbnail 区别:
    - 切片: <project_id>.jpg (data/projects/<id>/<project_id>.jpg)
    - 混剪: data/projects/<mix_id>/output/thumbnail.jpg (跟 mix_output.mp4 同目录)
    """
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 边界: video 时长 < ss_seconds 时取一半
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, timeout=30,
            )
            vid_duration = float(result.stdout.strip() or 0)
        except Exception:
            vid_duration = 0

        actual_ss = ss_seconds
        if vid_duration > 0 and ss_seconds >= vid_duration:
            actual_ss = max(0.5, vid_duration / 2)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(actual_ss),
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=720:-2",
            "-q:v", "3",
            str(thumbnail_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.warning(f"thumbnail ffmpeg failed: {result.stderr[:300]}")
            return False
        return thumbnail_path.exists() and thumbnail_path.stat().st_size > 0
    except Exception as e:
        logger.warning(f"generate_thumbnail exception: {e}")
        return False
