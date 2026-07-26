"""Watchdog broker 一致性 check test (v2.2.23)

测 scripts/check_workers.sh 的 worker_actual_broker / worker_actual_queue /
worker_broker_mismatch helper 函数. 不实际启 worker (慢, 依赖 redis),
直接 mock ps eww 输出.

关键: 不能 source 整个 watchdog (会跑主体, 启 worker 等), 只 source
到函数定义结束, 提前 return 0.
"""
import re
import subprocess
from pathlib import Path

import pytest

WATCHDOG = Path(__file__).parent.parent / "scripts" / "check_workers.sh"


def _extract_function_defs(until_marker: str) -> str:
    """从 watchdog 抽函数定义到指定 marker 行 (不跑主体).

    marker: 一个 stop marker (例 "log \"WARN" 表示抽到第一个 log 调用)
    """
    content = WATCHDOG.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    out = []
    for line in lines:
        if until_marker in line:
            break
        out.append(line)
    return "".join(out)


def _run_bash_helper(func_name: str, *args, fake_ps_output: str = "") -> tuple[int, str, str]:
    """跑 watchdog 的 bash helper 函数 (mock 外部命令).

    Returns: (helper return code 0/1, stdout, stderr)
    """
    # 抽函数定义到第一个 if [ "$release_count" (主体开始)
    func_defs = _extract_function_defs('if [ "$release_count"')

    fake_block = ""
    if fake_ps_output:
        # mock ps eww -p 命令 (helper 内部用)
        fake_block = f'ps() {{ echo "{fake_ps_output}"; }}\n'

    # 用 sentinel 把 helper return code 写出来 (避免末尾 echo 重置 $?)
    script = f"""
{fake_block}
{func_defs}
{func_name} {' '.join(repr(a) for a in args)}
rc=$?
echo "---RC=$rc---"
"""
    r = subprocess.run(
        ["bash", "-c", script],
        capture_output=True, text=True, timeout=10, check=False,
    )
    # 解析 ---RC=N--- 拿 helper return code
    rc = 0
    out_clean = r.stdout
    for line in r.stdout.splitlines():
        if line.startswith("---RC="):
            try:
                rc = int(line.replace("---RC=", "").replace("---", ""))
            except ValueError:
                pass
            # 移走 sentinel line
            out_clean = out_clean.replace(line, "").rstrip()
    return rc, out_clean, r.stderr


# === worker_actual_broker ===

def test_worker_actual_broker_ok():
    """正确读 ps eww 输出, 拿 CELERY_BROKER_URL"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/0 CELERY_QUEUE_NAME=processing_mix OTHER=foo"
    _, out, _ = _run_bash_helper("worker_actual_broker", "12345", fake_ps_output=fake)
    assert out == "redis://localhost:6379/0"


def test_worker_actual_broker_empty_pid():
    """空 PID 返空"""
    _, out, _ = _run_bash_helper("worker_actual_broker", "")
    assert out == ""


def test_worker_actual_broker_no_env_var():
    """ps 没 CELERY_BROKER_URL → 返空 (可能 process 死了或格式异常)"""
    fake = "PID USER ... OTHER_VAR=foo"
    _, out, _ = _run_bash_helper("worker_actual_broker", "12345", fake_ps_output=fake)
    assert out == ""


def test_worker_actual_broker_db1():
    """db=1 broker 也正确读"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/1"
    _, out, _ = _run_bash_helper("worker_actual_broker", "99999", fake_ps_output=fake)
    assert out == "redis://localhost:6379/1"


# === worker_actual_queue ===

def test_worker_actual_queue_ok():
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/0 CELERY_QUEUE_NAME=processing_mix"
    _, out, _ = _run_bash_helper("worker_actual_queue", "12345", fake_ps_output=fake)
    assert out == "processing_mix"


def test_worker_actual_queue_empty_pid():
    _, out, _ = _run_bash_helper("worker_actual_queue", "")
    assert out == ""


# === worker_broker_mismatch ===

def test_mismatch_returns_1_when_same():
    """broker + queue 一致 → return 1 (match)"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/0 CELERY_QUEUE_NAME=processing_mix"
    rc, _, _ = _run_bash_helper(
        "worker_broker_mismatch", "12345",
        "redis://localhost:6379/0", "processing_mix",
        fake_ps_output=fake,
    )
    assert rc == 1  # 1 = 一致 (if 返回的 fall-through)


def test_mismatch_returns_0_when_different_broker():
    """broker 不一致 → return 0 (mismatch)"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/1 CELERY_QUEUE_NAME=processing_mix"
    rc, _, _ = _run_bash_helper(
        "worker_broker_mismatch", "12345",
        "redis://localhost:6379/0", "processing_mix",
        fake_ps_output=fake,
    )
    # 0 = 不一致 (return 0 在 if 块内)
    assert rc == 0


def test_mismatch_returns_0_when_queue_differs():
    """queue 不一致 → return 0 (mismatch)"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/0 CELERY_QUEUE_NAME=processing_beta"
    rc, _, _ = _run_bash_helper(
        "worker_broker_mismatch", "12345",
        "redis://localhost:6379/0", "processing_mix",
        fake_ps_output=fake,
    )
    assert rc == 0


def test_mismatch_empty_pid_returns_0():
    """空 PID (没 env) → broker/queue 都空, 跟任何期望都不一致 → return 0"""
    rc, _, _ = _run_bash_helper(
        "worker_broker_mismatch", "",
        "redis://localhost:6379/0", "processing_mix",
    )
    assert rc == 0


def test_mismatch_db1_consistent():
    """db=1 一致 (beta 模式)"""
    fake = "PID USER ... CELERY_BROKER_URL=redis://localhost:6379/1 CELERY_QUEUE_NAME=processing_beta"
    rc, _, _ = _run_bash_helper(
        "worker_broker_mismatch", "12345",
        "redis://localhost:6379/1", "processing_beta",
        fake_ps_output=fake,
    )
    assert rc == 1


# === watchdog 端到端语法 ===

def test_watchdog_syntax():
    """watchdog bash 语法正确 (防止 v2.2.23 加 broker check 引入 syntax 错)"""
    r = subprocess.run(
        ["bash", "-n", str(WATCHDOG)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert r.returncode == 0, f"watchdog syntax err: {r.stderr}"


def test_watchdog_actual_run_tick():
    """watchdog 实际跑一次 (实际 worker 状态, 不 mock), 应返 "tick done" 行"""
    r = subprocess.run(
        ["bash", str(WATCHDOG)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert r.returncode == 0
    assert "tick done" in r.stdout
    # 应该有 worker count (13 进程 healthy 时 release=3 beta=3 mix=1)
    assert "release=" in r.stdout
    assert "mix=" in r.stdout
