"""语音识别工具"""
import gc
import logging
from pathlib import Path
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# 全局模型缓存（单例，避免重复加载）
_whisper_model_cache = None


class SpeechRecognitionMethod(str, Enum):
    """语音识别方法"""
    BCUT_ASR = "bcut_asr"
    FASTER_WHISPER = "faster_whisper"
    MLX_WHISPER = "mlx_whisper"  # Apple Silicon 优化，3-5 倍加速


class SpeechRecognizer:
    """语音识别器"""
    
    def __init__(self):
        self.bcut_available = self._check_bcut_asr()
        self.faster_whisper_available = self._check_faster_whisper()
        self.mlx_whisper_available = self._check_mlx_whisper()
    
    def _check_bcut_asr(self) -> bool:
        """检查 bcut-asr 是否可用"""
        try:
            from bcut_asr import BcutASR
            from ..core.config import settings
            return bool(settings.BCUT_SESSDATA)
        except ImportError:
            return False
    
    def _check_faster_whisper(self) -> bool:
        """检查 faster-whisper 是否可用"""
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False
    
    def _check_mlx_whisper(self) -> bool:
        """检查 mlx-whisper 是否可用（Apple Silicon 优化）"""
        try:
            from mlx_whisper import transcribe
            return True
        except ImportError:
            return False
    
    def generate(
        self,
        video_path: Path,
        output_path: Path,
        method: SpeechRecognitionMethod = SpeechRecognitionMethod.FASTER_WHISPER,
        model: str = "tiny",
        language: str = "zh"
    ) -> Path:
        """生成字幕"""
        if method == SpeechRecognitionMethod.BCUT_ASR:
            return self._generate_bcut(video_path, output_path)
        elif method == SpeechRecognitionMethod.MLX_WHISPER:
            return self._generate_mlx_whisper(video_path, output_path, model, language)
        elif method == SpeechRecognitionMethod.FASTER_WHISPER:
            return self._generate_faster_whisper(video_path, output_path, model, language)
        else:
            raise ValueError(f"不支持的识别方法：{method}")
    
    def _generate_bcut(self, video_path: Path, output_path: Path) -> Path:
        """使用 bcut-asr 生成字幕"""
        from bcut_asr import BcutASR
        from ..core.config import settings
        
        asr = BcutASR()
        asr.set_file(str(video_path))
        asr.set_cookie(settings.BCUT_SESSDATA)
        
        logger.info("上传视频到 B 站...")
        asr.upload()
        
        logger.info("开始识别...")
        asr.create_task()
        asr.result()
        
        logger.info("导出字幕...")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        asr.save(str(output_path))
        
        return output_path
    
    def _generate_mlx_whisper(
        self,
        video_path: Path,
        output_path: Path,
        model: str = "tiny",
        language: str = "zh"
    ) -> Path:
        """使用 mlx-whisper 生成字幕（Apple Silicon 优化，3-5 倍加速）"""
        from mlx_whisper import transcribe
        import subprocess
        
        logger.info(f"加载 mlx-whisper 模型：{model} (Apple Silicon 优化)")
        
        # 提取音频
        logger.info("提取音频...")
        audio_path = output_path.parent / "temp_audio.wav"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(audio_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info("开始转录...")
        
        # mlx-whisper transcribe 函数
        result = transcribe(
            str(audio_path),
            path_or_hf_repo=f"mlx-community/whisper-1-{model}",  # 使用 mlx 优化版本
            language=language if language != "auto" else None,
            task="transcribe",
            vad_filter=True
        )
        
        # 写入 SRT
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(result.get("segments", []), 1):
                start = self._format_srt_time(segment.get("start", 0))
                end = self._format_srt_time(segment.get("end", 0))
                text = segment.get("text", "").strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        
        # 清理临时文件
        if audio_path.exists():
            audio_path.unlink()
        
        logger.info(f"字幕生成完成：{output_path}")
        return output_path
    
    def _generate_faster_whisper(
        self,
        video_path: Path,
        output_path: Path,
        model: str = "tiny",
        language: str = "zh"
    ) -> Path:
        """使用 faster-whisper 生成字幕"""
        from faster_whisper import WhisperModel
        import subprocess
        global _whisper_model_cache
        
        logger.info(f"加载 faster-whisper 模型：{model}")
        
        # 使用全局缓存，避免重复加载
        if _whisper_model_cache is None:
            logger.info("首次加载模型到缓存...")
            _whisper_model_cache = WhisperModel(model, device="cpu", compute_type="int8")
        else:
            logger.info("使用缓存的模型实例")
        whisper_model = _whisper_model_cache
        
        # 提取音频
        logger.info("提取音频...")
        audio_path = output_path.parent / "temp_audio.wav"
        subprocess.run([
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vn", "-acodec", "pcm_s16le",
            "-ar", "16000", "-ac", "1",
            str(audio_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        logger.info("开始转录...")
        segments, info = whisper_model.transcribe(
            str(audio_path),
            language=language if language != "auto" else None,
            vad_filter=True
        )
        
        logger.info(f"检测到语言：{info.language}")
        
        # 写入 SRT
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments, 1):
                start = self._format_srt_time(segment.start)
                end = self._format_srt_time(segment.end)
                text = segment.text.strip()
                f.write(f"{i}\n{start} --> {end}\n{text}\n\n")
        
        # 清理临时文件
        if audio_path.exists():
            audio_path.unlink()
        
        # 强制垃圾回收，释放内存
        logger.info("清理内存...")
        gc.collect()
        
        logger.info(f"字幕生成完成：{output_path}")
        return output_path
    
    def _format_srt_time(self, seconds: float) -> str:
        """格式化 SRT 时间"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
