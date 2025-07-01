"""
ViSQOL-rs-py - Battery-included ViSQOL audio quality assessment tool

这个包提供了批量计算ViSQOL（Virtual Speech Quality Objective Listener）指标的工具。
支持多线程并行处理，自动文件匹配，详细的统计分析等功能。
Battery-included with pre-compiled binaries for easy installation.

主要组件:
- ViSQOLCalculator: 核心计算类
- cli: 命令行接口
- utils: 工具函数

使用示例:
    from visqol_rs_py import ViSQOLCalculator
    
    calculator = ViSQOLCalculator()
    results = calculator.calculate_batch(
        reference_dir="./reference",
        degraded_dir="./degraded"
    )
"""

__version__ = "1.0.0"
__author__ = "Xingjian Du"
__email__ = "xingjian.du97@gmail.com"
__license__ = "MIT"

from .core import ViSQOLCalculator
from .utils import get_visqol_executable_path, check_installation

__all__ = [
    "ViSQOLCalculator",
    "get_visqol_executable_path", 
    "check_installation",
    "__version__",
]