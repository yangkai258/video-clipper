"""LLM 服务 - 大纲提取、时间线创建等"""

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def _normalize_min_score(value) -> float:
    """把 min_score 归一化成 0-1 比例 (v2.1.25 fix 数据契约)

    历史/不同来源可能给不同单位:
    - 0.55 / 0.6 / 0.8 → 直接返回 (0-1 比例)
    - 55 / 60 / 80 → 除以 100 (旧 migrations 或误写成 0-100 整数)
    - None / 0 → 用默认 0.6
    - 其他越界值 → clamp 到 [0, 1]
    """
    if value is None:
        return 0.6
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.6
    # 自动识别单位: > 1 视为 0-100 整数
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def _call_llm(prompt: str, model: str | None = None) -> str | None:
    """调用 MiniMax LLM（OpenAI 兼容接口），返回生成的文本内容

    Args:
        prompt: 完整 prompt
        model: 模型名（默认用 settings.MINIMAX_MODEL）

    Returns:
        LLM 返回的文本内容；失败返回 None
    """
    import httpx

    from ..core.config import settings

    api_key = settings.MINIMAX_API_KEY
    if not api_key:
        logger.error("MINIMAX_API_KEY 未配置")
        return None

    base_url = settings.MINIMAX_BASE_URL.rstrip("/")
    model = model or settings.MINIMAX_MODEL

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        # v2.1.50: 加 max_tokens 避免输出截断
        # 之前没设 → MiniMax API 默认 4096 → LLM 想输出 30+ segment JSON 时被截
        # step3 阿甘 1GB 给 40 个 outline → step2 映射时只输出 1 个 segment 就截断了
        "max_tokens": 8000,
    }

    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error(
                    f"MiniMax API 调用失败：{resp.status_code} {resp.text[:200]}"
                )
                return None
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"MiniMax API 调用异常：{e}")
        return None


