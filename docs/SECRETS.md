# Secrets 管理 (v2.2.22)

团队接手时, 怎么安全地共享 LLM API key / DB 密码等敏感配置.

## TL;DR

```bash
# 1. 一人生成 master key, 存到 1Password / Keychain
python scripts/secrets.py generate-key

# 2. 加密 .env → 提交 data/.env.encrypted
ENV_MASTER_KEY=<key> python scripts/secrets.py encrypt
git add data/.env.encrypted && git commit -m "..."

# 3. 团队成员 / CI 拿 key decrypt
ENV_MASTER_KEY=<key> python scripts/secrets.py decrypt
# 启动 uvicorn 时也会自动 decrypt (config.py 集成)
```

---

## 原理

| 文件 | 状态 | 内容 |
|---|---|---|
| `.env` | 本地, **不提交** (.gitignore) | 明文 LLM key / DB url 等 |
| `data/.env.encrypted` | **提交** (团队共享) | Fernet 加密的 .env 副本 |
| `ENV_MASTER_KEY` env | **不提交**, 团队各自保管 | 32-byte url-safe base64, 用来加解密 |

**加密算法**: Fernet (AES-128-CBC + HMAC-SHA256) — `cryptography` 库标准实现, 不是自创.

**自动加载**: `backend/core/config.py` 启动时检测 `data/.env.encrypted`, 有 master key 时自动 decrypt 写 `.env` (本地 dev 模式不覆盖已有 .env).

---

## 首次设置 (ramply / 项目 owner)

### 1. 生成 master key

```bash
.venv/bin/python scripts/secrets.py generate-key
# 输出: 复制保存到 1Password / macOS Keychain
# 例: ENV_MASTER_KEY='gAAAAA...44chars...='
```

⚠️ **不要 commit 这个 key**, 丢了就没法 decrypt `.env.encrypted`.

### 2. 存到 1Password / macOS Keychain

**macOS Keychain** (推荐, 1 人本地开发):
```bash
security add-generic-password -a "$USER" -s "video-clipper-env-master-key" -w "<key>"
# 用时:
export ENV_MASTER_KEY=$(security find-generic-password -a "$USER" -s "video-clipper-env-master-key" -w)
```

**1Password CLI** (团队共享):
```bash
# 1Password 存 "Video Clipper / ENV_MASTER_KEY" 条目
export ENV_MASTER_KEY=$(op read "op://Private/Video Clipper/ENV_MASTER_KEY")
```

**GitHub Actions secret** (CI):
```
Settings → Secrets → New repository secret
Name: ENV_MASTER_KEY
Value: <paste>
```

### 3. 加密 .env

```bash
export ENV_MASTER_KEY=<key>
.venv/bin/python scripts/secrets.py encrypt
# 输出: 加密完成 → data/.env.encrypted (xxx chars → yyy chars)

git add data/.env.encrypted
git commit -m "chore(secrets) v2.2.22: 加密 .env → data/.env.encrypted"
git push
```

### 4. 验证

```bash
# 删本地 .env, 模拟 CI 启动
rm .env
ENV_MASTER_KEY=<key> python scripts/secrets.py verify
# 输出: ✅ key 正确, 可 decrypt (N 行 secrets)

# 启动 uvicorn 看 log
ENV_MASTER_KEY=<key> .venv/bin/uvicorn backend.main:app --reload
# log: "已从 data/.env.encrypted 解密 secrets → .env"
```

---

## 团队成员接手

### 拿到 master key

1. 找 ramply 拿 (他存 1Password / Keychain)
2. 配到本地 (上面 §2 三种方式任选)

### 解密 / 启动

```bash
git clone ...
cd video-clipper
.venv/bin/python -m pip install -r requirements.txt

export ENV_MASTER_KEY=<key>  # 或用 security / op 取

# 启动后端 (自动 decrypt + 写 .env)
.venv/bin/uvicorn backend.main:app --reload
```

或显式先 decrypt:
```bash
ENV_MASTER_KEY=<key> python scripts/secrets.py decrypt  # 写 .env
.venv/bin/uvicorn backend.main:app --reload
```

### 修改 secrets

```bash
# 1. 改 .env (现在 .env 已经 decrypt 出来)
vim .env

# 2. 重新加密
ENV_MASTER_KEY=<key> python scripts/secrets.py encrypt

# 3. 提交
git add data/.env.encrypted
git commit -m "chore(secrets) update XXX API key"
```

---

## CI / Docker 部署

```yaml
# GitHub Actions
- name: Decrypt secrets
  env:
    ENV_MASTER_KEY: ${{ secrets.ENV_MASTER_KEY }}
  run: |
    .venv/bin/python scripts/secrets.py decrypt
    # 之后跑 pytest / uvicorn 跟本地一样
```

```dockerfile
# Dockerfile
ENV ENV_MASTER_KEY=""  # 运行时 -e 注入
COPY scripts/secrets.py /app/scripts/
# entrypoint: ENV_MASTER_KEY=... python scripts/secrets.py verify || exit 1
```

```bash
# 启容器
docker run -e ENV_MASTER_KEY=$(op read "op://Private/Video Clipper/ENV_MASTER_KEY") video-clipper
```

---

## 没 master key 时

- 启动正常, logger warning: "data/.env.encrypted 存在但 ENV_MASTER_KEY 未设, 跳过解密"
- 走原 `.env` (本地 dev 用), 或 system env / Docker env (部署用)
- 不阻塞启动, **不会报 fatal**

适合场景:
- 本地 dev 阶段 (不需 decrypt, 已有 .env)
- 测试 / CI 用 system env 注入 key
- 排查问题临时跑

---

## 安全提示

1. **不要**把 `ENV_MASTER_KEY` 写进 .env, .sh, .yml, 任何文件
2. **不要** commit `data/.env.encrypted` 时打 `chmod 644`, 应 `chmod 600` (owner only)
3. **轮换** master key: 删 encrypted + generate 新 key + 重新 encrypt + 通知团队
4. **离职**交接: 把 1Password / Keychain 条目转给继任, 同时轮换 key
5. **审计**: `git log data/.env.encrypted` 看历史, 确认每个 commit 是预期 owner

---

## 故障排查

| 症状 | 原因 | 修法 |
|---|---|---|
| `data/.env.encrypted 不存在` | 还没 encrypt | 跑 `encrypt` 命令 |
| `InvalidToken` decrypt 失败 | master key 错 | 检查 1Password / Keychain |
| 解密后启动报 `API key invalid` | .env 改过没重新加密 | encrypt + 提交新版本 |
| uvicorn 启动慢 2-3s | decrypt 跑一次, 1ms 都不到, 不会慢 | 检查文件系统 |
| 想 disable 自动 decrypt | 设 `DISABLE_ENCRYPTED_SECRETS=1` | (v2.2.22+ 支持) |
