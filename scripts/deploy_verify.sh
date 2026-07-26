#!/usr/bin/env bash
# v2.2.51: 一键 hybrid deploy 健康检查脚本
#
# 检查项:
#  1. 期望进程数 (3 release worker + 3 beta worker + 1 mix release + 1 mix beta + 2 uvicorn)
#  2. uvicorn 8000/8030 port listen + health 端点
#  3. Vite 3000/3030 port listen
#  4. Redis db 0/1 connectivity
#  5. Release/beta sqlite db 存在 + 表数
#  6. git tag 跟 APP_VERSION 一致 (跟 pre-commit 关 4 同款)
#  7. ruff + eslint 0 error
#  8. pytest + vitest 全过
#
# 退出码: 0=全过, 1=有 fail
#
# 用: bash scripts/deploy_verify.sh

set -uo pipefail

WORKSPACE="/Users/zhuobao/.openclaw-rescue4/workspace/video-clipper"
LOG="/tmp/video-clipper-deploy-verify.log"

# 颜色
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; NC=''
fi

pass=0
fail=0
warn=0

p() { echo -e "${GREEN}✓ $1${NC}"; pass=$((pass+1)); }
f() { echo -e "${RED}✗ $1${NC}"; fail=$((fail+1)); }
w() { echo -e "${YELLOW}⚠ $1${NC}"; warn=$((warn+1)); }
h() { echo -e "\n${CYAN}── $1 ──${NC}"; }

cd "$WORKSPACE" || exit 1

# ─────────────────────── 1. 期望进程数 ───────────────────────
h "1/8 进程数"

# release worker (3 个, -Q processing)
release_w=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk '$18 == "processing" {print $2}' | wc -l | tr -d ' ')
if [ "$release_w" -eq 3 ]; then p "release worker: 3/3"; else f "release worker: $release_w/3 (期望 3)"; fi

# beta worker (3 个, -Q processing_beta)
beta_w=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk '$18 == "processing_beta" {print $2}' | wc -l | tr -d ' ')
if [ "$beta_w" -eq 3 ]; then p "beta worker: 3/3"; else f "beta worker: $beta_w/3 (期望 3)"; fi

# mix worker (1 release + 1 beta, v2.2.37 启 2 个)
mix_w=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk '$18 == "processing_mix" {print $2}' | wc -l | tr -d ' ')
if [ "$mix_w" -eq 1 ]; then p "mix release worker: 1/1"; else f "mix release worker: $mix_w/1 (期望 1)"; fi

mix_beta_w=$(ps aux | grep "celery -A backend.core.celery_app worker" | grep -v grep | awk '$18 == "processing_mix_beta" {print $2}' | wc -l | tr -d ' ')
if [ "$mix_beta_w" -eq 1 ]; then p "mix beta worker: 1/1"; else f "mix beta worker: $mix_beta_w/1 (期望 1)"; fi

# uvicorn 8000 + 8030
uv_8000=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' ')
if [ "$uv_8000" -ge 1 ]; then p "uvicorn :8000 listen"; else f "uvicorn :8000 没 listen"; fi

uv_8030=$(lsof -nP -iTCP:8030 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' ')
if [ "$uv_8030" -ge 1 ]; then p "uvicorn :8030 listen"; else f "uvicorn :8030 没 listen"; fi

# ─────────────────────── 2. health 端点 ───────────────────────
h "2/8 health 端点"

r8000=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8000/health || echo "fail")
if [ "$r8000" = "200" ]; then p "release :8000 health 200"; else f "release :8000 health $r8000"; fi

r8030=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:8030/health || echo "fail")
if [ "$r8030" = "200" ]; then p "beta :8030 health 200"; else f "beta :8030 health $r8030"; fi

# ─────────────────────── 3. Vite 端口 ───────────────────────
h "3/8 Vite 端口"

v3000=$(lsof -nP -iTCP:3000 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' ')
if [ "$v3000" -ge 1 ]; then p "vite :3000 listen (release 前端)"; else f "vite :3000 没 listen"; fi

v3030=$(lsof -nP -iTCP:3030 -sTCP:LISTEN 2>/dev/null | wc -l | tr -d ' ')
if [ "$v3030" -ge 1 ]; then p "vite :3030 listen (beta 前端)"; else f "vite :3030 没 listen"; fi

# ─────────────────────── 4. Redis db 0/1 ───────────────────────
h "4/8 Redis db"

if command -v redis-cli >/dev/null 2>&1; then
    # db 0 (release) - 期望有 processing / processing_mix queue
    r0_keys=$(redis-cli -n 0 DBSIZE 2>/dev/null)
    if [ -n "$r0_keys" ] && [ "$r0_keys" -ge 0 ]; then p "redis db 0 (release) OK, $r0_keys keys"; else f "redis db 0 fail"; fi

    # db 1 (beta) - 期望有 processing_beta / processing_mix_beta queue
    r1_keys=$(redis-cli -n 1 DBSIZE 2>/dev/null)
    if [ -n "$r1_keys" ] && [ "$r1_keys" -ge 0 ]; then p "redis db 1 (beta) OK, $r1_keys keys"; else f "redis db 1 fail"; fi
