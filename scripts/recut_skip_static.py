#!/usr/bin/env python3
"""对源视频做「智能重切」：自动跳过低动态段，输出新切片。

用法：
  python3 scripts/recut_skip_static.py <source_video.mp4> <out_dir> [min_static=2.0] [min_dynamic=3.0]

逻辑：
  1. 跑 trim_static.py 找整段低动态区间
  2. 把视频按"动态段"切成多个新 clip
  3. 每个新 clip 至少 min_dynamic 秒
  4. 用 moviepy 重切，保留原始音视频，不重新编码（-c copy）

输出：
  out_dir/1_xxx.mp4, 2_xxx.mp4, ...
"""
import sys
import re
import subprocess
from pathlib import Path
from moviepy import VideoFileClip


def probe_duration(video_path: Path) -> float:
    r = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=nw=1:nk=1', str(video_path)],
        capture_output=True, text=True
    )
    return float(r.stdout.strip())


def detect_scene_changes(video_path: Path, threshold: float = 0.05) -> list[float]:
    r = subprocess.run(
        ['ffmpeg', '-i', str(video_path),
         '-vf', f'scdet=threshold={threshold}:show=true',
         '-an', '-f', 'null', '-'],
        capture_output=True, text=True
    )
    return [float(t) for t in re.findall(r'pts_time:([\d.]+)', r.stderr)]


def find_dynamic_segments(scene_times: list[float], total_duration: float,
                          min_duration: float = 3.0,
                          margin: float = 0.5) -> list[tuple[float, float]]:
    """在 scene change 之间找动态段，< min_duration 的丢掉（剪掉头尾 + margin）"""
    boundaries = [0.0] + scene_times + [total_duration]
    segments = []
    for i in range(len(boundaries) - 1):
        s = max(0.0, boundaries[i] + margin)
        e = min(total_duration, boundaries[i + 1] - margin)
        if e - s >= min_duration:
            segments.append((round(s, 2), round(e, 2)))
    return segments


def cut_segment(src: Path, out_path: Path, start: float, end: float):
    """用 moviepy 切一段（保留原始编码，不重新编码）"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with VideoFileClip(str(src)) as video:
        sub = video.subclipped(start, end)
        sub.write_videofile(
            str(out_path),
            codec='libx264', audio_codec='aac', preset='ultrafast',
            ffmpeg_params=['-movflags', '+faststart', '-crf', '18'],
            logger=None,
        )
        sub.close()
        video.close()


def main():
    if len(sys.argv) < 3:
        print('Usage: recut_skip_static.py <source.mp4> <out_dir> [min_static=2.0] [min_dynamic=3.0]')
        sys.exit(1)
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    min_static = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
    min_dynamic = float(sys.argv[4]) if len(sys.argv) > 4 else 3.0

    if not src.exists():
        print(f'Source not found: {src}')
        sys.exit(1)

    print(f'分析 {src} ...')
    duration = probe_duration(src)
    scene_times = detect_scene_changes(src)
    dynamic_segs = find_dynamic_segments(scene_times, duration, min_dynamic)

    print(f'视频时长: {duration:.1f}s')
    print(f'scene changes: {len(scene_times)}')
    print(f'动态段（≥{min_dynamic}s）: {len(dynamic_segs)} 段')
    for i, (s, e) in enumerate(dynamic_segs):
        print(f'  [{i+1}] {s:.2f}s - {e:.2f}s  ({e-s:.1f}s)')

    if not dynamic_segs:
        print('⚠️ 没找到任何动态段（视频可能全程低动态）')
        sys.exit(2)

    out_dir.mkdir(parents=True, exist_ok=True)
    print(f'\n开始切割到 {out_dir}/ ...')
    for i, (s, e) in enumerate(dynamic_segs):
        out = out_dir / f'{i+1:02d}_dynamic_{s:.0f}s-{e:.0f}s.mp4'
        print(f'  [{i+1}/{len(dynamic_segs)}] {out.name}', end=' ... ')
        try:
            cut_segment(src, out, s, e)
            print('ok')
        except Exception as ex:
            print(f'FAIL: {ex}')

    print(f'\n✅ 完成，{len(dynamic_segs)} 个切片已输出到 {out_dir}/')


if __name__ == '__main__':
    main()
