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
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess

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
    
    def calculate_single(self, reference_file: str, degraded_file: str) -> Dict:
        """计算单对音频文件的ViSQOL指标
        
        Args:
            reference_file: 参考音频文件路径
            degraded_file: 降质音频文件路径
            
        Returns:
            包含ViSQOL计算结果的字典
        """
        start_time = time.time()
        
        try:
            # 构建命令
            cmd = [
                self.visqol_executable,
                "--reference_file", str(reference_file),
                "--degraded_file", str(degraded_file),
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