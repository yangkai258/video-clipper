#!/usr/bin/env python
"""Secrets 加密工具 (v2.2.22)

加密 .env 提交到 git (团队共享), master key 通过 ENV_MASTER_KEY env 加载
(从 1Password CLI / macOS Keychain / GitHub Actions secret / Docker secret).

用法:
    # 1. 首次生成 master key (保存到 1Password / Keychain, 不提交)
    .venv/bin/python scripts/secrets.py generate-key

    # 2. 加密 .env → data/.env.encrypted (提交)
    ENV_MASTER_KEY=<key> .venv/bin/python scripts/secrets.py encrypt

    # 3. 团队成员 decrypt (CI / 部署)
    ENV_MASTER_KEY=<key> .venv/bin/python scripts/secrets.py decrypt

加密算法: Fernet (AES-128-CBC + HMAC-SHA256), cryptography 库
文件位置:
    输入:  .env (本地, 不提交)
    输出:  data/.env.encrypted (提交, encrypted)
    key:   ENV_MASTER_KEY env (从 1Password/keychain 取, 不提交)
"""
import argparse
import os
import sys
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"
ENCRYPTED_FILE = ROOT / "data" / ".env.encrypted"


def generate_key() -> str:
    """生成新的 master key (Fernet 32-byte url-safe base64)."""
    return Fernet.generate_key().decode()


def encrypt(plaintext: str, key: str) -> str:
    """加密 → 返 base64 string."""
    f = Fernet(key.encode())
    return f.encrypt(plaintext.encode()).decode()


def decrypt(token: str, key: str) -> str:
    """解密 → 返明文."""
    f = Fernet(key.encode())
    return f.decrypt(token.encode()).decode()


def cmd_generate_key(args) -> int:
    key = generate_key()
    print("✅ 新的 master key (复制保存到 1Password / Keychain, 不提交!):")
    print()
    print(f"  {key}")
    print()
    print("用法:")
    print(f"  export ENV_MASTER_KEY='{key}'")
    print()
    print("⚠️  不要 commit 这个 key, 丢了就没法 decrypt .env.encrypted")
    return 0


def cmd_encrypt(args) -> int:
    key = os.environ.get("ENV_MASTER_KEY")
    if not key:
        print("❌ 缺 ENV_MASTER_KEY env var", file=sys.stderr)
        print("   1. 先生成:  python scripts/secrets.py generate-key", file=sys.stderr)
        print("   2. 存到 1Password / macOS Keychain", file=sys.stderr)
        print("   3. export ENV_MASTER_KEY=...", file=sys.stderr)
        return 1
    if not ENV_FILE.exists():
        print(f"❌ {ENV_FILE} 不存在", file=sys.stderr)
        return 1

    plaintext = ENV_FILE.read_text(encoding="utf-8")
    token = encrypt(plaintext, key)

    # 加 metadata header (说明加密时间 + 算法)
    from datetime import datetime, timezone
    header = f"# video-clipper encrypted secrets\n# algorithm: fernet (AES-128-CBC + HMAC-SHA256)\n# created: {datetime.now(timezone.utc).isoformat()}\n"
    ENCRYPTED_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENCRYPTED_FILE.write_text(header + token, encoding="utf-8")

    print(f"✅ 加密完成 → {ENCRYPTED_FILE.relative_to(ROOT)} ({len(plaintext)} chars → {len(token)} chars)")
    print(f"   提交:  git add {ENCRYPTED_FILE.relative_to(ROOT)}")
    return 0


def cmd_decrypt(args) -> int:
    key = os.environ.get("ENV_MASTER_KEY")
    if not key:
        print("❌ 缺 ENV_MASTER_KEY env var", file=sys.stderr)
        return 1
    if not ENCRYPTED_FILE.exists():
        print(f"❌ {ENCRYPTED_FILE} 不存在", file=sys.stderr)
        return 1

    content = ENCRYPTED_FILE.read_text(encoding="utf-8")
    # 跳过 metadata header
    lines = content.splitlines()
    token_lines = [l for l in lines if not l.startswith("#")]
    token = "\n".join(token_lines).strip()
    if not token:
        print(f"❌ {ENCRYPTED_FILE} 空", file=sys.stderr)
        return 1

    try:
        plaintext = decrypt(token, key)
    except InvalidToken:
        print("❌ ENV_MASTER_KEY 错 (无法 decrypt)", file=sys.stderr)
        return 1

    output = Path(args.output) if args.output else ENV_FILE
    output.write_text(plaintext, encoding="utf-8")
    print(f"✅ 解密完成 → {output}")
    return 0


def cmd_verify(args) -> int:
    """验证 key 能 decrypt 现有 encrypted 文件 (不写 .env)."""
    key = os.environ.get("ENV_MASTER_KEY")
    if not key:
        print("❌ 缺 ENV_MASTER_KEY env var", file=sys.stderr)
        return 1
    if not ENCRYPTED_FILE.exists():
        print(f"❌ {ENCRYPTED_FILE} 不存在", file=sys.stderr)
        return 1
    content = ENCRYPTED_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()
    token_lines = [l for l in lines if not l.startswith("#")]
    token = "\n".join(token_lines).strip()
    try:
        plaintext = decrypt(token, key)
    except InvalidToken:
        print("❌ ENV_MASTER_KEY 错")
        return 1
    # 数行
    line_count = len(plaintext.splitlines())
    print(f"✅ key 正确, 可 decrypt ({line_count} 行 secrets)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=".env 加密/解密 (Fernet AES)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("generate-key", help="生成新 master key").set_defaults(func=cmd_generate_key)
    sub.add_parser("encrypt", help="加密 .env → data/.env.encrypted").set_defaults(func=cmd_encrypt)
    sp_dec = sub.add_parser("decrypt", help="解密 data/.env.encrypted → .env")
    sp_dec.add_argument("-o", "--output", help="输出路径 (默认 .env)")
    sp_dec.set_defaults(func=cmd_decrypt)
    sub.add_parser("verify", help="验证 key 可 decrypt").set_defaults(func=cmd_verify)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
