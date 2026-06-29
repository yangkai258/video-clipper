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

    @pytest.mark.asyncio
    async def test_complete_upload_passes_db_to_get_subtitle_style(self, client, tmp_path, monkeypatch):
        """complete_upload 不再漏传 db 给 _get_last_subtitle_style (回归测试 v2.1.3)

        之前 bug: _get_last_subtitle_style() 漏传 db, 触发 500
        修法: await _get_last_subtitle_style(db)
        """
        # 准备：init + 上传一个 1KB 文件 + 调 complete
        import io
        r = await client.post(
            "/api/v1/uploads/init",
            data={"name": "回归测试", "filename": "tiny.mp4", "total_size": 1024},
        )
        assert r.status_code == 200, r.text
        upload_id = r.json()["upload_id"]

        # 上传 1 个 1KB 分片
        r = await client.put(
            f"/api/v1/uploads/{upload_id}/chunk?offset=0",
            files={"chunk": ("chunk", io.BytesIO(b"\x00" * 1024), "application/octet-stream")},
        )
        assert r.status_code == 200, r.text

        # 关键: complete 不应 500 (老 bug 是 500)
        r = await client.post(f"/api/v1/uploads/{upload_id}/complete")
        # 可能 200 (成功) 或 4xx (ffprobe 拒绝非真 mp4)，但绝对不能 500
        assert r.status_code != 500, f"complete_upload 仍然 500: {r.text}"
        assert r.status_code in (200, 400, 422), f"unexpected status {r.status_code}: {r.text}"


class TestProgressGranularity:
    """进度更新细粒度 (v2.1.4)"""

    def test_update_task_progress_helper_writes_to_db(self):
        """_update_task_progress 应该写入 progress + current_step 到 db"""
        from backend.core.database import sync_get_db
        from backend.models.database import Task, Project
        from backend.tasks.processing import _update_task_progress
        from datetime import datetime

        with sync_get_db() as db:
            db.add(Project(id="p_prog", name="P", status="processing",
                           created_at=datetime.utcnow()))
            db.add(Task(id="t_prog", project_id="p_prog", task_type="video_processing",
                        status="running", progress=0, current_step=""))
            db.commit()

        _update_task_progress("t_prog", 42, "测试中")

        with sync_get_db() as db:
            from sqlalchemy import select
            t = db.execute(select(Task).where(Task.id == "t_prog")).scalar_one()
            assert t.progress == 42, f"期望 42, 实际 {t.progress}"
            assert t.current_step == "测试中"

    def test_update_task_progress_clamps_range(self):
        """progress 限制在 0-100 之间"""
        from backend.core.database import sync_get_db
        from backend.models.database import Task, Project
        from backend.tasks.processing import _update_task_progress
        from datetime import datetime
        from sqlalchemy import select

        with sync_get_db() as db:
            db.add(Project(id="p_clamp", name="P", status="processing",
                           created_at=datetime.utcnow()))
            db.add(Task(id="t_clamp", project_id="p_clamp", task_type="video_processing",
                        status="running", progress=0, current_step=""))
            db.commit()

        # 上界
        _update_task_progress("t_clamp", 150, "X")
        with sync_get_db() as db:
            t = db.execute(select(Task).where(Task.id == "t_clamp")).scalar_one()
            assert t.progress == 100, f"150 应被 clamp 到 100, 实际 {t.progress}"
        # 下界
        _update_task_progress("t_clamp", -5, "X")
        with sync_get_db() as db:
            t = db.execute(select(Task).where(Task.id == "t_clamp")).scalar_one()
            assert t.progress == 0, f"-5 应被 clamp 到 0, 实际 {t.progress}"

    def test_update_task_progress_nonexistent_task_safe(self):
        """task_id 不存在时只 warning, 不抛错"""
        from backend.tasks.processing import _update_task_progress
        # 不应抛错
        _update_task_progress("nonexistent_task_id_xxx", 50, "X")


