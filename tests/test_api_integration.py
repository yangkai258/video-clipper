"""v2.2.14 httpx 集成测试 (P3-4)

跟 unit test (test_core_fixes / test_project_style) 不同, 集成 test 跑真实 server:
- 跑 /watch-folders, /library, /mix, /projects 等所有 router smoke test
- 验 auth (admin 401 / 200)
- 验 search (P2-1) / size 校验 (P1-2) / DELETE protection (P1-3)
- 验 schema 同步 (lifespan migration runner)

前置: uvicorn 8000 必须在跑 (start-release.sh / uvicorn 手动启)

运行:
    pytest tests/test_api_integration.py -v
"""
# v2.2.14: 必须在 import backend.* 之前设 DATABASE_URL, 避免被 test_core_fixes
# 的 tempfile db url 抢走 (会触发 OperationalError no such table).
# 因为 pytest 默认按字母顺序 import, test_api_integration 会在 test_core_fixes
# 之后, 但 core_fixes 设的 os.environ["DATABASE_URL"] 在 module-level
# 已经 import backend.* 之前生效.
# 修法: 强制重设 DATABASE_URL 到 production db (跟 uvicorn 用的)
import os as _os
_os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/video_clipper.db"
_os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
_os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"

import os
import tempfile
import uuid
from pathlib import Path

import pytest
import requests  # sync 集成 test, 比 httpx AsyncClient 简单

BASE = "http://localhost:8000/api/v1"
ADMIN = ("team", "video123")


# === Health check ===

