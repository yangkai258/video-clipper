"""Regression check for task_health stuck-task detection (P0#2).

Background:
    v2.1.18 (a146818) added _cleanup_stuck_tasks with a 30min hard cutoff
    from created_at.  1GB / 3.6h videos take 50-60min, so the cutoff killed
    long-running jobs while they were still cutting clips.

    task_health.find_stuck_tasks uses two predicates:
      1. no_worker_pickup  : status=running, started_at IS NULL, created_at > 5min
      2. no_progress_update: status=running, progress_changed_at > 30min stale

This test does NOT spin up a DB. It re-implements the predicates and
asserts the corrected one does NOT misclassify a 1GB video that has been
running for 40min with recent progress updates.

ponytail: standalone, no DB / LLM / ffmpeg, no fixtures.
"""
from datetime import datetime, timedelta


def old_predicate(task, now, idle_min=30):
    """v2.1.18: hard 30min from created_at - bug: kills long-running tasks."""
    return (
        task["status"] == "running"
        and (now - task["created_at"]).total_seconds() > idle_min * 60
    )


def new_predicate(task, now, stuck_after_min=5, idle_after_min=30):
    """task_health: heartbeat-based - only stale-progress tasks are stuck."""
    if task["status"] != "running":
        return False
    if task.get("started_at") is None:
        return (now - task["created_at"]).total_seconds() > stuck_after_min * 60
    last_change = task.get("progress_changed_at") or task["started_at"]
    return (now - last_change).total_seconds() > idle_after_min * 60


def test_long_running_1gb_video_not_killed():
    created = datetime(2026, 6, 29, 14, 15, 0)
    started = created + timedelta(seconds=30)
    now = started + timedelta(minutes=40)
    task = {
        "status": "running",
        "created_at": created,
        "started_at": started,
        "progress_changed_at": now - timedelta(minutes=5),
    }
    assert old_predicate(task, now) is True, "sanity: old predicate DOES misclassify"
    assert new_predicate(task, now) is False, "new predicate must not misclassify"


def test_no_pickup_is_stuck():
    now = datetime(2026, 6, 29, 14, 25, 0)
    task = {
        "status": "running",
        "created_at": now - timedelta(minutes=10),
        "started_at": None,
        "progress_changed_at": None,
    }
    assert new_predicate(task, now) is True


def test_no_progress_is_stuck():
    now = datetime(2026, 6, 29, 14, 50, 0)
    task = {
        "status": "running",
        "created_at": now - timedelta(hours=1),
        "started_at": now - timedelta(minutes=50),
        "progress_changed_at": now - timedelta(minutes=35),
    }
    assert new_predicate(task, now) is True


def test_completed_not_stuck():
    now = datetime(2026, 6, 29, 14, 50, 0)
    task = {
        "status": "completed",
        "created_at": now - timedelta(hours=2),
        "started_at": now - timedelta(hours=1, minutes=50),
        "progress_changed_at": now - timedelta(hours=1, minutes=50),
    }
    assert new_predicate(task, now) is False


def test_fallback_to_started_at():
    now = datetime(2026, 6, 29, 14, 50, 0)
    task = {
        "status": "running",
        "created_at": now - timedelta(hours=1),
        "started_at": now - timedelta(minutes=45),
        "progress_changed_at": None,
    }
    assert new_predicate(task, now) is True