class TestEtaEstimation:
    """进度 ETA 估算 (v2.1.5)"""

    def test_eta_linear_extrapolation_after_5pct(self):
        """progress >= 5% 时用线性外推"""
        from backend.api.projects import _estimate_eta_seconds
        # 跑了 60s, progress=20% → 预计总 300s → 剩余 240s
        assert _estimate_eta_seconds(20, 60) == 240
        # 跑了 120s, progress=50% → 预计总 240s → 剩余 120s
        assert _estimate_eta_seconds(50, 120) == 120
        # 跑了 300s, progress=99% → 预计总 303s → 剩余 3s (允许 ±1)
        assert abs(_estimate_eta_seconds(99, 300) - 3) <= 1

    def test_eta_heuristic_under_5pct(self):
        """progress < 5% 时用启发式 (基于视频时长)"""
        from backend.api.projects import _estimate_eta_seconds
        # 跑了 30s, progress=0%, 视频 600s (10分钟)
        # 启发式: 总 = 600 * 0.25 + 180 = 330s, 剩余 300s
        eta = _estimate_eta_seconds(0, 30, video_duration_seconds=600)
        assert eta == 300, f"启发式 10 分钟视频 30s 后剩余应 300s, 实际 {eta}"
        # 跑了 30s, progress=3%, 同上
        eta = _estimate_eta_seconds(3, 30, video_duration_seconds=600)
        assert eta == 300
        # 没视频时长 → None
        assert _estimate_eta_seconds(0, 30, video_duration_seconds=None) is None

    def test_eta_returns_none_when_too_early(self):
        """elapsed = 0 时算不出"""
        from backend.api.projects import _estimate_eta_seconds
        assert _estimate_eta_seconds(50, 0) is None
        assert _estimate_eta_seconds(50, -1) is None

    def test_eta_floors_at_zero(self):
        """剩余时间不会小于 0"""
        from backend.api.projects import _estimate_eta_seconds
        # 跑了 600s, progress=100% → 总 600s → 剩余 0
        assert _estimate_eta_seconds(100, 600) == 0
        # 跑了 800s, progress=100% → 负数 → clamp 0
        assert _estimate_eta_seconds(100, 800) == 0