def extract_outline(
    srt_path: Path,
    metadata_dir: Path,
    strategy_config: dict = None,
    srt_text: str = None,
) -> list[dict]:
    """从字幕提取大纲

    Args:
        srt_path: 字幕文件路径（与 srt_text 二选一）
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选），包含 style_positioning / keep_rules / remove_rules / content_guidelines
        srt_text: SRT 文本字符串（可选，用于 in-memory 模式，不落盘）
    """
    strategy_config = strategy_config or {}

    # 读取字幕（优先用 srt_text，否则从 srt_path 读）
    if srt_text is None:
        if srt_path is None or not Path(srt_path).exists():
            logger.error("extract_outline 需要 srt_path 或 srt_text")
            return []
        logger.info("读取字幕文件...")
        with open(srt_path, "r", encoding="utf-8") as f:
            srt_content = f.read()
    else:
        srt_content = srt_text
        logger.info("使用内存中的字幕文本（不落盘模式）")

    # 提取纯文本
    text = _extract_text_from_srt(srt_content)

    # 分块处理（每块 ~6000 字符，约 4-5 分钟字幕）
    # v2.1.47: 改大 chunk + 删 prompt 内的 chunk[:4000] 截断
    # 之前 max_chars=5000 + chunk[:4000] 实际只给 LLM 看前 4000 字符 (约 10 分钟)
    # 1GB 阿甘正传 1699 段字幕 → LLM 只看前 10 分钟 → 只识别 1-2 个 topic
    # 现在 max_chars=6000 + 完整传 chunk → LLM 看完整 chunk 约 5 分钟 × 30+ chunks
    chunks = _chunk_text(text, max_chars=6000)
    logger.info(f"文本分为 {len(chunks)} 块")

    # 构建风格引导 prompt 片段
    style_block = _build_style_prompt_block(strategy_config)
    if style_block:
        logger.info(
            f"使用风格化 prompt：style_positioning='{strategy_config.get('style_positioning', '')[:30]}'"
        )
    else:
        logger.info("使用默认 prompt（未配置风格）")

    all_outlines = []

    for i, chunk in enumerate(chunks):
        logger.info(f"处理第 {i + 1}/{len(chunks)} 块")

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
{chunk}
"""

        try:
            content = _call_llm(prompt)
            if content:
                outlines = _parse_outline_response(content)
                all_outlines.extend(outlines)
                logger.info(f"第 {i + 1} 块提取到 {len(outlines)} 个话题")
            else:
                logger.warning(f"第 {i + 1} 块 LLM 调用失败")

        except Exception as e:
            logger.error(f"处理第 {i + 1} 块失败：{e}")

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
        blocks.append(
            f"【风格定位】{style_positioning}\n（内容应匹配此调性——这是账号/人设的差异化标签）"
        )

    content_types = strategy_config.get("content_types") or []
    if content_types:
        types_str = "、".join(content_types)
        blocks.append(
            f"【内容分类】{types_str}\n（只挑选这些分类下的内容，其他分类的话题不列入大纲）"
        )

    content_guidelines = strategy_config.get("content_guidelines", "").strip()
    if content_guidelines:
        blocks.append(f"【内容指南】{content_guidelines}\n（只关注这些类型的内容）")

    keep_rules = strategy_config.get("keep_rules", "").strip()
    if keep_rules:
        blocks.append(
            f"【保留规则】{keep_rules}\n（符合这些特征的话题优先保留，权重最高）"
        )

    remove_rules = strategy_config.get("remove_rules", "").strip()
    if remove_rules:
        blocks.append(f"【删除规则】{remove_rules}\n（这些内容直接忽略，不要列入大纲）")

    if not blocks:
        return ""

    # 前置空行，让 prompt 在主 prompt 里更清晰
    return "\n" + "\n\n".join(blocks) + "\n"


def _parse_rules_to_keywords(rules_text: str) -> list[str]:
    """把 keep_rules / remove_rules 文本解析成关键词列表

    支持分隔符：、, ， ; ； 换行
    过滤空字符串和过短词（< 2 字符）
    """
    if not rules_text:
        return []

    import re

    # 用多种分隔符拆分
    parts = re.split(r"[、,，;；\n]+", rules_text)
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


def _chunk_text(text: str, max_chars: int = 5000) -> list[str]:
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


def _parse_outline_response(response: str) -> list[dict]:
    """解析 LLM 响应"""
    try:
        # 尝试直接解析 JSON
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            json_str = match.group()
            return json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.debug(f"outline JSON 解析失败，回退到 Markdown：{e}")

    # 尝试解析 Markdown 格式
    outlines = []
    lines = response.split("\n")
    current_outline = None

    for line in lines:
        line = line.strip()
        if re.match(r"^\d+\.\s*\*\*", line):
            if current_outline:
                outlines.append(current_outline)
            # 安全提取 topic name（避免 IndexError）
            if "**" in line:
                parts = line.split("**")
                topic_name = parts[1] if len(parts) > 1 else ""
            else:
                topic_name = line.split(".", 1)[1].strip() if "." in line else line
            current_outline = {"title": topic_name, "subtopics": []}
        elif line.startswith("-") and current_outline:
            subtopic = line[1:].strip()
            if subtopic:
                current_outline["subtopics"].append(subtopic)

    if current_outline:
        outlines.append(current_outline)

    return outlines


def create_timeline(
    outlines: list[dict],
    srt_path: Path,
    metadata_dir: Path,
    strategy_config: dict = None,
) -> list[dict]:
    """创建时间线 - 让 LLM 把话题大纲映射到字幕中的具体时间段

    Args:
        outlines: 从 extract_outline 得到的话题列表
        srt_path: SRT 字幕文件路径（含时间戳）
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选）

    Returns:
        带 start_time / end_time 的 timeline 列表
    """
    # 优先尝试 LLM 真正映射；失败则回退到简化版（每话题 5 分钟等分）
    try:
        timeline = _create_timeline_with_llm(outlines, srt_path, strategy_config or {})
        if timeline:
            timeline_path = metadata_dir / "step2_timeline.json"
            with open(timeline_path, "w", encoding="utf-8") as f:
                json.dump(timeline, f, ensure_ascii=False, indent=2)
            logger.info(f"时间线创建（LLM版）完成：{len(timeline)} 个话题")
            return timeline
    except Exception as e:
        logger.warning(f"LLM 时间线创建失败：{e}，回退到简化版")

    # 回退：简化版
    logger.info("时间线创建（简化版）- 每话题 5 分钟等分")
    timeline = []
    for i, outline in enumerate(outlines[:10]):
        timeline.append(
            {
                "title": outline["title"],
                "start_time": float(i * 300),
                "end_time": float((i + 1) * 300),
                "subtopics": outline.get("subtopics", []),
            }
        )

    timeline_path = metadata_dir / "step2_timeline.json"
    with open(timeline_path, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)

    return timeline


def _create_timeline_with_llm(
    outlines: list[dict], srt_path: Path, strategy_config: dict
) -> list[dict]:
    """用 LLM 把话题映射到字幕中的具体时间戳"""
    # 解析 SRT → 时间戳列表（减少传给 LLM 的 token）
    parsed_segments = parse_srt_for_timeline(srt_path)
    if not parsed_segments:
        return []

    # 转成简洁格式：[12.5-67.8] 文本...
    srt_compact = "\n".join(
        f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}"
        for seg in parsed_segments
    )

    # 限制大小（避免超 context）
    # v2.1.49: 25000 → 50000 让 LLM 看更多字幕 (1GB 阿甘 srt 104181 字符, 之前截到 25k LLM 跳过大半)
    MAX_CHARS = 50000
    if len(srt_compact) > MAX_CHARS:
        logger.warning(
            f"SRT 紧凑格式 {len(srt_compact)} 字符超过 {MAX_CHARS}，按比例截取"
        )
        # 等比例采样：每 N 条取一条
        # ponytail: 原公式多乘了 len(parsed_segments) -> 1.5GB SRT (~5000 段 / 150k 字符) 算出 step=7651, 几乎全跳过. 正确 stride = 整串字符 / 目标字符.
        # 已知上限: 采样会丢时间轴连续性, 超大 SRT (>>1GB) 仍可能 LLM 截断 -> 真彻底解是 P2#8 改分块
        step = len(srt_compact) // MAX_CHARS + 1
        sampled = parsed_segments[::step]
        srt_compact = "\n".join(
            f"[{seg['start']:.1f}-{seg['end']:.1f}] {seg['text']}" for seg in sampled
        )
        logger.info(f"采样后 SRT：{len(sampled)} 段，{len(srt_compact)} 字符")

    outlines_json = json.dumps(outlines, ensure_ascii=False, indent=2)

    # 风格引导
    style_block = _build_style_prompt_block(strategy_config)

    prompt = f"""你是一位专业的视频内容编辑。请根据以下视频话题大纲和带时间戳的字幕文本，把每个话题映射到具体的开始/结束时间。
{style_block}
【话题大纲】
{outlines_json}

