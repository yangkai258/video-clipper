"""本地视频处理 - 不依赖外部 API 的备用方案"""
import json
import logging
import re
from pathlib import Path
from typing import List, Dict

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
    
    logger.info(f"本地处理 - 目标时长：{target_duration}s, 最大切片数：{max_clips}")
    
    # 解析字幕
    segments = parse_srt(srt_path)
    logger.info(f"解析到 {len(segments)} 个字幕段落")
    
    if not segments:
        return {"outlines": [], "clips": [], "collections": []}
    
    # 合并短段落（<3 秒）
    merged = merge_short_segments(segments, min_duration=3.0)
    logger.info(f"合并后 {len(merged)} 个段落")

    # 短视频场景不再走"按时间等分"——尊重语义边界：
    # - 单段超长 → 硬切
    # - 段间静默 > target/2 → 强制切
    # - 累积接近 target → 切
    # 短段（< target）也保持原长，不补齐
    clips = generate_clips(merged, target_duration=target_duration)
    logger.info(f"生成 {len(clips)} 个切片（按语义边界）")

    # 前置 1s + 退出 1s 缓冲（避免相邻重叠）
    video_end = segments[-1]["end"] if segments else None
    clips = _apply_buffers(clips, pre_roll=1.0, post_roll=1.0, video_end=video_end)
    
    # 根据策略限制最大切片数
    if len(clips) > max_clips:
        logger.info(f"根据策略限制切片数：{len(clips)} → {max_clips}")
        clips = clips[:max_clips]
    
    # 生成简单标题
    titled_clips = generate_simple_titles(clips)
    
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


def generate_simple_titles(clips: List[Dict]) -> List[Dict]:
    """生成简单标题（从内容提取关键词）"""
    titled = []

    for clip in clips:
        # 优先用 _title_text（短片兜底走的时间等分）；否则从 segments 取
        if clip.get("_title_text"):
            text = clip["_title_text"]
        elif clip.get("segments"):
            text = clip["segments"][0].get("text", "")
        else:
            text = ""
        # 清理标点
        text = re.sub(r'[^\w\s\u4e00-\u9fff]', '', text)
        title = text[:30] + "..." if len(text) > 30 else text

        titled.append({
            "index": clip["index"],
            "start": clip["start"],
            "end": clip["end"],
            "duration": clip["duration"],
            "title": f"片段 {clip['index']}: {title}" if title else f"片段 {clip['index']}",
            "score": 50,  # 默认分数
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
