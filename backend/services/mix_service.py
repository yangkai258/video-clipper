"""混剪服务 v2.2.3 (跟切片项目解耦)

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
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────── LLM 脚本分段 ────────────────────────────


def parse_script(script_text: str, target_duration: int = 60) -> List[Dict]:
    """LLM 把脚本按主题/动作分段

    返回 [{position: int, text: str, keywords: [str]}, ...]
    """
    from ..services.llm_service import _call_llm

    prompt = f"""你是一个短视频脚本分析师。用户要做一个 {target_duration} 秒的混剪视频。

任务: 把下面的直播脚本按"主题/位置/动作"切成多个片段 (segment), 每个 segment 应该:
1. 描述一个独立的视觉场景 (例如"屋顶","外墙","阳台","材料展示","施工动作")
2. 包含原始脚本中的对应文字 (一字不漏, 保持原顺序)
3. 提供 2-4 个关键词 (用于从素材库找匹配的视频片段)

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
- keywords 是名词/动词, 用于匹配视频内容

只输出 JSON 数组, 不要任何其他文字.
"""
    content = _call_llm(prompt)
    if not content:
        logger.error("LLM 解析脚本失败")
        return []

    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        if text.startswith("json"):
            text = text[4:]
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


# ──────────────────────────── 素材库构建 ────────────────────────────


def build_clip_library_from_slice_db(
    candidate_clip_ids: List[str],
    slice_db_session_factory=None,
) -> List[Dict]:
    """从切片 db 读 candidate_clip_ids 的 clip 详情 (不写切片 db)

    返回 [{clip_id, source_project_id, source_project_name, title,
           subtitle_text, video_path, duration, width, height}, ...]
    """
    from ..models.database import Clip, Project
    from ..core.database import sync_get_db

    library = []
    with sync_get_db() as db:
        for clip_id in candidate_clip_ids:
            clip = db.query(Clip).filter(Clip.id == clip_id).first()
            if not clip:
                logger.warning(f"candidate_clip_id 不存在: {clip_id}")
                continue
            project = db.query(Project).filter(Project.id == clip.project_id).first()
            subtitle_text = (clip.description or clip.title or "").strip()
            if clip.clip_metadata and isinstance(clip.clip_metadata, dict):
                st = clip.clip_metadata.get("subtitle_text")
                if st:
                    subtitle_text = st
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
            })
    logger.info(f"从切片 db 加载 {len(library)} 个 clip")
    return library


# ──────────────────────────── 关键词匹配 ────────────────────────────


def match_clips_for_segments(
    segments: List[Dict],
    clip_library: List[Dict],
    target_duration: int = 60,
) -> List[Dict]:
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

        scored = []
        for clip in clip_library:
            # v2.2.3 改进: 搜索文本 = title + subtitle_text (subtitle_text 经常是空/不命中)
            # title 是 LLM 评分生成的, 含主题关键词 ("屋顶防水施工" 等), 命中率高
            search_text = (clip.get("title", "") + " " + clip.get("subtitle_text", "")).strip()
            if not search_text:
                continue
            # v2.2.3 改进: keywords 按空格 split (LLM 可能给 "防水套装" 当 1 个 keyword,
            # 但 clip title 是 "防水 套装", 需要 split 后才命中)
            expanded_keywords = []
            for kw in keywords:
                if not kw:
                    continue
                expanded_keywords.append(kw)
                # 复合词按空格切 (中文不带空格, 但 LLM 可能偶尔加空格)
                if " " in kw or len(kw) > 4:
                    expanded_keywords.extend(kw.replace(" ", ""))
            hits = sum(1 for kw in expanded_keywords if kw in search_text)
            if hits == 0:
                continue
            score = hits / max(len(expanded_keywords), 1)
            # 标题完全命中额外加分 (title 是 LLM 给的核心词)
            if any(kw and kw in clip.get("title", "") for kw in expanded_keywords):
                score *= 1.5
            scored.append((score, clip))

        if not scored:
            logger.warning(f"segment {seg['position']} 没匹配到任何 clip (keywords={keywords})")
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
            "source_start": float(start),
            "source_end": float(end),
            "clip_duration": use_dur,
            "match_score": float(best_score),
        })

    logger.info(f"匹配完成: {len(results)}/{len(segments)} 段")
    return results


# ──────────────────────────── ffmpeg 拼接 ────────────────────────────


def assemble_mix_video(
    segments: List[Dict],
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
            # v2.2.3 修: source clip 路径 = data/projects/<project_id>/<video_path>
            # 之前漏了 project_id 中间层, 现在用 seg["source_project_id"] 拼
            project_id = seg.get("source_project_id", "")
            src_rel = seg["matched_video_path"]
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
                logger.warning(f"extract part {i} 失败: {e}")

        if not part_files:
            raise RuntimeError("所有 part extract 都失败")

        with open(concat_list, "w") as f:
            for pf in part_files:
                f.write(f"file '{pf.absolute()}'\n")

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


def build_script_srt(segments: List[Dict], total_duration: float = None) -> str:
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
    subtitle_style: Optional[Dict] = None,
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
        # 替换 end_time (保留 start_time)
        start_match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3}) -->", ts_line)
        if start_match:
            lines[last_ts_idx] = f"{start_match.group(1)} --> {new_ts}"

    return "\n".join(lines) + "\n"