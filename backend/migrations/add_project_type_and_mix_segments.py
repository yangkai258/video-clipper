"""Add project_type / mix fields to projects + MixSegment table (v2.2.3 混剪功能).

新字段:
  projects.project_type  — 'clip' (默认, 切片项目) | 'mix' (混剪项目)
  projects.script_text   — 用户输入的直播脚本
  projects.script_segments — LLM 分段 [{text, keywords, position}]
  projects.target_duration_seconds — 用户选的目标时长 (30/60/180/300)
  projects.output_video_path — 混剪输出 mp4 路径

新表:
  mix_segments — 混剪片段关联: mix project → source clip 的 N:N 引用 + 拼接顺序

Idempotent: 安全重复跑.
"""
import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATABASE_PATH = os.path.join(BASE_DIR, "data", "video_clipper.db")
BETA_DB = os.path.join(BASE_DIR, "data", "video_clipper_beta.db")


def _migrate_one(path):
    if not os.path.exists(path):
        print(f"  skip (not found): {path}")
        return
    conn = sqlite3.connect(path)
    cur = conn.cursor()

    # 1) projects 表加 5 个新列
    cur.execute("PRAGMA table_info(projects)")
    cols = {row[1] for row in cur.fetchall()}

    added = []
    if "project_type" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN project_type VARCHAR(20) DEFAULT 'clip'")
        added.append("project_type")
    if "script_text" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN script_text TEXT DEFAULT ''")
        added.append("script_text")
    if "script_segments" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN script_segments JSON DEFAULT '[]'")
        added.append("script_segments")
    if "target_duration_seconds" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN target_duration_seconds INTEGER DEFAULT 60")
        added.append("target_duration_seconds")
    if "output_video_path" not in cols:
        cur.execute("ALTER TABLE projects ADD COLUMN output_video_path VARCHAR(512)")
        added.append("output_video_path")
    conn.commit()

    # 2) 新建 mix_segments 表
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mix_segments (
        id VARCHAR(36) PRIMARY KEY,
        mix_project_id VARCHAR(36) NOT NULL,
        source_clip_id VARCHAR(36) NOT NULL,
        source_project_id VARCHAR(36) NOT NULL,
        position INTEGER DEFAULT 0,
        script_segment_text TEXT DEFAULT '',
        match_score FLOAT DEFAULT 0.0,
        start_time FLOAT DEFAULT 0.0,
        end_time FLOAT DEFAULT 0.0,
        duration FLOAT DEFAULT 0.0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (mix_project_id) REFERENCES projects(id),
        FOREIGN KEY (source_clip_id) REFERENCES clips(id),
        FOREIGN KEY (source_project_id) REFERENCES projects(id)
    )
    """)
    conn.commit()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mix_segments_mix_project ON mix_segments(mix_project_id, position)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_mix_segments_source_clip ON mix_segments(source_clip_id)")
    conn.commit()

    if added:
        print(f"  + projects added: {', '.join(added)}  ({path})")
    else:
        print(f"  projects already has all columns: {path}")
    print(f"  + mix_segments table created (idempotent)  ({path})")
    conn.close()


def migrate():
    for db in (DATABASE_PATH, BETA_DB):
        _migrate_one(db)


if __name__ == "__main__":
    migrate()