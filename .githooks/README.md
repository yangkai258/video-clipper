# Git hooks (v2.2.18+)

`core.hooksPath` = `.githooks/`. **3 道关防回归**, 任何 commit 必须通过:

| 关 | 检查 | 范围 | 耗时 |
|---|---|---|---|
| 1 | `ruff check` | 改动的 `backend/**/*.py` | ~3s |
| 2 | `pytest -k` (核心 ~30) | 改动的 backend/test | ~10s |
| 3 | `vitest run` | 改动的 `frontend/**/*.{js,jsx}` | ~3s |

**装** (新机器 / clone 后):
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

**跳关** (紧急 release 不推荐):
```bash
git commit --no-verify -m "..."
```

**为什么这样做**:
- ramply 之前 v2.2.x 多次 commit 测试 fail, 7/17 worker 崩 7 天没 auto restart, 跟"commit 没把关"正相关
- 3 关 0 误伤: pytest 走 `-k` 核心 subset (不全跑, ~10s), vitest 6 tests (~3s), ruff ~3s
- 改动不涉及对应语言就 warn 跳过 (例: 纯 docs 改动 → 3 关都跳过, 0 延迟)
