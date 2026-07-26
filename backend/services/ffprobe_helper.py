"""ffprobe helper — 提取视频元数据 (v2.1.26)

用 subprocess 调系统 ffprobe, 返回标准化 dict.
失败/缺失 ffprobe 时返回 None, 让调用方降级处理.
"""

import json
import subprocess
from pathlib import Path


def get_video_dimensions(video_path: Path) -> tuple[int, int] | None:
    """提取视频宽高 (px)

    Returns:
        (width, height) 元组, 失败返回 None
    """
    if not Path(video_path).exists():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return None
        stream = streams[0]
        w = int(stream.get("width", 0))
        h = int(stream.get("height", 0))
        if w <= 0 or h <= 0:
            return None
        return (w, h)
    except (
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        ValueError,
        FileNotFoundError,
    ):
        return None


def get_orientation(width: int, height: int) -> str:
    """根据宽高判断视频方向 (v2.1.26 加 cinemascope)

    Returns:
        "portrait" | "landscape" | "cinemascope" | "square"
    """
    if not width or not height:
        return "landscape"  # 默认横屏, 防止 None
    if height > width * 1.2:  # 明显竖屏 (>1.2:1)
        return "portrait"
    if width >= height * 2.0:  # 2:1 以上宽银幕 (2.35:1 电影)
        return "cinemascope"
    if width > height * 1.2:  # 普通横屏 (1.2 ~ 2.0)
        return "landscape"
    return "square"
