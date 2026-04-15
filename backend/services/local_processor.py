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
    
    # 生成切片（根据策略的目标时长）
    clips = generate_clips(merged, target_duration=target_duration)
    logger.info(f"生成 {len(clips)} 个切片")
    
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
    """生成切片（按目标时长分组）"""
    if not segments:
        return []
    
    clips = []
    current_clip = {
        "start": segments[0]["start"],
        "end": segments[0]["end"],
        "segments": [segments[0]],
    }
    
    for seg in segments[1:]:
        clip_duration = current_clip["end"] - current_clip["start"]
        
        if clip_duration < target_duration:
            # 继续添加
            current_clip["end"] = seg["end"]
            current_clip["segments"].append(seg)
        else:
            # 保存当前，开始新的
            clips.append(current_clip)
            current_clip = {
                "start": seg["start"],
                "end": seg["end"],
                "segments": [seg],
            }
    
    # 最后一个
    if current_clip["segments"]:
        clips.append(current_clip)
    
    # 添加索引和时长
    for i, clip in enumerate(clips):
        clip["index"] = i + 1
        clip["duration"] = clip["end"] - clip["start"]
    
    return clips


def generate_simple_titles(clips: List[Dict]) -> List[Dict]:
    """生成简单标题（从内容提取关键词）"""
    titled = []
    
    for clip in clips:
        # 提取第一段的前 20 个字作为标题
        text = clip["segments"][0]["text"] if clip["segments"] else ""
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
