"""
video-clipper 核心 API 单元测试

覆盖最近修复的核心点：
- 时间字段 ISO+Z 后缀
- ORM 替代 hardcoded sync sqlite3
- path traversal 防护
- 软删 + processing 状态保护
- sync_get_db contextmanager
- watch_folders CRUD + include_disabled
- to_iso_utc helper

运行：
    pytest tests/ -v
"""
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# ============== Fixtures ==============

# 使用临时 DB（每个测试会话独立）
TEST_DB_FILE = tempfile.NamedTemporaryFile(suffix=".db", delete=False).name
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"
os.environ["DATABASE_URL"] = TEST_DB_URL

# 测试期间禁用 CELERY 避免引入 worker
os.environ["CELERY_BROKER_URL"] = "memory://"
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"

# 在 import app 之前设置环境变量
@pytest_asyncio.fixture(scope="session")
async def app_instance():
    """整个测试 session 共享一个 app + DB"""
    from backend.main import app
    from backend.core.database import sync_engine
    from backend.models.database import Base

    # 用 sync engine 创建 schema（避免 asyncio.run() 冲突）
    Base.metadata.create_all(bind=sync_engine)

    yield app

    # 清理
    try:
        os.unlink(TEST_DB_FILE)
    except OSError:
        pass


@pytest_asyncio.fixture
async def client(app_instance):
    """每个测试一个 client + DB 重置"""
    from backend.core.database import engine, AsyncSessionLocal
    from backend.models.database import (
        Project, Style, UserPreference, WatchFolder, Clip, Collection, Task
    )
    from sqlalchemy import text

    # 清空所有表（保 schema）
    async with engine.begin() as conn:
        for tbl in [Clip, Collection, Task, Project, Style, UserPreference, WatchFolder]:
            await conn.execute(text(f"DELETE FROM {tbl.__tablename__}"))

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============== 核心修复点测试 ==============

class TestTimeFormat:
    """时间字段 ISO+Z 后缀（修复 #M2）"""

    @pytest.mark.asyncio
    async def test_watch_folders_time_z_suffix(self, client):
        """watch_folders 时间字段必须有 Z 后缀"""
        r = await client.post("/api/v1/watch-folders", json={
            "name": "test", "path": "/tmp", "source_action": "delete"
        })
        assert r.status_code == 200
        folder = r.json()["folder"]
        for field in ["created_at", "last_scan_at", "last_processed_at"]:
            v = folder.get(field)
            if v is not None:
                assert v.endswith("Z"), f"{field}={v} no Z suffix"

    @pytest.mark.asyncio
    async def test_styles_time_z_suffix(self, client):
        """styles 时间字段必须有 Z 后缀"""
        r = await client.post("/api/v1/styles", json={
            "name": "test-style", "target_duration": 45
        })
        assert r.status_code == 200
        s = r.json()
        assert s["created_at"].endswith("Z")
        assert s["updated_at"].endswith("Z")

    @pytest.mark.asyncio
    async def test_projects_time_z_suffix(self, client):
        """projects 时间字段必须有 Z 后缀"""
        r = await client.post("/api/v1/styles", json={"name": "x", "target_duration": 30})
        assert r.status_code == 200
        r = await client.get("/api/v1/projects/")
        assert r.status_code == 200
        for p in r.json()["projects"]:
            for f in ["created_at", "completed_at", "deleted_at"]:
                v = p.get(f)
                if v is not None:
                    assert v.endswith("Z"), f"{f}={v} no Z"


class TestDatabaseCore:
    """core/database.py 修复"""

    def test_sync_get_db_is_contextmanager(self):
        """sync_get_db 必须支持 `with` 语法（修复 #6）

        @contextmanager 装饰器让 sync_get_db() 返回的对象具有 __enter__/__exit__
        """
        from backend.core.database import sync_get_db, SyncSessionLocal
        ctx = sync_get_db()  # 调用应返回 GeneratorContextManager
        assert hasattr(ctx, "__enter__"), "sync_get_db() 返回对象缺 __enter__"
        assert hasattr(ctx, "__exit__"), "sync_get_db() 返回对象缺 __exit__"

    def test_to_iso_utc_helper(self):
        """to_iso_utc 必须返回带 Z 后缀的 ISO 字符串"""
        from backend.core.database import to_iso_utc
        dt = datetime(2026, 6, 27, 14, 0, 0)
        assert to_iso_utc(dt) == "2026-06-27T14:00:00Z"
        assert to_iso_utc(None) is None

    def test_to_iso_utc_handles_microseconds(self):
        """to_iso_utc 必须保留微秒精度"""
        from backend.core.database import to_iso_utc
        dt = datetime(2026, 6, 27, 14, 0, 0, 123456)
        result = to_iso_utc(dt)
        assert "123456" in result
        assert result.endswith("Z")


