"""本地视频处理 - 不依赖外部 API 的备用方案"""
import json
import logging
import re
from pathlib import Path
from typing import List, Dict

# 复用 llm_service 的 min_score 归一化 (v2.1.25 统一数据契约)
from .llm_service import _normalize_min_score

logger = logging.getLogger(__name__)


def generate_clips_from_subtitle(srt_path: Path, metadata_dir: Path, strategy_config: dict = None) -> Dict:
    """从字幕生成本地切片方案（不依赖 AI）
    
    Args:
        srt_path: 字幕文件路径
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选）
    """
    strategy_config = strategy_config or {}
    target_duration = strategy_config.get("target_duration", 45.0)
    max_clips = strategy_config.get("max_clips", 20)
    rules = strategy_config.get("rules") or {}
    even_split = rules.get("even_split", False)
    avoid_silence = rules.get("avoid_silence", False)

    logger.info(f"本地处理 - 目标时长：{target_duration}s, 最大切片数：{max_clips}, even_split={even_split}, avoid_silence={avoid_silence}")

    # 解析字幕
    segments = parse_srt(srt_path)
    logger.info(f"解析到 {len(segments)} 个字幕段落")

    if not segments:
        return {"outlines": [], "clips": [], "collections": []}

    # 合并短段落（<3 秒）
    merged = merge_short_segments(segments, min_duration=3.0)
    logger.info(f"合并后 {len(merged)} 个段落")

    # 决定切分路径：
    # - even_split=true：按 target_duration 均匀切（教程/课程类内容）
    # - 否则：按语义边界（单段超长硬切 / 段间静默强制切 / 累积接近 target 切）
    if even_split:
        video_end = segments[-1]["end"]
        clips = generate_clips_even_split(video_end, target_duration, segments=merged)
        logger.info(f"生成 {len(clips)} 个切片（even_split 均匀切分）")
    else:
        # 短视频场景不再走"按时间等分"——尊重语义边界：
        # - 单段超长 → 硬切
        # - 段间静默 > target/2 → 强制切
        # - 累积接近 target → 切
        # 短段（< target）也保持原长，不补齐
        clips = generate_clips(merged, target_duration=target_duration)
        logger.info(f"生成 {len(clips)} 个切片（按语义边界）")

    # avoid_silence：丢掉静默占比 > 50% 的切片（视频很长的内部静默或单人独白空段）
    if avoid_silence and clips:
        before = len(clips)
        clips = filter_silent_clips(clips, segments, silence_threshold=0.5)
        if len(clips) != before:
            logger.info(f"avoid_silence：{before} → {len(clips)} 个切片（丢弃静默段）")

    # 前置 1s + 退出 1s 缓冲（避免相邻重叠）
    video_end = segments[-1]["end"] if segments else None
    clips = _apply_buffers(clips, pre_roll=1.0, post_roll=1.0, video_end=video_end)

    # 根据策略限制最大切片数
    if len(clips) > max_clips:
        logger.info(f"根据策略限制切片数：{len(clips)} → {max_clips}")
        clips = clips[:max_clips]

    # 生成简单标题（传 all_segments 让标题取自覆盖该 clip 最长的段 + strategy_config 用于本地评分）
    titled_clips = generate_simple_titles(clips, all_segments=segments, strategy_config=strategy_config)
    
    # 按时间分组为合集（根据策略的目标时长计算每组大小）
    # 假设每个切片约 15 秒，目标时长 60 秒 → 每组 4 个切片
    clips_per_collection = max(3, min(8, int(target_duration) // 15))
    collections = group_into_collections(titled_clips, group_size=clips_per_collection)
    logger.info(f"分组为 {len(collections)} 个合集 (每组约{clips_per_collection}个切片)")
    
    # 生成大纲（简单版）
    outlines = [
        {
            "title": f"合集 {i+1}: {c['title']}",
            "subtopics": [clip["title"] for clip in c["clips"]]
        }
        for i, c in enumerate(collections)
    ]
    
    # 保存结果
    result = {
        "outlines": outlines,
        "clips": titled_clips,
        "collections": collections,
    }
    
    outline_path = metadata_dir / "step1_outline.json"
    with open(outline_path, "w", encoding="utf-8") as f:
        json.dump(outlines, f, ensure_ascii=False, indent=2)
    
    clips_path = metadata_dir / "step2_clips.json"
    with open(clips_path, "w", encoding="utf-8") as f:
        json.dump(titled_clips, f, ensure_ascii=False, indent=2)
    
    collections_path = metadata_dir / "step3_collections.json"
    with open(collections_path, "w", encoding="utf-8") as f:
        json.dump(collections, f, ensure_ascii=False, indent=2)
    
    logger.info(f"本地处理完成：{len(titled_clips)} 切片，{len(collections)} 合集")
    
    return result


def parse_srt(srt_path: Path) -> List[Dict]:
    """解析 SRT 文件"""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    segments = []
    blocks = re.split(r'\n\n+', content.strip())
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        
        try:
            # 序号
            index = int(lines[0])
            
            # 时间轴
            time_match = re.match(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})', lines[1])
            if not time_match:
                continue
            
            h1, m1, s1, ms1, h2, m2, s2, ms2 = time_match.groups()
            start = int(h1)*3600 + int(m1)*60 + int(s1) + int(ms1)/1000
            end = int(h2)*3600 + int(m2)*60 + int(s2) + int(ms2)/1000
            
            # 文本
            text = '\n'.join(lines[2:]).strip()
            
            segments.append({
                "index": index,
                "start": start,
                "end": end,
                "duration": end - start,
                "text": text,
            })
        except (ValueError, IndexError) as e:
            logger.debug(f"解析失败：{e}")
            continue
    
    return segments


def merge_short_segments(segments: List[Dict], min_duration: float = 3.0) -> List[Dict]:
    """合并短段落"""
    if not segments:
        return []
    
    merged = [segments[0].copy()]
    
    for seg in segments[1:]:
        last = merged[-1]
        if last["duration"] < min_duration:
            # 合并到上一个
            last["end"] = seg["end"]
            last["duration"] = last["end"] - last["start"]
            last["text"] += " " + seg["text"]
        else:
            merged.append(seg.copy())
    
    return merged


def generate_clips(segments: List[Dict], target_duration: float = 45.0) -> List[Dict]:
    """按语义边界分组生成切片（不再按时间等分）

    规则（按优先级）：
    1. 单段超长（> target）→ 硬切
    2. 段间静默（gap）> target / 2 → 强制切（语义断点，尊重原始结构）
    3. 累积接近 target → 切
    4. 否则累积

    短视频也会尊重原始 SRT 段落结构（不补齐、不等分），所以
    9.9s 的段就是 9.9s，6.4s 的段就是 6.4s。
    """
    if not segments:
        return []

    silence_gap_threshold = target_duration / 2.0

    # 单段就超长 → 直接硬切（不进循环）
    if len(segments) == 1 and (segments[0]["end"] - segments[0]["start"]) > target_duration:
        return [
            {
                "start": p["start"],
                "end": p["end"],
                "duration": p["end"] - p["start"],
                "index": i + 1,
                "segments": [p],
            }
            for i, p in enumerate(_split_long_segment(segments[0], target_duration))
        ]

    clips = []
    current = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "segments": [segments[0]],
    }

    for seg in segments[1:]:
        seg_dur = seg["end"] - seg["start"]
        cur_dur = current["end"] - current["start"]
        gap = seg["start"] - current["end"]
        combined_dur = seg["end"] - current["start"]

        # 1. 单段超长 → 硬切
        if seg_dur > target_duration:
            if current["segments"]:
                clips.append(current)
            for part in _split_long_segment(seg, target_duration):
                clips.append({
                    "start": part["start"],
                    "end": part["end"],
                    "segments": [part],
                })
            current = {"start": seg["start"], "end": seg["end"], "segments": []}
            continue

        # 2. 段间静默太大 → 强制切（语义断点）
        if gap > silence_gap_threshold and current["segments"]:
            clips.append(current)
            current = {"start": seg["start"], "end": seg["end"], "segments": [seg]}
            continue

        # 3. 累积超 target → 切
        if combined_dur > target_duration and current["segments"]:
            clips.append(current)
            current = {"start": seg["start"], "end": seg["end"], "segments": [seg]}
            continue

        # 4. 累积
        current["end"] = seg["end"]
        current["segments"].append(seg)

    if current["segments"]:
        clips.append(current)

    for i, c in enumerate(clips):
        c["index"] = i + 1
        c["duration"] = c["end"] - c["start"]

    return clips


