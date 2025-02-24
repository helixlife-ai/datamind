"""
执行器模块，负责协调搜索和交付物生成
"""
import logging
import pandas as pd
from typing import Dict, List, Optional, Any
import os
from datetime import datetime, date
import numpy as np
import json
from pathlib import Path
import hashlib
from ..utils.common import DateTimeEncoder

logger = logging.getLogger(__name__)


class ResultFormatter:
    """统一的结果格式化器"""
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def format(self, results: Dict) -> Dict:
        """格式化结果
        
        Args:
            results: 要格式化的结果
            
        Returns:
            格式化后的结果
        """
        return self._format_json(results)

    def _format_json(self, results: Dict) -> Dict:
        """格式化为JSON结构"""
        return {
            "metadata": {
                "original_query": results.get("metadata", {}).get("original_query", ""),
                "generated_at": datetime.now().isoformat(),
                "version": "1.0",
                "summary": {
                    "total_results": results["stats"]["total"],
                    "structured_count": results["stats"]["structured_count"],
                    "vector_count": results["stats"]["vector_count"]
                }
            },
            "results": {
                "structured": results.get("structured", []),
                "vector": results.get("vector", [])
            }
        }

class ResultSaver:
    """统一的结果保存器"""
    def __init__(self, work_dir: str = "output", logger: Optional[logging.Logger] = None):
        self.work_dir = work_dir
        self.logger = logger or logging.getLogger(__name__)
        self.formatter = ResultFormatter(logger=self.logger)

    def save(self, results: Dict, filename: str) -> str:
        """保存结果
        
        Args:
            results: 要保存的结果
            filename: 文件名
            
        Returns:
            str: 保存文件的路径
        """
        self._ensure_dir()
        filepath = self._get_filepath(filename, 'json')
        
        try:
            formatted_data = self.formatter.format(results)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            
            self.logger.info(f"文件已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存文件失败: {str(e)}")
            return None
            
    def _ensure_dir(self):
        """确保输出目录存在"""
        os.makedirs(self.work_dir, exist_ok=True)
        
    def _get_filepath(self, filename: str, extension: str) -> str:
        """获取完整的文件路径"""
        return os.path.join(self.work_dir, f"{filename}.{extension}")
        
    def _json_serializer(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if pd.isna(obj):
            return None
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine, work_dir="work_dir", logger: Optional[logging.Logger] = None):
        """初始化搜索计划执行器
        
        Args:
            search_engine: 搜索引擎实例
            work_dir: 工作目录
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.engine = search_engine
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用新的内部格式化器和保存器
        self.result_saver = ResultSaver(work_dir=str(self.work_dir), logger=self.logger)

    def set_work_dir(self, work_dir: str):
        """设置工作目录"""
        self.work_dir = work_dir
        # 更新所有保存器的工作目录
        self.result_saver.work_dir = work_dir
            
    async def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划"""
        try:
            # 创建执行结果目录
            execution_dir = self.work_dir / "search_results" 
            execution_dir.mkdir(parents=True, exist_ok=True)
            
            # 初始化文件路径跟踪
            saved_files = {
                "plan": str(execution_dir / "input_plan.json"),
                "final_results": str(execution_dir / "final_results.json"),
                "execution_stats": str(execution_dir / "execution_stats.json"),
                "search_results": {
                    "structured": [],
                    "vector": []
                }
            }
            
            # 保存输入的计划
            with open(saved_files["plan"], "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            
            # 初始化结果结构
            results = self._initialize_results(plan)
            # 更新结果中的文件路径
            results["saved_files"] = saved_files  # 在这里添加初始文件路径
            
            # 执行基础搜索
            search_results = await self._execute_basic_search(plan, results, execution_dir)
            if search_results:
                results = search_results
            
            # 保存最终结果
            with open(saved_files["final_results"], "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 保存执行统计信息
            stats = {
                "execution_time": datetime.now().isoformat(),
                "query": plan.get("metadata", {}).get("original_query", ""),
                "total_results": results["stats"]["total"],
                "structured_results": results["stats"]["structured_count"],
                "vector_results": results["stats"]["vector_count"]
            }
            with open(saved_files["execution_stats"], "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            
            return results
            
        except Exception as e:
            self.logger.error(f"执行检索计划失败: {str(e)}", exc_info=True)
            raise

    def _initialize_results(self, plan: Dict) -> Dict:
        """初始化结果结构"""
        results = {
            "structured": [],
            "vector": [],
            "stats": {
                "structured_count": 0,
                "vector_count": 0,
                "total": 0
            },
            "metadata": {
                "original_query": plan.get("metadata", {}).get("original_query", ""),
                "generated_at": plan.get("metadata", {}).get("generated_at", ""),
                "execution_time": datetime.now().isoformat()
            }
        }
        return results

    async def _execute_basic_search(self, plan: Dict, results: Dict, execution_dir: Path):
        """执行基础搜索"""
        try:
            seen_fingerprints = set()
            search_results_dir = execution_dir / "search_results"
            search_results_dir.mkdir(exist_ok=True)
            
            # 执行结构化查询
            if plan.get("structured_queries"):
                structured_dir = search_results_dir / "structured"
                structured_dir.mkdir(exist_ok=True)
                
                for i, query in enumerate(plan["structured_queries"]):
                    try:
                        df = self.engine.execute_structured_query(query)
                        if df is not None and not df.empty:
                            # 将DataFrame转换为记录之前处理Timestamp
                            for col in df.select_dtypes(include=['datetime64[ns]']).columns:
                                df[col] = df[col].astype(str)
                                
                            records = df.to_dict('records')
                            filtered_records = []
                            for record in records:
                                fingerprint = self._generate_content_fingerprint(record.get('data', ''))
                                if fingerprint not in seen_fingerprints:
                                    seen_fingerprints.add(fingerprint)
                                    filtered_records.append(record)
                                    results["structured"].append(record)
                            
                            # 保存结果并记录文件路径
                            result_path = structured_dir / f"query_{i+1}_results.json"
                            with open(result_path, "w", encoding="utf-8") as f:
                                json.dump(filtered_records, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
                            results["saved_files"]["search_results"]["structured"].append(str(result_path))
                    except Exception as e:
                        self.logger.error(f"结构化查询执行失败: {str(e)}", exc_info=True)
                        continue
            
            # 执行向量查询
            if plan.get("vector_queries"):
                vector_dir = search_results_dir / "vector"
                vector_dir.mkdir(exist_ok=True)
                
                for i, vector_query in enumerate(plan["vector_queries"]):
                    try:
                        vector_results = self.engine.execute_vector_search(
                            vector_query["reference_text"],
                            vector_query["top_k"]
                        )
                        
                        if vector_results:
                            filtered_results = []
                            threshold = vector_query["similarity_threshold"]
                            for result in vector_results:
                                if result["similarity"] >= threshold:
                                    if isinstance(result["similarity"], np.float32):
                                        result["similarity"] = float(result["similarity"])
                                    
                                    fingerprint = self._generate_content_fingerprint(result.get('data', ''))
                                    if fingerprint not in seen_fingerprints:
                                        seen_fingerprints.add(fingerprint)
                                        filtered_results.append(result)
                                        results["vector"].append(result)
                            
                            # 保存结果并记录文件路径
                            result_path = vector_dir / f"query_{i+1}_results.json"
                            with open(result_path, "w", encoding="utf-8") as f:
                                json.dump(filtered_results, f, ensure_ascii=False, indent=2)
                            results["saved_files"]["search_results"]["vector"].append(str(result_path))
                    except Exception as e:
                        self.logger.error(f"向量查询执行失败: {str(e)}", exc_info=True)
                        continue
            
            # 更新统计信息
            results["stats"]["structured_count"] = len(results["structured"])
            results["stats"]["vector_count"] = len(results["vector"])
            results["stats"]["total"] = (
                results["stats"]["structured_count"] + 
                results["stats"]["vector_count"]
            )
            
            return results
            
        except Exception as e:
            self.logger.error(f"基础搜索执行失败: {str(e)}", exc_info=True)
            raise

    def _generate_content_fingerprint(self, content: str) -> str:
        """生成内容指纹
        
        Args:
            content: 需要生成指纹的内容
            
        Returns:
            str: 内容的唯一指纹
        """
        # 预处理内容
        processed_content = str(content).lower()  # 转小写
        processed_content = ' '.join(processed_content.split())  # 规范化空白字符
        
        # 生成MD5指纹
        return hashlib.md5(processed_content.encode('utf-8')).hexdigest()

    def set_search_engine(self, search_engine):
        """设置搜索引擎"""
        self.engine = search_engine
