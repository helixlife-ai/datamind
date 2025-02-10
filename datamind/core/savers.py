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
from .formatters import BaseFormatter, SearchResultFormatter, ExcelFormatter, JSONFormatter, HTMLFormatter, MarkdownFormatter

class ResultSaver(ABC):
    """结果保存器基类"""
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        self.work_dir = work_dir
        self.logger = logging.getLogger(__name__)
        self.formatter = formatter

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
        
        try:
            formatted_data = self.formatter.format(results)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(formatted_data, f, ensure_ascii=False, indent=2, default=self._json_serializer)
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
        super().__init__(formatter or SearchResultFormatter(), work_dir)
        self.meta_columns = ['search_type', 'similarity', 'file_path', 
                           'file_name', 'file_type', 'processed_at']
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为CSV格式"""
        filepath = self._get_filepath(filename, "csv")
        
        try:
            formatted_results = self.formatter.format(results)
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
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        super().__init__(formatter or ExcelFormatter(), work_dir)
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为Excel格式"""
        filepath = self._get_filepath(filename, "xlsx")
        
        try:
            formatted_data = self.formatter.format(results)
            
            with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
                # 保存概述sheet
                pd.DataFrame(formatted_data['summary']).to_excel(
                    writer, 
                    sheet_name="概述", 
                    index=False
                )
                
                # 保存结构化结果
                if formatted_data['structured_results']:
                    pd.DataFrame(formatted_data['structured_results']).to_excel(
                        writer, 
                        sheet_name="结构化搜索结果",
                        index=False
                    )
                
                # 保存向量结果
                if formatted_data['vector_results']:
                    pd.DataFrame(formatted_data['vector_results']).to_excel(
                        writer, 
                        sheet_name="向量搜索结果",
                        index=False
                    )
                
                # 保存洞察结果
                if formatted_data['insights']:
                    pd.DataFrame(formatted_data['insights']).to_excel(
                        writer, 
                        sheet_name="分析洞察",
                        index=False
                    )
            
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
            html_content = self.formatter.format(results)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)
                
            self.logger.info(f"HTML文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存HTML文件失败: {str(e)}")
            return None

class MarkdownSaver(ResultSaver):
    """Markdown保存器"""
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        super().__init__(formatter or MarkdownFormatter(), work_dir)
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为Markdown格式"""
        filepath = self._get_filepath(filename, "md")
        
        try:
            markdown_content = self.formatter.format(results)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)
                
            self.logger.info(f"Markdown文件已保存: {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"保存Markdown文件失败: {str(e)}")
            return None

class SaverFactory:
    """保存器工厂类"""
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # 初始化默认格式化器
        self._formatters = {
            'csv': SearchResultFormatter(),
            'json': JSONFormatter(),
            'excel': ExcelFormatter(),
            'html': HTMLFormatter(),
            'md': MarkdownFormatter()
        }
        
        # 初始化保存器类
        self._savers = {
            'csv': CSVSaver,
            'json': JSONSaver,
            'excel': ExcelSaver,
            'html': HTMLSaver,
            'md': MarkdownSaver  # 添加 Markdown 保存器
        }
    
    def register_formatter(self, format_type: str, formatter: BaseFormatter):
        """注册格式化器
        
        Args:
            format_type: 格式类型
            formatter: 格式化器实例
        """
        self._formatters[format_type.lower()] = formatter
    
    def register_saver(self, format_type: str, saver_class: type):
        """注册保存器类
        
        Args:
            format_type: 格式类型
            saver_class: 保存器类
        """
        if not issubclass(saver_class, ResultSaver):
            raise ValueError(f"保存器类必须继承自 ResultSaver: {saver_class}")
        self._savers[format_type.lower()] = saver_class
    
    def create_saver(self, format_type: str, work_dir: str = "output") -> ResultSaver:
        """创建保存器实例
        
        Args:
            format_type: 格式类型
            work_dir: 工作目录
            
        Returns:
            ResultSaver: 保存器实例
            
        Raises:
            ValueError: 如果格式类型不支持
        """
        format_type = format_type.lower()
        
        # 获取保存器类
        saver_class = self._savers.get(format_type)
        if not saver_class:
            raise ValueError(f"不支持的格式类型: {format_type}")
        
        # 获取对应的格式化器
        formatter = self._formatters.get(format_type)
        if not formatter:
            self.logger.warning(f"未找到格式化器: {format_type}，将使用保存器默认格式化器")
        
        # 创建保存器实例
        return saver_class(formatter=formatter, work_dir=work_dir)

# 其他保存器类... 