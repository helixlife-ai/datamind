"""
执行器模块，负责协调搜索和交付物生成
"""
import logging
import pandas as pd
from typing import Dict, List, Optional, Any
import os
from datetime import datetime, date
from collections import defaultdict
import numpy as np
from itertools import combinations
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib
import time

from .formatters import (
    HTMLFormatter, 
    MarkdownFormatter, 
    JSONFormatter, 
    ExcelFormatter,
    SearchResultFormatter
)
from .savers import (
    SaverFactory
)
from .analyzers import ResultAnalyzer
from ..utils.common import DateTimeEncoder
logger = logging.getLogger(__name__)

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine, work_dir="output", logger: Optional[logging.Logger] = None):
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
        self.nlp_processor = None  # 用于文本分析，后续初始化
        self.knowledge_graph = None  # 用于关系分析，后续初始化
        self.supported_formats = ['csv', 'json', 'excel', 'html', 'md']
        
        # 初始化分析器，传递logger
        self.analyzer = ResultAnalyzer(logger=self.logger)
        
        # 初始化保存器工厂，传递logger
        self.saver_factory = SaverFactory(logger=self.logger)
        
        # 初始化格式化器字典，传递logger
        self.formatters = {
            'html': HTMLFormatter(logger=self.logger),
            'md': MarkdownFormatter(logger=self.logger),
            'json': JSONFormatter(logger=self.logger),
            'excel': ExcelFormatter(logger=self.logger),
            'csv': SearchResultFormatter(logger=self.logger)
        }
        
        # 使用工厂创建保存器
        self.savers = {
            format_type: self.saver_factory.create_saver(format_type, self.work_dir)
            for format_type in self.supported_formats
        }

    def set_work_dir(self, work_dir: str):
        """设置工作目录"""
        self.work_dir = work_dir
        # 更新所有保存器的工作目录
        self.savers = {
            format_type: self.saver_factory.create_saver(format_type, self.work_dir)
            for format_type in self.supported_formats
        }
            
    async def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划"""
        try:
            # 创建执行结果目录
            execution_dir = self.work_dir / "search_results" 
            execution_dir.mkdir(parents=True, exist_ok=True)
            
            # 保存输入的计划
            with open(execution_dir / "input_plan.json", "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            
            # 初始化结果结构
            results = self._initialize_results(plan)
            
            # 执行基础搜索
            search_results = await self._execute_basic_search(plan, results, execution_dir)
            if search_results:
                results = search_results
            
            # 分析结果
            if results['stats']['total'] > 0:
                self.analyzer.analyze(results)
                
                # 保存分析结果
                analysis_dir = execution_dir / "analysis"
                analysis_dir.mkdir(exist_ok=True)
                
                # 保存关键概念
                if results['insights']['key_concepts']:
                    with open(analysis_dir / "key_concepts.json", "w", encoding="utf-8") as f:
                        json.dump(results['insights']['key_concepts'], f, ensure_ascii=False, indent=2)
                
                # 保存关系分析
                if results['insights']['relationships']:
                    with open(analysis_dir / "relationships.json", "w", encoding="utf-8") as f:
                        json.dump(results['insights']['relationships'], f, ensure_ascii=False, indent=2)
                
                # 保存时间线
                if results['insights']['timeline']:
                    with open(analysis_dir / "timeline.json", "w", encoding="utf-8") as f:
                        json.dump(results['insights']['timeline'], f, ensure_ascii=False, indent=2)
                
                # 保存重要性排名
                if results['insights']['importance_ranking']:
                    with open(analysis_dir / "importance_ranking.json", "w", encoding="utf-8") as f:
                        json.dump(results['insights']['importance_ranking'], f, ensure_ascii=False, indent=2)
            
            # 保存最终结果
            with open(execution_dir / "final_results.json", "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
            
            # 保存执行统计信息
            stats = {
                "execution_time": datetime.now().isoformat(),
                "query": plan.get("metadata", {}).get("original_query", ""),
                "total_results": results["stats"]["total"],
                "structured_results": results["stats"]["structured_count"],
                "vector_results": results["stats"]["vector_count"]
            }
            with open(execution_dir / "execution_stats.json", "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
            
            return results
            
        except Exception as e:
            self.logger.error(f"执行检索计划失败: {str(e)}", exc_info=True)
            raise

    def format_results(self, results: Dict, format: str = 'json') -> str:
        """格式化结果"""
        formatter = self.formatters.get(format)
        if not formatter:
            raise ValueError(f"不支持的格式: {format}")
        return formatter.format(results)

    def save_results(self, results: Dict, format: str, output_dir: str = None) -> str:
        """保存结果"""
        saver = self.savers.get(format)
        if not saver:
            raise ValueError(f"不支持的格式: {format}")
        
        if output_dir:
            saver.work_dir = output_dir
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"search_results_{timestamp}"
        
        return saver.save(results, filename)

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
            "insights": {
                "key_concepts": [],
                "relationships": [],
                "timeline": [],
                "importance_ranking": []
            },
            "context": {
                "historical": [],
                "related": [],
                "dependencies": []
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
                            
                            # 使用DateTimeEncoder保存结果
                            with open(structured_dir / f"query_{i+1}_results.json", "w", encoding="utf-8") as f:
                                json.dump(filtered_records, f, ensure_ascii=False, indent=2, cls=DateTimeEncoder)
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
                            # 过滤相似度阈值并排重
                            filtered_results = []
                            threshold = vector_query["similarity_threshold"]
                            for result in vector_results:
                                if result["similarity"] >= threshold:
                                    # 将 float32 转换为 Python float
                                    if isinstance(result["similarity"], np.float32):
                                        result["similarity"] = float(result["similarity"])
                                    
                                    fingerprint = self._generate_content_fingerprint(result.get('data', ''))
                                    if fingerprint not in seen_fingerprints:
                                        seen_fingerprints.add(fingerprint)
                                        filtered_results.append(result)
                                        results["vector"].append(result)
                            
                            # 保存每个查询的结果
                            with open(vector_dir / f"query_{i+1}_results.json", "w", encoding="utf-8") as f:
                                json.dump(filtered_results, f, ensure_ascii=False, indent=2)
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
