"""资源库 LLM auto-tag service (v2.2.19)

上传 / from-clip 后 fire-and-forget 自动给资源打 tag, 减少运营手动点 ✨.

- 复用现有 _call_llm() (services/llm_service.py) — 已支持 GPT-4o-mini + Anthropic
- 失败 fallback: 从 name / source_project_name 抽 keyword (中文 + 英文)
- 不阻塞主流程: upload / from-clip 用 BackgroundTasks 加任务
- manual retry: 端点 POST /library/{id}/auto-tag
"""
import logging
import re

from ..core.database import sync_get_db
from ..models.database import ResourceClip

logger = logging.getLogger(__name__)


# 中文停用词 (auto-tag 不当 keyword)
STOP_WORDS = {
    "的", "了", "是", "在", "和", "与", "或", "我", "你", "他", "她", "它",
    "我们", "你们", "他们", "这个", "那个", "这", "那", "一个", "一些",
    "上", "下", "里", "外", "前", "后", "中", "大", "小", "多", "少",
    "好", "坏", "新", "老", "高", "低", "长", "短", "快", "慢",
    "啊", "嗯", "哦", "呀", "吧", "呢", "吗", "嘛", "哈",
    "今天", "明天", "昨天", "现在", "刚才", "已经", "正在", "会", "能",
    "什么", "怎么", "为什么", "哪里", "哪个", "多少",
    "from", "to", "of", "in", "the", "a", "an", "and", "or", "is", "are",
    "this", "that", "it", "we", "you", "he", "she", "they", "with",
    "for", "on", "at", "by", "as", "be", "have", "has", "had",
}


def _keyword_fallback(name: str, project_name: str, description: str = "") -> list[str]:
    """LLM 不可用 / 失败时的 keyword fallback.

    从 name / source_project_name / description 抽 2-3 字中文词 / 英文单词.
    简单 substring split, 不做 jieba (避免额外 dep).
    """
    text = " ".join([name or "", project_name or "", description or ""]).strip()
    if not text:
        return []

    tags = []
    seen = set()

    # 1. 中文 2-4 字词 (按常见 n-gram)
    # 抽 2-字 / 3-字 / 4-字 组合, 保留高频
    for n in (4, 3, 2):
        for m in re.finditer(rf"[\u4e00-\u9fff]{{{n}}}", text):
            w = m.group()
            if w in STOP_WORDS or w in seen:
                continue
            # 简单过滤: 至少有一个中文字符 (上面 regex 已保证)
            seen.add(w)
            tags.append(w)
            if len(tags) >= 5:
                return tags

    # 2. 英文单词 (lowercase, 长度 >= 3)
    for m in re.finditer(r"[A-Za-z]{3,}", text):
        w = m.group().lower()
        if w in STOP_WORDS or w in seen:
            continue
        seen.add(w)
        tags.append(w)
        if len(tags) >= 5:
            break

    return tags[:5]


def _call_llm_for_tags(name: str, project_name: str, description: str = "") -> list[str] | None:
    """调 LLM 给资源生成 1-3 个 tag. 失败返 None (走 fallback)."""
    try:
        from .llm_service import _call_llm
    except ImportError:
        return None

    if not name and not project_name:
        return None

    # 简短 prompt — 1-3 主题词, 限 50 chars (防 LLM timeout)
    context_parts = []
    if name:
        context_parts.append(f"标题: {name}")
    if project_name:
        context_parts.append(f"项目: {project_name}")
    if description:
        context_parts.append(f"描述: {description[:100]}")
    context = "\n".join(context_parts)

    prompt = f"""你是短视频素材库 tagger. 给下面视频素材生成 1-3 个最贴切的主题 tag (中文优先).

{context}

要求:
- 1-3 个 tag, 逗号分隔
- 中文 2-4 字优先 (例: 防水, 屋面, 直播)
- 不要动词 / 副词 / 停用词
- 只输出 tag, 不要解释

输出:"""

    try:
        response = _call_llm(prompt, model="gpt-4o-mini")
        if not response:
            return None
        # 解析: 逗号 / 顿号 / 换行 分隔
        raw = response.strip()
        for sep in ["\n", "、", ","]:
            if sep in raw:
                parts = [p.strip() for p in raw.split(sep) if p.strip()]
                break
        else:
            parts = [raw]

        # 清洗: 去标点 / 限长
        tags = []
        for p in parts[:3]:
            # 去首尾标点 + 限 8 字
            p = re.sub(r"^[^\u4e00-\u9fffA-Za-z]+|[^\u4e00-\u9fffA-Za-z]+$", "", p)
            if p and 2 <= len(p) <= 8 and p not in STOP_WORDS:
                tags.append(p)
        return tags if tags else None
    except Exception as e:  # noqa: BLE001 — LLM 可抛任意异常, 静默走 fallback
        logger.warning(f"LLM auto-tag 失败 (fallback 走 keyword): {e}")
        return None


def generate_tags_for_resource(resource_id: str) -> list[str]:
    """给单条资源生成 tags, 写到 db.

    Returns: 最终写入的 tags list. 失败时返 fallback keyword.
    """
    with sync_get_db() as db:
        rc = db.query(ResourceClip).filter(ResourceClip.id == resource_id).first()
        if not rc:
            logger.warning(f"auto-tag: resource {resource_id} 不存在")
            return []

        # 1. 试 LLM
        llm_tags = _call_llm_for_tags(
            name=rc.name or "",
            project_name=rc.source_project_name or "",
            description=rc.description or "",
        )

        # 2. fallback 拼 LLM 不足
        if not llm_tags or len(llm_tags) < 2:
            fallback = _keyword_fallback(
                name=rc.name or "",
                project_name=rc.source_project_name or "",
                description=rc.description or "",
            )
            if llm_tags:
                # LLM 1 个 + fallback 补 1-2 个, 去重
                seen = set(llm_tags)
                for t in fallback:
                    if t not in seen:
                        llm_tags.append(t)
                        seen.add(t)
                        if len(llm_tags) >= 3:
                            break
            else:
                llm_tags = fallback

        # 限 3 个
        llm_tags = llm_tags[:3]

        # 写 db
        rc.tags = llm_tags
        db.commit()
        logger.info(f"auto-tag: resource={resource_id} tags={llm_tags}")
        return llm_tags
