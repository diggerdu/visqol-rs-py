# ViSQOL-rs-py

一个高效的Python包，用于批量计算音频文件的ViSQOL（Virtual Speech Quality Objective Listener）质量指标。
**Battery-included** - 包含预编译的visqol-rs二进制文件，无需手动编译。

## 特性

- 🚀 **高效并行处理**: 支持多线程并行计算，显著提升处理速度
- 📁 **智能文件匹配**: 自动匹配参考文件和降质文件
- 📊 **详细统计分析**: 提供完整的统计信息和质量指标分析
- 🔧 **Battery-included**: 包含预编译的visqol-rs二进制文件，一键安装即用
- 💻 **命令行友好**: 提供完整的CLI工具和简化版交互界面
- 📝 **丰富输出格式**: 支持JSON格式结果输出和详细日志
- 🎯 **Numpy数组支持**: 直接处理1D numpy数组，无需保存临时文件，大幅减少I/O开销
- ⚡ **原生Rust绑定**: 实验性原生Rust实现，提供6倍性能提升，零子进程开销

## 安装

### 从PyPI安装（推荐）

```bash
pip install visqol-rs-py
```

**一键安装即用** - 包含预编译的二进制文件：
- ✅ 无需安装Rust工具链
- ✅ 无需编译过程
- ✅ 包含所需的模型文件

### 从源码安装

```bash
git clone https://github.com/diggerdu/visqol-rs-py.git
cd visqol-rs-py
pip install -e .
```

### 从Git安装（开发版）

```bash
pip install git+https://github.com/diggerdu/visqol-rs-py.git
```

## 快速开始

### 命令行使用

```bash
# 基本用法
visqol-batch ./reference_audio ./degraded_audio

# 指定输出文件和线程数
visqol-batch ./reference_audio ./degraded_audio -o results.json -w 8

# 检查安装状态
visqol-batch --check

# 查看帮助
visqol-batch --help
```

### Python API使用

#### 文件批量处理

```python
from visqol_rs_py import ViSQOLCalculator

# 创建计算器
calculator = ViSQOLCalculator(max_workers=4)

# 批量计算
results = calculator.calculate_batch(
    reference_dir="./reference_audio",
    degraded_dir="./degraded_audio",
    output_file="results.json"
)

# 查看统计信息
stats = results["statistics"]
print(f"成功处理: {stats['successful']}/{stats['total_files']} 文件")
print(f"平均MOS-LQO: {stats['mos_lqo_mean']:.3f}")
```

#### Numpy数组直接处理（推荐）

**新功能**: 直接使用1D numpy数组进行ViSQOL计算，无需保存为WAV文件，大幅减少I/O开销。

```python
import numpy as np
from visqol_rs_py import ViSQOLCalculator

# 创建计算器
calculator = ViSQOLCalculator(max_workers=4)

# 准备音频数据（1D numpy数组，值范围[-1.0, 1.0]）
sample_rate = 48000
duration = 3.0  # 3秒
t = np.linspace(0, duration, int(sample_rate * duration))

# 参考音频（纯正弦波）
reference_audio = 0.5 * np.sin(2 * np.pi * 440 * t)

# 降质音频（加噪声）
degraded_audio = reference_audio + 0.1 * np.random.randn(len(reference_audio))

# 单个音频对计算
result = calculator.calculate_single_numpy(
    reference_array=reference_audio,
    degraded_array=degraded_audio,
    sample_rate=sample_rate
)

print(f"MOS-LQO分数: {result['mos_lqo']:.3f}")
print(f"处理时间: {result['processing_time']:.2f}秒")

# 批量numpy数组计算
reference_arrays = [reference_audio, reference_audio * 0.8]
degraded_arrays = [degraded_audio, degraded_audio * 0.8]

batch_results = calculator.calculate_batch_numpy(
    reference_arrays=reference_arrays,
    degraded_arrays=degraded_arrays,
    sample_rate=sample_rate
)

print(f"批量处理完成，平均MOS-LQO: {batch_results['statistics']['mos_lqo_mean']:.3f}")
```

#### 原生Rust绑定（最快性能）

**实验性功能**: 使用原生Rust实现，提供最佳性能，无子进程开销。

```python
import numpy as np
import visqol_native

# 创建原生计算器（语音模式，16kHz优化）
calculator = visqol_native.VisqolCalculator.speech_mode()

# 准备音频数据（1D numpy数组，值范围[-1.0, 1.0]）
sample_rate = 16000  # 语音模式使用16kHz
duration = 2.0  # 2秒
t = np.linspace(0, duration, int(sample_rate * duration))

# 参考音频
reference_audio = 0.5 * np.sin(2 * np.pi * 440 * t)

# 降质音频（加噪声）
degraded_audio = reference_audio + 0.05 * np.random.randn(len(reference_audio))

# 直接计算（无文件I/O，无子进程）
result = calculator.calculate(
    reference_audio=reference_audio,
    degraded_audio=degraded_audio,
    sample_rate=sample_rate
)

print(f"MOS-LQO分数: {result.moslqo:.3f}")
print(f"相似度分数: {result.similarity_score:.3f}")
print(f"处理时间: {result.processing_time:.3f}秒")  # ~6x faster!
```

### 简化版交互界面

