#!/usr/bin/env python3
"""
把切片项目所有 clip 批量入库资源库 (v2.2.36)

按项目循环调 POST /api/v1/library/from-clip 端点 (已有), 跳过已存在的
(source_project_id + source_clip_id 联合去重).

用法:
  python scripts/batch_sync_slice_to_library.py [--dry-run] [--host http://127.0.0.1:8030]
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

import requests


def fetch_completed_projects(db_path: str) -> list[dict]:
    """从切片 db 查所有 status=completed 的项目 + clip 数."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, name, status, completed_at,
               (SELECT COUNT(*) FROM clips WHERE clips.project_id = projects.id) AS clip_count
        FROM projects
        WHERE status = 'completed' AND deleted_at IS NULL
        ORDER BY completed_at DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_project_clips(db_path: str, project_id: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT id, title, video_path, duration
        FROM clips
        WHERE project_id = ?
        ORDER BY start_time ASC
    """, (project_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def fetch_existing_in_library(db_path: str, source_project_id: str) -> set[str]:
    """查 resource_clips 已有 source_clip_id, 用于去重."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute("""
        SELECT source_clip_id FROM resource_clips
        WHERE source_project_id = ? AND deleted_at IS NULL
    """, (source_project_id,)).fetchall()
    conn.close()
    return {r[0] for r in rows if r[0]}


def sync_one(host: str, db_path: str, project: dict, dry_run: bool) -> tuple[int, int]:
    """同步 1 个项目的所有 clip 入库. 返 (added, skipped)."""
    existing = fetch_existing_in_library(db_path, project["id"])
    clips = fetch_project_clips(db_path, project["id"])
    if not clips:
        return 0, 0

    added, skipped = 0, 0
    for clip in clips:
        if clip["id"] in existing:
            skipped += 1
            continue
        if dry_run:
            print(f"  [DRY] + {clip['title'][:40]!r}")
            added += 1
            continue
        try:
            r = requests.post(
                f"{host}/api/v1/library/from-clip",
                json={
                    "source_project_id": project["id"],
                    "source_clip_id": clip["id"],
                },
                timeout=30,
            )
            if r.status_code == 200:
                added += 1
                print(f"  ✓ + {clip['title'][:40]!r}")
            elif r.status_code == 409:
                # already in library (race or 重复)
                skipped += 1
            else:
                print(f"  ✗ {r.status_code} {clip['title'][:40]!r}: {r.text[:100]}")
                skipped += 1
        except Exception as e:
            print(f"  ✗ ERR {clip['title'][:40]!r}: {e}")
            skipped += 1
        # 礼貌限速, 避免打爆 worker
        time.sleep(0.05)

    return added, skipped


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="只列不加")
    p.add_argument("--host", default="http://127.0.0.1:8030", help="backend host (默认 beta :8030)")
    p.add_argument("--db", default=None, help="db path (默认自动选 beta)")
    args = p.parse_args()

    db_path = args.db or "data/video_clipper_beta.db"
    if not Path(db_path).exists():
        db_path = "data/video_clipper.db"

    print(f"db: {db_path}")
    print(f"host: {args.host}")
    if args.dry_run:
        print("[DRY-RUN] 只列, 不真加\n")

    projects = fetch_completed_projects(db_path)
    print(f"completed 项目: {len(projects)}\n")

    total_added, total_skipped = 0, 0
    for proj in projects:
        print(f"📦 {proj['name']} ({proj['id'][:8]}) — {proj['clip_count']} clip")
        added, skipped = sync_one(args.host, db_path, proj, args.dry_run)
        total_added += added
        total_skipped += skipped
        print(f"   +{added} 跳过 {skipped}\n")

    print(f"===")
    print(f"总计 +{total_added}  跳过 {total_skipped}")


if __name__ == "__main__":
    sys.exit(main())
