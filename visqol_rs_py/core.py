"""
ViSQOL批量计算器核心模块

提供ViSQOLCalculator类，用于批量计算音频文件的ViSQOL质量指标。
支持多线程并行处理、自动文件匹配、详细统计分析等功能。
"""

import os
import re
import json
import time
import logging
import tempfile
import wave
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import numpy as np

from .utils import get_visqol_executable_path, setup_logging


class ViSQOLCalculator:
    """ViSQOL批量计算器
    
    用于批量计算参考音频和降质音频之间的ViSQOL质量指标。
    支持多种音频格式，提供并行处理和详细的统计分析。
    """
    
    def __init__(self, 
                 visqol_executable: Optional[str] = None,
                 max_workers: int = 4,
                 verbose: bool = True):
        """初始化ViSQOL计算器
        
        Args:
            visqol_executable: ViSQOL可执行文件路径，如果为None则自动查找
            max_workers: 最大并行工作线程数
            verbose: 是否启用详细日志输出
        """
        self.visqol_executable = visqol_executable or get_visqol_executable_path()
        self.max_workers = max_workers
        self.verbose = verbose
        
        # 设置日志
        self.logger = setup_logging(verbose)
        
        # 验证ViSQOL可执行文件
        if not os.path.exists(self.visqol_executable):
            raise FileNotFoundError(f"ViSQOL可执行文件未找到: {self.visqol_executable}")
        
        # 查找模型文件
        self.model_file = self._find_model_file()
        if not self.model_file:
            raise FileNotFoundError("ViSQOL模型文件未找到")
        
        self.logger.info(f"ViSQOL可执行文件: {self.visqol_executable}")
        self.logger.info(f"模型文件: {self.model_file}")
        self.logger.info(f"最大工作线程数: {self.max_workers}")
    
    def _find_model_file(self) -> Optional[str]:
        """查找ViSQOL模型文件"""
        # 可能的模型文件路径（按优先级排序）
        possible_paths = [
            # 包内预编译模型（最高优先级）
            os.path.join(os.path.dirname(__file__), "model", "libsvm_nu_svr_model.txt"),
            # 包内路径 - 基于可执行文件位置
            os.path.join(os.path.dirname(self.visqol_executable), "..", "model", "libsvm_nu_svr_model.txt"),
            os.path.join(os.path.dirname(self.visqol_executable), "model", "libsvm_nu_svr_model.txt"),
            # 兼容性路径 - 基于包目录（用于开发/测试）
            os.path.join(os.path.dirname(__file__), "visqol-rs", "model", "libsvm_nu_svr_model.txt"),
            os.path.join(os.path.dirname(__file__), "..", "visqol-rs", "model", "libsvm_nu_svr_model.txt"),
            # 相对路径（用于开发）
            "./visqol-rs/model/libsvm_nu_svr_model.txt",
            "./model/libsvm_nu_svr_model.txt",
            # 绝对路径
            "/usr/local/share/visqol/model/libsvm_nu_svr_model.txt",
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return os.path.abspath(path)  # 返回绝对路径
        
        return None
    
    def _validate_and_convert_audio(self, audio_file: str) -> str:
        """验证并转换音频文件格式，确保ViSQOL可以处理
        
        Args:
            audio_file: 音频文件路径
            
        Returns:
            处理后的音频文件路径（可能是临时文件）
            
        Raises:
            ValueError: 如果音频文件无效或转换失败
        """
        try:
            # 首先检查是否是WAV文件
            if not audio_file.lower().endswith('.wav'):
                raise ValueError(f"仅支持WAV格式文件，当前文件: {audio_file}")
            
            # 检查WAV文件格式
            with wave.open(audio_file, 'rb') as wav_file:
                sample_rate = wav_file.getframerate()
                bits_per_sample = wav_file.getsampwidth() * 8
                channels = wav_file.getnchannels()
                
                self.logger.debug(f"音频文件信息: {audio_file}")
                self.logger.debug(f"  采样率: {sample_rate} Hz")
                self.logger.debug(f"  位深: {bits_per_sample} bits")
                self.logger.debug(f"  声道: {channels}")
                
                # ViSQOL支持的格式检查
                supported_sample_rates = [8000, 16000, 22050, 44100, 48000]
                supported_bits = [16]  # ViSQOL主要支持16位
                
                needs_conversion = False
                conversion_reason = []
                
                if sample_rate not in supported_sample_rates:
                    needs_conversion = True
                    conversion_reason.append(f"采样率 {sample_rate} Hz")
                
                if bits_per_sample not in supported_bits:
                    needs_conversion = True
                    conversion_reason.append(f"位深 {bits_per_sample} bits")
                
                if channels != 1:
                    needs_conversion = True
                    conversion_reason.append(f"声道数 {channels}")
                
                # 如果不需要转换，直接返回原文件
                if not needs_conversion:
                    return audio_file
                
                # 需要转换，记录日志
                self.logger.info(f"需要转换音频格式: {', '.join(conversion_reason)}")
                self.logger.info(f"目标格式: 48000 Hz, 16 bits, 单声道")
                
                # 转换音频文件
                return self._convert_audio_format(audio_file, wav_file)
                
        except wave.Error as e:
            raise ValueError(f"无效的WAV文件: {audio_file}, 错误: {e}")
        except Exception as e:
            raise ValueError(f"音频文件处理失败: {audio_file}, 错误: {e}")
    
    def _convert_audio_format(self, audio_file: str, source_wav) -> str:
        """转换音频文件格式为ViSQOL支持的格式
        
        Args:
            audio_file: 原始音频文件路径
            source_wav: 已打开的wave文件对象
            
        Returns:
            转换后的临时文件路径
        """
        # 读取原始音频数据
        frames = source_wav.readframes(source_wav.getnframes())
        original_sample_rate = source_wav.getframerate()
        original_channels = source_wav.getnchannels()
        original_sampwidth = source_wav.getsampwidth()
        
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav', prefix='visqol_converted_')
        os.close(temp_fd)  # 关闭文件描述符，让wave模块使用
        
        try:
            # 目标格式
            target_sample_rate = 48000
            target_channels = 1
            target_sampwidth = 2  # 16位
            
            # 简单的格式转换（基础实现）
            
            # 将音频数据转换为numpy数组
            if original_sampwidth == 1:
                audio_data = np.frombuffer(frames, dtype=np.uint8)
                audio_data = (audio_data.astype(np.float32) - 128) / 128.0
            elif original_sampwidth == 2:
                audio_data = np.frombuffer(frames, dtype=np.int16)
                audio_data = audio_data.astype(np.float32) / 32767.0
            elif original_sampwidth == 3:
                # 24位音频处理
                audio_bytes = np.frombuffer(frames, dtype=np.uint8)
                audio_data = []
                for i in range(0, len(audio_bytes), 3):
                    sample = int.from_bytes(audio_bytes[i:i+3], byteorder='little', signed=True)
                    audio_data.append(sample)
                audio_data = np.array(audio_data, dtype=np.float32) / 8388607.0
            elif original_sampwidth == 4:
                audio_data = np.frombuffer(frames, dtype=np.int32)
                audio_data = audio_data.astype(np.float32) / 2147483647.0
            else:
                raise ValueError(f"不支持的音频位深: {original_sampwidth * 8} bits")
            
            # 处理多声道转单声道
            if original_channels > 1:
                audio_data = audio_data.reshape(-1, original_channels)
                audio_data = np.mean(audio_data, axis=1)  # 取平均值转为单声道
            
            # 重采样（简单的线性插值）
            if original_sample_rate != target_sample_rate:
                duration = len(audio_data) / original_sample_rate
                target_length = int(duration * target_sample_rate)
                indices = np.linspace(0, len(audio_data) - 1, target_length)
                audio_data = np.interp(indices, np.arange(len(audio_data)), audio_data)
            
            # 转换为16位整数
            audio_data = np.clip(audio_data, -1.0, 1.0)
            audio_data = (audio_data * 32767).astype(np.int16)
            
            # 写入转换后的文件
            with wave.open(temp_path, 'wb') as temp_wav:
                temp_wav.setnchannels(target_channels)
                temp_wav.setsampwidth(target_sampwidth)
                temp_wav.setframerate(target_sample_rate)
                temp_wav.writeframes(audio_data.tobytes())
            
            self.logger.info(f"音频转换完成: {audio_file} -> {temp_path}")
            return temp_path
            
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise ValueError(f"音频格式转换失败: {e}")
    
    def calculate_single(self, reference_file: str, degraded_file: str) -> Dict:
        """计算单对音频文件的ViSQOL指标
        
        Args:
            reference_file: 参考音频文件路径
            degraded_file: 降质音频文件路径
            
        Returns:
            包含ViSQOL计算结果的字典
        """
        start_time = time.time()
        converted_ref = None
        converted_deg = None
        
        try:
            # 预处理音频文件，确保格式兼容
            self.logger.debug(f"预处理参考文件: {reference_file}")
            processed_ref = self._validate_and_convert_audio(reference_file)
            converted_ref = processed_ref if processed_ref != reference_file else None
            
            self.logger.debug(f"预处理降质文件: {degraded_file}")
            processed_deg = self._validate_and_convert_audio(degraded_file)
            converted_deg = processed_deg if processed_deg != degraded_file else None
            
            # 构建命令
            cmd = [
                self.visqol_executable,
                "--reference_file", str(processed_ref),
                "--degraded_file", str(processed_deg),
                "--similarity_to_quality_model", self.model_file,
                "--verbose"
            ]
            
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # 60秒超时
            )
            
            if result.returncode != 0:
                error_msg = f"ViSQOL执行失败: {result.stderr}"
                self.logger.error(error_msg)
                return {
                    "reference_file": reference_file,
                    "degraded_file": degraded_file,
                    "success": False,
                    "error": error_msg,
                    "processing_time": time.time() - start_time
                }
            
            # 解析输出
            mos_lqo = self._parse_mos_lqo(result.stdout)
            
            if mos_lqo is None:
                error_msg = "无法从输出中解析MOS-LQO分数"
                self.logger.error(f"{error_msg}: {result.stdout}")
                return {
                    "reference_file": reference_file,
                    "degraded_file": degraded_file,
                    "success": False,
                    "error": error_msg,
                    "processing_time": time.time() - start_time
                }
            
            processing_time = time.time() - start_time
            
            result_dict = {
                "reference_file": reference_file,
                "degraded_file": degraded_file,
                "success": True,
                "mos_lqo": mos_lqo,
                "processing_time": processing_time
            }
            
            self.logger.info(f"成功计算: {os.path.basename(reference_file)} -> {mos_lqo:.3f} ({processing_time:.2f}s)")
            return result_dict
            
        except subprocess.TimeoutExpired:
            error_msg = "ViSQOL执行超时"
            self.logger.error(error_msg)
            return {
                "reference_file": reference_file,
                "degraded_file": degraded_file,
                "success": False,
                "error": error_msg,
                "processing_time": time.time() - start_time
            }
        except Exception as e:
            error_msg = f"执行过程中发生错误: {str(e)}"
            self.logger.error(error_msg)
            return {
                "reference_file": reference_file,
                "degraded_file": degraded_file,
                "success": False,
                "error": error_msg,
                "processing_time": time.time() - start_time
            }
        finally:
            # 清理临时文件
            if converted_ref and os.path.exists(converted_ref):
                try:
                    os.unlink(converted_ref)
                    self.logger.debug(f"已清理临时参考文件: {converted_ref}")
                except Exception as e:
                    self.logger.warning(f"清理临时参考文件失败: {e}")
            
            if converted_deg and os.path.exists(converted_deg):
                try:
                    os.unlink(converted_deg)
                    self.logger.debug(f"已清理临时降质文件: {converted_deg}")
                except Exception as e:
                    self.logger.warning(f"清理临时降质文件失败: {e}")
    
    def _parse_mos_lqo(self, output: str) -> Optional[float]:
        """从ViSQOL输出中解析MOS-LQO分数"""
        # 查找MOS-LQO分数的正则表达式
        patterns = [
            r"MOS-LQO:\s*([\d.]+)",
            r"mos_lqo:\s*([\d.]+)",
            r"Quality score:\s*([\d.]+)",
            r"Score:\s*([\d.]+)"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def find_audio_files(self, directory: str) -> List[str]:
        """查找目录中的音频文件
        
        Args:
            directory: 要搜索的目录路径
            
        Returns:
            音频文件路径列表
        """
        audio_extensions = {'.wav', '.flac', '.mp3', '.m4a', '.aac', '.ogg'}
        audio_files = []
        
        directory_path = Path(directory)
        if not directory_path.exists():
            self.logger.error(f"目录不存在: {directory}")
            return []
        
        for file_path in directory_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in audio_extensions:
                audio_files.append(str(file_path))
        
        audio_files.sort()
        self.logger.info(f"在 {directory} 中找到 {len(audio_files)} 个音频文件")
        return audio_files
    
    def match_files(self, reference_files: List[str], degraded_files: List[str]) -> List[Tuple[str, str]]:
        """匹配参考文件和降质文件
        
        Args:
            reference_files: 参考音频文件列表
            degraded_files: 降质音频文件列表
            
        Returns:
            匹配的文件对列表
        """
        matched_pairs = []
        
        # 创建基于文件名的映射
        degraded_map = {}
        for degraded_file in degraded_files:
            basename = Path(degraded_file).stem
            degraded_map[basename] = degraded_file
        
        # 匹配文件
        for reference_file in reference_files:
            ref_basename = Path(reference_file).stem
            if ref_basename in degraded_map:
                matched_pairs.append((reference_file, degraded_map[ref_basename]))
            else:
                self.logger.warning(f"未找到匹配的降质文件: {ref_basename}")
        
        self.logger.info(f"成功匹配 {len(matched_pairs)} 对文件")
        return matched_pairs
    
    def calculate_batch(self, 
                       reference_dir: str, 
                       degraded_dir: str,
                       output_file: Optional[str] = None) -> Dict:
        """批量计算ViSQOL指标
        
        Args:
            reference_dir: 参考音频文件目录
            degraded_dir: 降质音频文件目录
            output_file: 输出结果文件路径（可选）
            
        Returns:
            包含所有计算结果和统计信息的字典
        """
        start_time = time.time()
        
        # 查找音频文件
        self.logger.info("正在查找音频文件...")
        reference_files = self.find_audio_files(reference_dir)
        degraded_files = self.find_audio_files(degraded_dir)
        
        if not reference_files:
            raise ValueError(f"在参考目录中未找到音频文件: {reference_dir}")
        if not degraded_files:
            raise ValueError(f"在降质目录中未找到音频文件: {degraded_dir}")
        
        # 匹配文件
        self.logger.info("正在匹配文件...")
        file_pairs = self.match_files(reference_files, degraded_files)
        
        if not file_pairs:
            raise ValueError("未找到匹配的文件对")
        
        # 并行计算
        self.logger.info(f"开始并行计算 {len(file_pairs)} 对文件...")
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_pair = {
                executor.submit(self.calculate_single, ref, deg): (ref, deg)
                for ref, deg in file_pairs
            }
            
            # 收集结果
            for future in as_completed(future_to_pair):
                result = future.result()
                results.append(result)
        
        # 计算统计信息
        total_time = time.time() - start_time
        stats = self._calculate_statistics(results, total_time)
        
        # 准备最终结果
        final_result = {
            "results": results,
            "statistics": stats,
            "metadata": {
                "reference_dir": reference_dir,
                "degraded_dir": degraded_dir,
                "total_pairs": len(file_pairs),
                "max_workers": self.max_workers,
                "visqol_executable": self.visqol_executable,
                "model_file": self.model_file
            }
        }
        
        # 保存结果到文件
        if output_file:
            self._save_results(final_result, output_file)
        
        # 打印摘要
        self._print_summary(stats)
        
        return final_result
    
    def _calculate_statistics(self, results: List[Dict], total_time: float) -> Dict:
        """计算统计信息"""
        successful_results = [r for r in results if r["success"]]
        failed_results = [r for r in results if not r["success"]]
        
        stats = {
            "total_files": len(results),
            "successful": len(successful_results),
            "failed": len(failed_results),
            "success_rate": len(successful_results) / len(results) if results else 0,
            "total_processing_time": total_time,
            "average_processing_time": sum(r["processing_time"] for r in results) / len(results) if results else 0
        }
        
        if successful_results:
            mos_scores = [r["mos_lqo"] for r in successful_results]
            stats.update({
                "mos_lqo_mean": sum(mos_scores) / len(mos_scores),
                "mos_lqo_min": min(mos_scores),
                "mos_lqo_max": max(mos_scores),
                "mos_lqo_std": self._calculate_std(mos_scores)
            })
        
        return stats
    
    def _calculate_std(self, values: List[float]) -> float:
        """计算标准差"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5
    
    def _save_results(self, results: Dict, output_file: str):
        """保存结果到文件"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            self.logger.info(f"结果已保存到: {output_file}")
        except Exception as e:
            self.logger.error(f"保存结果失败: {e}")
    
    def _print_summary(self, stats: Dict):
        """打印计算摘要"""
        self.logger.info("=" * 50)
        self.logger.info("ViSQOL批量计算完成")
        self.logger.info("=" * 50)
        self.logger.info(f"总文件数: {stats['total_files']}")
        self.logger.info(f"成功处理: {stats['successful']}")
        self.logger.info(f"处理失败: {stats['failed']}")
        self.logger.info(f"成功率: {stats['success_rate']:.1%}")
        self.logger.info(f"总处理时间: {stats['total_processing_time']:.2f}秒")
        self.logger.info(f"平均处理时间: {stats['average_processing_time']:.2f}秒/文件")
        
        if 'mos_lqo_mean' in stats:
            self.logger.info(f"MOS-LQO平均值: {stats['mos_lqo_mean']:.3f}")
            self.logger.info(f"MOS-LQO范围: {stats['mos_lqo_min']:.3f} - {stats['mos_lqo_max']:.3f}")
            self.logger.info(f"MOS-LQO标准差: {stats['mos_lqo_std']:.3f}")
        
        self.logger.info("=" * 50)
    
    def _numpy_array_to_wav(self, audio_data: np.ndarray, sample_rate: int = 48000) -> str:
        """将numpy数组转换为临时WAV文件
        
        Args:
            audio_data: 1D numpy音频数组，值范围应在[-1.0, 1.0]
            sample_rate: 采样率，默认48000Hz
            
        Returns:
            临时WAV文件路径
            
        Raises:
            ValueError: 如果音频数据格式无效
        """
        # 验证输入
        if not isinstance(audio_data, np.ndarray):
            raise ValueError("audio_data必须是numpy数组")
        
        if audio_data.ndim != 1:
            raise ValueError("audio_data必须是1D数组")
        
        if len(audio_data) == 0:
            raise ValueError("audio_data不能为空")
        
        # 检查数据范围
        if np.max(np.abs(audio_data)) > 1.0:
            self.logger.warning("音频数据超出[-1.0, 1.0]范围，将进行归一化")
            max_val = np.max(np.abs(audio_data))
            audio_data = audio_data / max_val
        
        # 创建临时文件
        temp_fd, temp_path = tempfile.mkstemp(suffix='.wav', prefix='visqol_numpy_')
        os.close(temp_fd)
        
        try:
            # 转换为16位整数
            audio_data_int16 = np.clip(audio_data, -1.0, 1.0)
            audio_data_int16 = (audio_data_int16 * 32767).astype(np.int16)
            
            # 写入WAV文件
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)  # 单声道
                wav_file.setsampwidth(2)  # 16位
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(audio_data_int16.tobytes())
            
            self.logger.debug(f"Numpy数组转换为WAV文件: {temp_path}")
            self.logger.debug(f"  数组长度: {len(audio_data)}")
            self.logger.debug(f"  采样率: {sample_rate} Hz")
            self.logger.debug(f"  时长: {len(audio_data) / sample_rate:.2f}秒")
            
            return temp_path
            
        except Exception as e:
            # 清理临时文件
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise ValueError(f"Numpy数组转WAV失败: {e}")
    
    def calculate_single_numpy(self, 
                              reference_array: np.ndarray, 
                              degraded_array: np.ndarray,
                              sample_rate: int = 48000) -> Dict:
        """使用numpy数组计算单对音频的ViSQOL指标
        
        Args:
            reference_array: 参考音频的1D numpy数组，值范围[-1.0, 1.0]
            degraded_array: 降质音频的1D numpy数组，值范围[-1.0, 1.0]
            sample_rate: 采样率，默认48000Hz
            
        Returns:
            包含ViSQOL计算结果的字典
        """
        start_time = time.time()
        ref_temp_file = None
        deg_temp_file = None
        
        try:
            # 转换numpy数组为临时WAV文件
            self.logger.debug("将参考音频numpy数组转换为WAV文件")
            ref_temp_file = self._numpy_array_to_wav(reference_array, sample_rate)
            
            self.logger.debug("将降质音频numpy数组转换为WAV文件")
            deg_temp_file = self._numpy_array_to_wav(degraded_array, sample_rate)
            
            # 构建命令
            cmd = [
                self.visqol_executable,
                "--reference_file", ref_temp_file,
                "--degraded_file", deg_temp_file,
                "--similarity_to_quality_model", self.model_file,
                "--verbose"
            ]
            
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                error_msg = f"ViSQOL执行失败: {result.stderr}"
                self.logger.error(error_msg)
                return {
                    "reference_array_shape": reference_array.shape,
                    "degraded_array_shape": degraded_array.shape,
                    "sample_rate": sample_rate,
                    "success": False,
                    "error": error_msg,
                    "processing_time": time.time() - start_time
                }
            
            # 解析输出
            mos_lqo = self._parse_mos_lqo(result.stdout)
            
            if mos_lqo is None:
                error_msg = "无法从输出中解析MOS-LQO分数"
                self.logger.error(f"{error_msg}: {result.stdout}")
                return {
                    "reference_array_shape": reference_array.shape,
                    "degraded_array_shape": degraded_array.shape,
                    "sample_rate": sample_rate,
                    "success": False,
                    "error": error_msg,
                    "processing_time": time.time() - start_time
                }
            
            processing_time = time.time() - start_time
            
            result_dict = {
                "reference_array_shape": reference_array.shape,
                "degraded_array_shape": degraded_array.shape,
                "sample_rate": sample_rate,
                "success": True,
                "mos_lqo": mos_lqo,
                "processing_time": processing_time
            }
            
            self.logger.info(f"成功计算numpy数组: {reference_array.shape} -> {mos_lqo:.3f} ({processing_time:.2f}s)")
            return result_dict
            
        except Exception as e:
            error_msg = f"Numpy数组计算过程中发生错误: {str(e)}"
            self.logger.error(error_msg)
            return {
                "reference_array_shape": reference_array.shape if isinstance(reference_array, np.ndarray) else "invalid",
                "degraded_array_shape": degraded_array.shape if isinstance(degraded_array, np.ndarray) else "invalid",
                "sample_rate": sample_rate,
                "success": False,
                "error": error_msg,
                "processing_time": time.time() - start_time
            }
        finally:
            # 清理临时文件
            if ref_temp_file and os.path.exists(ref_temp_file):
                try:
                    os.unlink(ref_temp_file)
                    self.logger.debug(f"已清理临时参考文件: {ref_temp_file}")
                except Exception as e:
                    self.logger.warning(f"清理临时参考文件失败: {e}")
            
            if deg_temp_file and os.path.exists(deg_temp_file):
                try:
                    os.unlink(deg_temp_file)
                    self.logger.debug(f"已清理临时降质文件: {deg_temp_file}")
                except Exception as e:
                    self.logger.warning(f"清理临时降质文件失败: {e}")
    
    def calculate_batch_numpy(self, 
                             reference_arrays: List[np.ndarray], 
                             degraded_arrays: List[np.ndarray],
                             sample_rate: int = 48000) -> Dict:
        """批量计算numpy数组的ViSQOL指标
        
        Args:
            reference_arrays: 参考音频numpy数组列表
            degraded_arrays: 降质音频numpy数组列表
            sample_rate: 采样率，默认48000Hz
            
        Returns:
            包含所有计算结果和统计信息的字典
        """
        start_time = time.time()
        
        # 验证输入
        if len(reference_arrays) != len(degraded_arrays):
            raise ValueError("参考数组和降质数组的数量必须相同")
        
        if not reference_arrays:
            raise ValueError("数组列表不能为空")
        
        self.logger.info(f"开始并行计算 {len(reference_arrays)} 对numpy数组...")
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_index = {
                executor.submit(self.calculate_single_numpy, ref_arr, deg_arr, sample_rate): i
                for i, (ref_arr, deg_arr) in enumerate(zip(reference_arrays, degraded_arrays))
            }
            
            # 收集结果
            for future in as_completed(future_to_index):
                result = future.result()
                result["array_index"] = future_to_index[future]  # 添加数组索引
                results.append(result)
        
        # 按索引排序结果
        results.sort(key=lambda x: x["array_index"])
        
        # 计算统计信息
        total_time = time.time() - start_time
        stats = self._calculate_statistics(results, total_time)
        
        # 准备最终结果
        final_result = {
            "results": results,
            "statistics": stats,
            "metadata": {
                "total_arrays": len(reference_arrays),
                "sample_rate": sample_rate,
                "max_workers": self.max_workers,
                "visqol_executable": self.visqol_executable,
                "model_file": self.model_file
            }
        }
        
        # 打印摘要
        self._print_summary(stats)
        
        return final_result