def _split_long_segment(seg: Dict, target_duration: float) -> List[Dict]:
    """把一个超长字幕段硬切成多个 ≤ target_duration 的段（保留 text）"""
    duration = seg["end"] - seg["start"]
    if duration <= target_duration:
        return [seg]
    n = max(2, int(round(duration / target_duration)))
    piece = duration / n
    parts = []
    for i in range(n):
        parts.append({
            "start": seg["start"] + i * piece,
            "end": seg["start"] + (i + 1) * piece if i < n - 1 else seg["end"],
            "text": seg.get("text", ""),
        })
    return parts


def _apply_buffers(clips: List[Dict], pre_roll: float = 1.0, post_roll: float = 1.0, video_end: float = None) -> List[Dict]:
    """给每个 clip 加前置 1s + 退出 1s 缓冲

    避免与上一个 clip 重叠（clip[i].start = max(clip[i].start - pre, clip[i-1].end)）
    视频边界保护：start >= 0，end <= video_end
    """
    if not clips:
        return clips

    for i, c in enumerate(clips):
        new_start = c["start"] - pre_roll
        new_end = c["end"] + post_roll

        # 视频边界保护
        new_start = max(0.0, new_start)
        if video_end is not None:
            new_end = min(new_end, video_end)

        # 避免与上一个 clip 重叠
        if i > 0:
            new_start = max(new_start, clips[i - 1]["end"])

        c["start"] = new_start
        c["end"] = new_end
        c["duration"] = new_end - new_start

    return clips


