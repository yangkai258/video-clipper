#!/usr/bin/env python3
"""
预加载 faster-whisper 模型到 Worker 进程缓存

使用方法：
1. 启动 Worker 后立即执行
2. 或在 start-release.sh / start-beta.sh 中加入此步骤

示例：
    python3 scripts/preload_whisper_model.py
"""

import sys
import logging
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)


def preload_model(model_name: str = "tiny"):
    """预加载 faster-whisper 模型"""
    logger.info(f"开始预加载 faster-whisper 模型：{model_name}")
    
    try:
        from faster_whisper import WhisperModel
        
        logger.info("正在加载模型到内存...")
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
        
        logger.info("✅ 模型加载成功！")
        logger.info(f"   模型：{model_name}")
        logger.info(f"   设备：CPU (int8)")
        logger.info("   提示：Worker 进程保持运行时，后续任务将直接使用缓存模型")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 模型加载失败：{e}")
        return False


if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "tiny"
    success = preload_model(model)
    sys.exit(0 if success else 1)
