"""
v2.1.2 项目列表显示风格测试

覆盖：
- 后端返回 style_id + style_name
- 没选过风格时返回默认 (gray)
"""
import os
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


TEST_DB_FILE = "/tmp/_test_ui_project_style.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB_FILE}"
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"


@pytest_asyncio.fixture(scope="session")
async def app_instance():
    from backend.main import app
    from backend.core.database import sync_engine
    from backend.models.database import Base

    Base.metadata.create_all(bind=sync_engine)
    yield app
    try:
        os.unlink(TEST_DB_FILE)
    except OSError:
        pass


@pytest_asyncio.fixture
async def client(app_instance):
    from backend.core.database import engine
    from backend.models.database import Project, Style
    from sqlalchemy import text

    async with engine.begin() as conn:
        for tbl in [Project, Style]:
            await conn.execute(text(f"DELETE FROM {tbl.__tablename__}"))

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_list_projects_returns_style_fields(client):
    """GET /projects/ 每个项目必须包含 style_id + style_name"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project
    with sync_get_db() as db:
        db.add(Project(id="p1", name="A", status="completed"))
        db.add(Project(id="p2", name="B", status="completed",
                       processing_config={"style_id": "preset_golden_quotes"}))
        db.commit()

    # 实际跑请求
    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    assert res.status_code == 200
    projects = {p["name"]: p for p in res.json()["projects"]}
    assert "style_id" in projects["A"]
    assert "style_name" in projects["A"]
    assert "style_id" in projects["B"]
    assert "style_name" in projects["B"]


def test_default_style_for_unset_project(client):
    """没选过风格的项目应返回 style_id='_default' + style_name='默认'"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project
    with sync_get_db() as db:
        db.add(Project(id="p_default", name="NoStyle", status="completed"))
        db.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    p = next(p for p in res.json()["projects"] if p["name"] == "NoStyle")
    assert p["style_id"] == "_default", f"应为 _default, 实际 {p['style_id']}"
    assert p["style_name"] == "默认", f"应为 '默认', 实际 {p['style_name']}"


def test_known_style_id_resolved_to_name(client):
    """有 style_id 时应查 Style 表返回真实 name"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project, Style
    with sync_get_db() as db:
        db.add(Style(id="preset_golden_quotes", name="金句优先",
                     target_duration=45, max_clips=30,
                     content_types=[], rules={}))
        db.add(Project(id="p_styled", name="Styled", status="completed",
                       processing_config={"style_id": "preset_golden_quotes"}))
        db.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    p = next(p for p in res.json()["projects"] if p["name"] == "Styled")
    assert p["style_id"] == "preset_golden_quotes"
    assert p["style_name"] == "金句优先", f"应为 '金句优先', 实际 {p['style_name']}"


def test_orphan_style_id_falls_back(client):
    """style_id 写但 Style 已删 → name='已删除'"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project
    with sync_get_db() as db:
        db.add(Project(id="p_orphan", name="Orphan", status="completed",
                       processing_config={"style_id": "nonexistent_style"}))
        db.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    p = next(p for p in res.json()["projects"] if p["name"] == "Orphan")
    assert p["style_id"] == "nonexistent_style"  # 保留原 ID 用于追溯
    assert p["style_name"] == "已删除"  # 但显示"已删除"


def test_style_returns_target_duration_and_max_clips(client):
    """list 应返回 target_duration + max_clips（来自 Style 或 project config 覆盖）"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project, Style
    with sync_get_db() as db:
        db.add(Style(id="s1", name="金句优先", target_duration=45, max_clips=30,
                     content_types=[], rules={}))
        # 1. 无项目级覆盖 → 用 Style 表的值
        db.add(Project(id="p1", name="FromStyle", status="completed",
                       processing_config={"style_id": "s1"}))
        # 2. 项目级覆盖 target_duration + max_clips
        db.add(Project(id="p2", name="Overridden", status="completed",
                       processing_config={
                           "style_id": "s1",
                           "target_duration": 120,
                           "max_clips": 5,
                       }))
        # 3. 没选过风格 → None
        db.add(Project(id="p3", name="NoStyle", status="completed"))
        db.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    by_name = {p["name"]: p for p in res.json()["projects"]}
    # 1. 默认从 Style 表拿
    p1 = by_name["FromStyle"]
    assert p1["target_duration"] == 45, f"期望 45, 实际 {p1['target_duration']}"
    assert p1["max_clips"] == 30
    # 2. project config 覆盖
    p2 = by_name["Overridden"]
    assert p2["target_duration"] == 120  # 覆盖 Style 的 45
    assert p2["max_clips"] == 5  # 覆盖 Style 的 30
    # 3. 没选过 → None
    p3 = by_name["NoStyle"]
    assert p3["target_duration"] is None
    assert p3["max_clips"] is None


def test_list_returns_has_subtitle_from_processing_config(client):
    """has_subtitle 直接来自 processing_config.with_subtitle (bool)"""
    from backend.core.database import sync_get_db
    from backend.models.database import Project
    with sync_get_db() as db:
        db.add(Project(id="p_sub_on", name="WithSub", status="completed",
                       processing_config={"style_id": "s1", "with_subtitle": True}))
        db.add(Project(id="p_sub_off", name="NoSub", status="completed",
                       processing_config={"style_id": "s1", "with_subtitle": False}))
        db.add(Project(id="p_sub_default", name="UnsetSub", status="completed",
                       processing_config={"style_id": "s1"}))  # 没设置
        db.commit()

    import asyncio
    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(client.get("/api/v1/projects/"))
    loop.close()

    by_name = {p["name"]: p for p in res.json()["projects"]}
    assert by_name["WithSub"]["has_subtitle"] is True
    assert by_name["NoSub"]["has_subtitle"] is False
    # 未设置默认 False (没字幕 = 默认行为)
    assert by_name["UnsetSub"]["has_subtitle"] is False