def generate_clips_even_split(video_end: float, target_duration: float, segments: List[Dict] = None) -> List[Dict]:
    """even_split 路径：按 target_duration 均匀切视频（教学/课程类内容）"""
    if video_end <= 0 or target_duration <= 0:
        return []

    n = max(1, int(round(video_end / target_duration)))
    piece = video_end / n
    clips = []
    for i in range(n):
        s = i * piece
        e = (i + 1) * piece if i < n - 1 else video_end
        overlaps = [
            (max(0.0, min(e, seg["end"]) - max(s, seg["start"])), seg)
            for seg in (segments or [])
        ]
        overlaps = [(ov, seg) for ov, seg in overlaps if ov > 0]
        overlaps.sort(key=lambda x: -x[0])
        seg = overlaps[0][1] if overlaps else None
        text = seg.get("text", "") if seg else ""
        clips.append({
            "start": s,
            "end": e,
            "duration": e - s,
            "index": i + 1,
            "segments": [seg] if seg else [],
            "_title_text": text,
        })
    return clips


def filter_silent_clips(clips: List[Dict], segments: List[Dict], silence_threshold: float = 0.5) -> List[Dict]:
    """avoid_silence 路径：丢弃静默占比超过阈值的切片

    静默判定：切片时段内没有字幕段覆盖的时长 / 切片总时长 > silence_threshold
    """
    if not clips or not segments:
        return clips

    out = []
    for c in clips:
        covered = 0.0
        for seg in segments:
            ov = max(0.0, min(c["end"], seg["end"]) - max(c["start"], seg["start"]))
            covered += ov
        if c["duration"] <= 0:
            continue
        silence_ratio = 1.0 - min(1.0, covered / c["duration"])
        if silence_ratio <= silence_threshold:
            out.append(c)
        else:
            logger.info(f"avoid_silence 丢弃: [{c['start']:.1f}, {c['end']:.1f}] 静默占比 {silence_ratio:.0%}")
    return out


def _pick_representative_text(clip: Dict, all_segments: List[Dict]) -> str:
    """挑一个能代表该 clip 内容的字幕段（覆盖时长最长的段）

    之前用 segments[0]：可能首段很短或不典型 → 标题错
    现在从全量 SRT 里挑覆盖 [start, end] 时间最长的段 → 标题来自该 clip 中心
    """
    if not all_segments:
        return ""
    best_text = ""
    best_overlap = 0.0
    for seg in all_segments:
        overlap = max(0.0, min(clip["end"], seg["end"]) - max(clip["start"], seg["start"]))
        if overlap > best_overlap:
            best_overlap = overlap
            best_text = seg.get("text", "")
    return best_text


def _clip_subtitle_text(clip: Dict, all_segments: List[Dict]) -> str:
    """收集该 clip 时间范围内所有字幕段的全文（用于评分）"""
    parts = []
    for seg in (all_segments or []):
        if seg["end"] > clip["start"] and seg["start"] < clip["end"]:
            parts.append(seg.get("text", ""))
    return " ".join(parts)


def _parse_keywords(text: str) -> List[str]:
    """把 '保留规则' / '删除规则' 文本解析成关键词列表（按行 / 标点）"""
    if not text:
        return []
    keywords = []
    for line in text.replace("，", ",").replace("、", ",").replace("；", ",").split("\n"):
        for part in line.split(","):
            part = part.strip()
            if part and len(part) >= 2:
                keywords.append(part)
    return keywords