class TestZeroClipGuard:
    """v2.1.23: 0-clip guard 防止 'completed 但 0 产物' 假成功"""

    def test_pipeline_has_zero_clip_guard(self):
        """processing.py 必须有 0-clip guard 逻辑"""
        from pathlib import Path
        processing_path = Path(__file__).parent.parent / "backend" / "tasks" / "processing.py"
        content = processing_path.read_text()
        # 检查 guard 关键字
        assert "0-clip guard" in content
        assert "no_clips_generated" in content
        # 检查 guard 检查的是 clips+collections 长度
        assert "len(titled_clips) == 0" in content
        assert "len(collections) == 0" in content
        # guard 必须把 status 改成 failed 而非 completed
        guard_block = content[content.find("0-clip guard"):]
        assert 'status = "failed"' in guard_block
        # guard 必须有 error_message 提示
        assert "未能识别到任何切片片段" in guard_block

    @pytest.mark.asyncio
    async def test_zero_clip_guard_runs_after_db_write(self, client):
        """guard 必须在 db.commit() 之后运行 (这样才能覆盖 completed 写库)"""
        from pathlib import Path
        processing_path = Path(__file__).parent.parent / "backend" / "tasks" / "processing.py"
        content = processing_path.read_text()

        # 用专用 marker 定位 (v2.1.23 review fix: 不依赖注释文字)
        guard_idx = content.find("# ZERO_CLIP_GUARD_MARKER")
        commit_idx = content.find("# STEP10_DB_COMMIT_MARKER")
        assert guard_idx > 0, "0-clip guard marker not found"
        assert commit_idx > 0, "Step 10 db.commit marker not found"
        # guard 必须在 commit 之后 (能在 commit 写库后改写 status)
        assert guard_idx > commit_idx, "0-clip guard must run after db.commit()"

    @pytest.mark.asyncio
    async def test_zero_clip_guard_runs_before_cleanup(self, client):
        """guard 必须在 cleanup raw 之前! (v2.1.24 fix: 否则 raw 被删, 用户改风格重切就没文件了)

        之前 guard 在 cleanup 之后, 0-clip 时 raw 已被删, 保留 raw 失败原因就是
        用户希望 '改风格重切' 但 raw 没了。
        """
        from pathlib import Path
        processing_path = Path(__file__).parent.parent / "backend" / "tasks" / "processing.py"
        content = processing_path.read_text()

        guard_idx = content.find("# ZERO_CLIP_GUARD_MARKER")
        # 找 cleanup raw 的注释位置
        cleanup_idx = content.find("=== 清理 raw 视频")
        assert guard_idx > 0, "0-clip guard marker not found"
        assert cleanup_idx > 0, "cleanup section not found"
        # guard 必须在 cleanup 之前 (raw 还没删就 return)
        assert guard_idx < cleanup_idx, \
            "0-clip guard must run BEFORE cleanup (v2.1.24 fix: 用户改风格重切需要 raw 视频)"

    @pytest.mark.asyncio
    async def test_zero_clip_guard_skips_deleted_projects(self, client):
        """guard 不应覆盖已 soft-delete 的项目 (review fix: 加 deleted_at 检查)"""
        from pathlib import Path
        processing_path = Path(__file__).parent.parent / "backend" / "tasks" / "processing.py"
        content = processing_path.read_text()

        # 找 helper 函数定义位置 (review fix: helper 抽出来后, deleted_at 检查也在 helper 里)
        helper_idx = content.find("def _mark_zero_output_failed")
        assert helper_idx > 0, "helper _mark_zero_output_failed not found"
        # helper 函数体必须包含 deleted_at 检查
        helper_block = content[helper_idx:helper_idx + 1500]
        assert "deleted_at is None" in helper_block, \
            "guard should skip soft-deleted projects to avoid overriding user delete"

    @pytest.mark.asyncio
    async def test_mark_zero_output_failed_actually_marks_failed(self, client):
        """真触发 helper: completed 项目 → 调 helper → 变 failed (end-to-end 行为测试)"""
        from backend.tasks.processing import _mark_zero_output_failed
        from backend.core.database import sync_get_db
        from backend.models.database import Project, Task
        from datetime import datetime

        # 直接用 sync engine 准备数据 (避免 asyncio.run 在 pytest-asyncio 里冲突)
        with sync_get_db() as db:
            proj = Project(
                id="proj_zcg_e2e",
                name="0-clip 测试",
                status="completed",
                video_path="raw/input.mp4",
                completed_at=datetime.utcnow(),
            )
            db.add(proj)
            task = Task(
                id="task_zcg_e2e",
                project_id="proj_zcg_e2e",
                task_type="video_processing",
                name="test task",
                status="completed",
                progress=100,
            )
            db.add(task)
            db.commit()

        # 触发: 调 helper
        _mark_zero_output_failed(
            project_id="proj_zcg_e2e",
            task_id="task_zcg_e2e",
            reason="未能识别到任何切片片段 (视频过短 或 无有效切点)",
        )

        # 断言: status 改了
        with sync_get_db() as db:
            proj = db.query(Project).filter(Project.id == "proj_zcg_e2e").first()
            assert proj.status == "failed"
            assert proj.completed_at is None

            task_row = db.query(Task).filter(Task.id == "task_zcg_e2e").first()
            assert task_row.status == "failed"
            assert "未能识别" in task_row.error_message

        # 清理
        with sync_get_db() as db:
            db.query(Task).filter(Task.id == "task_zcg_e2e").delete()
            db.query(Project).filter(Project.id == "proj_zcg_e2e").delete()
            db.commit()

    @pytest.mark.asyncio
    async def test_mark_zero_output_skips_deleted_projects(self, client):
        """helper 不应覆盖 soft-delete 的项目 (review fix 行为验证)"""
        from backend.tasks.processing import _mark_zero_output_failed
        from backend.core.database import sync_get_db
        from backend.models.database import Project
        from datetime import datetime

        with sync_get_db() as db:
            proj = Project(
                id="proj_zcg_deleted",
                name="已删除测试",
                status="completed",
                video_path="raw/input.mp4",
                completed_at=datetime.utcnow(),
                deleted_at=datetime.utcnow(),  # 已 soft-delete
            )
            db.add(proj)
            db.commit()

        _mark_zero_output_failed(
            project_id="proj_zcg_deleted",
            task_id=None,
            reason="test",
        )

        # 断言: soft-delete 的项目状态保持 completed (不被 guard 覆盖)
        with sync_get_db() as db:
            proj = db.query(Project).filter(Project.id == "proj_zcg_deleted").first()
            assert proj.status == "completed", \
                "guard should NOT override soft-deleted project's status"
            assert proj.deleted_at is not None

        with sync_get_db() as db:
            db.query(Project).filter(Project.id == "proj_zcg_deleted").delete()
            db.commit()

