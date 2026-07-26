#!/usr/bin/env python3
"""
重置并重派发指定 mix project (v2.2.42 helper)

背景: v2.2.36 之前跑的 mix project 用 v2.2.26 fallback 路径 (clip_library[0] 固定), 多段重复.
修了 v2.2.42 round-robin 后, 想重跑老 project 验证. 但 worker 不清老 source_clips/output, 直接重派发会 duplicate.

用法:
  python scripts/reset_and_redispatch_mix.py <project_id> [--db path]
  python scripts/reset_and_redispatch_mix.py bc65f840-851b-421c-9349-5251d671fb9c
"""
import argparse
import sqlite3
import sys
from pathlib import Path
import subprocess


def main():
    p = argparse.ArgumentParser()
    p.add_argument("project_id", help="MixProject UUID")
    p.add_argument("--db", default="data/video_clipper_mix.db")
    args = p.parse_args()

    project_id = args.project_id
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"db 不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    proj = conn.execute("SELECT * FROM mix_projects WHERE id = ?", (project_id,)).fetchone()
    if not proj:
        print(f"project 不存在: {project_id}")
        sys.exit(1)

    print(f"=== 重置 {project_id} ===")
    print(f"name: {proj['name']}")
    print(f"status: {proj['status']}")
    print(f"script_text 长度: {len(proj['script_text'] or '')}")
    print(f"script_segments 长度: {len(proj['script_segments'] or '')}")
    print(f"target_duration: {proj['target_duration_seconds']}")

    # 1. 找老 source_clip_ids (重跑需要这些 candidate)
    old_src = conn.execute(
        "SELECT DISTINCT source_clip_id FROM mix_source_clips WHERE mix_project_id = ?",
        (project_id,),
    ).fetchall()
    candidate_clip_ids = [r["source_clip_id"] for r in old_src]
    print(f"老 source_clips 候选: {len(candidate_clip_ids)} 个")

    # 1b. 如果老 source_clips 已空 (前次跑清空), 从 release 资源库找 from-project 候选
    #     保证重置后能跑出结果 (>= 3 candidate 才能 round-robin 有意义)
    if not candidate_clip_ids:
        print("老 source_clips 空, 从 release 资源库找 from-project 候选...")
        # 用 release db (跟 release uvicorn :8000 一致)
        rel_db = Path("data/video_clipper.db")
        if rel_db.exists():
            rel_conn = sqlite3.connect(str(rel_db))
            rel_conn.row_factory = sqlite3.Row
            rows = rel_conn.execute("""
                SELECT id FROM resource_clips
                WHERE deleted_at IS NULL AND source_type = 'from_project'
                ORDER BY created_at DESC LIMIT 8
            """).fetchall()
            rel_conn.close()
            candidate_clip_ids = [r["id"] for r in rows]
            print(f"  从 release 资源库拿 {len(candidate_clip_ids)} 个 from-project clip")
    print(f"candidate_clip_ids: {len(candidate_clip_ids)} 个")

    # 2. DELETE 老 source_clips + 任务
    src_count = conn.execute(
        "SELECT COUNT(*) FROM mix_source_clips WHERE mix_project_id = ?", (project_id,)
    ).fetchone()[0]
    task_count = conn.execute(
        "SELECT COUNT(*) FROM mix_tasks WHERE mix_project_id = ?", (project_id,)
    ).fetchone()[0]
    print(f"DELETE {src_count} 老 source_clips + {task_count} 老 task")
    conn.execute("DELETE FROM mix_source_clips WHERE mix_project_id = ?", (project_id,))
    conn.execute("DELETE FROM mix_tasks WHERE mix_project_id = ?", (project_id,))
    conn.commit()

    # 3. UPDATE project status=pending
    conn.execute("""
        UPDATE mix_projects
        SET status = 'pending',
            output_video_path = NULL,
            video_size = NULL,
            video_duration = NULL,
            thumbnail_path = NULL,
            completed_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (project_id,))
    conn.commit()
    print("project 重置为 pending")

    # 4. DELETE 老 mp4 + thumbnail
    import json
    base = Path("data/projects") / project_id / "output"
    if base.exists():
        for f in base.glob("mix_output*.mp4"):
            f.unlink()
            print(f"DELETE {f}")
        for f in base.glob("thumbnail.jpg"):
            f.unlink()
            print(f"DELETE {f}")
        for sub in ("_extract_parts",):
            d = base / sub
            if d.exists():
                import shutil
                shutil.rmtree(d)
                print(f"DELETE {d}/")

    # 5. 重新派发 task (直接调 dispatch_mix_task, 不创建新 project)
    print()
    print(f"=== 重新派发 (直接 dispatch_mix_task 到 {project_id}) ===")

    # 用 subprocess 跑内联 Python 调 dispatch, 避免跟脚本进程 event loop 冲突
    dispatch_script = f"""
import sys, os
sys.path.insert(0, '.')
# 跟 worker 一致 env (release mode 走 db=0/processing_mix)
os.environ['DATABASE_URL'] = 'sqlite+aiosqlite:///./data/video_clipper.db'
os.environ['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
os.environ['CELERY_RESULT_BACKEND'] = 'redis://localhost:6379/0'
os.environ['CELERY_QUEUE_NAME'] = 'processing_mix'
from backend.services.mix_dispatch import dispatch_mix_task
import uuid
task_id = str(uuid.uuid4())
celery_id = dispatch_mix_task(
    mix_project_id='{project_id}',
    script_text={proj['script_text']!r},
    target_duration_seconds={proj['target_duration_seconds'] or 60},
    candidate_clip_ids={candidate_clip_ids!r},
    task_id=task_id,
)
print(f'dispatched: task_id={{task_id}} celery_id={{celery_id}}')
"""
    dispatch_path = Path("/tmp/mix_reset_dispatch.py")
    dispatch_path.write_text(dispatch_script)

    r = subprocess.run(
        [".venv/bin/python", str(dispatch_path)],
        capture_output=True, text=True, timeout=30,
    )
    print(f"  stdout: {r.stdout}")
    if r.returncode != 0:
        print(f"  stderr: {r.stderr[:500]}")
    conn.close()


if __name__ == "__main__":
    main()
