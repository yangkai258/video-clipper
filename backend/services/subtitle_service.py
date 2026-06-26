"""字幕生成服务"""
import logging
import platform
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_subtitle(video_path: Path, output_path: Path) -> Path:
    """生成字幕文件

    引擎选择策略：
    - Apple Silicon (macOS arm64) + mlx-whisper 可用 → 优先 mlx-whisper（3-5x 加速）
    - 否则 → faster-whisper tiny（CPU int8）
    - 任何主引擎失败 → 回退 faster-whisper
    """
    from ..utils.speech_recognizer import SpeechRecognizer, SpeechRecognitionMethod

    logger.info(f"开始为视频生成字幕：{video_path}")

    recognizer = SpeechRecognizer()

    # 检测是否优先使用 mlx-whisper
    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    use_mlx = is_apple_silicon and recognizer.mlx_whisper_available

    if use_mlx:
        logger.info("检测到 Apple Silicon + mlx-whisper 可用，优先使用 mlx-whisper（3-5x 加速）")
        try:
            return recognizer.generate(
                video_path,
                output_path,
                method=SpeechRecognitionMethod.MLX_WHISPER,
                model="tiny",
            )
        except Exception as e:
            logger.warning(f"mlx-whisper 失败：{e}，回退到 faster-whisper")

    # 默认 / 回退：faster-whisper
    try:
        logger.info("使用 faster-whisper 生成字幕")
        return recognizer.generate(
            video_path,
            output_path,
            method=SpeechRecognitionMethod.FASTER_WHISPER,
            model="tiny",
        )
    except Exception as e:
        logger.error(f"faster-whisper 失败：{e}")
        raise Exception("字幕生成失败")