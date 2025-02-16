import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional
from html import escape
import logging
import numpy as np
from datetime import date
from abc import ABC, abstractmethod

class BaseFormatter(ABC):
    """格式化器基类"""
    def __init__(self, work_dir: str = None, logger: Optional[logging.Logger] = None):
        """初始化格式化器
        
        Args:
            work_dir: 工作目录
            logger: 可选，日志记录器实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.work_dir = work_dir

    @abstractmethod
    def format(self, results: Dict) -> Any:
        """格式化结果的抽象方法"""
        pass

class SearchResultFormatter(BaseFormatter):
    """搜索结果格式化器 - 用于CSV等表格格式"""
    def format(self, results: Dict) -> List[Dict]:
        """格式化搜索结果为列表字典格式"""
        formatted_results = []
        
        # 处理结构化搜索结果
        for item in results.get('structured', []):
            formatted_results.append(self._format_item(item, '结构化搜索'))
            
        # 处理向量搜索结果    
        for item in results.get('vector', []):
            formatted_results.append(self._format_item(item, '向量搜索'))
            
        return formatted_results
    
    def _format_item(self, item: Dict, search_type: str) -> Dict:
        """格式化单个结果项"""
        formatted = {
            'search_type': search_type,
            'similarity': item.get('similarity', 'N/A'),
            'file_path': item.get('_file_path', '') or item.get('file_path', ''),
            'file_name': item.get('_file_name', '') or item.get('file_name', ''),
            'file_type': item.get('_file_type', '') or item.get('file_type', ''),
            'processed_at': item.get('_processed_at', '') or item.get('processed_at', '')
        }
        
        # 解析data字段
        if isinstance(item.get('data'), str):
            try:
                data_dict = json.loads(item['data'])
                formatted.update(data_dict)
            except json.JSONDecodeError:
                formatted['raw_content'] = item.get('data', '')
        elif isinstance(item.get('data'), dict):
            formatted.update(item['data'])
            
        return formatted

class HTMLFormatter(BaseFormatter):
    """HTML格式化器"""
    def format(self, results: Dict) -> Dict[str, Any]:
        """格式化为HTML模板所需的数据结构"""
        return {
            'title': '搜索结果报告',
            'metadata': results.get('metadata', {}),
            'stats': results.get('stats', {}),
            'structured_results': results.get('structured', []),
            'vector_results': results.get('vector', []),
            'insights': results.get('insights', {})
        }

class MarkdownFormatter(BaseFormatter):
    """Markdown格式化器"""
    def format(self, results: Dict) -> str:
        """生成Markdown格式的报告"""
        try:
            stats = results.get("stats", {})
            metadata = results.get("metadata", {})
            
            md_lines = []
            
            # 添加标题和元数据
            md_lines.extend([
                "# 搜索结果报告\n",
                "## 查询信息\n",
                f"- 原始查询: {metadata.get('original_query', '')}\n",
                f"- 生成时间: {metadata.get('generated_at', '')}\n",
                f"- 执行时间: {metadata.get('execution_time', '')}\n\n"
            ])
            
            # 添加统计信息
            md_lines.extend([
                "## 统计信息\n",
                f"- 总结果数: {stats.get('total', 0)}\n",
                f"- 结构化结果数: {stats.get('structured_count', 0)}\n",
                f"- 向量结果数: {stats.get('vector_count', 0)}\n\n"
            ])
            
            # 添加洞察结果
            insights = results.get("insights", {})
            if insights:
                md_lines.append("## 关键发现\n")
                for concept in insights.get("key_concepts", []):
                    md_lines.append(f"- {concept}\n")
                md_lines.append("\n")
                
                if insights.get("relationships"):
                    md_lines.append("### 关系发现\n")
                    for rel in insights["relationships"]:
                        md_lines.append(f"- {rel['type']}: {rel['doc1']} - {rel['doc2']}\n")
                    md_lines.append("\n")
            
            # 添加搜索结果
            def format_results(results_list: List[Dict], section_title: str):
                if not results_list:
                    return [f"## {section_title}\n无结果\n\n"]
                
                section_lines = [f"## {section_title}\n"]
                
                for result in results_list:
                    section_lines.extend([
                        f"### {result.get('file_name', '未知文件')}\n",
                        f"- 文件路径: {result.get('file_path', '')}\n",
                        f"- 文件类型: {result.get('file_type', '')}\n",
                        f"- 相似度: {result.get('similarity', 'N/A')}\n",
                        f"- 处理时间: {result.get('processed_at', '')}\n\n"
                    ])
                    
                    # 处理data字段
                    data = result.get('data', {})
                    if isinstance(data, str):
                        try:
                            data = json.loads(data)
                        except json.JSONDecodeError:
                            section_lines.append(f"```\n{data}\n```\n\n")
                            continue
                    
                    if isinstance(data, dict):
                        for key, value in data.items():
                            if key not in ['file_path', 'file_type', 'similarity', 'processed_at']:
                                section_lines.append(f"- {key}: {value}\n")
                    
                    section_lines.append("\n")
                
                return section_lines
            
            # 添加结构化搜索结果
            md_lines.extend(format_results(results.get("structured", []), "结构化查询结果"))
            
            # 添加向量搜索结果
            md_lines.extend(format_results(results.get("vector", []), "向量查询结果"))
            
            return "".join(md_lines)
            
        except Exception as e:
            self.logger.error(f"Markdown格式化失败: {str(e)}")
            return f"# 错误\n\n格式化失败: {str(e)}"

class JSONFormatter(BaseFormatter):
    """JSON格式化器"""
    def format(self, results: Dict) -> Dict:
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
                "vector": results.get("vector", []),
                "insights": results.get("insights", {})
            }
        }

class ExcelFormatter(BaseFormatter):
    """Excel格式化器"""
    def format(self, results: Dict) -> Dict[str, Any]:
        """格式化为Excel格式所需的数据结构"""
        # 概述数据
        summary_data = {
            "指标": ["总结果数", "结构化结果数", "向量结果数"],
            "数值": [
                results["stats"]["total"],
                results["stats"]["structured_count"],
                results["stats"]["vector_count"]
            ]
        }
        
        # 处理搜索结果
        def process_results(items: List[Dict]) -> List[Dict]:
            if not items:
                return []
            
            rows = []
            for item in items:
                row = {
                    'file_name': item.get('_file_name', '') or item.get('file_name', ''),
                    'file_path': item.get('_file_path', '') or item.get('file_path', ''),
                    'file_type': item.get('_file_type', '') or item.get('file_type', ''),
                    'processed_at': item.get('_processed_at', '') or item.get('processed_at', ''),
                    'similarity': item.get('similarity', 'N/A')
                }
                
                # 解析data字段
                if isinstance(item.get('data'), str):
                    try:
                        data_dict = json.loads(item['data'])
                        row.update(data_dict)
                    except json.JSONDecodeError:
                        row['raw_content'] = item.get('data', '')
                elif isinstance(item.get('data'), dict):
                    row.update(item['data'])
                
                rows.append(row)
            
            return rows
        
        # 处理洞察数据
        insights_data = []
        for concept in results.get("insights", {}).get("key_concepts", []):
            insights_data.append({
                "类型": "关键概念",
                "内容": concept
            })
        
        for relation in results.get("insights", {}).get("relationships", []):
            insights_data.append({
                "类型": "关系发现",
                "内容": f"{relation['type']}: {relation['doc1']} - {relation['doc2']}"
            })
        
        return {
            'summary': summary_data,
            'structured_results': process_results(results.get("structured", [])),
            'vector_results': process_results(results.get("vector", [])),
            'insights': insights_data
        }

# 其他格式化器类... 