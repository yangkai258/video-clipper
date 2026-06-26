"""LLM 服务 - 大纲提取、时间线创建等"""
import json
import logging
import re
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def extract_outline(srt_path: Path, metadata_dir: Path, strategy_config: dict = None) -> List[Dict]:
    """从字幕提取大纲

    Args:
        srt_path: 字幕文件路径
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选），包含 style_positioning / keep_rules / remove_rules / content_guidelines
    """
    from ..core.config import settings
    import dashscope

    dashscope.api_key = settings.DASHSCOPE_API_KEY

    strategy_config = strategy_config or {}

    # 读取字幕
    logger.info("读取字幕文件...")
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    # 提取纯文本
    text = _extract_text_from_srt(srt_content)

    # 分块处理（每块约 30 分钟）
    chunks = _chunk_text(text, max_chars=5000)
    logger.info(f"文本分为 {len(chunks)} 块")

    # 构建风格引导 prompt 片段
    style_block = _build_style_prompt_block(strategy_config)
    if style_block:
        logger.info(f"使用风格化 prompt：style_positioning='{strategy_config.get('style_positioning', '')[:30]}'")
    else:
        logger.info("使用默认 prompt（未配置风格）")

    all_outlines = []

    for i, chunk in enumerate(chunks):
        logger.info(f"处理第 {i+1}/{len(chunks)} 块")

        prompt = f"""你是一位专业的视频内容分析师。请从以下视频字幕文本中提取主要话题大纲。
{style_block}
要求：
1. 提取 2-5 个核心话题
2. 每个话题包含标题和 2-4 个子话题
3. 严格遵守上述【风格定位】【保留规则】【删除规则】【内容指南】
4. 按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

[
  {{
    "title": "话题标题",
    "subtopics": ["子话题 1", "子话题 2"]
  }}
]

字幕文本：
{chunk[:4000]}
"""

        try:
            response = dashscope.Generation.call(
                model=settings.MODEL_NAME,
                messages=[{"role": "user", "content": prompt}]
            )

            if response.status_code == 200:
                content = response.output.text
                outlines = _parse_outline_response(content)
                all_outlines.extend(outlines)
                logger.info(f"第 {i+1} 块提取到 {len(outlines)} 个话题")
            else:
                logger.warning(f"LLM 调用失败：{response.code}")

        except Exception as e:
            logger.error(f"处理第 {i+1} 块失败：{e}")
    
    # 保存大纲
    outline_path = metadata_dir / "step1_outline.json"
    with open(outline_path, "w", encoding="utf-8") as f:
        json.dump(all_outlines, f, ensure_ascii=False, indent=2)
    
    logger.info(f"大纲提取完成，共 {len(all_outlines)} 个话题")
    return all_outlines


def _build_style_prompt_block(strategy_config: dict) -> str:
    """根据 strategy_config 构建风格引导 prompt 片段

    Args:
        strategy_config: 包含 style_positioning / keep_rules / remove_rules / content_guidelines

    Returns:
        拼接好的多行字符串（带前缀标签），若无任何配置则返回空字符串
    """
    if not strategy_config:
        return ""

    blocks = []

    style_positioning = strategy_config.get("style_positioning", "").strip()
    if style_positioning:
        blocks.append(f"【风格定位】{style_positioning}\n（内容应匹配此调性——这是账号/人设的差异化标签）")

    content_guidelines = strategy_config.get("content_guidelines", "").strip()
    if content_guidelines:
        blocks.append(f"【内容指南】{content_guidelines}\n（只关注这些类型的内容）")

    keep_rules = strategy_config.get("keep_rules", "").strip()
    if keep_rules:
        blocks.append(f"【保留规则】{keep_rules}\n（符合这些特征的话题优先保留，权重最高）")

    remove_rules = strategy_config.get("remove_rules", "").strip()
    if remove_rules:
        blocks.append(f"【删除规则】{remove_rules}\n（这些内容直接忽略，不要列入大纲）")

    if not blocks:
        return ""

    # 前置空行，让 prompt 在主 prompt 里更清晰
    return "\n" + "\n\n".join(blocks) + "\n"


def _parse_rules_to_keywords(rules_text: str) -> List[str]:
    """把 keep_rules / remove_rules 文本解析成关键词列表

    支持分隔符：、, ， ; ； 换行
    过滤空字符串和过短词（< 2 字符）
    """
    if not rules_text:
        return []

    import re
    # 用多种分隔符拆分
    parts = re.split(r'[、,，;；\n]+', rules_text)
    keywords = [p.strip() for p in parts if p.strip() and len(p.strip()) >= 2]
    return keywords


def _extract_text_from_srt(srt_content: str) -> str:
    """从 SRT 提取纯文本"""
    lines = srt_content.strip().split("\n")
    texts = []
    
    for line in lines:
        if "-->" not in line and not line.isdigit() and line.strip():
            texts.append(line.strip())
    
    return " ".join(texts)


def _chunk_text(text: str, max_chars: int = 5000) -> List[str]:
    """分块文本"""
    chunks = []
    current_chunk = ""
    
    for word in text.split():
        if len(current_chunk) + len(word) + 1 > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = word + " "
        else:
            current_chunk += word + " "
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks


