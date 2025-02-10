import os
import json
import pandas as pd
from datetime import datetime, date
from typing import Dict, List, Optional, Any
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

class BaseTemplate:
    """基础HTML模板类"""
    def get_style(self) -> str:
        return """
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 20px;
            line-height: 1.6;
        }
        .query-info {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }
        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin: 1em 0;
        }
        .results-table th, .results-table td {
            padding: 8px;
            border: 1px solid #ddd;
            text-align: left;
        }
        .results-table th {
            background-color: #f5f5f5;
            font-weight: bold;
        }
        .results-table tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        .table-responsive {
            overflow-x: auto;
            margin: 1em 0;
        }
        .insight-section {
            background: #f5f5f5;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .chart-container {
            height: 300px;
            margin: 20px 0;
            padding: 20px;
            background: white;
            border: 1px solid #eee;
            border-radius: 4px;
        }
        """
    
    def get_scripts(self) -> str:
        return """
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            const ctx = document.getElementById('resultsChart');
            if (ctx) {
                new Chart(ctx, {
                    type: 'bar',
                    data: window.chartData,
                    options: {
                        responsive: true,
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
            }
        });
        </script>
        """

class SearchResultTemplate(BaseTemplate):
    """搜索结果HTML模板类"""
    def render(self, context: Dict[str, Any]) -> str:
        """渲染HTML模板"""
        chart_data = self._prepare_chart_data(context)
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{context.get('title', '搜索结果报告')}</title>
            <style>{self.get_style()}</style>
            <script>
            window.chartData = {json.dumps(chart_data)};
            </script>
            {self.get_scripts()}
        </head>
        <body>
            {self._render_header(context)}
            {self._render_stats(context)}
            {self._render_insights(context)}
            {self._render_results(context)}
        </body>
        </html>
        """
    
    def _prepare_chart_data(self, context: Dict[str, Any]) -> Dict:
        """准备图表数据"""
        return {
            'labels': ['结构化搜索', '向量搜索'],
            'datasets': [{
                'label': '结果数量',
                'data': [
                    context.get('stats', {}).get('structured_count', 0),
                    context.get('stats', {}).get('vector_count', 0)
                ],
                'backgroundColor': ['#36a2eb', '#ff6384']
            }]
        }
    
    def _render_header(self, context: Dict[str, Any]) -> str:
        """渲染页头部分"""
        metadata = context.get('metadata', {})
        return f"""
        <h1>{context.get('title', '搜索结果报告')}</h1>
        <div class="query-info">
            <p><strong>原始查询:</strong> {metadata.get('original_query', '')}</p>
            <p><strong>生成时间:</strong> {metadata.get('generated_at', '')}</p>
            <p><strong>执行时间:</strong> {metadata.get('execution_time', '')}</p>
        </div>
        """
    
    def _render_stats(self, context: Dict[str, Any]) -> str:
        """渲染统计信息部分"""
        stats = context.get('stats', {})
        return f"""
        <h2>统计信息</h2>
        <div class="stats-section">
            <p>总结果数: {stats.get('total', 0)}</p>
            <p>结构化结果数: {stats.get('structured_count', 0)}</p>
            <p>向量结果数: {stats.get('vector_count', 0)}</p>
            <div class="chart-container">
                <canvas id="resultsChart"></canvas>
            </div>
        </div>
        """
    
    def _render_insights(self, context: Dict[str, Any]) -> str:
        """渲染洞察部分"""
        insights = context.get('insights', {})
        if not insights:
            return ""
            
        html = "<h2>分析洞察</h2><div class='insight-section'>"
        
        if insights.get('key_concepts'):
            html += "<h3>关键概念</h3><ul>"
            for concept in insights['key_concepts']:
                html += f"<li>{escape(concept)}</li>"
            html += "</ul>"
            
        if insights.get('relationships'):
            html += "<h3>关系发现</h3><ul>"
            for rel in insights['relationships']:
                html += f"<li>{escape(rel['type'])}: {escape(rel['doc1'])} - {escape(rel['doc2'])}</li>"
            html += "</ul>"
            
        html += "</div>"
        return html
    
    def _render_results(self, context: Dict[str, Any]) -> str:
        """渲染搜索结果部分"""
        html = []
        
        # 渲染结构化结果
        if context.get('structured_results'):
            html.append("<h2>结构化搜索结果</h2>")
            html.append(self._render_result_table(context['structured_results']))
            
        # 渲染向量结果    
        if context.get('vector_results'):
            html.append("<h2>向量搜索结果</h2>")
            html.append(self._render_result_table(context['vector_results']))
            
        return "\n".join(html)
    
    def _render_result_table(self, results: List[Dict]) -> str:
        """渲染结果表格"""
        if not results:
            return "<p>无结果</p>"
            
        html = ["<div class='table-responsive'><table class='results-table'>"]
        
        # 表头
        headers = set()
        for result in results:
            headers.update(result.keys())
        headers = sorted(headers)
        
        html.append("<tr>")
        for header in headers:
            html.append(f"<th>{escape(header)}</th>")
        html.append("</tr>")
        
        # 表格内容
        for result in results:
            html.append("<tr>")
            for header in headers:
                value = result.get(header, '')
                html.append(f"<td>{escape(str(value))}</td>")
            html.append("</tr>")
            
        html.append("</table></div>")
        return "\n".join(html)

class HTMLSaver(ResultSaver):
    """HTML保存器"""
    def __init__(self, formatter: Optional[BaseFormatter] = None, work_dir: str = "output"):
        super().__init__(formatter or HTMLFormatter(), work_dir)
        self.template = SearchResultTemplate()
    
    def save(self, results: Dict, filename: str) -> str:
        """保存为HTML格式"""
        filepath = self._get_filepath(filename, "html")
        
        try:
            formatted_data = self.formatter.format(results)
            html_content = self.template.render(formatted_data)
            
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