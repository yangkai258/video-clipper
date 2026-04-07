"""字幕生成服务"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def generate_subtitle(video_path: Path, output_path: Path) -> Path:
    """生成字幕文件 - 直接使用 faster-whisper"""
    from ..utils.speech_recognizer import SpeechRecognizer, SpeechRecognitionMethod
    
    logger.info(f"开始为视频生成字幕：{video_path}")
    
    recognizer = SpeechRecognizer()
    
    # 直接使用 faster-whisper（跳过 bcut-asr 和 mlx-whisper）
    try:
        logger.info("使用 faster-whisper 生成字幕")
        return recognizer.generate(
            video_path,
            output_path,
            method=SpeechRecognitionMethod.FASTER_WHISPER,
            model="tiny"
        )
    except Exception as e:
        logger.error(f"faster-whisper 失败：{e}")
        raise Exception("字幕生成失败")
