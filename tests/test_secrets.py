"""Secrets 加密工具 test (v2.2.22)

测 Fernet encrypt/decrypt 往返 + scripts/secrets.py CLI 命令.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# 必须在 backend.* import 前设 env, 防止 conftest 阶段 import backend.core.config
# 触发 _load_encrypted_secrets() 跟 production .env 冲突
os.environ["ENV_MASTER_KEY"] = ""  # test 期间强制 disable decrypt

from cryptography.fernet import Fernet, InvalidToken

from scripts.secrets import (
    decrypt,
    encrypt,
    generate_key,
)

# === 单元测试: encrypt/decrypt ===

def test_generate_key_format():
    """generate_key 返 Fernet-valid 44 字符 url-safe base64"""
    key = generate_key()
    # Fernet key 是 32-byte url-safe-base64 (44 chars)
    assert len(key) == 44
    # 验证 Fernet 能用它
    f = Fernet(key.encode())
    assert f is not None


def test_encrypt_decrypt_roundtrip():
    """encrypt + decrypt 返原值"""
    key = generate_key()
    plaintext = "MINIMAX_API_KEY=secret-123\nDEBUG=True\n"
    token = encrypt(plaintext, key)
    assert plaintext != token
    # decrypt 拿回 plaintext
    assert decrypt(token, key) == plaintext


def test_encrypt_decrypt_unicode():
    """中文内容 + emoji 正确加解密"""
    key = generate_key()
    plaintext = "# 备注: 屋面防水工程 🔧\nMINIMAX_API_KEY=中文+emoji 测试\n"
    token = encrypt(plaintext, key)
    assert decrypt(token, key) == plaintext


def test_decrypt_wrong_key_fails():
    """错 key 抛 InvalidToken"""
    key1 = generate_key()
    key2 = generate_key()
    token = encrypt("secret", key1)
    with pytest.raises(InvalidToken):
        decrypt(token, key2)


def test_encrypt_fernet_token_format():
    """Fernet token = 4 段 base64 (Version|TS|IV|CT+HMAC), 总长 200+"""
    key = generate_key()
    token = encrypt("test", key)
    # 1.0!Version(1) + 8B TS + 16B IV + ~20B+CT + 32B HMAC
    # 估算: 4 段 base64 各 ~24 chars ≈ 100 chars (4B 头 + 8B TS + 16B IV + N BCT + 32B HMAC)
    assert len(token) >= 100
    # Fernet token 是 1 段 base64url (不像 JWT 有点分隔)
    assert "." not in token
    # 必须 url-safe base64 字符
    import re as _re
    assert _re.match(r"^[A-Za-z0-9_\-]+=*$", token)


# === CLI 集成测试 ===

SECRETS_PY = Path(__file__).parent.parent / "scripts" / "secrets.py"


def _run_cli(*args, env_master_key: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """跑 scripts/secrets.py 子进程."""
    env = os.environ.copy()
    if env_master_key is not None:
        env["ENV_MASTER_KEY"] = env_master_key
    elif "ENV_MASTER_KEY" in env:
        del env["ENV_MASTER_KEY"]
    return subprocess.run(
        [sys.executable, str(SECRETS_PY), *args],
        capture_output=True, text=True, env=env,
        cwd=cwd or Path(__file__).parent.parent,
        timeout=30, check=False,
    )


def test_cli_generate_key():
    """generate-key 返 44 字符 key"""
    r = _run_cli("generate-key")
    assert r.returncode == 0
    # stdout 含 key (44 chars), 提取最后那个 line 长度 44
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip() and not l.startswith(("✅", "用法", "⚠️", "1.", "2.", "3."))]
    key = next((l for l in lines if len(l) == 44 and l.endswith("=")), None)
    assert key is not None, f"key not found in output: {r.stdout!r}"


def test_cli_encrypt_decrypt_roundtrip(tmp_path, monkeypatch):
    """encrypt 写 encrypted, decrypt 还原 .env"""
    # 准备 .env + 隔离目录
    env_file = tmp_path / ".env"
    env_file.write_text("MINIMAX_API_KEY=test-secret-123\nDEBUG=True\n", encoding="utf-8")

    # monkeypatch ROOT 路径 (scripts/secrets.py 用 ROOT = file parent.parent)
    # 简化: 直接用真实 ROOT, 备份 .env, 跑 CLI, 还原
    real_root = Path(__file__).parent.parent
    real_env = real_root / ".env"
    real_encrypted = real_root / "data" / ".env.encrypted"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None

    try:
        # 写测试 .env
        real_env.write_text(env_file.read_text(), encoding="utf-8")

        key = generate_key()

        # encrypt
        r = _run_cli("encrypt", env_master_key=key)
        assert r.returncode == 0, f"encrypt fail: {r.stderr}"
        assert real_encrypted.exists(), "encrypted file not created"
        encrypted_content = real_encrypted.read_text()
        # 不应该含明文 secret
        assert "test-secret-123" not in encrypted_content
        # 应该含 header
        assert "fernet" in encrypted_content.lower() or "encrypted" in encrypted_content.lower()

        # delete .env 模拟 production 没明文
        real_env.unlink()

        # decrypt
        r = _run_cli("decrypt", env_master_key=key)
        assert r.returncode == 0, f"decrypt fail: {r.stderr}"
        assert real_env.exists()
        assert real_env.read_text() == env_file.read_text()

    finally:
        # 还原
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        if real_encrypted.exists():
            real_encrypted.unlink()


def test_cli_encrypt_no_key_fails():
    """没 ENV_MASTER_KEY → encrypt 退出 1"""
    r = _run_cli("encrypt", env_master_key="")
    assert r.returncode == 1
    assert "ENV_MASTER_KEY" in r.stderr


def test_cli_decrypt_wrong_key_fails(tmp_path):
    """错 key decrypt → 退出 1 + 报错"""
    real_root = Path(__file__).parent.parent
    real_env = real_root / ".env"
    real_encrypted = real_root / "data" / ".env.encrypted"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    try:
        # 准备: encrypt 1 个
        real_env.write_text("MINIMAX_API_KEY=test\n", encoding="utf-8")
        key = generate_key()
        r = _run_cli("encrypt", env_master_key=key)
        assert r.returncode == 0

        # 删 .env
        real_env.unlink()

        # 错 key decrypt
        wrong_key = generate_key()
        r = _run_cli("decrypt", env_master_key=wrong_key)
        assert r.returncode == 1
        assert "InvalidToken" in r.stderr or "无法 decrypt" in r.stderr or "错" in r.stderr

    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        if real_encrypted.exists():
            real_encrypted.unlink()


def test_cli_verify_correct_key(tmp_path):
    """verify 用对 key 返 0 + 显示行数"""
    real_root = Path(__file__).parent.parent
    real_env = real_root / ".env"
    real_encrypted = real_root / "data" / ".env.encrypted"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    try:
        real_env.write_text("MINIMAX_API_KEY=a\nDEBUG=True\nMAX_UPLOAD_SIZE=5368709120\n", encoding="utf-8")
        key = generate_key()
        r = _run_cli("encrypt", env_master_key=key)
        assert r.returncode == 0
        real_env.unlink()

        r = _run_cli("verify", env_master_key=key)
        assert r.returncode == 0
        assert "key 正确" in r.stdout or "可 decrypt" in r.stdout
        assert "3 行" in r.stdout
    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        if real_encrypted.exists():
            real_encrypted.unlink()


# === config.py 集成 ===

def test_config_loads_encrypted_when_no_plaintext(tmp_path, monkeypatch):
    """config.py: encrypted 存在 + 没明文 .env + 有 key → 自动 decrypt"""
    # 隔离环境: 把 ROOT 指 tmp_path (复杂, 简化)
    # 实际只测 _load_encrypted_secrets() 的 unit logic
    # 因为改 ROOT 涉及 sys.path
    from backend.core import config as cfg

    # mock 路径
    real_encrypted = cfg.settings.DATA_DIR / ".env.encrypted"
    real_env = Path(cfg.settings.BASE_DIR) / ".env"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    had_encrypted = real_encrypted.exists()

    try:
        # 准备 encrypted
        key = generate_key()
        token = encrypt("MINIMAX_API_KEY=auto-decrypted\n", key)
        real_encrypted.parent.mkdir(parents=True, exist_ok=True)
        real_encrypted.write_text(f"# header\n{token}", encoding="utf-8")

        # 删 .env
        if real_env.exists():
            real_env.unlink()

        # 设 key, 调 _load_encrypted_secrets
        monkeypatch.setenv("ENV_MASTER_KEY", key)
        cfg._load_encrypted_secrets()

        # .env 应该被创建
        assert real_env.exists()
        content = real_env.read_text()
        assert "auto-decrypted" in content
    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        else:
            if real_env.exists():
                real_env.unlink()
        if not had_encrypted and real_encrypted.exists():
            real_encrypted.unlink()


def test_config_skips_when_plaintext_exists(tmp_path, monkeypatch):
    """config.py: 明文 .env 已存在 → 不动 (本地 dev 优先)"""
    from backend.core import config as cfg
    real_encrypted = cfg.settings.DATA_DIR / ".env.encrypted"
    real_env = Path(cfg.settings.BASE_DIR) / ".env"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    had_encrypted = real_encrypted.exists()

    try:
        # 准备 encrypted
        key = generate_key()
        token = encrypt("MINIMAX_API_KEY=should-not-overwrite\n", key)
        real_encrypted.parent.mkdir(parents=True, exist_ok=True)
        real_encrypted.write_text(f"# header\n{token}", encoding="utf-8")

        # 写明文 .env (本地 dev)
        real_env.write_text("MINIMAX_API_KEY=local-dev-key\n", encoding="utf-8")
        before = real_env.read_text()

        monkeypatch.setenv("ENV_MASTER_KEY", key)
        cfg._load_encrypted_secrets()

        # .env 不变
        assert real_env.read_text() == before
    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        else:
            if real_env.exists():
                real_env.unlink()
        if not had_encrypted and real_encrypted.exists():
            real_encrypted.unlink()


def test_config_skips_when_no_master_key(monkeypatch):
    """config.py: 没 ENV_MASTER_KEY → 警告跳过 (本地 dev 模式)"""
    from backend.core import config as cfg
    real_encrypted = cfg.settings.DATA_DIR / ".env.encrypted"
    real_env = Path(cfg.settings.BASE_DIR) / ".env"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    had_encrypted = real_encrypted.exists()

    try:
        key = generate_key()
        token = encrypt("MINIMAX_API_KEY=test\n", key)
        real_encrypted.parent.mkdir(parents=True, exist_ok=True)
        real_encrypted.write_text(f"# header\n{token}", encoding="utf-8")

        if real_env.exists():
            real_env.unlink()

        monkeypatch.delenv("ENV_MASTER_KEY", raising=False)
        # 不应该抛
        cfg._load_encrypted_secrets()
        # .env 不应该被创建
        assert not real_env.exists()
    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        else:
            if real_env.exists():
                real_env.unlink()
        if not had_encrypted and real_encrypted.exists():
            real_encrypted.unlink()


def test_config_wrong_key_logs_error(monkeypatch, caplog):
    """config.py: 错 key → logger.error, .env 不创建"""
    import logging

    from backend.core import config as cfg
    real_encrypted = cfg.settings.DATA_DIR / ".env.encrypted"
    real_env = Path(cfg.settings.BASE_DIR) / ".env"
    backup_env = real_env.read_text(encoding="utf-8") if real_env.exists() else None
    had_encrypted = real_encrypted.exists()

    try:
        real_key = generate_key()
        token = encrypt("MINIMAX_API_KEY=test\n", real_key)
        real_encrypted.parent.mkdir(parents=True, exist_ok=True)
        real_encrypted.write_text(f"# header\n{token}", encoding="utf-8")
        if real_env.exists():
            real_env.unlink()

        wrong_key = generate_key()
        monkeypatch.setenv("ENV_MASTER_KEY", wrong_key)
        with caplog.at_level(logging.ERROR, logger="backend.core.config"):
            cfg._load_encrypted_secrets()
        # 不抛, .env 不创建, error log
        assert not real_env.exists()
        # logger.error 至少 1 条
        assert any("ENV_MASTER_KEY 错" in r.message or "解密" in r.message for r in caplog.records)
    finally:
        if backup_env is not None:
            real_env.write_text(backup_env, encoding="utf-8")
        else:
            if real_env.exists():
                real_env.unlink()
        if not had_encrypted and real_encrypted.exists():
            real_encrypted.unlink()
