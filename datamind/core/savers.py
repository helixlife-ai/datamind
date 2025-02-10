import os
import json
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional
import logging
from pathlib import Path
import numpy as np
from html import escape
from abc import ABC, abstractmethod
from .formatters import BaseFormatter, SearchResultFormatter

class ResultSaver(ABC):
    """结果保存器基类"""
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        self.work_dir = work_dir
        self.logger = logging.getLogger(__name__)
        self.formatter = formatter or SearchResultFormatter()

    @abstractmethod
    def save(self, results: Dict, filename: str) -> str:
        """保存结果的抽象方法"""
        pass
        
    def _ensure_dir(self):
        """确保输出目录存在"""
        os.makedirs(self.work_dir, exist_ok=True)
        
    def _get_filepath(self, filename: str, extension: str) -> str:
        """获取完整的文件路径"""
        self._ensure_dir()
        return os.path.join(self.work_dir, f"{filename}.{extension}")

class JSONSaver(ResultSaver):
    """JSON保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为JSON格式"""
        filepath = self._get_filepath(filename, "json")
        
        # 添加元数据
        output = {
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
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2, default=self._json_serializer)
            self.logger.info(f"JSON文件已保存: {filepath}")
            return filepath
        except Exception as e:
            self.logger.error(f"保存JSON文件失败: {str(e)}")
            return None

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

class CSVSaver(ResultSaver):
    """CSV保存器"""
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        super().__init__(formatter, work_dir)
        self.meta_columns = ['search_type', 'similarity', 'file_path', 
                           'file_name', 'file_type', 'processed_at']
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为CSV格式"""
        filepath = self._get_filepath(filename, "csv")
        
        try:
            # 使用 SearchResultFormatter 来格式化结果
            search_formatter = SearchResultFormatter()
            formatted_results = search_formatter.format_results(results)
            
            if not formatted_results:
                self.logger.warning("没有搜索结果可保存")
                return None
                
            df = self._create_dataframe(formatted_results)
            df.to_csv(filepath, index=False, encoding='utf-8-sig')
            self.logger.info(f"CSV文件已保存: {filepath}")
            return filepath
                
        except Exception as e:
            self.logger.error(f"保存CSV文件失败: {str(e)}")
            return None
            
    def _create_dataframe(self, formatted_results: List[Dict]) -> pd.DataFrame:
        """创建DataFrame并排序列"""
        df = pd.DataFrame(formatted_results)
        other_columns = sorted([col for col in df.columns if col not in self.meta_columns])
        return df.reindex(columns=self.meta_columns + other_columns)

class ExcelSaver(ResultSaver):
    """Excel保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为Excel格式"""
        filepath = self._get_filepath(filename, "xlsx")
        
        try:
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # 概述sheet
                summary_data = {
                    "指标": ["总结果数", "结构化结果数", "向量结果数"],
                    "数值": [
                        results["stats"]["total"],
                        results["stats"]["structured_count"],
                        results["stats"]["vector_count"]
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name="概述", index=False)
                
                # 处理搜索结果
                def process_results(items, sheet_name):
                    if not items:
                        return
                    
                    rows = []
                    for item in items:
                        row = {
                            'file_name': item.get('_file_name', ''),
                            'file_path': item.get('_file_path', ''),
                            'file_type': item.get('_file_type', ''),
                            'processed_at': item.get('_processed_at', ''),
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
                    
                    if rows:
                        df = pd.DataFrame(rows)
                        # 对列进行排序：元数据列在前，其他列按字母顺序排序
                        meta_columns = ['file_name', 'file_path', 'file_type', 'processed_at', 'similarity']
                        other_columns = sorted([col for col in df.columns if col not in meta_columns])
                        df = df.reindex(columns=meta_columns + other_columns)
                        df.to_excel(writer, sheet_name=sheet_name, index=False)
                
                # 保存结构化结果
                process_results(results.get("structured", []), "结构化搜索结果")
                
                # 保存向量结果
                process_results(results.get("vector", []), "向量搜索结果")
                
                # 保存洞察结果
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
                
                if insights_data:
                    pd.DataFrame(insights_data).to_excel(writer, sheet_name="分析洞察", index=False)
            
            self.logger.info(f"Excel文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存Excel文件失败: {str(e)}")
            return None

class HTMLSaver(ResultSaver):
    """HTML保存器"""
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为HTML格式"""
        filepath = self._get_filepath(filename, "html")
        
        try:
            # 获取统计数据和元数据
            stats = results.get("stats", {})
            metadata = results.get("metadata", {})
            structured_count = stats.get("structured_count", 0)
            vector_count = stats.get("vector_count", 0)
            original_query = metadata.get("original_query", "")
            
            # 生成HTML内容
            html_content = self._generate_html_content(
                results=results,
                stats=stats,
                metadata=metadata,
                structured_count=structured_count,
                vector_count=vector_count,
                original_query=escape(original_query)
            )
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存HTML文件失败: {str(e)}")
            return None
            
    def _generate_html_content(self, **kwargs) -> str:
        """生成HTML内容"""
        from .templates.base_template import SearchResultTemplate
        
        template = SearchResultTemplate()
        context = {
            'title': '搜索结果报告',
            'metadata': kwargs['metadata'],
            'stats': kwargs['stats'],
            'structured_results': kwargs['results'].get('structured', []),
            'vector_results': kwargs['results'].get('vector', []),
            'insights': kwargs['results'].get('insights', {}),
            'original_query': kwargs['original_query']
        }
        
        return template.render(context)

class SaverFactory:
    """保存器工厂类"""
    def __init__(self):
        self._formatters = {}
        self._savers = {
            'csv': CSVSaver,
            'json': JSONSaver,
            'excel': ExcelSaver,
            'html': HTMLSaver
        }
    
    def register_formatter(self, format_type: str, formatter: BaseFormatter):
        """注册格式化器"""
        self._formatters[format_type] = formatter
    
    def create_saver(self, format_type: str, work_dir: str = "output") -> ResultSaver:
        """创建保存器实例"""
        saver_class = self._savers.get(format_type.lower())
        if not saver_class:
            raise ValueError(f"不支持的格式类型: {format_type}")
            
        formatter = self._formatters.get(format_type.lower())
        return saver_class(formatter=formatter, work_dir=work_dir)

# 其他保存器类... 