"""
Style model padding columns 回归测试 (v2.2.31)

Background: 4afb777 refactor (v2.1.53) 漏了 pre_padding_seconds / post_padding_seconds 2 列.
db schema 有, ORM 没, 漂移 2 个月. 2026-07-26 user 传 style_id 触发 AttributeError 500.

防回归: 测 Style model 必须有 pre_padding_seconds + post_padding_seconds attribute, 默认 10.0/5.0.
"""
import pytest


def test_style_model_has_padding_columns():
    """Style model 必须有 pre_padding_seconds + post_padding_seconds."""
    from backend.models.database import Style
    assert hasattr(Style, "pre_padding_seconds"), "Style model 漏 pre_padding_seconds 列 (v2.1.53 4afb777 refactor drift)"
    assert hasattr(Style, "post_padding_seconds"), "Style model 漏 post_padding_seconds 列"


def test_style_model_padding_defaults():
    """默认 10.0 / 5.0 (历史 style 的 fallback)."""
    from backend.models.database import Style
    from sqlalchemy import inspect
    mapper = inspect(Style)
    pre = mapper.columns["pre_padding_seconds"]
    post = mapper.columns["post_padding_seconds"]
    assert pre.default.arg == 10.0, f"pre_padding default 应 10.0, 实 {pre.default.arg}"
    assert post.default.arg == 5.0, f"post_padding default 应 5.0, 实 {post.default.arg}"


def test_style_model_padding_types():
    """类型必须是 Float (跟 db schema 一致)."""
    from backend.models.database import Style
    from sqlalchemy import Float, inspect
    mapper = inspect(Style)
    assert isinstance(mapper.columns["pre_padding_seconds"].type, Float), "pre_padding_seconds 应 Float"
    assert isinstance(mapper.columns["post_padding_seconds"].type, Float), "post_padding_seconds 应 Float"


def test_db_schema_has_padding_columns():
    """实际 db 跟 ORM 都得有这 2 列 (跑两个 db)."""
    import sqlite3
    from pathlib import Path
    base = Path("/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper/data")
    for db_name in ("video_clipper.db", "video_clipper_beta.db"):
        db_path = base / db_name
        if not db_path.exists():
            continue
        conn = sqlite3.connect(str(db_path))
        cols = [r[1] for r in conn.execute("PRAGMA table_info(styles)").fetchall()]
        conn.close()
        assert "pre_padding_seconds" in cols, f"{db_name} styles 表缺 pre_padding_seconds"
        assert "post_padding_seconds" in cols, f"{db_name} styles 表缺 post_padding_seconds"
