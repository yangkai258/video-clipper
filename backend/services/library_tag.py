"""v2.2.7 资源库 LLM 自动标签生成

每个 ResourceClip 根据 title + source_project_name + description 生成 1-3 个主题标签.
LLM 失败时 fallback 到 keyword 提取 (从 title 切分).
"""
import json
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# 通用兜底: 屏蔽词 (单字/数字/语气词, 不当 tag)
_STOPWORDS = set([
    "的", "了", "和", "是", "在", "也", "都", "就", "不", "啊", "吧",
    "什么", "怎么", "为什么", "这个", "那个", "一种", "一下", "一些",
    "video", "clip", "test", "测试", "demo", "sample", "片段",
])


def _fallback_keyword_tags(text: str, max_tags: int = 3) -> List[str]:
    """LLM 失败时兜底: 从 title 切关键词 (去除停用词 + 单字 + 数字)

    返回 1-3 个 tag, 长度 2-6 字
    """
    if not text:
        return ["未分类"]
    # 切词 (中文按字, 英文按词)
    candidates = []
    # 1) 提取中文 2-4 字短语
    for m in re.finditer(r'[\u4e00-\u9fff]{2,4}', text):
        if m.group() not in _STOPWORDS:
            candidates.append(m.group())
    # 2) 提取英文单词 (去复数 s)
    for m in re.finditer(r'[a-zA-Z]{3,}', text):
        w = m.group().lower()
        if w not in _STOPWORDS:
            candidates.append(w)
    # 去重 + 按长度优先 (长的更具体)
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    # 优先 2-6 字
    primary = [c for c in unique if 2 <= len(c) <= 6]
    if not primary:
        primary = unique[:max_tags]
    return primary[:max_tags] if primary else ["未分类"]


def _normalize_tag(t: str) -> str:
    """规范化 tag (去空格, 限制长度)"""
    t = t.strip()
    if not t:
        return ""
    if len(t) > 8:
        return t[:8]
    return t


def generate_tags_for_clip(
    title: str,
    source_project_name: str = "",
    description: str = "",
    max_tags: int = 3,
    model: Optional[str] = None,
) -> List[str]:
    """LLM 生成 1-3 个主题标签, 失败 fallback 到 keyword 提取

    返回 ["防水", "施工", "屋顶"] 这种格式
    """
    text = (title or "") + " " + (description or "")
    if not text.strip():
        return ["未分类"]

    # 1) LLM 路径
    from ..services.llm_service import _call_llm
    prompt = f"""你是短视频内容分类专家. 给这段素材打 1-3 个主题标签 (中文优先, 没有中文用英文).

要求:
- 主题词 (不是动作词), 用户能搜到的概念 (防水/施工/材料/屋顶/外墙/阳台/工艺...)
- 长度 2-6 字
- 用逗号分隔, 严格输出 JSON 数组格式 (不要 markdown)
- 1-3 个标签, 重复/近义的只留 1 个

素材标题: {title.strip()[:80]}
来源项目: {(source_project_name or '').strip()[:40]}
描述: {(description or '').strip()[:200]}

直接输出 JSON, 例: ["防水", "施工"]
"""
    try:
        raw = _call_llm(prompt, model=model)
        if raw:
            # 提取 JSON (LLM 可能加 markdown fence 或说明)
            raw = raw.strip()
            # 去 markdown code fence
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)
            # 找 JSON 数组
            m = re.search(r'\[([^\]]+)\]', raw)
            if m:
                items = [t.strip().strip('"').strip("'") for t in m.group(1).split(',')]
                items = [_normalize_tag(t) for t in items if t.strip()]
                items = [t for t in items if t and t not in _STOPWORDS]
                if items:
                    return items[:max_tags]
    except Exception as e:
        logger.warning(f"LLM tag 生成失败, fallback 到 keyword: {e}")

    # 2) Fallback keyword
    return _fallback_keyword_tags(text, max_tags=max_tags)


def generate_tags_batch(
    clips: List[Dict],
    max_tags: int = 3,
    model: Optional[str] = None,
) -> List[List[str]]:
    """批量给 N 个 clip 生成标签 (逐个 LLM 调用, 不 batch 节省成本)

    输入 [{id, title, source_project_name, description, current_tags}]
    输出 [[tag1, tag2], ...] 同长度
    """
    return [
        generate_tags_for_clip(
            title=c.get("title", ""),
            source_project_name=c.get("source_project_name", ""),
            description=c.get("description", ""),
            max_tags=max_tags,
            model=model,
        )
        for c in clips
    ]