def test_health_no_auth():
    """GET /admin/health 公开 (健康检查)"""
    r = requests.get(f"{BASE}/admin/health", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["overall"] in ("healthy", "degraded", "unhealthy")


def test_health_checks_keys():
    """/admin/health 返 checks 子结构 (database/redis/disk)"""
    r = requests.get(f"{BASE}/admin/health", timeout=5)
    body = r.json()
    assert "checks" in body
    assert "database" in body["checks"]
    assert "redis" in body["checks"]
    assert "disk" in body["checks"]


# === Admin auth (P1-1 修) ===

def test_admin_system_no_auth_401():
    """GET /admin/system 无 auth 应 401"""
    r = requests.get(f"{BASE}/admin/system", timeout=5)
    assert r.status_code == 401


def test_admin_system_wrong_password_401():
    """/admin/system 错密码应 401"""
    r = requests.get(f"{BASE}/admin/system", auth=("team", "wrong"), timeout=5)
    assert r.status_code == 401


def test_admin_system_correct_password_200():
    """/admin/system 正确密码 (team/video123) 200 + 返 version"""
    r = requests.get(f"{BASE}/admin/system", auth=ADMIN, timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["version"].startswith("v"), f"version 应以 v 开头, 实际 {body['version']}"


def test_admin_users_list():
    """/admin/users 返 .htpasswd 账号列表 (P2-4 修)"""
    r = requests.get(f"{BASE}/admin/users", auth=ADMIN, timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "users" in body
    assert "team" in body["users"]
    assert body["count"] >= 1
    assert "source_file" in body


def test_admin_worker_status():
    """/admin/worker 返 celery worker 状态"""
    r = requests.get(f"{BASE}/admin/worker", auth=ADMIN, timeout=5)
    assert r.status_code == 200
    # 返 {} 或 {workers: ...} (没强制 schema, 只验不报错)


# === Projects (P2-1 search) ===

def test_projects_list_paginate():
    """GET /projects/ 返 projects + 默认分页"""
    r = requests.get(f"{BASE}/projects/", timeout=5)
    assert r.status_code == 200
    assert "projects" in r.json()


def test_projects_search():
    """?search= 模糊搜索 (P2-1 修)"""
    # 先建测试项目
    pid = f"integ-search-{uuid.uuid4().hex[:6]}"
    # 通过 DB 直接 insert (用 sync engine)
    from backend.core.database import sync_get_db
    from backend.models.database import Project
    with sync_get_db() as db:
        db.add(Project(id=pid, name="屋顶防水测试搜索专用", status="completed"))
        db.commit()
    try:
        # v2.2.20: uvicorn --reload reload 期间 5xx 概率高, retry 3 次
        import time as _t
        r = None
        for attempt in range(3):
            r = requests.get(f"{BASE}/projects/?search=屋顶", timeout=5)
            if r.status_code < 500:
                break
            _t.sleep(1)
        assert r is not None and r.status_code == 200, f"GET fail after 3 retries: {r.status_code if r else 'no response'}"
        names = [p["name"] for p in r.json()["projects"]]
        assert "屋顶防水测试搜索专用" in names
    finally:
        # 清理
        with sync_get_db() as db:
            from sqlalchemy import delete
            db.execute(delete(Project).where(Project.id == pid))
            db.commit()


def test_projects_search_no_match():
    """?search= 没匹配返空"""
    r = requests.get(f"{BASE}/projects/?search=xyz_no_match_zzz", timeout=5)
    assert r.status_code == 200
    assert r.json()["projects"] == []


# === Library ===

def test_library_list():
    """GET /library 返 resources + count + metrics"""
    r = requests.get(f"{BASE}/library", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "resources" in body
    assert "count" in body
    assert "metrics" in body


def test_library_tags():
    """GET /library 返 resources 含 tags 字段 (v2.2.7 LLM 自动 tag 已在 v2.2.7 merge)

    v2.2.15 修正: library router 没有 /tags 独立 endpoint (tags 在每个 resource 里),
    改测 list endpoint 验 resource.tags 字段存在 + 类型 list[str].
    """
    r = requests.get(f"{BASE}/library", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "resources" in body
    if body["resources"]:
        for rc in body["resources"]:
            assert "tags" in rc, f"resource {rc.get('id')} missing tags field"
            assert isinstance(rc["tags"], list), f"resource {rc.get('id')} tags must be list"
            for tag in rc["tags"]:
                assert isinstance(tag, str)


# === Mix ===

def test_mix_list():
    """GET /mix/ 返 projects list"""
    r = requests.get(f"{BASE}/mix/", timeout=5)
    assert r.status_code == 200
    assert "projects" in r.json()


def test_mix_batch_list():
    """GET /mix/batch 返 batches list"""
    r = requests.get(f"{BASE}/mix/batch", timeout=5)
    assert r.status_code == 200
    assert "batches" in r.json()


def test_mix_clips_library():
    """GET /mix/clips/library 返 library source clips"""
    r = requests.get(f"{BASE}/mix/clips/library?source=library", timeout=5)
    assert r.status_code == 200
    assert "clips" in r.json()


# === Uploads (P1-2 size) ===

def test_uploads_init_5gb_ok():
    """POST /uploads/init < 5GB 200"""
    r = requests.post(f"{BASE}/uploads/init", data={
        "name": "integ-test",
        "filename": "x.mp4",
        "total_size": 4 * 1024 * 1024 * 1024,  # 4GB
    }, timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert "upload_id" in body
    # 清理
    requests.delete(f"{BASE}/uploads/{body['upload_id']}", timeout=5)


def test_uploads_init_10gb_rejected():
    """POST /uploads/init > 5GB 400 (.env MAX_UPLOAD_SIZE=5GB 修后)"""
    r = requests.post(f"{BASE}/uploads/init", data={
        "name": "oversize",
        "filename": "x.mp4",
        "total_size": 10 * 1024 * 1024 * 1024,  # 10GB
    }, timeout=5)
    assert r.status_code == 400
    assert "上限" in r.json()["detail"]


# === Uploads chunk validation ===

def test_uploads_chunk_negative_offset_422():
    """PUT /uploads/{id}/chunk?offset=-1 应 422 (FastAPI Query ge=0)"""
    # 先建 session
    init = requests.post(f"{BASE}/uploads/init", data={
        "name": "t", "filename": "t.mp4", "total_size": 1024,
    }, timeout=5)
    upload_id = init.json()["upload_id"]
    try:
        r = requests.put(
            f"{BASE}/uploads/{upload_id}/chunk?offset=-1",
            files={"file": ("c", b"x", "application/octet-stream")},
            timeout=5,
        )
        assert r.status_code == 422
    finally:
        requests.delete(f"{BASE}/uploads/{upload_id}", timeout=5)


# === Library upload (P1-2 size) ===

def test_library_upload_5gb_rejected():
    """POST /library/upload > 5GB 应 413 (P1-2 修)

    v2.2.14: 5.5GB sparse file upload 行为:
    - server 写到 5GB+ 立即 unlink 半成品 + 写 413 response
    - 但 async 模式下 server 写耗时, client 已发完整个 5.5GB body,
      server 写完 5GB 后 detect 越界, 主动关连接
    - 实际测试: 接 413 OR ConnectionError 都算 success (server 真拒绝 5GB+)
    """
    big_file = Path(tempfile.gettempdir()) / "test_5gb.mp4"
    with open(big_file, "wb") as f:
        f.seek(5 * 1024 * 1024 * 1024 + 500 * 1024 * 1024 - 1)  # 5.5GB
        f.write(b"\x00")
    try:
        try:
            r = requests.post(
                f"{BASE}/library/upload",
                files={"file": ("test_5gb.mp4", open(big_file, "rb"), "video/mp4")},
                data={"name": "oversize-test"},
                timeout=120,
            )
            # server 写完 5GB 后返 413 (中等概率)
            assert r.status_code == 413, f"应 413, 实际 {r.status_code}"
            assert "5GB" in r.json()["detail"]
        except requests.exceptions.ConnectionError:
            # server 写完 5GB 后主动关连接 (正常 — P1-2 修 5GB limit 起效)
            pass
        # 验证 server 真的没存文件 (cleanup 验证)
        import time
        time.sleep(1)
        r2 = requests.get(f"{BASE}/library?limit=100", timeout=5)
        names = [r["name"] for r in r2.json()["resources"]]
        assert "oversize-test" not in names, "5GB+ 上传失败, server 应清理半成品"
    finally:
        big_file.unlink(missing_ok=True)


# === Cleanup endpoint (P2-2 days 范围校验) ===

def test_cleanup_trash_days_validation():
    """DELETE /trash?days=400 应 422 (P2-2 修)"""
    r = requests.delete(f"{BASE}/projects/trash?days=400", timeout=5)
    assert r.status_code == 422


def test_cleanup_trash_alias_post():
    """POST /trash/cleanup?older_than_days=30 应 200 (P2-2 alias 修)"""
    r = requests.post(f"{BASE}/projects/trash/cleanup?older_than_days=30", timeout=5)
    assert r.status_code == 200