def _score_clip_local(clip: Dict, all_segments: List[Dict], strategy_config: Dict) -> float:
    """本地兜底方案的真评分（基于字幕密度 + 时长匹配 + 关键词命中）

    比 AI 路径粗糙，但比"全给 50"有用得多

    评分维度（0-1）：
    - 基础分 0.55
    - 字幕字数合适（60-300 字）→ +0.10
    - 字幕稀疏（<30 字）或密集（>400 字）→ -0.15
    - 时长接近 target_duration（±50%）→ +0.10
    - 时长过短（<5s）或过长（>120s）→ -0.10
    - 命中 keep_rules 关键词（任一）→ +0.15
    - 命中 priority_keywords（任一）→ +0.10
    - 命中 content_types（任一）→ +0.05
    """
    config = strategy_config or {}
    rules = config.get("rules") or {}
    target_duration = config.get("target_duration", 45.0) or 45.0
    keep_kw = _parse_keywords(config.get("keep_rules", ""))
    remove_kw = _parse_keywords(config.get("remove_rules", ""))
    priority_kw = rules.get("priority_keywords") or []
    content_types = config.get("content_types") or []

    text = _clip_subtitle_text(clip, all_segments)
    title = _pick_representative_text(clip, all_segments) if all_segments else ""
    # 合并标题+正文一起算关键词命中（标题通常是核心）
    haystack = f"{title} {text}".lower()

    score = 0.55
    reasons = []

    # 1. 删除规则：命中直接 0（不进 list）
    if remove_kw and any(kw in haystack for kw in remove_kw):
        return -1.0  # 标记丢弃

    # 2. 字幕密度（按字数估算，1 字 ≈ 1 token）
    char_count = len(re.sub(r'\s', '', text))
    if 60 <= char_count <= 300:
        score += 0.10
        reasons.append(f"字数{char_count}")
    elif char_count < 30:
        score -= 0.15
        reasons.append(f"字数{char_count}过少")
    elif char_count > 400:
        score -= 0.15
        reasons.append(f"字数{char_count}过多")

    # 3. 时长匹配 target_duration
    duration = clip.get("duration", 0) or 0
    if duration <= 0:
        score -= 0.10
    elif 5 <= duration <= 120 and 0.5 * target_duration <= duration <= 1.5 * target_duration:
        score += 0.10
        reasons.append(f"时长{duration:.0f}s匹配")
    elif duration < 5:
        score -= 0.10
        reasons.append(f"时长{duration:.1f}s过短")
    elif duration > 120:
        score -= 0.10
        reasons.append(f"时长{duration:.0f}s过长")

    # 4. keep_rules 命中
    if keep_kw:
        matched = [kw for kw in keep_kw if kw.lower() in haystack]
        if matched:
            score += 0.15
            reasons.append(f"保留规则×{len(matched)}")

    # 5. priority_keywords 命中
    if priority_kw and any(kw.lower() in haystack for kw in priority_kw):
        score += 0.10
        reasons.append("优先关键词")

    # 6. content_types 命中
    if content_types and any(ct.lower() in haystack for ct in content_types):
        score += 0.05
        reasons.append("内容分类")

    # 限制在 0-1
    return max(0.0, min(1.0, score))


def generate_simple_titles(clips: List[Dict], all_segments: List[Dict] = None,
                            strategy_config: Dict = None) -> List[Dict]:
    """生成简单标题（从该 clip 时间范围覆盖最长的字幕段提取）+ 本地评分

    Args:
        clips: 切片列表
        all_segments: 全量 SRT 段落
        strategy_config: 策略配置（用于本地评分：keep_rules / remove_rules / target_duration 等）
    """
    config = strategy_config or {}
    min_score = _normalize_min_score((config.get("rules") or {}).get("min_score", 0.6))  # 本地默认 0.6（比 AI 路径 0.7 略低，扣分项多）

    titled = []

    for clip in clips:
        # 1. 短片兜底走的时间等分（已经设了 _title_text）
        if clip.get("_title_text"):
            text = clip["_title_text"]
        # 2. 优先用全量 SRT 挑代表段（更准：覆盖最长的段 = 中心内容）
        elif all_segments:
            text = _pick_representative_text(clip, all_segments)
        # 3. 兜底：用 clip 自带 segments[0]
        elif clip.get("segments"):
            text = clip["segments"][0].get("text", "")
        else:
            text = ""

        # 清理标点
        text_clean = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
        title = text_clean[:30] + "..." if len(text_clean) > 30 else text_clean

        # 本地评分
        score = _score_clip_local(clip, all_segments, config)
        if score < 0:
            # 删除规则命中 → 跳过这个 clip
            continue
        if score < min_score:
            # 低于阈值 → 也跳过（不写库）
            continue

        titled.append({
            "index": clip["index"],
            "start": clip["start"],
            "end": clip["end"],
            "duration": clip["duration"],
            "title": f"片段 {clip['index']}: {title}" if title else f"片段 {clip['index']}",
            "score": round(score, 2),
        })

    return titled


def group_into_collections(clips: List[Dict], group_size: int = 8) -> List[Dict]:
    """分组为合集"""
    if not clips:
        return []
    
    collections = []
    
    for i in range(0, len(clips), group_size):
        group = clips[i:i+group_size]
        collections.append({
            "index": len(collections) + 1,
            "title": f"合集 {len(collections) + 1}",
            "clip_ids": [c["index"] for c in group],
            "clips": group,  # 保留完整信息用于合并
        })
    
    return collections
