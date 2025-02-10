import logging
import pandas as pd
from typing import Dict, List, Optional
import os
from datetime import datetime, date
from collections import defaultdict
import numpy as np
from itertools import combinations
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import hashlib
from .formatters import (
    HTMLFormatter, 
    MarkdownFormatter, 
    JSONFormatter, 
    ExcelFormatter,
    SearchResultFormatter
)
from .savers import (
    SaverFactory, 
    JSONSaver, 
    CSVSaver, 
    ExcelSaver, 
    HTMLSaver,
    MarkdownSaver  # 添加 MarkdownSaver
)
from .analyzers import ResultAnalyzer

class SearchPlanExecutor:
    """搜索计划执行器"""
    
    def __init__(self, search_engine):
        self.engine = search_engine
        self.logger = logging.getLogger(__name__)
        self.work_dir = "output"  # 默认输出目录
        self.nlp_processor = None  # 用于文本分析，后续初始化
        self.knowledge_graph = None  # 用于关系分析，后续初始化
        self.supported_formats = ['csv', 'json', 'excel', 'html', 'md']
        
        # 初始化分析器
        self.analyzer = ResultAnalyzer()
        
        # 初始化保存器工厂
        self.saver_factory = SaverFactory()
        
        # 初始化格式化器字典
        self.formatters = {
            'html': HTMLFormatter(),
            'md': MarkdownFormatter(),
            'json': JSONFormatter(),
            'excel': ExcelFormatter(),
            'csv': SearchResultFormatter()
        }
        
        # 使用工厂创建保存器
        self.savers = {
            format_type: self.saver_factory.create_saver(format_type, self.work_dir)
            for format_type in self.supported_formats
        }

    def set_work_dir(self, work_dir: str):
        """设置工作目录"""
        self.work_dir = work_dir
        # 重新创建所有保存器
        self.savers = {
            format_type: self.saver_factory.create_saver(format_type, self.work_dir)
            for format_type in self.supported_formats
        }
            
    def execute_plan(self, plan: Dict) -> Dict:
        """执行检索计划"""
        try:
            # 检查plan是否有效
            if not plan:
                self.logger.error("检索计划为空")
                raise ValueError("检索计划不能为空")
            
            self.logger.info(f"开始执行检索计划: {plan.get('metadata', {}).get('original_query', '')}")
            
            # 初始化结果结构
            results = self._initialize_results(plan)
            self.logger.debug("结果结构初始化完成")
            
            # 检查搜索引擎
            if not self.engine:
                self.logger.error("搜索引擎未初始化")
                raise ValueError("搜索引擎未初始化")
            
            # 执行基础搜索
            search_results = self._execute_basic_search(plan, results)
            if search_results:
                results = search_results
            
            self.logger.debug(f"基础搜索完成，结果统计: {results['stats']}")
            
            # 分析结果
            if results['stats']['total'] > 0:
                self.analyzer.analyze(results)
                self.logger.debug("结果分析完成")
            else:
                self.logger.warning("没有找到搜索结果，跳过分析步骤")
            
            # 记录日志
            self.logger.info(f"检索计划执行完成，共找到 {results['stats']['total']} 条结果")
            
            return results
            
        except Exception as e:
            self.logger.error(f"执行检索计划失败: {str(e)}", exc_info=True)
            # 返回一个基本的结果结构而不是None
            return {
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
                    "generated_at": datetime.now().isoformat(),
                    "execution_time": datetime.now().isoformat(),
                    "error": str(e)
                }
            }

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

    def _execute_basic_search(self, plan: Dict, results: Dict):
        """执行基础搜索"""
        try:
            # 用于存储已见过的内容指纹
            seen_fingerprints = set()
            
            # 执行结构化查询
            if plan.get("structured_queries"):
                self.logger.debug(f"开始执行结构化查询: {plan['structured_queries']}")
                for query in plan["structured_queries"]:
                    try:
                        self.logger.debug(f"执行查询: {query}")
                        df = self.engine.execute_structured_query(query)
                        
                        if df is not None and not df.empty:
                            self.logger.debug(f"查询返回 {len(df)} 条结果")
                            records = df.to_dict('records')
                            # 对结构化查询结果进行排重
                            for record in records:
                                fingerprint = self._generate_content_fingerprint(record.get('data', ''))
                                if fingerprint not in seen_fingerprints:
                                    seen_fingerprints.add(fingerprint)
                                    results["structured"].append(record)
                        else:
                            self.logger.debug("查询返回空结果")
                    except Exception as e:
                        self.logger.error(f"结构化查询执行失败: {str(e)}", exc_info=True)
                        continue
                    
            results["stats"]["structured_count"] = len(results["structured"])
            self.logger.info(f"结构化查询结果: {len(results['structured'])} 条")
                
            # 执行向量查询
            if plan.get("vector_queries"):
                self.logger.debug(f"开始执行向量查询: {plan['vector_queries']}")
                for vector_query in plan["vector_queries"]:
                    try:
                        self.logger.debug(f"执行向量查询: {vector_query}")
                        vector_results = self.engine.execute_vector_search(
                            vector_query["reference_text"],
                            vector_query["top_k"]
                        )
                        
                        if vector_results:
                            self.logger.debug(f"向量查询返回 {len(vector_results)} 条结果")
                            # 过滤相似度阈值并排重
                            threshold = vector_query["similarity_threshold"]
                            for result in vector_results:
                                if result["similarity"] >= threshold:
                                    fingerprint = self._generate_content_fingerprint(result.get('data', ''))
                                    if fingerprint not in seen_fingerprints:
                                        seen_fingerprints.add(fingerprint)
                                        results["vector"].append(result)
                        else:
                            self.logger.debug("向量查询返回空结果")
                    except Exception as e:
                        self.logger.error(f"向量查询执行失败: {str(e)}", exc_info=True)
                        continue
                    
            results["stats"]["vector_count"] = len(results["vector"])
            self.logger.info(f"向量查询结果: {len(results['vector'])} 条")
                
            # 计算总数
            results["stats"]["total"] = (
                results["stats"]["structured_count"] + 
                results["stats"]["vector_count"]
            )
            
            self.logger.debug(f"搜索完成，总结果数: {results['stats']['total']}")
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