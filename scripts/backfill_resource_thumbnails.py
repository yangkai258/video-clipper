#!/usr/bin/env python3
"""
批量给已有 resource 抽 thumbnail (v2.2.38)

跑 1 次, 把所有 thumbnail_path 为空 / 不存在的 resource 重新 ffmpeg 抽 1 帧.

Usage:
  python scripts/backfill_resource_thumbnails.py [--db data/video_clipper.db] [--dry-run]
"""
import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path


def generate_thumb(video_path: Path, thumb_path: Path, t_seconds: float = 1.0) -> bool:
    """跟 backend.api.library._generate_thumbnail 同款, copy 过来避免依赖."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(t_seconds),
            "-i", str(video_path),
            "-frames:v", "1",
            "-vf", "scale=720:-2",
            "-q:v", "3",
            str(thumb_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not thumb_path.exists():
            cmd[2] = "0"  # fallback 0s
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            return r.returncode == 0 and thumb_path.exists()
        return True
    except Exception as e:
        print(f"  ERR: {e}")
        return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="data/video_clipper_beta.db", help="db path")
    p.add_argument("--dry-run", action="store_true", help="只列, 不真抽")
    p.add_argument("--limit", type=int, default=0, help="limit N (0=全部)")
    args = p.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        # fallback release
        db_path = Path("data/video_clipper.db")
    if not db_path.exists():
        print(f"db 不存在: {args.db}")
        sys.exit(1)

    print(f"db: {db_path}")
    if args.dry_run:
        print("[DRY-RUN] 只列, 不真抽\n")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # 找 thumbnail_path 空 / 文件不存在的
    rows = conn.execute("""
        SELECT id, name, file_path, thumbnail_path
        FROM resource_clips
        WHERE deleted_at IS NULL
          AND file_path IS NOT NULL AND file_path != ''
        ORDER BY created_at DESC
    """).fetchall()

    need = []
    for r in rows:
        tp = r["thumbnail_path"]
        if not tp or not Path(tp).exists():
            need.append(dict(r))

    if args.limit:
        need = need[:args.limit]

    print(f"需要回填: {len(need)} 个 (总 {len(rows)} 个 resource)\n")

    ok, fail, skip = 0, 0, 0
    for r in need:
        vp = Path(r["file_path"])
        if not vp.exists():
            print(f"  ✗ mp4 不存在: {r['name'][:30]!r} {r['file_path']}")
            fail += 1
            continue
        tp = vp.parent / f"{vp.stem}.jpg"
        if args.dry_run:
            print(f"  [DRY] {r['name'][:30]!r} → {tp.name}")
            ok += 1
            continue
        if generate_thumb(vp, tp, t_seconds=1.0):
            # 更新 db
            conn.execute("UPDATE resource_clips SET thumbnail_path = ? WHERE id = ?", (str(tp), r["id"]))
            conn.commit()
            print(f"  ✓ {r['name'][:30]!r} → {tp.name}")
            ok += 1
        else:
            print(f"  ✗ ffmpeg 失败: {r['name'][:30]!r}")
            fail += 1

    conn.close()
    print(f"\n=== 完成: ✓{ok} ✗{fail} 跳{skip} ===")


if __name__ == "__main__":
    sys.exit(main())
