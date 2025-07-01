"""
ViSQOL-rs-py命令行接口

提供完整的命令行工具，支持批量计算、配置选项、结果输出等功能。
Battery-included版本，无需额外编译。
"""

import argparse
import sys
import os
import json
from pathlib import Path
from typing import Optional

from .core import ViSQOLCalculator
from .utils import print_installation_status, get_package_version, setup_logging


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog="visqol-batch",
        description="ViSQOL-rs-py - Battery-included高效的音频质量评估工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基本用法
  visqol-batch ./reference ./degraded

  # 指定输出文件和线程数
  visqol-batch ./reference ./degraded -o results.json -w 8

  # 使用自定义ViSQOL可执行文件
  visqol-batch ./reference ./degraded --visqol-path /path/to/visqol

  # 检查安装状态
  visqol-batch --check

更多信息请访问: https://github.com/diggerdu/visqol-rs-py
        """
    )
    
    # 位置参数
    parser.add_argument(
        "reference_dir",
        nargs="?",
        help="参考音频文件目录"
    )
    
    parser.add_argument(
        "degraded_dir", 
        nargs="?",
        help="降质音频文件目录"
    )
    
    # 可选参数
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="输出结果文件路径 (JSON格式)"
    )
    
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=4,
        help="并行工作线程数 (默认: 4)"
    )
    
    parser.add_argument(
        "--visqol-path",
        type=str,
        help="ViSQOL可执行文件路径 (如果不指定则自动查找)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="启用详细输出"
    )
    
    parser.add_argument(
        "-q", "--quiet",
        action="store_true", 
        help="静默模式，只输出错误信息"
    )
    
    parser.add_argument(
        "--check",
        action="store_true",
        help="检查安装状态并退出"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"visqol-batch-calculator {get_package_version()}"
    )
    
    return parser


def validate_arguments(args) -> bool:
    """验证命令行参数"""
    if args.check:
        return True
    
    if not args.reference_dir or not args.degraded_dir:
        print("错误: 必须指定参考目录和降质目录", file=sys.stderr)
        return False
    
    if not os.path.exists(args.reference_dir):
        print(f"错误: 参考目录不存在: {args.reference_dir}", file=sys.stderr)
        return False
    
    if not os.path.exists(args.degraded_dir):
        print(f"错误: 降质目录不存在: {args.degraded_dir}", file=sys.stderr)
        return False
    
    if not os.path.isdir(args.reference_dir):
        print(f"错误: 参考路径不是目录: {args.reference_dir}", file=sys.stderr)
        return False
    
    if not os.path.isdir(args.degraded_dir):
        print(f"错误: 降质路径不是目录: {args.degraded_dir}", file=sys.stderr)
        return False
    
    if args.workers < 1:
        print("错误: 工作线程数必须大于0", file=sys.stderr)
        return False
    
    if args.workers > 32:
        print("警告: 工作线程数过多可能影响性能", file=sys.stderr)
    
    if args.visqol_path and not os.path.exists(args.visqol_path):
        print(f"错误: 指定的ViSQOL可执行文件不存在: {args.visqol_path}", file=sys.stderr)
        return False
    
    return True


def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 设置日志级别
    verbose = args.verbose and not args.quiet
    logger = setup_logging(verbose)
    
    # 验证参数
    if not validate_arguments(args):
        sys.exit(1)
    
    # 检查安装状态
    if args.check:
        success = print_installation_status()
        sys.exit(0 if success else 1)
    
    try:
        # 创建计算器
        calculator = ViSQOLCalculator(
            visqol_executable=args.visqol_path,
            max_workers=args.workers,
            verbose=verbose
        )
        
        # 执行批量计算
        logger.info(f"开始批量计算ViSQOL指标")
        logger.info(f"参考目录: {args.reference_dir}")
        logger.info(f"降质目录: {args.degraded_dir}")
        logger.info(f"工作线程数: {args.workers}")
        
        results = calculator.calculate_batch(
            reference_dir=args.reference_dir,
            degraded_dir=args.degraded_dir,
            output_file=args.output
        )
        
        # 输出简要结果
        stats = results["statistics"]
        if not args.quiet:
            print(f"\n计算完成!")
            print(f"成功处理: {stats['successful']}/{stats['total_files']} 文件")
            print(f"成功率: {stats['success_rate']:.1%}")
            
            if stats['successful'] > 0:
                print(f"平均MOS-LQO: {stats['mos_lqo_mean']:.3f}")
                print(f"MOS-LQO范围: {stats['mos_lqo_min']:.3f} - {stats['mos_lqo_max']:.3f}")
            
            if args.output:
                print(f"详细结果已保存到: {args.output}")
        
        # 根据成功率决定退出码
        if stats['success_rate'] < 1.0:
            sys.exit(1)
        else:
            sys.exit(0)
            
    except KeyboardInterrupt:
        logger.info("用户中断操作")
        sys.exit(130)
    except Exception as e:
        logger.error(f"执行过程中发生错误: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def simple_cli():
    """简化版命令行接口"""
    print("ViSQOL批量计算器 - 简化版")
    print("=" * 40)
    
    try:
        # 获取输入目录
        reference_dir = input("请输入参考音频目录路径: ").strip()
        if not reference_dir:
            print("错误: 必须指定参考目录")
            return
        
        degraded_dir = input("请输入降质音频目录路径: ").strip()
        if not degraded_dir:
            print("错误: 必须指定降质目录")
            return
        
        # 验证目录
        if not os.path.exists(reference_dir):
            print(f"错误: 参考目录不存在: {reference_dir}")
            return
        
        if not os.path.exists(degraded_dir):
            print(f"错误: 降质目录不存在: {degraded_dir}")
            return
        
        # 可选参数
        output_file = input("输出文件路径 (可选，按回车跳过): ").strip()
        if not output_file:
            output_file = None
        
        workers_input = input("并行线程数 (默认4，按回车使用默认值): ").strip()
        try:
            workers = int(workers_input) if workers_input else 4
        except ValueError:
            workers = 4
        
        # 创建计算器并执行
        print("\n开始计算...")
        calculator = ViSQOLCalculator(max_workers=workers, verbose=True)
        
        results = calculator.calculate_batch(
            reference_dir=reference_dir,
            degraded_dir=degraded_dir,
            output_file=output_file
        )
        
        # 显示结果
        stats = results["statistics"]
        print(f"\n计算完成!")
        print(f"成功处理: {stats['successful']}/{stats['total_files']} 文件")
        
        if stats['successful'] > 0:
            print(f"平均MOS-LQO: {stats['mos_lqo_mean']:.3f}")
        
        if output_file:
            print(f"详细结果已保存到: {output_file}")
            
    except KeyboardInterrupt:
        print("\n用户中断操作")
    except Exception as e:
        print(f"错误: {e}")


def simple_main():
    """简化版CLI入口点"""
    print("ViSQOL-rs-py 简化版CLI")
    print("请使用标准CLI: visqol-batch --help")
    print("或直接运行: visqol-batch <reference_dir> <degraded_dir>")


if __name__ == "__main__":
    main()