【字幕文本（时间戳-文本）】
{srt_compact}

要求：
1. 每个话题必须映射到字幕中具体的时间段（精确到秒，浮点数）
2. 时间要贴合话题内容的实际切换点（说话人/主题变化处）
3. 大部分话题都应该在字幕里能找到对应内容, 强制映射 (不要轻易跳过)
   - 找不到完全匹配的, 就用话题大致出现的时间段 (即使主题词没出现, 但讲述背景在)
   - 只有话题跟整段视频内容完全无关时才跳过
4. 同一个时间段不能被多个话题覆盖
5. 严格按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

[
  {{
    "title": "话题标题（必须与大纲一致）",
    "start_time": 12.5,
    "end_time": 67.8,
    "subtopics": ["子话题 1", "子话题 2"]
  }}
]
"""

    content = _call_llm(prompt)
    if content is None:
        return []

    timeline = _parse_timeline_response(content)

    # 验证：每个 item 必须有 title + start_time + end_time
    valid = []
    for item in timeline:
        if not all(k in item for k in ("title", "start_time", "end_time")):
            continue
        try:
            item["start_time"] = float(item["start_time"])
            item["end_time"] = float(item["end_time"])
        except (TypeError, ValueError):
            continue
        if item["end_time"] <= item["start_time"]:
            continue
        valid.append(item)

    return valid


def parse_srt_for_timeline(srt_path: Path) -> list[dict]:
    """解析 SRT 为 [{start, end, text}, ...]，供 timeline 映射用"""
    # 复用 local_processor.parse_srt 但不依赖其 logger 配置
    try:
        from .local_processor import parse_srt

        return parse_srt(srt_path)
    except Exception as e:
        logger.warning(f"解析 SRT 失败：{e}")
        return []


def _parse_timeline_response(response: str) -> list[dict]:
    """解析 LLM 返回的时间线 JSON"""
    try:
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception as e:
        logger.debug(f"解析 timeline JSON 失败：{e}")
    return []


def score_clips(
    timeline: list[dict], metadata_dir: Path, strategy_config: dict = None
) -> list[dict]:
    """切片评分

    Args:
        timeline: 时间线数据
        metadata_dir: 元数据目录
        strategy_config: 策略配置（可选），包含 keep_rules / remove_rules / rules.min_score / rules.priority_keywords
    """
    strategy_config = strategy_config or {}
    # 与 local_processor._score_clip_local 的默认 0.6 保持一致
    min_score = _normalize_min_score(
        strategy_config.get("rules", {}).get("min_score", 0.6)
    )

    # 解析 keep_rules / remove_rules 关键词
    keep_keywords = _parse_rules_to_keywords(strategy_config.get("keep_rules", ""))
    remove_keywords = _parse_rules_to_keywords(strategy_config.get("remove_rules", ""))
    priority_keywords = strategy_config.get("rules", {}).get("priority_keywords", [])
    # 内容分类命中加分（同时匹配分类词 = 这个分类下的话题）
    content_types = strategy_config.get("content_types") or []

    logger.info(
        f"切片评分 - 阈值:{min_score}, 保留关键词:{len(keep_keywords)}, 删除关键词:{len(remove_keywords)}, 优先关键词:{len(priority_keywords)}, 内容分类:{content_types}"
    )

    scored = []
    dropped_by_remove = 0
    dropped_by_type = 0

    for item in timeline:
        title = item.get("title", "")
        title_lower = title.lower()

        # 1) 删除规则优先：命中任何一个 remove_keyword 直接丢弃
        if remove_keywords and any(kw in title for kw in remove_keywords):
            dropped_by_remove += 1
            continue

        # 1.5) 内容分类过滤 (v2.1.24 fix: 原字符串子串匹配有 bug)
        # 原逻辑: title 必须包含 content_type 字符串, 但 LLM 生成的 title 是话题短语
        # 例: outline="商品链接引导" 不含 "直播带货" 字眼 → 被错杀
        # 改为: content_types 命中**加分**而非过滤, 让 score 自然筛选

        # 2) 基础分
        base_score = 0.8
        reasons = []

        # 2.5) 内容分类命中：加分 (v2.1.24 fix: 从过滤改为加分)
        if content_types and any(ct in title for ct in content_types):
            base_score = min(base_score + 0.1, 1.0)
            reasons.append(
                f"内容分类命中:{[ct for ct in content_types if ct in title]}"
            )

        # 3) 保留关键词命中：加分
        if keep_keywords:
            matched = [kw for kw in keep_keywords if kw in title]
            if matched:
                base_score = min(base_score + 0.15, 1.0)
                reasons.append(f"保留规则命中:{','.join(matched[:3])}")

        # 4) 优先关键词命中：加分
        if priority_keywords and any(
            kw.lower() in title_lower for kw in priority_keywords
        ):
            base_score = min(base_score + 0.15, 1.0)
            reasons.append("优先关键词命中")

        # 5) 只保留高于阈值的切片
        if base_score >= min_score:
            reason_str = " + ".join(reasons) if reasons else "基础分通过"
            scored.append(
                {
                    **item,
                    "score": base_score,
                    "score_reason": f"{reason_str} (阈值:{min_score})",
                }
            )
        else:
            # v2.1.24 debug: 记录被淘汰的 title + score + 阈值
            logger.info(
                f"淘汰 title='{title}' score={base_score:.2f} 阈值={min_score:.2f} reasons={reasons}"
            )

    scored_path = metadata_dir / "step3_scored.json"
    with open(scored_path, "w", encoding="utf-8") as f:
        json.dump(scored, f, ensure_ascii=False, indent=2)

    logger.info(
        f"评分完成：{len(scored)} 个通过 / {dropped_by_remove} 个被删除规则过滤 / {dropped_by_type} 个被内容分类过滤"
    )
    return scored


def generate_titles(
    scored_clips: list[dict],
    metadata_dir: Path,
    srt_path: Path = None,
    strategy_config: dict = None,
) -> list[dict]:
    """生成标题 - 优先用 LLM 生成吸引人的标题，失败回退简化版

    Args:
        scored_clips: 已评分的切片列表（来自 score_clips）
        metadata_dir: 元数据目录
        srt_path: SRT 字幕路径（可选，有则用 LLM 生成更有信息量的标题）
        strategy_config: 策略配置（可选），包含 style_positioning / keep_rules / remove_rules
    """
    if not scored_clips:
        return []

    # 优先尝试 LLM 生成（需要 srt_path 提供文本上下文）
    if srt_path and Path(srt_path).exists():
        try:
            titled = _generate_titles_with_llm(
                scored_clips, srt_path, strategy_config or {}
            )
            if titled:
                titled_path = metadata_dir / "step4_titled.json"
                with open(titled_path, "w", encoding="utf-8") as f:
                    json.dump(titled, f, ensure_ascii=False, indent=2)
                logger.info(f"标题生成（LLM版）完成：{len(titled)} 个")
                return titled
        except Exception as e:
            logger.warning(f"LLM 标题生成失败：{e}，回退到简化版")

    # 回退：简化版
    logger.info("标题生成（简化版）")
    titled = []
    for i, clip in enumerate(scored_clips):
        titled.append({**clip, "title": f"切片{i + 1}: {clip.get('title', '')}"})

    titled_path = metadata_dir / "step4_titled.json"
    with open(titled_path, "w", encoding="utf-8") as f:
        json.dump(titled, f, ensure_ascii=False, indent=2)

    return titled


def _generate_titles_with_llm(
    scored_clips: list[dict], srt_path: Path, strategy_config: dict
) -> list[dict]:
    """用 LLM 为每个切片生成吸引人的标题"""
    # 解析 SRT
    segments = parse_srt_for_timeline(srt_path)
    if not segments:
        return []

    # 为每个 clip 找到对应的字幕文本（按时间范围重叠）
    clip_inputs = []
    for i, clip in enumerate(scored_clips):
        start = clip.get("start_time", 0)
        end = clip.get("end_time", 0)

        # 找到时间范围内所有字幕段
        overlap_texts = [
            seg["text"] for seg in segments if seg["end"] > start and seg["start"] < end
        ]
        overlap_text = " ".join(overlap_texts)[:500]  # 限制每个 500 字

        clip_inputs.append(
            {
                "index": i + 1,
                "start": start,
                "end": end,
                "duration": end - start,
                "current_title": clip.get("title", ""),
                "text_preview": overlap_text or "(无字幕)",
            }
        )

    style_block = _build_style_prompt_block(strategy_config)

    prompt = f"""你是一位短视频标题专家。请为以下视频片段生成吸引人的标题。
{style_block}
【片段列表】
{json.dumps(clip_inputs, ensure_ascii=False, indent=2)}

