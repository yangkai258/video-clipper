"""字幕生成服务"""
import logging
import platform
import tempfile
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def generate_subtitle(video_path: Path, output_path: Path = None, in_memory: bool = False) -> Union[Path, str]:
    """生成字幕

    引擎选择策略：
    - Apple Silicon (macOS arm64) + mlx-whisper 可用 → 优先 mlx-whisper（3-5x 加速）
    - 否则 → faster-whisper base（CPU int8）— 比 tiny 准确率高 2-3 倍，速度慢 3-5x
    - 任何主引擎失败 → 回退 faster-whisper

    Args:
        video_path: 输入视频路径
        output_path: SRT 输出路径（in_memory=False 时必须，in_memory=True 时忽略）
        in_memory: 是否只返回字符串不落盘（in_memory=True 时返回 SRT 文本字符串）

    Returns:
        in_memory=False → output_path (Path)
        in_memory=True → SRT 文本字符串（临时文件会被删除）
    """
    from ..utils.speech_recognizer import SpeechRecognizer, SpeechRecognitionMethod

    logger.info(f"开始为视频生成字幕：{video_path} {'（in_memory 模式，不落盘）' if in_memory else ''}")

    recognizer = SpeechRecognizer()

    # 检测是否优先使用 mlx-whisper
    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    use_mlx = is_apple_silicon and recognizer.mlx_whisper_available

    # in_memory 模式：用临时文件存，写完读回立即删
    actual_output = output_path
    temp_to_cleanup = None
    if in_memory:
        tmp = tempfile.NamedTemporaryFile(
            suffix=".srt",
            delete=False,
            mode="w",
            encoding="utf-8",
            dir="/tmp",
        )
        tmp.close()
        actual_output = Path(tmp.name)
        temp_to_cleanup = actual_output
    elif output_path is None:
        raise ValueError("非 in_memory 模式必须提供 output_path")

    try:
        if use_mlx:
            logger.info("检测到 Apple Silicon + mlx-whisper 可用，优先使用 mlx-whisper（3-5x 加速）")
            try:
                result = recognizer.generate(
                    video_path,
                    actual_output,
                    method=SpeechRecognitionMethod.MLX_WHISPER,
                    model="base",
                )
            except Exception as e:
                logger.warning(f"mlx-whisper 失败：{e}，回退到 faster-whisper")
                result = recognizer.generate(
                    video_path,
                    actual_output,
                    method=SpeechRecognitionMethod.FASTER_WHISPER,
                    model="base",
                )
        else:
            logger.info("使用 faster-whisper 生成字幕")
            result = recognizer.generate(
                video_path,
                actual_output,
                method=SpeechRecognitionMethod.FASTER_WHISPER,
                model="base",
            )
    except Exception as e:
        if temp_to_cleanup and temp_to_cleanup.exists():
            temp_to_cleanup.unlink()
        logger.error(f"字幕生成失败：{e}")
        raise

    # v2.2.2: hallucination 检测 — Whisper 在静音 / 异常音频下会重复 initial_prompt
    # 当作识别结果 (base 模型中文直播常见). 检测: >40% segment 文本相同 = hallucination,
    # 标 failed 让 user 选别的 ASR 方法 / 重传. 修根因见 speech_recognizer._INITIAL_PROMPT.
    try:
        if actual_output.exists():
            srt_text = actual_output.read_text(encoding="utf-8")
            # 提取每段文字 (跳过 index + timestamp 行)
            lines = [l.strip() for l in srt_text.split("\n") if l.strip() and not l.strip().isdigit() and "-->" not in l]
            if lines:
                from collections import Counter
                counter = Counter(lines)
                most_common_text, most_common_count = counter.most_common(1)[0]
                repeat_ratio = most_common_count / len(lines)
                if repeat_ratio > 0.4:
                    msg = (f"字幕识别失败 (Whisper hallucination): "
                           f"{len(lines)} 段中有 {most_common_count} 段重复 '{most_common_text[:30]}'. "
                           f"可能是视频静音 / 纯背景音乐 / base 模型在中文直播短句上不可靠.")
                    logger.error(msg)
                    if temp_to_cleanup and temp_to_cleanup.exists():
                        temp_to_cleanup.unlink()
                    raise RuntimeError(msg)
    except RuntimeError:
        raise
    except Exception as e:
        # hallucination 检测本身失败, 不影响字幕生成, 走原流程
        logger.debug(f"hallucination 检查跳过: {e}")

    # in_memory 模式：读回内容，删除临时文件
    if in_memory:
        try:
            srt_content = result.read_text(encoding="utf-8")
            logger.info(f"字幕已生成（in_memory）：{len(srt_content)} 字符")
            return srt_content
        finally:
            if temp_to_cleanup and temp_to_cleanup.exists():
                temp_to_cleanup.unlink()
                logger.debug(f"已清理临时文件：{temp_to_cleanup}")

    return result