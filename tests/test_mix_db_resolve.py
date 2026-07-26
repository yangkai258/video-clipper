"""Mix db 一致性 test (v2.2.25)

测 _resolve_mix_db_path 永远返 release mix db (跨 release/beta 模式).

修 ramply 7-26 beta 模式混剪 task FAILURE 根因:
之前 _resolve_mix_db_path 按 DATABASE_URL 派生 (release → release mix db,
beta → beta mix db), 但 mix worker 永远跑在 release env (DATABASE_URL=
video_clipper.db), 派生 release mix db, 查不到 beta uvicorn 写到 _beta
mix db 的 project → RuntimeError → FAILURE.
"""

from backend.core.database_mix import _resolve_mix_db_path


def test_resolve_release_env():
    """release env → release mix db (跟之前一致)"""
    from backend.core import config as cfg
    real_db = cfg.settings.DATABASE_URL
    try:
        cfg.settings.DATABASE_URL = "sqlite+aiosqlite:///./data/video_clipper.db"
        path = _resolve_mix_db_path()
        assert "video_clipper_mix.db" in path
        assert "_beta" not in path
    finally:
        cfg.settings.DATABASE_URL = real_db


def test_resolve_beta_env_still_release_mix_db():
    """beta env → 仍 release mix db (v2.2.25 fix: 永远 release)"""
    from backend.core import config as cfg
    real_db = cfg.settings.DATABASE_URL
    try:
        cfg.settings.DATABASE_URL = "sqlite+aiosqlite:///./data/video_clipper_beta.db"
        path = _resolve_mix_db_path()
        # v2.2.25: 不再派生 _beta, 永远 release
        assert "video_clipper_mix.db" in path
        assert "_beta" not in path, f"v2.2.25 应不分 _beta, got {path}"
    finally:
        cfg.settings.DATABASE_URL = real_db


def test_resolve_independent_of_settings():
    """_resolve_mix_db_path 不读 settings.DATABASE_URL, 用 BASE_DIR/data/"""
    from backend.core import config as cfg
    from backend.core.database_mix import _resolve_mix_db_path

    real_db = cfg.settings.DATABASE_URL
    try:
        # 设各种奇怪的 DATABASE_URL, 都不影响派生
        for weird_url in [
            "sqlite+aiosqlite:///./random/path/whatever.db",
            "sqlite+aiosqlite:///./data/some_other_db.db",
            "postgresql://user:pass@host/db",
        ]:
            cfg.settings.DATABASE_URL = weird_url
            path = _resolve_mix_db_path()
            assert path.endswith("video_clipper_mix.db"), f"应总是 video_clipper_mix.db, got {path}"
    finally:
        cfg.settings.DATABASE_URL = real_db


def test_resolve_uses_base_dir():
    """_resolve_mix_db_path 用 settings.BASE_DIR 拼 data/video_clipper_mix.db"""
    from backend.core.config import settings
    from backend.core.database_mix import _resolve_mix_db_path

    path = _resolve_mix_db_path()
    expected = f"sqlite+aiosqlite:///{settings.BASE_DIR}/data/video_clipper_mix.db"
    assert path == expected


def test_no_beta_db_creation_on_dispatch(monkeypatch):
    """dispatch_mix_task 触发 database_mix 模块加载, _resolve_mix_db_path 走 release

    防止 future regression: 任何人改回 _beta 派生就 fail.
    """
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./data/video_clipper_beta.db")

    from backend.core.database_mix import _resolve_mix_db_path
    path = _resolve_mix_db_path()

    # v2.2.25 永远 release, 没 _beta 后缀
    assert "_beta" not in path, f"v2.2.25 应不分 _beta, got {path}"
    assert "video_clipper_mix.db" in path
