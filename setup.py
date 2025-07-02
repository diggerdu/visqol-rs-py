#!/usr/bin/env python3
"""
ViSQOL-rs-py - Battery-included PyPI package installation script
"""

import os
import sys
import shutil
import platform
from pathlib import Path
from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop

# 包信息
PACKAGE_NAME = "visqol-rs-py"
VERSION = "1.0.0"
DESCRIPTION = "Battery-included ViSQOL audio quality batch calculator with pre-compiled binaries"
AUTHOR = "Xingjian Du"
AUTHOR_EMAIL = "xingjian.du97@gmail.com"
URL = "https://github.com/diggerdu/visqol-rs-py"

# 读取长描述
def read_long_description():
    """读取README文件作为长描述"""
    readme_path = Path(__file__).parent / "README.md"
    if readme_path.exists():
        with open(readme_path, "r", encoding="utf-8") as f:
            return f.read()
    return DESCRIPTION

class PostInstallCommand(install):
    """安装后执行的自定义命令 - 只复制预编译的文件"""
    
    def run(self):
        install.run(self)
        self.execute(self._post_install, [], msg="正在设置ViSQOL-rs-py...")
    
    def _post_install(self):
        """安装后的处理 - 验证预编译文件"""
        print("=" * 60)
        print("正在验证ViSQOL-rs-py安装...")
        print("=" * 60)
        
        # 检查平台
        if platform.system() != "Linux" or platform.machine() != "x86_64":
            print("警告: 此包目前仅支持Linux x86_64平台")
            print("当前平台:", platform.system(), platform.machine())
            return
        
        # 获取包安装路径
        package_path = Path(self.install_lib) / "visqol_rs_py"
        visqol_exe = package_path / "bin" / "visqol"
        model_file = package_path / "model" / "libsvm_nu_svr_model.txt"
        
        # 验证文件存在
        if visqol_exe.exists() and model_file.exists():
            # 确保可执行文件有执行权限
            os.chmod(str(visqol_exe), 0o755)
            print("✅ ViSQOL-rs-py安装完成！")
            print(f"可执行文件: {visqol_exe}")
            print(f"模型文件: {model_file}")
        else:
            print("❌ 预编译文件未找到。请检查包完整性。")
            if not visqol_exe.exists():
                print(f"缺失: {visqol_exe}")
            if not model_file.exists():
                print(f"缺失: {model_file}")

class PostDevelopCommand(develop):
    """开发模式安装后执行的自定义命令"""
    
    def run(self):
        develop.run(self)
        print("开发模式安装完成。")

# 依赖包列表
INSTALL_REQUIRES = [
    "numpy>=1.19.0",  # 用于音频格式转换
]

# 可选依赖
EXTRAS_REQUIRE = {
    "dev": [
        "pytest>=6.0",
        "pytest-cov>=2.0",
        "black>=21.0",
        "flake8>=3.8",
    ],
    "docs": [
        "sphinx>=4.0",
        "sphinx-rtd-theme>=1.0",
    ]
}

# 分类器
CLASSIFIERS = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: MIT License",
    "Operating System :: POSIX :: Linux",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.7",
    "Programming Language :: Python :: 3.8",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Multimedia :: Sound/Audio :: Analysis",
    "Topic :: Scientific/Engineering :: Information Analysis",
]

# 控制台脚本
CONSOLE_SCRIPTS = [
    "visqol-batch=visqol_rs_py.cli:main",
    "visqol-simple=visqol_rs_py.cli:simple_main",
]

if __name__ == "__main__":
    setup(
        name=PACKAGE_NAME,
        version=VERSION,
        description=DESCRIPTION,
        long_description=read_long_description(),
        long_description_content_type="text/markdown",
        author=AUTHOR,
        author_email=AUTHOR_EMAIL,
        url=URL,
        license="MIT",
        packages=find_packages(),
        include_package_data=True,
        package_data={
            "visqol_rs_py": [
                "bin/*",
                "model/*",
                "*.md",
                "*.txt",
                "*.json",
            ]
        },
        install_requires=INSTALL_REQUIRES,
        extras_require=EXTRAS_REQUIRE,
        python_requires=">=3.7",
        classifiers=CLASSIFIERS,
        keywords="audio quality assessment visqol batch processing",
        entry_points={
            "console_scripts": CONSOLE_SCRIPTS,
        },
        cmdclass={
            "install": PostInstallCommand,
            "develop": PostDevelopCommand,
        },
        zip_safe=False,  # 因为包含二进制文件
    )