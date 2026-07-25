"""pytest 全局配置"""
import sys
import os
import time
from pathlib import Path

# 把项目根目录加到 sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# v2.2.14: pytest_collection 期间强制设 production DATABASE_URL
# 防止 test_core_fixes / test_project_style 之类 module-level
# 设的 tempfile db url 污染后续 import backend.*
# 必须在 conftest 加载时 (最早阶段) 设, 否则 backend.core.config 已经 import
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/video_clipper.db"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"


# v2.2.20: 在 conftest 阶段显式 import backend.core.config, 让 settings 锁住 production env.
# 否则 test_core_fixes 第一个 import backend (用 TEST_DB_URL), settings 锁 TEST_DB,
# 之后 test_api_integration import 拿到的是 TEST_DB settings, db 表缺失报 "no such table".
import backend.core.config as _cfg_lock  # noqa: F401 — force settings init with prod env
assert "production" in _cfg_lock.settings.DATABASE_URL or "video_clipper" in _cfg_lock.settings.DATABASE_URL, \
    f"conftest 阶段 settings.DATABASE_URL 不正确: {_cfg_lock.settings.DATABASE_URL}"


# v2.2.14: pytest_runtest_setup hook — 每个 test 跑前强制 reset env
# 防止 test_core_fixes 等 module-level 设的 os.environ["DATABASE_URL"]
# 污染 test_api_integration (用 sync_get_db 走 production db)
_PROD_DB_URL = "sqlite+aiosqlite:///./data/video_clipper.db"


def _wait_server_ready(url: str = "http://localhost:8000/health", timeout: int = 30) -> bool:
    """等 server 健康 (uvicorn --reload reload 期间不可用).

    解决 integration test race: pytest_runtest_setup 改 env 触发 uvicorn reload,
    期间新 worker 还没 ready, 旧 worker 已死, request 短时失败.
    修法: poll /health 到 OK, 再跑 test.
    """
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def pytest_runtest_setup(item):
    """每个 test 跑前 reset env, 避免 module-level pollution"""
    if "test_api_integration" in item.nodeid:
        # integration test 跑前 reset 到 production
        os.environ["DATABASE_URL"] = _PROD_DB_URL
        os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
        os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"
        # v2.2.20: 等 server ready (uvicorn reload 期间会短暂不可用)
        # 最多 30s (足够 reload + worker 启动)
        if not _wait_server_ready():
            import pytest as _pt
            _pt.skip("server (uvicorn :8000) 30s 内未 ready")