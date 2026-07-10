"""混剪服务 v2.2.3 MVP

输入: 直播脚本 + 素材库 (clips 表 + 新传 video 的字幕)
输出: 按脚本关键词匹配的 source clips 拼接 + 脚本原文本烧字幕

MVP 简化:
- 脚本分段: LLM 按主题/动作拆 (防水脚本: 屋顶/外墙/阳台/材料/施工...)
- 素材匹配: 关键词 substring 匹配 (快速稳, 不调 LLM 评分)
- 时长分配: 每段按时长比例分配, 总和 ≤ target_duration
- 拼接: ffmpeg concat demuxer
- 烧字幕: 用脚本原文本当字幕 (不是原 clip 字幕)
"""
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def parse_script(script_text: str, target_duration: int = 60) -> List[Dict]:
    """LLM 把脚本按主题/动作分段

    返回 [{position: int, text: str, keywords: [str]}, ...]
    """
    from .llm_service import _call_llm

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
- 切片数 3-8 段 (太少没变化, 太多每段太短)
- 总时长约 {target_duration} 秒 (用户期望输出长度)
- 每段 text 是脚本连续的一段 (按顺序不重叠)
- keywords 是名词/动词, 用于匹配视频内容 (避免用"啊"等语气词)

只输出 JSON 数组, 不要任何其他文字.
"""
    content = _call_llm(prompt)
    if not content:
        logger.error("LLM 解析脚本失败")
        return []

    # 解析 JSON (兼容 markdown 围栏)
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        segments = json.loads(text)
        if not isinstance(segments, list):
            logger.error(f"脚本分段结果不是 list: {type(segments)}")
            return []
        # 校验每段字段
        valid = []
        for i, seg in enumerate(segments):
            if not isinstance(seg, dict):
                continue
            seg.setdefault("position", i)
            seg.setdefault("text", "")
            seg.setdefault("keywords", [])
            if seg["text"]:  # text 必填
                valid.append(seg)
        logger.info(f"脚本解析: {len(valid)} 段")
        return valid
    except json.JSONDecodeError as e:
        logger.error(f"脚本分段 JSON 解析失败: {e}\n原始: {text[:500]}")
        return []


def build_clip_library(clip_records: List[Dict]) -> List[Dict]:
    """构造素材库 — 每条记录含 id, title, video_path, subtitle_text, source_project_id

    clip_records 来自 SELECT clips.* LEFT JOIN projects (拿 source_project_id)
    """
    library = []
    for c in clip_records:
        subtitle_text = (c.get("description") or c.get("title") or "").strip()
        # 优先用 clip.metadata.subtitle_text (运行时 LLM 已用过的描述), fallback title
        metadata = c.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("subtitle_text"):
            subtitle_text = metadata["subtitle_text"]
        library.append({
            "clip_id": c["id"],
            "source_project_id": c["project_id"],
            "title": c.get("title", ""),
            "subtitle_text": subtitle_text,
            "video_path": c.get("video_path", ""),
            "duration": c.get("duration", 0),
        })
    return library


def match_clips_for_segments(
    segments: List[Dict],
    clip_library: List[Dict],
    target_duration: int = 60,
) -> List[Dict]:
    """为每段 segment 匹配最合适的 clip + 时长分配

    返回 [{position, text, keywords, matched_clip_id, source_project_id,
            matched_video_path, source_start, source_end, clip_duration}, ...]
    """
    if not segments:
        return []

    # 每段时长分配 (按 text 长度比例, 总和 ≤ target_duration)
    total_chars = sum(len(s["text"]) for s in segments) or len(segments)
    durations = []
    remaining = target_duration
    for i, seg in enumerate(segments):
        ratio = len(seg["text"]) / total_chars
        if i == len(segments) - 1:
            seg_duration = max(5, remaining)  # 最后一段用完
        else:
            seg_duration = max(5, min(int(target_duration * ratio), remaining - 5 * (len(segments) - i - 1)))
            remaining -= seg_duration
        durations.append(seg_duration)

    results = []
    for seg, seg_dur in zip(segments, durations):
        keywords = seg.get("keywords", [])
        text_words = set(keywords + [w for w in seg["text"][:50] if len(w) >= 2])

        # 关键词 substring 匹配 (MVP), 后续可换 embedding 相似度
        scored = []
        for clip in clip_library:
            sub_text = clip.get("subtitle_text", "")
            if not sub_text:
                continue
            # 计算关键词命中数
            hits = sum(1 for kw in keywords if kw and kw in sub_text)
            if hits == 0:
                continue
            score = hits / max(len(keywords), 1)
            scored.append((score, clip))

        if not scored:
            logger.warning(f"segment {seg['position']} 没匹配到任何 clip (keywords={keywords})")
            continue

        scored.sort(key=lambda x: -x[0])
        best_score, best_clip = scored[0]
        clip_dur = best_clip.get("duration", 0) or 10

        # 决定从 source clip 上截多长 (用 clip 完整时长, 后续可改成掐头去尾)
        use_dur = min(seg_dur, clip_dur)
        # 简单截中间 (避免掐头去尾的转场问题)
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
            "matched_video_path": best_clip["video_path"],
            "source_start": float(start),
            "source_end": float(end),
            "clip_duration": use_dur,
            "match_score": float(best_score),
        })

    logger.info(f"匹配完成: {len(results)}/{len(segments)} 段匹配到 clip")
    return results


def assemble_mix_video(
    segments: List[Dict],
    clips_root: Path,
    output_path: Path,
    script_text: str = "",
    subtitle_style: Optional[Dict] = None,
) -> Path:
    """按 segments 顺序拼接 + 烧脚本原文本字幕

    segments: match_clips_for_segments 返回的列表
    clips_root: data/projects/ (source clip video_path 相对此)
    output_path: 输出 mp4 全路径
    """
    if not segments:
        raise ValueError("没有匹配的 segments, 无法拼接")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1) 写 concat list (按 position 顺序, 用 source_start/end 截取)
    concat_list = output_path.parent / "_concat_list.txt"
    extract_dir = output_path.parent / "_extract_parts"
    extract_dir.mkdir(parents=True, exist_ok=True)

    part_files = []
    try:
        for i, seg in enumerate(segments):
            src_video = clips_root / seg["matched_video_path"]
            if not src_video.is_absolute():
                src_video = (clips_root / seg["matched_video_path"]).resolve()
            if not src_video.exists():
                logger.warning(f"source clip 缺失: {src_video}")
                continue

            part_path = extract_dir / f"part_{i:03d}.mp4"
            # 用 ffmpeg 截取 source_start ~ source_end
            cmd_extract = [
                "ffmpeg", "-y",
                "-ss", str(seg["source_start"]),
                "-to", str(seg["source_end"]),
                "-i", str(src_video),
                "-c", "copy",  # 不重新编码, 快
                "-avoid_negative_ts", "make_zero",
                str(part_path),
            ]
            try:
                subprocess.run(cmd_extract, check=True, capture_output=True, timeout=120)
                if part_path.exists():
                    part_files.append(part_path)
            except subprocess.CalledProcessError as e:
                logger.warning(f"extract part {i} 失败: {e.stderr.decode()[:200]}")
            except subprocess.TimeoutExpired:
                logger.warning(f"extract part {i} 超时")

        if not part_files:
            raise RuntimeError("所有 part extract 都失败, 无法拼接")

        # 写 concat list
        with open(concat_list, "w") as f:
            for pf in part_files:
                f.write(f"file '{pf.absolute()}'\n")

        # 2) concat demuxer 拼接 (用 libx264 稳, 不用 h264_videotoolbox — v2.2.1 bug)
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
        # extract parts 留作 debug, 不删 (小, 几 MB)

    return output_path


def build_script_srt(segments: List[Dict], total_duration: float) -> str:
    """用脚本分段生成 SRT 字幕 (烧字幕用)

    segments: match_clips_for_segments 返回的列表
    total_duration: 输出视频总时长

    按 segments[].clip_duration 比例分配 SRT 时间戳
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

        # SRT 时间戳格式 HH:MM:SS,mmm
        def fmt_time(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t - int(t)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        text = seg.get("text", "").strip().replace("\n", " ")
        srt_lines.append(f"{i}\n{fmt_time(start)} --> {fmt_time(end)}\n{text}\n")

    return "\n".join(srt_lines)


def burn_mix_subtitle(
    video_path: Path,
    srt_text: str,
    subtitle_style: Optional[Dict] = None,
) -> Path:
    """烧字幕到视频 (用 moviepy, 跟 step 7 烧字幕同模式)

    输出新文件: <video>.subtitled.mp4
    """
    from .subtitle_burner import burn_subtitles_with_moviepy

    if not srt_text.strip():
        logger.info("srt 为空, 跳过烧字幕")
        return video_path

    output_path = video_path.parent / f"{video_path.stem}.subtitled.mp4"

    # 写临时 srt
    tmp_srt = video_path.parent / "_burn.srt"
    tmp_srt.write_text(srt_text, encoding="utf-8")

    try:
        burn_subtitles_with_moviepy(
            video_path,
            output_path,
            srt_path=tmp_srt,
            subtitle_config=subtitle_style or {},
        )
        logger.info(f"烧字幕完成: {output_path}")
        # 替换原文件 (这样 output_video_path 直接指向最终文件)
        video_path.unlink()
        output_path.rename(video_path)
        return video_path
    finally:
        if tmp_srt.exists():
            tmp_srt.unlink()