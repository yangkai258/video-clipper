"""pytest 全局配置"""
import sys
import os
from pathlib import Path

# 把项目根目录加到 sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))