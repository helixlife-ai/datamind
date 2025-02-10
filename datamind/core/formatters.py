import json
import pandas as pd
from datetime import datetime
from typing import Dict, List
from html import escape
import logging
import numpy as np
from datetime import date
from abc import ABC, abstractmethod

class BaseFormatter(ABC):
    """格式化器基类"""
    @abstractmethod
    def format_results(self, results: Dict) -> List[Dict]:
        """格式化搜索结果"""
        pass

class SearchResultFormatter(BaseFormatter):
    """搜索结果格式化器"""
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def format_results(self, results: Dict) -> List[Dict]:
        """格式化搜索结果"""
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

class ResultFormatter:
    """结果格式化器基类"""
    def __init__(self, work_dir: str = None):
        self.logger = logging.getLogger(__name__)
        self.work_dir = work_dir

    def format(self, results: Dict) -> str:
        """格式化结果的抽象方法"""
        raise NotImplementedError

class HTMLFormatter(ResultFormatter):
    """HTML格式化器"""
    def __init__(self, work_dir: str = None):
        super().__init__(work_dir)
    
    def format(self, results: Dict) -> str:
        """生成HTML格式的报告"""
        try:
            stats = results.get("stats", {})
            metadata = results.get("metadata", {})
            
            insights_section = self._generate_insights_section(results)
            results_section = self._generate_results_section(results)
            
            return self._generate_html_template(
                metadata=metadata,
                stats=stats,
                insights_section=insights_section,
                results_section=results_section
            )
        except Exception as e:
            self.logger.error(f"HTML格式化失败: {str(e)}")
            return self._generate_error_html(str(e), results)

    def _generate_insights_section(self, results: Dict) -> str:
        """生成洞察部分HTML"""
        # 实现从executor.py移动的_generate_html_insights逻辑
        pass

    def _generate_results_section(self, results: Dict) -> str:
        """生成结果部分HTML"""
        # 实现从executor.py移动的_generate_html_results逻辑
        pass

    def _generate_html_template(self, **kwargs) -> str:
        """生成HTML模板"""
        # 实现HTML模板生成逻辑
        pass

    def _generate_error_html(self, error_msg: str, results: Dict) -> str:
        """生成错误HTML报告"""
        # 实现错误报告生成逻辑
        pass

class MarkdownFormatter(ResultFormatter):
    """Markdown格式化器"""
    def __init__(self, work_dir: str = None):
        super().__init__(work_dir)
    
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

class JSONFormatter(ResultFormatter):
    """JSON格式化器"""
    
    def format(self, results: Dict) -> str:
        """生成JSON格式的报告
        
        Args:
            results: 搜索结果字典
            
        Returns:
            str: 格式化后的JSON字符串
        """
        try:
            # 准备输出结构
            output = {
                "summary": {
                    "total_results": results.get("stats", {}).get("total", 0),
                    "structured_count": results.get("stats", {}).get("structured_count", 0),
                    "vector_count": results.get("stats", {}).get("vector_count", 0)
                },
                "metadata": results.get("metadata", {}),
                "results": {
                    "structured": self._format_structured_results(results.get("structured", [])),
                    "vector": self._format_vector_results(results.get("vector", []))
                },
                "insights": self._format_insights(results.get("insights", {}))
            }
            
            # 转换为格式化的JSON字符串
            return json.dumps(output, ensure_ascii=False, indent=2, default=self._json_serializer)
            
        except Exception as e:
            self.logger.error(f"JSON格式化失败: {str(e)}")
            return json.dumps({
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, ensure_ascii=False)

    def _format_structured_results(self, items: List[Dict]) -> List[Dict]:
        """格式化结构化搜索结果"""
        formatted = []
        for item in items:
            result = {
                "file_info": {
                    "name": item.get("_file_name", ""),
                    "path": item.get("_file_path", ""),
                    "type": item.get("_file_type", ""),
                    "processed_at": item.get("_processed_at", "")
                }
            }
            
            # 处理data字段
            if isinstance(item.get("data"), str):
                try:
                    result["content"] = json.loads(item["data"])
                except json.JSONDecodeError:
                    result["content"] = item.get("data", "")
            else:
                result["content"] = item.get("data", {})
                
            formatted.append(result)
        return formatted

    def _format_vector_results(self, items: List[Dict]) -> List[Dict]:
        """格式化向量搜索结果"""
        formatted = []
        for item in items:
            result = {
                "similarity": item.get("similarity", 0),
                "file_info": {
                    "name": item.get("file_name", ""),
                    "path": item.get("file_path", ""),
                    "type": item.get("file_type", ""),
                    "processed_at": item.get("processed_at", "")
                }
            }
            
            # 处理data字段
            if isinstance(item.get("data"), str):
                try:
                    result["content"] = json.loads(item["data"])
                except json.JSONDecodeError:
                    result["content"] = item.get("data", "")
            else:
                result["content"] = item.get("data", {})
                
            formatted.append(result)
        return formatted

    def _format_insights(self, insights: Dict) -> Dict:
        """格式化洞察结果"""
        return {
            "key_concepts": insights.get("key_concepts", []),
            "relationships": insights.get("relationships", []),
            "timeline": [
                {
                    "date": event.get("date", ""),
                    "event": event.get("event", ""),
                    "source": event.get("source", "")
                }
                for event in insights.get("timeline", [])
            ],
            "importance_ranking": [
                {
                    "score": item.get("score", 0),
                    "content": self._summarize_content(item.get("item", {}))
                }
                for item in insights.get("importance_ranking", [])
            ]
        }

    def _json_serializer(self, obj):
        """自定义JSON序列化处理"""
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

    def _summarize_content(self, item: Dict) -> str:
        """生成内容摘要"""
        if isinstance(item.get("data"), str):
            content = item["data"]
        else:
            content = json.dumps(item.get("data", {}), ensure_ascii=False)
        return content[:200] + "..." if len(content) > 200 else content

# 其他格式化器类... 