class TestScoreClipsContentTypes:
    """v2.1.24: score_clips content_types 不再硬过滤 (改加分)"""

    def test_content_types_does_not_filter(self):
        """content_types 不应该硬过滤掉 title 不含分类名的 clip (会误杀)"""
        from backend.services.llm_service import score_clips
        from pathlib import Path
        import tempfile

        # 临时 metadata 目录
        tmp = Path(tempfile.mkdtemp())
        timeline = [
            {"title": "商品链接引导", "start_time": 0, "end_time": 10, "subtopics": []},
            {"title": "互动引导", "start_time": 31, "end_time": 38, "subtopics": []},
        ]
        strategy_config = {
            "content_types": ["直播带货", "口播催单", "商品介绍", "互动金句", "下单引导"],
            "rules": {"min_score": 0.55}
        }

        result = score_clips(timeline, tmp, strategy_config)
        # v2.1.24 fix: 之前 content_types 字符串子串匹配, "商品链接引导" 不含 "商品介绍"
        # → 0 通过. 修复后: content_types 改为加分而非过滤, 应该都通过 (基础分 0.8 > 0.55)
        assert len(result) == 2, \
            f"content_types should not filter, got {len(result)} clips (expected 2)"

    def test_content_types_gives_bonus_when_matched(self):
        """content_types 命中应该加分 (但不强制)"""
        from backend.services.llm_service import score_clips
        from pathlib import Path
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        timeline = [
            {"title": "直播带货介绍", "start_time": 0, "end_time": 10, "subtopics": []},
            {"title": "无关主题", "start_time": 11, "end_time": 20, "subtopics": []},
        ]
        strategy_config = {
            "content_types": ["直播带货", "口播催单"],
            "rules": {"min_score": 0.85}  # 高阈值, 只有匹配分类 + 基础分才能过
        }

        result = score_clips(timeline, tmp, strategy_config)
        # "直播带货介绍" 含 "直播带货" → 加分 (0.8 + 0.1 = 0.9 >= 0.85 通过)
        # "无关主题" 不含分类 → 基础分 0.8 < 0.85 淘汰
        titles = [c["title"] for c in result]
        assert "直播带货介绍" in titles
        assert "无关主题" not in titles

    def test_min_score_uses_0_to_1_scale(self):
        """min_score 是 0-1 比例 (0.55 = 55%), 不是 0-100 整数"""
        from backend.services.llm_service import score_clips
        from pathlib import Path
        import tempfile

        tmp = Path(tempfile.mkdtemp())
        timeline = [
            {"title": "测试切片", "start_time": 0, "end_time": 10, "subtopics": []},
        ]
        # min_score=0.55 意味着 score >= 0.55 通过 (基础分 0.8 直接过)
        strategy_config = {
            "content_types": [],
            "rules": {"min_score": 0.55}
        }
        result = score_clips(timeline, tmp, strategy_config)
        assert len(result) == 1, "min_score=0.55 should pass base score 0.8"


class TestCollectionsClipIds:
    """v2.1.24: collections 写库用 clip_ids 字段而非遍历 clips 找 index"""

    @pytest.mark.asyncio
    async def test_collections_use_clip_ids_field_not_traverse_clips(self, client):
        """processing.py 写库时应该用 coll_data['clip_ids'] 而不是遍历 clips 找 index"""
        from pathlib import Path
        processing_path = Path(__file__).parent.parent / "backend" / "tasks" / "processing.py"
        content = processing_path.read_text()

        # 找 Step 10 插入 collections 的部分
        # 必须用 coll_data.get("clip_ids", []) 而不是遍历 clips
        assert 'coll_data.get("clip_ids"' in content, \
            "processing.py should use clip_ids field, not traverse clips to find index"
        # 不应该有 KeyError 'index' 的写法
        assert 'c["index"] for c in coll_data.get("clips"' not in content, \
            "v2.1.24 fix: removed c['index'] traversal that caused KeyError"


class TestNormalizeMinScore:
    """v2.1.25: min_score 数据契约规范化 — 0-1 比例 + 自动转换 0-100 整数"""

    def test_already_normalized_passes_through(self):
        """0-1 范围的值原样返回"""
        from backend.services.llm_service import _normalize_min_score
        assert _normalize_min_score(0.55) == 0.55
        assert _normalize_min_score(0.6) == 0.6
        assert _normalize_min_score(0.0) == 0.0
        assert _normalize_min_score(1.0) == 1.0

    def test_0_to_100_integer_auto_divided(self):
        """1-100 整数自动除以 100 (历史 migrations / 用户误用)"""
        from backend.services.llm_service import _normalize_min_score
        assert _normalize_min_score(55) == 0.55
        assert _normalize_min_score(80) == 0.80
        assert _normalize_min_score(100) == 1.0
        assert _normalize_min_score(70) == 0.70

    def test_none_uses_default(self):
        """None / 非法值用默认 0.6"""
        from backend.services.llm_service import _normalize_min_score
        assert _normalize_min_score(None) == 0.6
        assert _normalize_min_score("abc") == 0.6

    def test_out_of_range_clamps(self):
        """越界值 clamp 到 [0, 1]"""
        from backend.services.llm_service import _normalize_min_score
        # 1.5 不是 0-1 也不是 0-100 (除以 100 后 0.015 < 0)
        # 实际会被识别为 > 1 → 除以 100 → 0.015
        # 但 1.5 < 1.0 不对, 实际上 v > 1.0 才除以 100
        # 1.5 > 1.0 所以除以 100 = 0.015
        assert _normalize_min_score(150) == 1.0  # > 100 clamp
        assert _normalize_min_score(-0.5) == 0.0  # < 0 clamp

    def test_string_numeric_supported(self):
        """字符串数字也能转"""
        from backend.services.llm_service import _normalize_min_score
        assert _normalize_min_score("0.7") == 0.7
        assert _normalize_min_score("55") == 0.55  # 字符串 '55' 转 float 后 > 1 → 除 100

    def test_llm_service_uses_normalize(self):
        """score_clips 必须用 _normalize_min_score"""
        from pathlib import Path
        llm_path = Path(__file__).parent.parent / "backend" / "services" / "llm_service.py"
        content = llm_path.read_text()
        score_fn_idx = content.find("def score_clips")
        assert score_fn_idx > 0
        score_fn_body = content[score_fn_idx:score_fn_idx + 2000]
        assert "_normalize_min_score" in score_fn_body, \
            "score_clips must use _normalize_min_score (v2.1.25 数据契约)"

    def test_local_processor_uses_normalize(self):
        """local_processor 必须用 _normalize_min_score"""
        from pathlib import Path
        lp_path = Path(__file__).parent.parent / "backend" / "services" / "local_processor.py"
        content = lp_path.read_text()
        assert "_normalize_min_score" in content, \
            "local_processor must use _normalize_min_score (v2.1.25 数据契约)"
        assert "from .llm_service import _normalize_min_score" in content, \
            "local_processor must import from llm_service"