else
    w "redis-cli 不在 PATH, skip redis check"
fi

# ─────────────────────── 5. SQLite db ───────────────────────
h "5/8 SQLite db"

if [ -f "data/video_clipper.db" ]; then
    p "release db exists: data/video_clipper.db"
    t_count=$(sqlite3 data/video_clipper.db "SELECT count(*) FROM sqlite_master WHERE type='table'" 2>/dev/null)
    if [ -n "$t_count" ] && [ "$t_count" -ge 10 ]; then p "release db $t_count tables"; else w "release db tables $t_count (期望 ≥10)"; fi
else
    f "release db 不存在"
fi

if [ -f "data/video_clipper_beta.db" ]; then
    p "beta db exists: data/video_clipper_beta.db"
    t_count=$(sqlite3 data/video_clipper_beta.db "SELECT count(*) FROM sqlite_master WHERE type='table'" 2>/dev/null)
    if [ -n "$t_count" ] && [ "$t_count" -ge 10 ]; then p "beta db $t_count tables"; else w "beta db tables $t_count (期望 ≥10)"; fi
else
    f "beta db 不存在"
fi

# ─────────────────────── 6. APP_VERSION 跟 git tag 一致 ───────────────────────
h "6/8 APP_VERSION drift"

if [ -f "backend/core/config.py" ]; then
    APP_VER=$(grep -E '^    APP_VERSION: str' backend/core/config.py | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
    LATEST_TAG=$(git tag --sort=-v:refname | head -1)
    if [ -n "$APP_VER" ] && [ -n "$LATEST_TAG" ]; then
        if [ "$APP_VER" = "$LATEST_TAG" ]; then
            p "APP_VERSION ($APP_VER) 跟 tag ($LATEST_TAG) 一致"
        else
            CUR_NUM=$(echo "$APP_VER" | sed 's/^v//' | awk -F. '{printf "%d%02d%02d", $1, $2, $3}')
            TAG_NUM=$(echo "$LATEST_TAG" | sed 's/^v//' | awk -F. '{printf "%d%02d%02d", $1, $2, $3}')
            if [ "$CUR_NUM" -lt "$TAG_NUM" ]; then
                f "APP_VERSION ($APP_VER) 落后 tag ($LATEST_TAG)"
            else
                w "APP_VERSION ($APP_VER) > tag ($LATEST_TAG) — commit 后记得 push tag"
            fi
        fi
    else
        w "无法读 APP_VERSION 或 git tag"
    fi
fi

# ─────────────────────── 7. lint (ruff + eslint) 0 error ───────────────────────
h "7/8 lint (ruff + eslint 0 error)"

if [ -x ".venv/bin/ruff" ]; then
    RUFF_ERR=$(.venv/bin/ruff check backend/ 2>&1 | tail -1 | grep -oE '[0-9]+ error' | grep -oE '[0-9]+' || echo "0")
    if [ "${RUFF_ERR:-0}" -eq 0 ]; then
        p "ruff: 0 error"
    else
        f "ruff: $RUFF_ERR errors (跑 'ruff check backend/' 看 detail)"
    fi
else
    w ".venv/bin/ruff 不在, skip"
fi

if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    ESLINT_ERR=$(npx eslint src 2>&1 | grep -c "^\s*[0-9]\+:[0-9]\+\s*error" 2>/dev/null | tr -d ' \n' | head -c 3)
    ESLINT_ERR=${ESLINT_ERR:-0}
    if [ "$ESLINT_ERR" = "0" ]; then
        p "eslint: 0 error"
    else
        f "eslint: $ESLINT_ERR errors"
    fi
    cd ..
fi

# ─────────────────────── 8. test 全过 ───────────────────────
h "8/8 test (pytest + vitest)"

if [ -x ".venv/bin/python" ]; then
    PYTEST_RESULT=$(.venv/bin/python -m pytest tests/ -q -m "not e2e" 2>&1 | tail -1 | grep -oE '[0-9]+ passed|[0-9]+ failed' | head -1)
    if [[ "$PYTEST_RESULT" == *"passed"* ]] && [[ "$PYTEST_RESULT" != *"failed"* ]]; then
        p "pytest: $PYTEST_RESULT"
    else
        f "pytest: $PYTEST_RESULT"
    fi
fi

if [ -d "frontend" ]; then
    cd frontend
    VITEST_RESULT=$(npx vitest run 2>&1 | grep "Tests" | head -1 | grep -oE '[0-9]+ passed')
    if [ -n "$VITEST_RESULT" ]; then
        p "vitest: $VITEST_RESULT"
    else
        f "vitest: no pass count"
    fi
    cd ..
fi

# ─────────────────────── 总结 ───────────────────────
echo ""
h "总结"
echo -e "  ${GREEN}pass=$pass${NC}  ${YELLOW}warn=$warn${NC}  ${RED}fail=$fail${NC}"
echo ""

if [ "$fail" -eq 0 ]; then
    echo -e "${GREEN}✅ hybrid deploy 验证全过${NC}"
    exit 0
else
    echo -e "${RED}❌ hybrid deploy 有 $fail 项 fail, 查 log 修${NC}"
    echo "log: $LOG"
    exit 1
fi