要求：
1. 每个片段生成 1 个最佳标题（选最吸引人的那个）
2. 长度 15-25 字
3. 突出内容亮点、引发好奇、适合短视频传播
4. 严格遵守风格定位和保留/删除规则
5. 严格按以下 JSON 格式输出（只输出 JSON，不要其他内容）：

[
  {{"index": 1, "title": "标题1"}},
  {{"index": 2, "title": "标题2"}}
]
"""

    content = _call_llm(prompt)
    if content is None:
        return []

    titles_map = _parse_titles_response(content)
    if not titles_map:
        return []

    # 合并到 clips
    titled = []
    for i, clip in enumerate(scored_clips):
        idx = i + 1
        new_title = titles_map.get(idx, f"切片{idx}: {clip.get('title', '')}")
        titled.append({**clip, "title": new_title})

    return titled


def _parse_titles_response(response: str) -> dict[int, str]:
    """解析 LLM 返回的标题 JSON 为 {index: title}"""
    try:
        match = re.search(r"\[.*\]", response, re.DOTALL)
        if match:
            items = json.loads(match.group())
            return {
                int(item["index"]): item["title"]
                for item in items
                if "index" in item and "title" in item
            }
    except Exception as e:
        logger.debug(f"解析 titles JSON 失败：{e}")
    return {}


def cluster_collections(
    titled_clips: list[dict], metadata_dir: Path, strategy_config: dict = None
) -> list[dict]:
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
        group = limited_clips[i : i + clips_per_collection]
        if group:
            collections.append(
                {
                    "title": f"合集{len(collections) + 1}",
                    "clip_ids": [
                        c.get("title", f"clip_{j}") for j, c in enumerate(group)
                    ],
                    "clips": group,
                }
            )

    collections_path = metadata_dir / "step5_collections.json"
    with open(collections_path, "w", encoding="utf-8") as f:
        json.dump(collections, f, ensure_ascii=False, indent=2)

    logger.info(f"聚类完成：{len(collections)} 个合集")
    return collections