```bash
python -m visqol_rs_py.cli simple_cli
```

## 支持的音频格式

- **WAV (.wav)** - 主要支持格式
  - 自动转换不支持的位深/采样率到ViSQOL兼容格式
  - 支持 8/16/24/32 位音频（自动转换为16位）
  - 支持多种采样率（自动转换为48kHz）
  - 支持单声道/立体声（立体声自动混合为单声道）

**注意**: 当前版本专注于WAV格式的完美支持，未来版本将支持更多格式。

## 输出结果

### 统计信息

```json
{
  "statistics": {
    "total_files": 10,
    "successful": 10,
    "failed": 0,
    "success_rate": 1.0,
    "total_processing_time": 45.2,
    "average_processing_time": 4.52,
    "mos_lqo_mean": 3.245,
    "mos_lqo_min": 2.891,
    "mos_lqo_max": 4.123,
    "mos_lqo_std": 0.456
  }
}
```

### 详细结果

```json
{
  "results": [
    {
      "reference_file": "./reference/audio1.wav",
      "degraded_file": "./degraded/audio1.wav", 
      "success": true,
      "mos_lqo": 3.245,
      "processing_time": 4.52
    }
  ]
}
```

## 配置选项

### ViSQOLCalculator参数

- `visqol_executable`: ViSQOL可执行文件路径（可选，自动查找）
- `max_workers`: 最大并行线程数（默认：4）
- `verbose`: 是否启用详细日志（默认：True）

### 命令行参数

```
usage: visqol-batch [-h] [-o OUTPUT] [-w WORKERS] [--visqol-path VISQOL_PATH]
                    [-v] [-q] [--check] [--version]
                    [reference_dir] [degraded_dir]

参数说明:
  reference_dir         参考音频文件目录
  degraded_dir          降质音频文件目录
  -o, --output          输出结果文件路径 (JSON格式)
  -w, --workers         并行工作线程数 (默认: 4)
  --visqol-path         ViSQOL可执行文件路径
  -v, --verbose         启用详细输出
  -q, --quiet           静默模式
  --check               检查安装状态
  --version             显示版本信息
```

## 性能优化

### 线程数设置

- **CPU密集型**: 设置为CPU核心数
- **I/O密集型**: 可以设置为CPU核心数的2-4倍
- **内存限制**: 注意每个线程会占用一定内存

```python
import os
optimal_workers = os.cpu_count()  # 获取CPU核心数
calculator = ViSQOLCalculator(max_workers=optimal_workers)
```

### 文件组织建议

```
project/
├── reference/
│   ├── audio1.wav
│   ├── audio2.wav
│   └── audio3.wav
└── degraded/
    ├── audio1.wav  # 与reference中的文件名匹配
    ├── audio2.wav
    └── audio3.wav
```

## 故障排除

### 检查安装状态

```bash
visqol-batch --check
```

### 常见问题

1. **找不到ViSQOL可执行文件**
   ```bash
   # 手动指定路径
   visqol-batch ./ref ./deg --visqol-path /path/to/visqol
   ```

2. **Rust工具链问题**
   ```bash
   # 重新安装Rust
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   ```

3. **权限问题**
   ```bash
   # 确保可执行文件有执行权限
   chmod +x /path/to/visqol
   ```

### 调试模式

```python
# 启用详细日志
calculator = ViSQOLCalculator(verbose=True)

# 或使用命令行
visqol-batch ./ref ./deg --verbose
```

## 系统要求

- **操作系统**: Linux x86-64
- **Python**: 3.7+
- **内存**: 建议4GB+
- **磁盘空间**: 100MB+（包含预编译二进制文件）

## 许可证

本项目基于MIT许可证开源。详见[LICENSE](LICENSE)文件。

## 作者

- **作者**: Xingjian Du
- **邮箱**: xingjian.du97@gmail.com
- **许可证**: MIT

## 贡献

欢迎提交Issue和Pull Request！

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启Pull Request

## 相关项目

- [visqol-rs](https://github.com/dstrub18/visqol-rs) - Rust实现的ViSQOL
- [ViSQOL](https://github.com/google/visqol) - Google的原始ViSQOL实现

## 更新日志

### v1.2.0 (实验性)
- **新增**: 原生Rust Python绑定 (`visqol_native`)
- **性能**: 6倍性能提升，无子进程和文件I/O开销
- **API**: 新增 `visqol_native.VisqolCalculator` 类
- **支持**: 语音模式(16kHz)原生计算
- **限制**: 当前仅支持语音模式，音频模式开发中

### v1.1.0
- **新增**: Numpy数组直接处理API
- **新增**: `calculate_single_numpy()` 和 `calculate_batch_numpy()` 方法
- **优化**: 减少临时文件I/O开销
- **改进**: 音频格式自动转换支持32位音频

### v1.0.0
- 初始版本发布
- 支持批量ViSQOL计算
- 自动依赖安装
- 完整的CLI工具

## 支持

如果您在使用过程中遇到问题，请：

1. 查看[故障排除](#故障排除)部分
2. 搜索已有的[Issues](https://github.com/diggerdu/visqol-rs-py/issues)
3. 创建新的Issue并提供详细信息

---

**注意**: 本包目前专门针对Linux x86-64平台优化。其他平台的支持正在开发中。