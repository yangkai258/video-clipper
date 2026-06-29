#!/bin/bash
# 清 video-clipper 磁盘：孤儿目录 + 30 天前回收站 + .uploads 临时文件
# 用法：./scripts/cleanup_storage.sh [--dry-run]

set -e

cd "$(dirname "$0")/.."
DB="data/video_clipper_beta.db"
PROJECTS_DIR="data/projects"
UPLOADS_DIR="data/.uploads"
DRY_RUN=""

[ "$1" = "--dry-run" ] && DRY_RUN="--dry-run" && echo "🟡 DRY RUN 模式（不会真删）"

echo "===== 1. 清孤儿目录（DB 找不到对应 project）====="
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python << PY
import sqlite3, os, shutil
db = sqlite3.connect("$DB")
c = db.cursor()
c.execute("SELECT id FROM projects")
db_ids = {r[0] for r in c.fetchall()}
disk_ids = set(os.listdir("$PROJECTS_DIR"))
orphans = disk_ids - db_ids
print(f"DB 中 {len(db_ids)} 个 project，磁盘有 {len(disk_ids)} 个目录")
if orphans:
    total = 0
    for oid in orphans:
        size = 0
        for root, _, files in os.walk(f"$PROJECTS_DIR/{oid}"):
            for f in files:
                try: size += os.path.getsize(os.path.join(root, f))
                except: pass
        total += size
        print(f"  孤儿: {oid[:8]}... ({size/1024/1024/1024:.2f} GB)")
    print(f"总孤儿: {len(orphans)} 个 / {total/1024/1024/1024:.2f} GB")
    if not "$DRY_RUN":
        for oid in orphans:
            shutil.rmtree(f"$PROJECTS_DIR/{oid}", ignore_errors=True)
            print(f"  ✓ 删除 {oid[:8]}")
else:
    print("无孤儿目录")
PY

echo
echo "===== 2. 清 .uploads 临时文件（>1h 前的）====="
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python << PY
import os, shutil, time
if not os.path.exists("$UPLOADS_DIR"):
    print("$UPLOADS_DIR 不存在")
else:
    now = time.time()
    cleaned = 0
    freed = 0
    for d in os.listdir("$UPLOADS_DIR"):
        full = os.path.join("$UPLOADS_DIR", d)
        age = now - os.path.getmtime(full)
        size = 0
        for root, _, files in os.walk(full):
            for f in files:
                try: size += os.path.getsize(os.path.join(root, f))
                except: pass
        if age > 3600:
            print(f"  {d} ({age/3600:.1f}h 前, {size/1024/1024:.1f} MB)")
            if not "$DRY_RUN":
                shutil.rmtree(full, ignore_errors=True)
                cleaned += 1
                freed += size
    if cleaned:
        print(f"清掉 {cleaned} 个 / 释放 {freed/1024/1024:.1f} MB")
    else:
        print("无过期临时文件")
PY

echo
echo "===== 3. 永久删 30 天前的回收站（保留 30 天可恢复的）====="
/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python << PY
import sqlite3, os, shutil
from datetime import datetime, timedelta
db = sqlite3.connect("$DB")
c = db.cursor()
cutoff = datetime.utcnow() - timedelta(days=30)
c.execute("SELECT id, name, deleted_at, video_size FROM projects WHERE deleted_at IS NOT NULL AND deleted_at < ?", (cutoff,))
rows = c.fetchall()
if rows:
    print(f"{len(rows)} 个超过 30 天的回收站项目:")
    total = 0
    for r in rows:
        print(f"  {r[0][:8]} {r[1]} ({r[2]}, {r[3]/1024/1024/1024:.2f} GB)")
        total += r[3]
    print(f"共 {total/1024/1024/1024:.2f} GB")
    if not "$DRY_RUN":
        for r in rows:
            shutil.rmtree(f"$PROJECTS_DIR/{r[0]}", ignore_errors=True)
            c.execute("DELETE FROM projects WHERE id=?", (r[0],))
        db.commit()
        print(f"  ✓ 删了 {len(rows)} 个")
else:
    print("无过期回收站")
PY

echo
echo "✅ 完成"