class TestFfprobeHelper:
    """v2.1.26: ffprobe helper - 提取视频宽高 + orientation 判断"""

    def test_get_orientation_portrait(self):
        from backend.services.ffprobe_helper import get_orientation
        assert get_orientation(720, 1280) == "portrait"
        assert get_orientation(540, 960) == "portrait"
        assert get_orientation(360, 640) == "portrait"

    def test_get_orientation_landscape(self):
        from backend.services.ffprobe_helper import get_orientation
        assert get_orientation(1280, 720) == "landscape"
        assert get_orientation(1920, 1080) == "landscape"

    def test_get_orientation_cinemascope(self):
        """2.35:1 电影比例识别为宽银幕"""
        from backend.services.ffprobe_helper import get_orientation
        assert get_orientation(1694, 720) == "cinemascope"
        assert get_orientation(2400, 1000) == "cinemascope"

    def test_get_orientation_square(self):
        from backend.services.ffprobe_helper import get_orientation
        assert get_orientation(1080, 1080) == "square"

    def test_get_orientation_default_landscape(self):
        """None/0 默认横屏"""
        from backend.services.ffprobe_helper import get_orientation
        assert get_orientation(0, 0) == "landscape"
        assert get_orientation(None, None) == "landscape"


class TestVideoEncoderArgs:
    """v2.1.26: output_format 控制 ffmpeg 编码参数"""

    def test_original_format(self):
        """original 返回基础硬件加速参数 (无 vf)"""
        from backend.services.video_service import _build_video_encoder_args
        args = _build_video_encoder_args("original")
        assert "-vf" not in args
        assert "h264_videotoolbox" in args

    def test_letterbox_format_has_vf(self):
        """letterbox 包含 scale+pad filter"""
        from backend.services.video_service import _build_video_encoder_args
        args = _build_video_encoder_args("9:16-letterbox")
        vf_idx = args.index("-vf")
        vf_value = args[vf_idx + 1]
        # 应该有 scale 和 pad
        assert "scale=1080" in vf_value
        assert "pad=1080:1920" in vf_value
        assert "color=black" in vf_value

    def test_unknown_format_falls_back_to_original(self):
        """未知 output_format 应回退 (在 cut_clips 里)"""
        # cut_clips 会 warning + 用 original
        # 这里直接验证 _build_video_encoder_args 不依赖 output_format 是否有效
        from backend.services.video_service import _build_video_encoder_args
        # 即使传奇怪的值, helper 返回基础参数 (因为 helper 不做校验, 校验在 cut_clips)
        args = _build_video_encoder_args("garbage")
        assert "-vf" not in args


class TestVideoWidthHeightSchema:
    """v2.1.26: Project/Clip 模型加 video_width/video_height / width/height 字段"""

    def test_project_has_video_dimensions_columns(self):
        from backend.models.database import Project
        assert hasattr(Project, 'video_width')
        assert hasattr(Project, 'video_height')

    def test_clip_has_dimensions_columns(self):
        from backend.models.database import Clip
        assert hasattr(Clip, 'width')
        assert hasattr(Clip, 'height')
