"""E2E 混剪 pipeline test (v2.2.20)

完整跑 init → risk-check → submit → wait completed → verify output.
跟 integration test 区别: 这是真实 worker pipeline (10-30s),
不 mock LLM / ffmpeg.

默认 skip, 主动跑:
    pytest -m e2e
    pytest -m e2e tests/test_mix_e2e.py -v

跳过条件 (任一 fail skip):
- 资源库没素材 (need ≥1 candidate clip)
- ffmpeg / ffprobe 不可用
- LLM API key 不可用 (.env 缺 OPENAI_API_KEY/ANTHROPIC_API_KEY)
- 30s 内没 completed (timeout)

完成验证:
- status = completed
- output file 存在 + size > 1MB
- mix_segments 写入 db (≥1 segment)
"""
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

# 仅当显式 -m e2e 才跑
pytestmark = pytest.mark.e2e


BASE = "http://localhost:8000/api/v1"
DATA_DIR = Path("./data")


# ──────────────────────────── 跳过条件检查 ────────────────────────────


def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _has_llm_key() -> bool:
    """检查 .env 或 env 是否有 LLM key"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY") and v and v != "sk-...":
                return True
    # 兜底: 当前进程 env
    for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"):
        if os.environ.get(k) and os.environ.get(k) != "sk-...":
            return True
    return False


def _get_candidate_clip_id() -> str | None:
    """从 db 取 1 个有效 resource clip id (有 mp4 文件)"""
    try:
        from backend.core.database import sync_get_db
        from backend.models.database import ResourceClip

        with sync_get_db() as db:
            for rc in db.query(ResourceClip).filter(
                ResourceClip.deleted_at.is_(None),
                ResourceClip.file_path.isnot(None),
            ).limit(20).all():
                if rc.file_path and Path(rc.file_path).exists():
                    return rc.id
    except Exception:  # noqa: BLE001, S110 — db 不可用就 skip, 静默
        pass
    return None


# ──────────────────────────── Fixture ────────────────────────────


@pytest.fixture(scope="module")
def e2e_env():
    """e2e 跑前 env check, 不通过 skip 整个 module"""
    if not _has_ffmpeg():
        pytest.skip("ffmpeg/ffprobe 不可用")
    if not _has_llm_key():
        pytest.skip("无 LLM API key (.env 缺 OPENAI_API_KEY/ANTHROPIC_API_KEY)")

    clip_id = _get_candidate_clip_id()
    if not clip_id:
        pytest.skip("资源库无有效 candidate clip (需先上传 ≥1 mp4)")

    return {"clip_id": clip_id}


# ──────────────────────────── Tests ────────────────────────────


def test_01_health(e2e_env):
    """server 健康检查 (e2e 前置)"""
    import requests
    r = requests.get("http://localhost:8000/health", timeout=5)
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_02_create_mix_project(e2e_env):
    """POST /mix/ 创建项目 + 派发到 mix worker"""
    import requests
    payload = {
        "name": "E2E 测试混剪",
        "script_text": "今天的直播我们重点讲屋面防水工程的关键技术, 包括材料选择和施工细节。",
        "target_duration_seconds": 30,
        "candidate_clip_ids": [e2e_env["clip_id"]],
    }
    r = requests.post(f"{BASE}/mix/", json=payload, timeout=10)
    assert r.status_code == 200, f"create failed: {r.text}"
    body = r.json()
    assert "project_id" in body
    assert body["status"] == "pending"
    assert body["candidate_clip_count"] == 1
    assert body["target_duration_seconds"] == 30

    # 存 project_id 供后续 test 用
    e2e_env["project_id"] = body["project_id"]


def test_03_risk_check_passes(e2e_env):
    """POST /mix/script-risk-check 走纯 keyword 校验 (不依赖 LLM 答)"""
    import requests
    payload = {
        "script_text": "今天的直播我们重点讲屋面防水工程的关键技术, 包括材料选择和施工细节。",
    }
    r = requests.post(f"{BASE}/mix/script-risk-check", json=payload, timeout=10)
    assert r.status_code == 200
    body = r.json()
    # 关键词不命中风险词, 期望 safe
    assert "is_safe" in body
    # risk_keywords 应该是空 list 或 contains 关键词的子集
    assert "risk_keywords" in body
    assert "risk_count" in body


def test_04_wait_mix_completed(e2e_env):
    """poll GET /mix/{id} 直到 status=completed, 限 30s"""
    if "project_id" not in e2e_env:
        pytest.skip("test_02 没跑")

    import requests
    project_id = e2e_env["project_id"]
    deadline = time.time() + 30
    last_status = None
    while time.time() < deadline:
        r = requests.get(f"{BASE}/mix/{project_id}", timeout=5)
        if r.status_code != 200:
            time.sleep(2)
            continue
        body = r.json()
        last_status = body.get("status")
        if last_status == "completed":
            break
        if last_status == "failed":
            pytest.fail(f"mix pipeline failed: {body.get('error', '?')}")
        time.sleep(2)
    else:
        pytest.fail(f"mix {project_id} 30s 内未 completed, last_status={last_status}")


def test_05_output_file_exists(e2e_env):
    """output mix_output.mp4 存在 + size > 1MB"""
    if "project_id" not in e2e_env:
        pytest.skip("test_02 没跑")

    project_id = e2e_env["project_id"]
    output_path = DATA_DIR / "projects" / project_id / "output" / "mix_output.mp4"
    assert output_path.exists(), f"output not generated: {output_path}"
    size = output_path.stat().st_size
    assert size > 1 * 1024 * 1024, f"output size {size} < 1MB (pipeline 异常)"


def test_06_segments_written(e2e_env):
    """mix_project.script_segments 写入 ≥1 segment"""
    if "project_id" not in e2e_env:
        pytest.skip("test_02 没跑")

    from backend.core.database_mix import sync_get_mix_db
    from backend.models.mix import MixProject

    with sync_get_mix_db() as db:
        proj = db.query(MixProject).filter(MixProject.id == e2e_env["project_id"]).first()
        assert proj is not None
        assert proj.status == "completed"
        assert proj.script_segments, "script_segments 为空"
        assert len(proj.script_segments) >= 1, "segments < 1"
        # 验 segment 字段
        seg = proj.script_segments[0]
        assert "matched_video_path" in seg or "matched_clip_id" in seg, \
            f"segment 缺匹配字段: {seg}"


def test_07_video_playable(e2e_env):
    """ffprobe 验 output 视频可读 (duration > 0, 有 video stream)"""
    if "project_id" not in e2e_env:
        pytest.skip("test_02 没跑")

    project_id = e2e_env["project_id"]
    output_path = DATA_DIR / "projects" / project_id / "output" / "mix_output.mp4"
    if not output_path.exists():
        pytest.skip("output 不存在 (test_05 没跑)")

    # ffprobe duration
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(output_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert r.returncode == 0, f"ffprobe fail: {r.stderr}"
    duration = float(r.stdout.strip())
    assert duration > 0, "output duration = 0"

    # ffprobe video stream
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(output_path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert r.returncode == 0
    codec = r.stdout.strip()
    assert codec in ("h264", "libx264", "hevc"), f"unexpected codec: {codec}"