def _parse_outline_response(response: str) -> List[Dict]:
    """解析 LLM 响应"""
    try:
        # 尝试直接解析 JSON
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            json_str = match.group()
            return json.loads(json_str)
    except:
        pass
    
    # 尝试解析 Markdown 格式
    outlines = []
    lines = response.split("\n")
    current_outline = None
    
    for line in lines:
        line = line.strip()
        if re.match(r'^\d+\.\s*\*\*', line):
            if current_outline:
                outlines.append(current_outline)
            topic_name = line.split('**')[1] if '**' in line else line.split('.', 1)[1].strip()
            current_outline = {"title": topic_name, "subtopics": []}
        elif line.startswith('-') and current_outline:
            subtopic = line[1:].strip()
            if subtopic:
                current_outline["subtopics"].append(subtopic)
    
    if current_outline:
        outlines.append(current_outline)
    
    return outlines


def create_timeline(outlines: List[Dict], srt_path: Path, metadata_dir: Path) -> List[Dict]:
    """创建时间线"""
    # TODO: 实现时间线创建
    logger.info("时间线创建（简化版）")
    
    timeline = []
    for i, outline in enumerate(outlines[:10]):  # 限制数量
        timeline.append({
            "title": outline["title"],
            "start_time": i * 300,  # 假设每个话题 5 分钟
            "end_time": (i + 1) * 300,
            "subtopics": outline.get("subtopics", [])
        })
    
    timeline_path = metadata_dir / "step2_timeline.json"
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    
    return timeline


def score_clips(timeline: List[Dict], metadata_dir: Path, strategy_config: dict = None) -> List[Dict]:
    """切片评分

    Args:
        timeline: 时间线数据
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选），包含 keep_rules / remove_rules / rules.min_score / rules.priority_keywords
    """
    strategy_config = strategy_config or {}
    min_score = strategy_config.get("rules", {}).get("min_score", 0.7)

    # 解析 keep_rules / remove_rules 关键词
    keep_keywords = _parse_rules_to_keywords(strategy_config.get("keep_rules", ""))
    remove_keywords = _parse_rules_to_keywords(strategy_config.get("remove_rules", ""))
    priority_keywords = strategy_config.get("rules", {}).get("priority_keywords", [])

    logger.info(f"切片评分 - 阈值:{min_score}, 保留关键词:{len(keep_keywords)}, 删除关键词:{len(remove_keywords)}, 优先关键词:{len(priority_keywords)}")

    scored = []
    dropped_by_remove = 0

    for item in timeline:
        title = item.get("title", "")
        title_lower = title.lower()

        # 1) 删除规则优先：命中任何一个 remove_keyword 直接丢弃
        if remove_keywords and any(kw in title for kw in remove_keywords):
            dropped_by_remove += 1
            continue

        # 2) 基础分
        base_score = 0.8
        reasons = []

        # 3) 保留关键词命中：加分
        if keep_keywords:
            matched = [kw for kw in keep_keywords if kw in title]
            if matched:
                base_score = min(base_score + 0.15, 1.0)
                reasons.append(f"保留规则命中:{','.join(matched[:3])}")

        # 4) 优先关键词命中：加分
        if priority_keywords and any(kw.lower() in title_lower for kw in priority_keywords):
            base_score = min(base_score + 0.15, 1.0)
            reasons.append("优先关键词命中")

        # 5) 只保留高于阈值的切片
        if base_score >= min_score:
            reason_str = " + ".join(reasons) if reasons else "基础分通过"
            scored.append({
                **item,
                "score": base_score,
                "score_reason": f"{reason_str} (阈值:{min_score})"
            })

    scored_path = metadata_dir / "step3_scored.json"
    with open(scored_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)

    logger.info(f"评分完成：{len(scored)} 个通过 / {dropped_by_remove} 个被删除规则过滤")
    return scored


def generate_titles(scored_clips: List[Dict], metadata_dir: Path) -> List[Dict]:
    """生成标题"""
    logger.info("生成标题（简化版）")
    
    titled = []
    for i, clip in enumerate(scored_clips):
        titled.append({
            **clip,
            "title": f"切片{i+1}: {clip['title']}"
        })
    
    titled_path = metadata_dir / "step4_titled.json"
    with open(titled_path, "w", encoding="utf-8") as f:
        json.dump(titled, f, ensure_ascii=False, indent=2)
    
    return titled


def cluster_collections(titled_clips: List[Dict], metadata_dir: Path, strategy_config: dict = None) -> List[Dict]:
    """主题聚类
    
    Args:
        titled_clips: 带标题的切片数据
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选）
    """
    strategy_config = strategy_config or {}
    max_clips = strategy_config.get("max_clips", 20)
    
    logger.info(f"主题聚类（简化版）- 最大切片数：{max_clips}")
    
    # 根据策略的最大切片数限制
    limited_clips = titled_clips[:max_clips]
    if len(limited_clips) < len(titled_clips):
        logger.info(f"根据策略限制切片数：{len(titled_clips)} → {len(limited_clips)}")
    
    # 计算每组合集的大小（根据目标时长估算）
    target_duration = strategy_config.get("target_duration", 60)
    clips_per_collection = max(3, min(8, target_duration // 15))  # 假设每个切片约 15 秒
    
    collections = []
    for i in range(0, len(limited_clips), clips_per_collection):
        group = limited_clips[i:i+clips_per_collection]
        if group:
            collections.append({
                "title": f"合集{len(collections)+1}",
                "clip_ids": [c.get("title", f"clip_{j}") for j, c in enumerate(group)],
                "clips": group
            })
    
    collections_path = metadata_dir / "step5_collections.json"
    with open(collections_path, "w", encoding="utf-8") as f:
        json.dump(collections, f, ensure_ascii=False, indent=2)
    
    logger.info(f"聚类完成：{len(collections)} 个合集")
    return collections