class TestORMStyle:
    """styles.py 改用 ORM（修复 #7-8）"""

    @pytest.mark.asyncio
    async def test_create_style_orm(self, client):
        """POST /styles 走 ORM，应能创建并读回"""
        r = await client.post("/api/v1/styles", json={
            "name": "ORM-Test",
            "target_duration": 60,
            "max_clips": 15,
            "content_types": ["金句"],
            "rules": {"min_score": 0.7},
            "keep_rules": "金句, 观点",
            "style_positioning": "犀利"
        })
        assert r.status_code == 200
        s = r.json()
        assert s["name"] == "ORM-Test"
        assert s["keep_rules"] == "金句, 观点"
        assert s["style_positioning"] == "犀利"
        assert s["target_duration"] == 60
        # 验证 DB 中真实存在
        r2 = await client.get(f"/api/v1/styles/{s['id']}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "ORM-Test"

    @pytest.mark.asyncio
    async def test_partial_update(self, client):
        """PUT 部分更新：未传字段保持原值"""
        r = await client.post("/api/v1/styles", json={
            "name": "Partial",
            "target_duration": 45,
            "keep_rules": "金句"
        })
        assert r.status_code == 200
        sid = r.json()["id"]

        # 只更新 max_clips
        r = await client.put(f"/api/v1/styles/{sid}", json={"max_clips": 25})
        assert r.status_code == 200
        updated = r.json()
        assert updated["max_clips"] == 25
        assert updated["keep_rules"] == "金句"  # 保留
        assert updated["target_duration"] == 45  # 保留

    @pytest.mark.asyncio
    async def test_delete_style_cascades(self, client):
        """DELETE 后 GET 应 404"""
        r = await client.post("/api/v1/styles", json={"name": "Del", "target_duration": 30})
        sid = r.json()["id"]
        r = await client.delete(f"/api/v1/styles/{sid}")
        assert r.status_code == 200
        r = await client.get(f"/api/v1/styles/{sid}")
        assert r.status_code == 404


class TestORMUserPreferences:
    """user_preferences.py 改用 ORM + PATCH 部分更新"""

    @pytest.mark.asyncio
    async def test_orm_upsert_creates_default_row(self, client):
        """PUT 创建 default 行（修复之前的硬编码 DB 路径 bug）"""
        r = await client.put("/api/v1/preferences/subtitle-style", json={
            "font_size": 32, "txt_color": "yellow", "position": 0.85
        })
        assert r.status_code == 200
        # 读回
        r = await client.get("/api/v1/preferences")
        s = r.json()["last_used_subtitle_style"]
        assert s["font_size"] == 32
        assert s["txt_color"] == "yellow"

    @pytest.mark.asyncio
    async def test_patch_keeps_other_fields(self, client):
        """PATCH 只更新指定字段（修复：之前 PUT 会覆盖其他字段为 default）"""
        # 先 PUT 完整设置
        await client.put("/api/v1/preferences/subtitle-style", json={
            "font_size": 32, "txt_color": "yellow",
            "stroke_color": "red", "stroke_width": 3, "position": 0.85
        })
        # PATCH 只改 font_size
        r = await client.patch("/api/v1/preferences/subtitle-style", json={
            "font_size": 40
        })
        assert r.status_code == 200
        s = r.json()["last_used_subtitle_style"]
        # 更新了
        assert s["font_size"] == 40
        # 其他字段保留
        assert s["txt_color"] == "yellow"
        assert s["stroke_color"] == "red"
        assert s["stroke_width"] == 3
        assert s["position"] == 0.85


class TestWatchFolders:
    """watch_folders 完整 CRUD"""

    @pytest.mark.asyncio
    async def test_create_with_invalid_path(self, client):
        """路径不存在应 400"""
        r = await client.post("/api/v1/watch-folders", json={
            "name": "bad", "path": "/nonexistent/xyz", "source_action": "delete"
        })
        assert r.status_code == 400
        assert "路径不存在" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_with_relative_path(self, client):
        """相对路径应 400"""
        r = await client.post("/api/v1/watch-folders", json={
            "name": "bad", "path": "tmp/relative", "source_action": "delete"
        })
        assert r.status_code == 400
        assert "绝对路径" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_invalid_source_action(self, client):
        """source_action 无效值应 400"""
        r = await client.post("/api/v1/watch-folders", json={
            "name": "bad", "path": "/tmp", "source_action": "format_c"
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_min_scan_interval_enforced(self, client):
        """scan_interval < 10 应被强制到 10"""
        r = await client.post("/api/v1/watch-folders", json={
            "name": "min", "path": "/tmp", "source_action": "delete",
            "scan_interval_seconds": 2
        })
        assert r.status_code == 200
        assert r.json()["folder"]["scan_interval_seconds"] == 10

    @pytest.mark.asyncio
    async def test_include_disabled_filter(self, client):
        """include_disabled=false 默认只列 enabled=true"""
        # 创建 1 个启用 + 1 个停用
        r1 = await client.post("/api/v1/watch-folders", json={
            "name": "enabled", "path": "/tmp", "source_action": "delete", "enabled": True
        })
        r2 = await client.post("/api/v1/watch-folders", json={
            "name": "disabled", "path": "/tmp", "source_action": "delete", "enabled": False
        })
        wid1, wid2 = r1.json()["id"], r2.json()["id"]

        # 默认（不含 disabled）
        r = await client.get("/api/v1/watch-folders")
        ids = [f["id"] for f in r.json()["folders"]]
        assert wid1 in ids
        assert wid2 not in ids

        # include_disabled=true
        r = await client.get("/api/v1/watch-folders?include_disabled=true")
        ids = [f["id"] for f in r.json()["folders"]]
        assert wid1 in ids
        assert wid2 in ids


class TestProjectsSoftDelete:
    """projects 软删 + processing 保护"""

    @pytest.mark.asyncio
    async def test_soft_delete_completed(self, client):
        """completed 项目可软删"""
        # 创建一个项目
        r = await client.post("/api/v1/styles", json={"name": "x", "target_duration": 30})
        # 完整走流程（直接 DB 标记 completed 模拟）
        from backend.core.database import SyncSessionLocal
        from backend.models.database import Project
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        # 简化：手动建 project + 标 completed
        # 用 PATCH 更新 project.status
        pid = "test-pid-completed"
        with sync_get_db() as db:
            db.add(Project(id=pid, name="completed-test", status="completed"))
            db.commit()
        r = await client.delete(f"/api/v1/projects/{pid}")
        assert r.status_code == 200
        assert r.json()["permanent"] is False
        assert "deleted_at" in r.json()

    @pytest.mark.asyncio
    async def test_soft_delete_processing_rejected(self, client):
        """processing 状态软删应 409（保护 worker 写文件）"""
        pid = "test-pid-processing"
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        with sync_get_db() as db:
            db.add(Project(id=pid, name="processing-test", status="processing"))
            db.commit()
        r = await client.delete(f"/api/v1/projects/{pid}")
        assert r.status_code == 409
        assert "处理中" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_force_delete_processing_allowed(self, client):
        """?permanent=true 可强删 processing 项目"""
        pid = "test-pid-processing-force"
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        with sync_get_db() as db:
            db.add(Project(id=pid, name="force-delete", status="processing"))
            db.commit()
        r = await client.delete(f"/api/v1/projects/{pid}?permanent=true")
        assert r.status_code == 200
        assert r.json()["permanent"] is True

    @pytest.mark.asyncio
    async def test_restore_deleted(self, client):
        """恢复软删项目 → deleted_at 清空"""
        pid = "test-pid-restore"
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        from datetime import datetime
        with sync_get_db() as db:
            db.add(Project(id=pid, name="restore-test",
                           status="deleted",
                           deleted_at=datetime.utcnow()))
            db.commit()

        r = await client.post(f"/api/v1/projects/{pid}/restore")
        assert r.status_code == 200
        # 验证 deleted_at 清空
        r = await client.get(f"/api/v1/projects/{pid}")
        assert r.json()["project"]["deleted_at"] is None

    @pytest.mark.asyncio
    async def test_cleanup_old_trash(self, client):
        """cleanup older_than_days 删过期项目"""
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        from datetime import datetime, timedelta

        # 创建一个 40 天前删除的
        old_id = "old-trash-1"
        with sync_get_db() as db:
            db.add(Project(id=old_id, name="old", status="deleted",
                           deleted_at=datetime.utcnow() - timedelta(days=40)))
            db.commit()

        # 一个 5 天前删除的（不应被清理）
        recent_id = "recent-trash-1"
        with sync_get_db() as db:
            db.add(Project(id=recent_id, name="recent", status="deleted",
                           deleted_at=datetime.utcnow() - timedelta(days=5)))
            db.commit()

        r = await client.post("/api/v1/projects/trash/cleanup?older_than_days=30")
        assert r.status_code == 200
        cleaned = r.json()["cleaned_count"]
        assert old_id in r.json()["project_ids"]
        assert recent_id not in r.json()["project_ids"]

    @pytest.mark.asyncio
    async def test_cleanup_boundary_validation(self, client):
        """cleanup days 参数边界校验"""
        r = await client.post("/api/v1/projects/trash/cleanup?older_than_days=0")
        assert r.status_code == 422  # Pydantic ge=1
        r = await client.post("/api/v1/projects/trash/cleanup?older_than_days=500")
        assert r.status_code == 422  # Pydantic le=365


class TestProjectsSearch:
    """projects 搜索过滤"""

    @pytest.mark.asyncio
    async def test_search_by_name(self, client):
        """?search= 模糊搜索 name"""
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        for name in ["直播切片-A", "短视频-B", "直播切片-C", "其他"]:
            with sync_get_db() as db:
                db.add(Project(id=f"search-{name}", name=name, status="completed"))
                db.commit()

        r = await client.get("/api/v1/projects/?search=直播")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["projects"]]
        assert "直播切片-A" in names
        assert "直播切片-C" in names
        assert "短视频-B" not in names
        assert "其他" not in names

    @pytest.mark.asyncio
    async def test_search_no_results(self, client):
        """无匹配返回空 list"""
        r = await client.get("/api/v1/projects/?search=nonexistent_xyz")
        assert r.status_code == 200
        assert r.json()["projects"] == []


class TestSecurityPathTraversal:
    """Path traversal 防护"""

    @pytest.mark.asyncio
    async def test_project_file_not_found(self, client):
        """不存在 project 的文件请求应 404"""
        r = await client.get("/api/v1/projects/nonexistent/files/raw/input.mp4")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_absolute_path_blocked(self, client):
        """绝对路径尝试应 403"""
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        pid = "sec-test-1"
        with sync_get_db() as db:
            db.add(Project(id=pid, name="sec", status="completed"))
            db.commit()
        # /etc/passwd 绝对路径尝试
        r = await client.get(f"/api/v1/projects/{pid}/files//etc/passwd")
        assert r.status_code == 403
        assert "outside project" in r.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_traversal_in_path(self, client):
        """路径含 ../ 应 404（路由不匹配）"""
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        pid = "sec-test-2"
        with sync_get_db() as db:
            db.add(Project(id=pid, name="sec2", status="completed"))
            db.commit()
        r = await client.get(f"/api/v1/projects/{pid}/files/output/../../../etc/passwd")
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_project_file_blocked(self, client):
        """软删 project 文件应 404"""
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        from datetime import datetime
        pid = "sec-test-deleted"
        with sync_get_db() as db:
            db.add(Project(id=pid, name="del", status="deleted",
                           deleted_at=datetime.utcnow()))
            db.commit()
        r = await client.get(f"/api/v1/projects/{pid}/files/output/anything.mp4")
        assert r.status_code == 404


class TestUploadsValidation:
    """uploads input validation"""

    @pytest.mark.asyncio
    async def test_invalid_ext_rejected(self, client):
        """不支持的扩展名应 400"""
        r = await client.post("/api/v1/uploads/init", data={
            "name": "x", "filename": "video.exe", "total_size": 1024
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_zero_size_rejected(self, client):
        """total_size=0 应 400"""
        r = await client.post("/api/v1/uploads/init", data={
            "name": "x", "filename": "x.mp4", "total_size": 0
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_oversize_rejected(self, client):
        """total_size > 5GB 应 400"""
        r = await client.post("/api/v1/uploads/init", data={
            "name": "x", "filename": "x.mp4", "total_size": 10 * 1024**3
        })
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_negative_offset_rejected(self, client):
        """offset=-1 应 422"""
        import io
        r = await client.put(
            "/api/v1/uploads/up_test/chunk?offset=-1",
            files={"chunk": ("chunk", io.BytesIO(b"x"), "application/octet-stream")}
        )
        assert r.status_code == 422