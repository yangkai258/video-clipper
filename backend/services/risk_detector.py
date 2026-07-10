"""v2.2.4 风险词检测服务

扫描脚本中的抖音直播违规词 + 广告法敏感词, 提交前给运营警告.
不阻止提交 (用户可能故意), 仅高亮警告 + 提交时再次提示.

词库: backend/data/risk_words.json (版本化, 可热加载)
"""
import json
import re
from pathlib import Path
from typing import Dict, List

_RISK_WORDS_PATH = Path(__file__).parent.parent / "data" / "risk_words.json"
_cache: Dict = {"mtime": 0, "data": None}


def _load_risk_words() -> Dict:
    """懒加载 + mtime 缓存 (避免每次请求都 IO)"""
    if not _RISK_WORDS_PATH.exists():
        return {"categories": {}}

    mtime = _RISK_WORDS_PATH.stat().st_mtime
    if _cache["data"] and _cache["mtime"] == mtime:
        return _cache["data"]

    try:
        with open(_RISK_WORDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        _cache["mtime"] = mtime
        _cache["data"] = data
        return data
    except Exception:
        return {"categories": {}}


def check_script_risk(text: str) -> Dict:
    """扫描文本中的风险词

    返回:
    {
        "total_risk_count": 3,
        "has_risk": True,
        "level": "high",   # "none" / "low" (1-2) / "medium" (3-5) / "high" (6+)
        "hits": [
            {"category": "极限词", "word": "最好", "positions": [{"start": 12, "end": 14, "context": "防水效果最好"}]},
            ...
        ],
        "version": "2026-07",
    }
    """
    if not text or not text.strip():
        return {"total_risk_count": 0, "has_risk": False, "level": "none", "hits": [], "version": ""}

    data = _load_risk_words()
    categories = data.get("categories", {})
    version = data.get("version", "")

    hits = []
    total = 0

    for category, words in categories.items():
        for word in words:
            # 简单 substring 扫描 (中文不分词)
            positions = []
            start = 0
            while True:
                idx = text.find(word, start)
                if idx < 0:
                    break
                # context: 前后 5 个字符
                ctx_start = max(0, idx - 5)
                ctx_end = min(len(text), idx + len(word) + 5)
                positions.append({
                    "start": idx,
                    "end": idx + len(word),
                    "context": text[ctx_start:ctx_end],
                })
                start = idx + len(word)
                total += 1

            if positions:
                hits.append({
                    "category": category,
                    "word": word,
                    "count": len(positions),
                    "positions": positions,
                })

    # 风险等级 (跟数量挂钩, 不看严重度 — 因为当前词库所有词都同权重)
    if total == 0:
        level = "none"
    elif total <= 2:
        level = "low"
    elif total <= 5:
        level = "medium"
    else:
        level = "high"

    return {
        "total_risk_count": total,
        "has_risk": total > 0,
        "level": level,
        "hits": hits,
        "version": version,
    }