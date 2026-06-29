#!/usr/bin/env python3
"""检测视频低动态段（人几乎不动），输出可修剪时间窗口。

原理：
  1. ffmpeg scdet 检测 scene change（场景切换）时间戳
  2. 相邻 scene change 间隔 > min_static_duration 的，就是低动态段
  3. 用 moviepy 跳过这些段，重新输出

用法：
  python3 scripts/trim_static.py /path/to/clip.mp4 [min_static_duration=2.0]
"""
import sys
import re
import subprocess
import json
from pathlib import Path


def probe_duration(video_path: Path) -> float:
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=nw=1:nk=1', str(video_path)],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def detect_scene_changes(video_path: Path, threshold: float = 0.05) -> list[float]:
    """用 ffmpeg scdet 返回每个 scene change 的时间戳（秒）"""
    r = subprocess.run(
        ['ffmpeg', '-i', str(video_path),
         '-vf', f'scdet=threshold={threshold}:show=true',
         '-an', '-f', 'null', '-'],
        capture_output=True, text=True
    )
    times = [float(t) for t in re.findall(r'pts_time:([\d.]+)', r.stderr)]
    return times


def find_static_segments(scene_times: list[float], total_duration: float,
                          min_duration: float = 2.0) -> list[tuple[float, float]]:
    """在 scene change 列表里找连续 > min_duration 的低动态段"""
    segments = []
    last = 0.0
    for t in scene_times:
        if t - last >= min_duration:
            segments.append((round(last, 2), round(t, 2)))
        last = t
    if total_duration - last >= min_duration:
        segments.append((round(last, 2), round(total_duration, 2)))
    return segments


def main():
    if len(sys.argv) < 2:
        print('Usage: trim_static.py <video.mp4> [min_static_duration=2.0]')
        sys.exit(1)
    video_path = Path(sys.argv[1])
    min_static = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    if not video_path.exists():
        print(f'File not found: {video_path}')
        sys.exit(1)

    duration = probe_duration(video_path)
    scene_times = detect_scene_changes(video_path)
    static_segs = find_static_segments(scene_times, duration, min_static)

    result = {
        'file': str(video_path),
        'duration': round(duration, 2),
        'scene_change_count': len(scene_times),
        'scene_change_times': [round(t, 2) for t in scene_times],
        'static_segments': static_segs,
        'static_total_seconds': round(sum(e - s for s, e in static_segs), 2),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
