"""pytest 全局配置"""
import sys
import os
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


# v2.2.14: pytest_runtest_setup hook — 每个 test 跑前强制 reset env
# 防止 test_core_fixes 等 module-level 设的 os.environ["DATABASE_URL"]
# 污染 test_api_integration (用 sync_get_db 走 production db)
_PROD_DB_URL = "sqlite+aiosqlite:///./data/video_clipper.db"


def pytest_runtest_setup(item):
    """每个 test 跑前 reset env, 避免 module-level pollution"""
    if "test_api_integration" in item.nodeid:
        # integration test 跑前 reset 到 production
        os.environ["DATABASE_URL"] = _PROD_DB_URL
        os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
        os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"