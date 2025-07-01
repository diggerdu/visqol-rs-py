"""
ViSQOL-rs-py工具函数模块

提供各种辅助功能，包括路径查找、日志设置、安装检查等。
Battery-included版本，优先使用预编译的二进制文件。
"""

import os
import sys
import logging
import subprocess
from pathlib import Path
from typing import Optional


def get_visqol_executable_path() -> str:
    """获取ViSQOL可执行文件路径
    
    Battery-included版本：优先使用包内预编译的二进制文件
    
    Returns:
        ViSQOL可执行文件的完整路径
        
    Raises:
        FileNotFoundError: 如果找不到ViSQOL可执行文件
    """
    # 获取包的安装目录
    package_dir = Path(__file__).parent
    
    # 可能的可执行文件路径（按优先级排序）
    possible_paths = [
        # 包内预编译版本（最高优先级）
        package_dir / "bin" / "visqol",
        # 兼容性路径（用于开发/测试）
        package_dir / "visqol-rs" / "target" / "release" / "visqol",
        package_dir / "visqol-rs" / "visqol",
        # 相对路径（用于开发）
        Path("./visqol-rs/target/release/visqol"),
        Path("./visqol-rs/visqol"),
        Path("./visqol"),
        # 系统路径
        Path("/usr/local/bin/visqol"),
        Path("/usr/bin/visqol"),
    ]
    
    # 检查每个可能的路径
    for path in possible_paths:
        if path.exists() and path.is_file():
            # 检查是否可执行
            if os.access(str(path), os.X_OK):
                return str(path.absolute())
    
    # 尝试在PATH中查找
    try:
        result = subprocess.run(
            ["which", "visqol"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        path = result.stdout.strip()
        if path and os.path.exists(path):
            return path
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # 如果都找不到，抛出异常
    raise FileNotFoundError(
        "找不到ViSQOL可执行文件。请确保已正确安装visqol-rs，或者手动指定可执行文件路径。\n"
        f"搜索路径包括: {[str(p) for p in possible_paths]}"
    )


def check_installation() -> dict:
    """检查ViSQOL安装状态
    
    Returns:
        包含安装状态信息的字典
    """
    status = {
        "visqol_found": False,
        "visqol_path": None,
        "model_found": False,
        "model_path": None,
        "rust_found": False,
        "cargo_found": False,
        "errors": []
    }
    
    # 检查ViSQOL可执行文件
    try:
        visqol_path = get_visqol_executable_path()
        status["visqol_found"] = True
        status["visqol_path"] = visqol_path
    except FileNotFoundError as e:
        status["errors"].append(str(e))
    
    # 检查模型文件
    if status["visqol_found"]:
        model_paths = [
            # 包内预编译模型（最高优先级）
            os.path.join(os.path.dirname(__file__), "model", "libsvm_nu_svr_model.txt"),
            # 包内路径 - 基于可执行文件位置
            os.path.join(os.path.dirname(status["visqol_path"]), "..", "model", "libsvm_nu_svr_model.txt"),
            os.path.join(os.path.dirname(status["visqol_path"]), "model", "libsvm_nu_svr_model.txt"),
            # 兼容性路径 - 基于包目录（用于开发/测试）
            os.path.join(os.path.dirname(__file__), "visqol-rs", "model", "libsvm_nu_svr_model.txt"),
            os.path.join(os.path.dirname(__file__), "..", "visqol-rs", "model", "libsvm_nu_svr_model.txt"),
            # 相对路径（用于开发）
            "./visqol-rs/model/libsvm_nu_svr_model.txt",
            "./model/libsvm_nu_svr_model.txt",
        ]
        
        for model_path in model_paths:
            if os.path.exists(model_path):
                status["model_found"] = True
                status["model_path"] = os.path.abspath(model_path)
                break
        
        if not status["model_found"]:
            status["errors"].append("找不到ViSQOL模型文件 (libsvm_nu_svr_model.txt)")
    
    # 检查Rust工具链
    try:
        subprocess.run(["rustc", "--version"], capture_output=True, check=True)
        status["rust_found"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        status["errors"].append("找不到Rust编译器 (rustc)")
    
    try:
        subprocess.run(["cargo", "--version"], capture_output=True, check=True)
        status["cargo_found"] = True
    except (subprocess.CalledProcessError, FileNotFoundError):
        status["errors"].append("找不到Cargo包管理器")
    
    return status


def setup_logging(verbose: bool = True) -> logging.Logger:
    """设置日志记录
    
    Args:
        verbose: 是否启用详细日志输出
        
    Returns:
        配置好的Logger对象
    """
    logger = logging.getLogger("visqol_batch_calculator")
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 设置日志级别
    level = logging.INFO if verbose else logging.WARNING
    logger.setLevel(level)
    
    # 创建控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    
    # 设置日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # 添加handler到logger
    logger.addHandler(console_handler)
    
    return logger


def validate_audio_file(file_path: str) -> bool:
    """验证音频文件是否有效
    
    Args:
        file_path: 音频文件路径
        
    Returns:
        文件是否为有效的音频文件
    """
    if not os.path.exists(file_path):
        return False
    
    # 检查文件扩展名
    audio_extensions = {'.wav', '.flac', '.mp3', '.m4a', '.aac', '.ogg'}
    file_ext = Path(file_path).suffix.lower()
    
    if file_ext not in audio_extensions:
        return False
    
    # 检查文件大小（至少应该有一些内容）
    try:
        file_size = os.path.getsize(file_path)
        if file_size < 100:  # 小于100字节可能不是有效的音频文件
            return False
    except OSError:
        return False
    
    return True


def format_duration(seconds: float) -> str:
    """格式化时间长度
    
    Args:
        seconds: 秒数
        
    Returns:
        格式化的时间字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}分{secs:.1f}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours}小时{minutes}分{secs:.1f}秒"


def get_package_version() -> str:
    """获取包版本号
    
    Returns:
        版本号字符串
    """
    try:
        from . import __version__
        return __version__
    except ImportError:
        return "unknown"


def create_output_directory(output_path: str) -> str:
    """创建输出目录
    
    Args:
        output_path: 输出文件路径
        
    Returns:
        创建的目录路径
    """
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    return output_dir


def get_system_info() -> dict:
    """获取系统信息
    
    Returns:
        包含系统信息的字典
    """
    import platform
    
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
    }


def print_installation_status():
    """打印安装状态信息"""
    print("ViSQOL批量计算器 - 安装状态检查")
    print("=" * 50)
    
    status = check_installation()
    
    # ViSQOL可执行文件
    if status["visqol_found"]:
        print(f"✓ ViSQOL可执行文件: {status['visqol_path']}")
    else:
        print("✗ ViSQOL可执行文件: 未找到")
    
    # 模型文件
    if status["model_found"]:
        print(f"✓ 模型文件: {status['model_path']}")
    else:
        print("✗ 模型文件: 未找到")
    
    # Rust工具链
    if status["rust_found"]:
        print("✓ Rust编译器: 已安装")
    else:
        print("✗ Rust编译器: 未安装")
    
    if status["cargo_found"]:
        print("✓ Cargo包管理器: 已安装")
    else:
        print("✗ Cargo包管理器: 未安装")
    
    # 错误信息
    if status["errors"]:
        print("\n错误信息:")
        for error in status["errors"]:
            print(f"  - {error}")
    
    # 系统信息
    print(f"\n系统信息:")
    sys_info = get_system_info()
    for key, value in sys_info.items():
        print(f"  {key}: {value}")
    
    print("=" * 50)
    
    # 总体状态
    if status["visqol_found"] and status["model_found"]:
        print("✓ 安装状态: 正常，可以使用")
        return True
    else:
        print("✗ 安装状态: 不完整，需要修复")
        return False