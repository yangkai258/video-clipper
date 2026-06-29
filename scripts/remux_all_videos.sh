#!/bin/bash
# 批量 remux 项目里的 mp4 到 faststart 格式
# 用法：bash scripts/remux_all_videos.sh
# 原理：ffmpeg -c copy -movflags +faststart 原地重写 moov atom
# 容器层重写，不重新编码，几秒完成每个文件
# faststart = moov atom 在文件头，浏览器能秒开（无需下载整个文件）

set -e
cd "$(dirname "$0")/.."

COUNT_OK=0
COUNT_FAIL=0

echo "🔍 扫描需要 remux 的老视频（moov 在文件末尾）..."

/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app/Contents/MacOS/Python << 'PYEOF'
import subprocess
from pathlib import Path
import os

count_ok = 0
count_fail = 0
fails = []

for proj in Path('data/projects').iterdir():
    if not proj.is_dir(): continue
    output = proj / 'output'
    if not output.exists(): continue
    for clip_dir in output.rglob('clips'):
        for clip in clip_dir.glob('*.mp4'):
            data = clip.read_bytes()
            moov = data.find(b'moov')
            mdat = data.find(b'mdat')
            if moov <= mdat: continue
            tmp = clip.with_suffix('.tmp.mp4')
            r = subprocess.run(
                ['ffmpeg', '-y', '-i', str(clip), '-c', 'copy', '-movflags', '+faststart', str(tmp)],
                capture_output=True
            )
            if r.returncode == 0 and tmp.exists():
                os.replace(tmp, clip)
                count_ok += 1
            else:
                count_fail += 1
                fails.append(clip.name)
                if tmp.exists(): tmp.unlink()

print(f'✅ ok: {count_ok}, ❌ fail: {count_fail}')
for f in fails[:5]: print(f'  FAIL: {f}')
PYEOF
