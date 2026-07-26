"""v2.2.55: 给老 ResourceClip backfill visual_tags

v2.2.47 ResourceClip 加 visual_tags 列 + from-clip/upload 同步生成.
但老 clip (v2.2.47 之前入库) 还没 visual_tags, 显示空 list,
视觉匹配公式 (v2.2.47 combined_tag_overlap) 拿不到这些.

这个脚本: 遍历所有 visual_tags=[] 或 NULL 的 ResourceClip,
走 generate_visual_tags (含 0 依赖 + 真 vision API), 写回 db.

跟 v2.2.38 backfill_resource_thumbnails.py 模式一致.

跑法:
    python scripts/backfill_resource_visual_tags.py              # 跑 release db
    python scripts/backfill_resource_visual_tags.py --db beta    # 跑 beta db
    python scripts/backfill_resource_visual_tags.py --limit 10    # 限 10 个测
    python scripts/backfill_resource_visual_tags.py --force       # 覆盖已有 visual_tags

target DB:
    data/video_clipper.db             release
    data/video_clipper_beta.db        beta
"""
import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

from backend.core.config import settings  # noqa: E402
from backend.services.visual_tag_service import generate_visual_tags  # noqa: E402


def get_db_path(db_name: str) -> Path:
    """db_name: 'release' / 'beta'"""
    data_dir = Path(getattr(settings, "DATA_DIR", "data"))
    if db_name == "beta":
        return data_dir / "video_clipper_beta.db"
    return data_dir / "video_clipper.db"


def list_clips_needing_tags(db_path: Path, limit: int, force: bool) -> list[dict]:
    """查 visual_tags=[] 或 NULL 的 resource_clips"""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        if force:
            sql = """
                SELECT id, file_path FROM resource_clips
                WHERE deleted_at IS NULL AND file_path IS NOT NULL
                ORDER BY created_at DESC
                LIMIT ?
            """
        else:
            sql = """
                SELECT id, file_path FROM resource_clips
                WHERE deleted_at IS NULL AND file_path IS NOT NULL
                AND (visual_tags IS NULL OR visual_tags = '[]' OR visual_tags = '')
                ORDER BY created_at DESC
                LIMIT ?
            """
        rows = conn.execute(sql, (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_clip_visual_tags(db_path: Path, clip_id: str, visual_tags: list) -> None:
    """写回 db"""
    import json
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "UPDATE resource_clips SET visual_tags = ? WHERE id = ?",
            (json.dumps(visual_tags, ensure_ascii=False), clip_id),
        )
        conn.commit()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="backfill ResourceClip.visual_tags")
    parser.add_argument(
        "--db",
        default="release",
        choices=["release", "beta", "all"],
        help="目标 db (release / beta / all 两个都跑)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="最多处理 N 个 (默认 1000)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有 visual_tags (默认 skip 已有的)",
    )
    args = parser.parse_args()

    db_names = ["release", "beta"] if args.db == "all" else [args.db]
    total_processed = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0

    for db_name in db_names:
        db_path = get_db_path(db_name)
        if not db_path.exists():
            print(f"[skip] {db_path} 不存在")
            continue

        print(f"\n=== {db_name} db: {db_path} ===")
        clips = list_clips_needing_tags(db_path, args.limit, args.force)
        print(f"找到 {len(clips)} 个需要 backfill 的 clip (limit={args.limit}, force={args.force})")

        if not clips:
            continue

        for i, clip in enumerate(clips, 1):
            clip_id = clip["id"]
            file_path = clip["file_path"]
            if not file_path:
                print(f"  [{i}/{len(clips)}] {clip_id[:8]} skip: file_path 空")
                total_skipped += 1
                continue

            mp4_path = Path(file_path)
            if not mp4_path.exists():
                print(f"  [{i}/{len(clips)}] {clip_id[:8]} skip: 文件不存在 {mp4_path}")
                total_skipped += 1
                continue

            t0 = time.time()
            try:
                visual_tags = generate_visual_tags(mp4_path) or []
            except Exception as e:
                print(f"  [{i}/{len(clips)}] {clip_id[:8]} ERR: {e}")
                total_errors += 1
                continue

            try:
                update_clip_visual_tags(db_path, clip_id, visual_tags)
            except Exception as e:
                print(f"  [{i}/{len(clips)}] {clip_id[:8]} DB ERR: {e}")
                total_errors += 1
                continue

            elapsed = time.time() - t0
            total_processed += 1
            total_updated += 1
            print(
                f"  [{i}/{len(clips)}] {clip_id[:8]} "
                f"→ {len(visual_tags)} tags {visual_tags[:5]}{'...' if len(visual_tags) > 5 else ''} "
                f"({elapsed:.1f}s)"
            )

    print(f"\n=== 总结 ===")
    print(f"  processed: {total_processed}")
    print(f"  updated:   {total_updated}")
    print(f"  skipped:   {total_skipped}")
    print(f"  errors:    {total_errors}")


if __name__ == "__main__":
    main()
